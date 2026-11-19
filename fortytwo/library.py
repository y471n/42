"""Index local PDF passages for later full-text and semantic retrieval."""

import hashlib
import io
import math
import re
import sqlite3
import uuid
from contextlib import closing
from pathlib import Path
from urllib.parse import quote

import chromadb
import numpy as np
from chromadb.config import Settings
from chromadb.errors import NotFoundError
from langchain_core.embeddings import Embeddings
from langchain_ollama import OllamaEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader


ROOT = Path(__file__).resolve().parent.parent
INDEX_VERSION = "page-chunks-900-100-nomic-document-prefix-v1"

SCHEMA = """
CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY,
    path TEXT NOT NULL UNIQUE,
    sha256 TEXT NOT NULL,
    index_version TEXT NOT NULL,
    embedding_model TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page INTEGER NOT NULL,
    text TEXT NOT NULL,
    embedding TEXT NOT NULL
);
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    text, content='chunks', content_rowid='id'
);
CREATE TRIGGER IF NOT EXISTS chunks_insert AFTER INSERT ON chunks BEGIN
    INSERT INTO chunks_fts(rowid, text) VALUES (new.id, new.text);
END;
CREATE TRIGGER IF NOT EXISTS chunks_delete AFTER DELETE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, text) VALUES ('delete', old.id, old.text);
END;
"""


def index_library(directory: Path, database: Path, embeddings: Embeddings, model: str) -> None:
    directory = directory.resolve()
    if not directory.is_dir():
        raise FileNotFoundError(f"Library directory not found: {directory}")
    files = sorted(path for path in directory.rglob("*") if path.is_file() and path.suffix.lower() == ".pdf")
    if not files:
        raise ValueError(f"No PDFs found in {directory}; the existing index was not changed.")

    database.parent.mkdir(parents=True, exist_ok=True)
    splitter = RecursiveCharacterTextSplitter(chunk_size=900, chunk_overlap=100)
    with closing(sqlite3.connect(database)) as db:
        db.execute("PRAGMA foreign_keys = ON")
        db.executescript(SCHEMA)
        if "vector_collection" not in {row[1] for row in db.execute("PRAGMA table_info(documents)")}:
            db.execute("ALTER TABLE documents ADD COLUMN vector_collection TEXT")
        previous_root = db.execute("SELECT value FROM metadata WHERE key = 'library_root'").fetchone()
        if previous_root and previous_root[0] != str(directory):
            raise ValueError(f"Index belongs to another library: {previous_root[0]}")
        db.execute("INSERT OR IGNORE INTO metadata(key, value) VALUES ('library_root', ?)", (str(directory),))
        db.commit()
        client = chromadb.PersistentClient(
            path=str(database.with_name(database.stem + "-vectors")),
            settings=Settings(anonymized_telemetry=False),
        )

        for path in files:
            relative = path.relative_to(directory).as_posix()
            data = path.read_bytes()
            digest = hashlib.sha256(data).hexdigest()
            existing = db.execute(
                "SELECT id, sha256, index_version, embedding_model, vector_collection FROM documents WHERE path = ?",
                (relative,),
            ).fetchone()
            if existing and existing[1:4] == (digest, INDEX_VERSION, model) and existing[4]:
                try:
                    collection = client.get_collection(existing[4])
                except NotFoundError:
                    print(f"Chroma collection missing; rebuilding: {relative}")
                else:
                    chunk_count = db.execute(
                        "SELECT COUNT(*) FROM chunks WHERE document_id = ?", (existing[0],)
                    ).fetchone()[0]
                    if chunk_count and collection.count() == chunk_count:
                        print(f"Unchanged: {relative}")
                        continue
                    print(f"Chroma collection incomplete; rebuilding: {relative}")

            print(f"Indexing: {relative}", flush=True)
            reader = PdfReader(io.BytesIO(data))
            passages = []
            empty_pages = 0
            for number, page in enumerate(reader.pages, 1):
                text = page.extract_text().strip()
                if not text:
                    empty_pages += 1
                    continue
                passages.extend((number, chunk) for chunk in splitter.split_text(text))
            if not passages:
                raise ValueError(f"No extractable text in {relative}; OCR may be needed.")

            vectors = []
            for start in range(0, len(passages), 32):
                texts = ["search_document: " + text for _, text in passages[start:start + 32]]
                batch = embeddings.embed_documents(texts)
                if len(batch) != len(texts) or any(
                    not vector or not any(vector) or any(not math.isfinite(value) for value in vector)
                    for vector in batch
                ):
                    raise ValueError(f"Invalid embeddings returned for {relative}.")
                vectors.extend(batch)
            dimensions = {len(vector) for vector in vectors}
            if len(dimensions) != 1:
                raise ValueError(f"Inconsistent embedding dimensions for {relative}.")

            collection_name = f"document-{uuid.uuid4().hex}"
            collection = client.create_collection(
                name=collection_name, configuration={"hnsw": {"space": "cosine"}}
            )
            # ponytail: old snapshots remain on disk; add safe garbage collection if storage becomes an issue.
            with db:
                if existing:
                    db.execute("DELETE FROM documents WHERE id = ?", (existing[0],))
                cursor = db.execute(
                    """INSERT INTO documents(path, sha256, index_version, embedding_model, vector_collection)
                       VALUES (?, ?, ?, ?, ?)""",
                    (relative, digest, INDEX_VERSION, model, collection_name),
                )
                ids = []
                for page, text in passages:
                    # The legacy SQLite schema requires this column; vectors live in Chroma.
                    chunk = db.execute(
                        "INSERT INTO chunks(document_id, page, text, embedding) VALUES (?, ?, ?, '[]')",
                        (cursor.lastrowid, page, text),
                    )
                    ids.append(str(chunk.lastrowid))
                for start in range(0, len(ids), 32):
                    collection.add(ids=ids[start:start + 32], embeddings=vectors[start:start + 32])
            print(f"  {len(passages)} chunks from {len(reader.pages)} pages; {empty_pages} pages without text.")

        paths = {path.relative_to(directory).as_posix() for path in files}
        with db:
            for document_id, path in db.execute("SELECT id, path FROM documents").fetchall():
                if path not in paths:
                    db.execute("DELETE FROM documents WHERE id = ?", (document_id,))
                    print(f"Removed from index: {path}")


