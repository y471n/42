import argparse
import uuid
from pathlib import Path

import chromadb
import numpy as np
from chromadb.config import Settings
from langchain_ollama import OllamaEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader

VECTOR_DIR = Path(".data/workshop-vectors")
CURRENT_INDEX = Path(".data/workshop-current.txt")


def extract_chunks(path):
    reader = PdfReader(path)
    splitter = RecursiveCharacterTextSplitter(chunk_size=900, chunk_overlap=100)
    chunks = [
        (page_number, chunk)
        for page_number, page in enumerate(reader.pages, 1)
        for chunk in splitter.split_text(page.extract_text() or "")
    ]
    if not chunks:
        raise ValueError(f"No extractable text in {path}. Try a text-based PDF or OCR.")
    return chunks


def embed_chunks(chunks, embeddings):
    vectors = embeddings.embed_documents(["search_document: " + text for _, text in chunks])
    if len(vectors) != len(chunks) or any(
        not vector or not np.isfinite(vector).all() or not np.linalg.norm(vector)
        for vector in vectors
    ):
        raise ValueError("The embedding model returned invalid vectors.")
    return vectors


def save_chunks(path, chunks, vectors):
    client = chromadb.PersistentClient(
        path=str(VECTOR_DIR), settings=Settings(anonymized_telemetry=False)
    )
    name = f"workshop-{uuid.uuid4().hex}"
    collection = client.create_collection(
        name=name, configuration={"hnsw": {"space": "cosine"}}
    )
    for start in range(0, len(chunks), 32):
        batch = chunks[start:start + 32]
        collection.add(
            ids=[str(i) for i in range(start, start + len(batch))],
            embeddings=vectors[start:start + 32],
            documents=[text for _, text in batch],
            metadatas=[{"path": str(path), "page": page} for page, _ in batch],
        )
    temporary = CURRENT_INDEX.with_suffix(".tmp")
    temporary.write_text(name, encoding="utf-8")
    temporary.replace(CURRENT_INDEX)


def index_pdf(path, embeddings):
    path = Path(path).resolve()
    chunks = extract_chunks(path)
    vectors = embed_chunks(chunks, embeddings)
    save_chunks(path, chunks, vectors)
    print(f"Indexed {len(chunks)} chunks from {path}")


def load_collection():
    if not CURRENT_INDEX.is_file() or not VECTOR_DIR.is_dir():
        raise FileNotFoundError("Index a PDF first: uv run python -m museum.library index library/example.pdf")
    client = chromadb.PersistentClient(
        path=str(VECTOR_DIR), settings=Settings(anonymized_telemetry=False)
    )
    return client.get_collection(CURRENT_INDEX.read_text(encoding="utf-8").strip())


def search_index(query, embeddings, limit=3):
    collection = load_collection()
    query_vector = embeddings.embed_query("search_query: " + query)
    if not query_vector or not np.isfinite(query_vector).all() or not np.linalg.norm(query_vector):
        raise ValueError("The query embedding is invalid.")
    matches = collection.query(
        query_embeddings=[query_vector], n_results=min(limit, collection.count()),
        include=["documents", "metadatas", "distances"],
    )
    return [
        {"path": metadata["path"], "page": metadata["page"], "text": text,
         "score": 1 - distance}
        for text, metadata, distance in zip(
            matches["documents"][0], matches["metadatas"][0], matches["distances"][0], strict=True
        )
    ]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["index", "search"])
    parser.add_argument("value", help="PDF path for index, or question for search")
    args = parser.parse_args()
    embeddings = OllamaEmbeddings(model="nomic-embed-text")
    if args.action == "index":
        index_pdf(args.value, embeddings)
    else:
        for item in search_index(args.value, embeddings):
            print(f"\n{item['path']} page {item['page']} (score {item['score']:.3f})\n{item['text'][:400]}")