def search_library(database: Path, query: str, embeddings: Embeddings, limit: int = 12) -> list[dict]:
    if not database.is_file():
        return []
    with closing(sqlite3.connect(f"{database.resolve().as_uri()}?mode=ro", uri=True)) as db:
        if "vector_collection" not in {row[1] for row in db.execute("PRAGMA table_info(documents)")}:
            raise ValueError("This index predates Chroma; reindex your library.")
        root_row = db.execute("SELECT value FROM metadata WHERE key = 'library_root'").fetchone()
        if not root_row:
            raise ValueError("Local index has no library root; reindex your library.")
        root = Path(root_row[0]).resolve()
        documents = db.execute(
            """SELECT d.path, d.sha256, d.vector_collection,
                      (SELECT COUNT(*) FROM chunks c WHERE c.document_id = d.id)
               FROM documents d"""
        ).fetchall()
        for path, digest, collection_name, _ in documents:
            pdf = (root / path).resolve()
            if not pdf.is_relative_to(root) or not pdf.is_file() or hashlib.sha256(pdf.read_bytes()).hexdigest() != digest:
                raise ValueError(f"Indexed PDF is missing or changed; reindex your library: {path}")
            if not collection_name:
                raise ValueError(f"Document has no Chroma index; reindex your library: {path}")
        rows = db.execute(
            """SELECT c.id, d.path, c.page, c.text,
                      (SELECT first.text FROM chunks first
                       WHERE first.document_id = d.id ORDER BY first.page, first.id LIMIT 1)
               FROM chunks c JOIN documents d ON d.id = c.document_id"""
        ).fetchall()
        if not rows:
            return []
        terms = list(dict.fromkeys(re.findall(r"[^\W_]{3,}", query.casefold())))[:16]
        lexical = []
        if terms:
            match = " OR ".join(f'"{term}"' for term in terms)
            lexical = [row[0] for row in db.execute(
                "SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH ? ORDER BY rank LIMIT 100",
                (match,),
            )]

    query_vector = np.asarray(embeddings.embed_query("search_query: " + query), dtype=np.float32)
    if query_vector.ndim != 1 or not query_vector.size or not np.isfinite(query_vector).all():
        raise ValueError("Invalid query embedding.")
    query_norm = np.linalg.norm(query_vector)
    if not query_norm:
        raise ValueError("Query embedding has zero magnitude.")
    vector_path = database.with_name(database.stem + "-vectors")
    if not vector_path.is_dir():
        raise ValueError("Chroma index is missing; reindex your library.")
    client = chromadb.PersistentClient(
        path=str(vector_path), settings=Settings(anonymized_telemetry=False)
    )
    similarities = []
    for path, _, collection_name, chunk_count in documents:
        try:
            collection = client.get_collection(collection_name)
        except NotFoundError as error:
            raise ValueError(f"Chroma collection missing; reindex your library: {path}") from error
        if not chunk_count or collection.count() != chunk_count:
            raise ValueError(f"Chroma collection incomplete; reindex your library: {path}")
        result = collection.query(
            query_embeddings=[query_vector.tolist()], n_results=min(100, chunk_count),
            include=["distances"],
        )
        similarities.extend((int(chunk_id), distance) for chunk_id, distance in
                            zip(result["ids"][0], result["distances"][0], strict=True))
    scores = {}
    semantic = [item[0] for item in sorted(similarities, key=lambda item: item[1])[:100]]
    for ranking in (lexical, semantic):
        for rank, chunk_id in enumerate(ranking, 1):
            scores[chunk_id] = scores.get(chunk_id, 0) + 1 / (60 + rank)
    by_id = {row[0]: row for row in rows}
    results = []
    counts = {}
    for chunk_id in sorted(scores, key=lambda item: -scores[item]):
        _, path, page, text, first_page = by_id[chunk_id]
        if counts.get(path, 0) >= 2:
            continue
        counts[path] = counts.get(path, 0) + 1
        results.append({"path": path, "page": page, "content": text, "first_page": first_page,
                        "url": f"/api/library/{quote(path, safe='/')}#page={page}"})
        if len(results) >= limit:
            break
    return results


if __name__ == "__main__":
    index_library(ROOT / "library", ROOT / ".data" / "library.sqlite",
                  OllamaEmbeddings(model="nomic-embed-text"), "nomic-embed-text")
