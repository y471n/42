import hashlib
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from langchain_core.embeddings import Embeddings
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject


def write_pdf(path, texts):
    writer = PdfWriter()
    font = writer._add_object(DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
    }))
    for text in texts:
        page = writer.add_blank_page(width=400, height=400)
        page[NameObject("/Resources")] = DictionaryObject({
            NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})
        })
        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 14 Tf 50 350 Td ({text}) Tj ET".encode("ascii"))
        page[NameObject("/Contents")] = writer._add_object(stream)
    with path.open("wb") as file:
        writer.write(file)


class LocalEmbeddings(Embeddings):
    def embed_documents(self, texts):
        return [[float(len(text)), 1.0] for text in texts]

    def embed_query(self, text):
        return [float(len(text)), 1.0]


class FailingEmbeddings(LocalEmbeddings):
    def embed_documents(self, texts):
        raise RuntimeError("Embedding service unavailable")


class DirectionalEmbeddings(Embeddings):
    def embed_documents(self, texts):
        return [[0.0, 1.0] if "second" in text else [1.0, 0.0] for text in texts]

    def embed_query(self, text):
        return [0.0, 1.0]


class LibraryTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name) / "library"
        self.directory.mkdir()
        self.pdf = self.directory / "work.pdf"
        self.database = Path(self.temp.name) / "library.sqlite"
        write_pdf(self.pdf, ["The Will to Believe by William James", "A second page about freedom"])

    def test_vectors_persist_in_chroma_and_support_semantic_search(self):
        import chromadb
        from chromadb.config import Settings
        from fortytwo.library import index_library, search_library

        index_library(self.directory, self.database, LocalEmbeddings(), "test-model")
        vector_path = self.database.with_name(self.database.stem + "-vectors")
        self.assertTrue(vector_path.is_dir())
        client = chromadb.PersistentClient(path=str(vector_path), settings=Settings(anonymized_telemetry=False))
        collections = client.list_collections()
        self.assertEqual(sum(collection.count() for collection in collections), 2)
        results = search_library(self.database, "belief", LocalEmbeddings())
        self.assertTrue(any("The Will to Believe" in item["content"] for item in results))

    def test_semantic_results_come_from_chroma_not_legacy_sqlite_vectors(self):
        from fortytwo.library import index_library, search_library

        index_library(self.directory, self.database, DirectionalEmbeddings(), "directional")
        with closing(sqlite3.connect(self.database)) as db:
            with db:
                db.execute("UPDATE chunks SET embedding = '[1, 0]'")
        results = search_library(self.database, "unrelated", DirectionalEmbeddings(), limit=1)
        self.assertEqual(results[0]["page"], 2)

    def test_failed_vector_write_preserves_previous_index(self):
        from chromadb.api.models.Collection import Collection
        from fortytwo.library import index_library, search_library

        index_library(self.directory, self.database, LocalEmbeddings(), "test-model")
        original_pdf = self.pdf.read_bytes()
        write_pdf(self.pdf, ["A replacement passage by Immanuel Kant"])
        with patch.object(Collection, "add", side_effect=RuntimeError("Chroma write failed")):
            with self.assertRaisesRegex(RuntimeError, "Chroma write failed"):
                index_library(self.directory, self.database, LocalEmbeddings(), "test-model")
        self.pdf.write_bytes(original_pdf)
        results = search_library(self.database, "belief", LocalEmbeddings())
        self.assertTrue(any("The Will to Believe" in item["content"] for item in results))

    def test_reindex_recovers_a_missing_chroma_collection(self):
        import chromadb
        from chromadb.config import Settings
        from fortytwo.library import index_library, search_library

        index_library(self.directory, self.database, LocalEmbeddings(), "test-model")
        vector_path = self.database.with_name(self.database.stem + "-vectors")
        client = chromadb.PersistentClient(path=str(vector_path), settings=Settings(anonymized_telemetry=False))
        for collection in client.list_collections():
            client.delete_collection(collection.name)
        with self.assertRaisesRegex(ValueError, "reindex"):
            search_library(self.database, "belief", LocalEmbeddings())
        index_library(self.directory, self.database, LocalEmbeddings(), "test-model")
        self.assertTrue(search_library(self.database, "belief", LocalEmbeddings()))

    def test_removed_pdf_no_longer_appears_in_search(self):
        from fortytwo.library import index_library, search_library

        write_pdf(self.directory / "another.pdf", ["Another source about choice"])
        index_library(self.directory, self.database, LocalEmbeddings(), "test-model")
        self.pdf.unlink()
        index_library(self.directory, self.database, LocalEmbeddings(), "test-model")
        results = search_library(self.database, "belief", LocalEmbeddings())
        self.assertTrue(results)
        self.assertTrue(all(result["path"] == "another.pdf" for result in results))

    def test_existing_sqlite_index_is_migrated_without_erasing_it_first(self):
        from fortytwo.library import INDEX_VERSION, SCHEMA, index_library, search_library

        with closing(sqlite3.connect(self.database)) as db, db:
            db.executescript(SCHEMA)
            db.execute("INSERT INTO metadata VALUES ('library_root', ?)", (str(self.directory.resolve()),))
            db.execute(
                "INSERT INTO documents(path, sha256, index_version, embedding_model) VALUES (?, ?, ?, ?)",
                ("work.pdf", hashlib.sha256(self.pdf.read_bytes()).hexdigest(), INDEX_VERSION, "test-model"),
            )
            db.execute(
                "INSERT INTO chunks(document_id, page, text, embedding) VALUES (1, 1, ?, '[1, 1]')",
                ("The Will to Believe by William James",),
            )
        with self.assertRaisesRegex(ValueError, "reindex"):
            search_library(self.database, "belief", LocalEmbeddings())
        with self.assertRaisesRegex(RuntimeError, "Embedding service unavailable"):
            index_library(self.directory, self.database, FailingEmbeddings(), "test-model")
        with closing(sqlite3.connect(self.database)) as db:
            self.assertEqual(db.execute("SELECT text FROM chunks").fetchone()[0],
                             "The Will to Believe by William James")
        index_library(self.directory, self.database, LocalEmbeddings(), "test-model")
        self.assertTrue(search_library(self.database, "belief", LocalEmbeddings()))

    def test_indexes_pages_for_full_text_and_semantic_search_without_duplicates(self):
        from fortytwo.library import index_library

        index_library(self.directory, self.database, LocalEmbeddings(), "test-model")
        with closing(sqlite3.connect(self.database)) as db:
            row = db.execute(
                """SELECT c.page, c.text FROM chunks c
                   JOIN chunks_fts f ON c.id = f.rowid
                   WHERE chunks_fts MATCH 'William AND James'
                   ORDER BY c.page LIMIT 1"""
            ).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row[0], 1)
            self.assertIn("The Will to Believe", row[1])
            original_count = db.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
            self.assertEqual(db.execute(
                "SELECT page FROM chunks WHERE text LIKE '%second page%'"
            ).fetchone()[0], 2)

        index_library(self.directory, self.database, FailingEmbeddings(), "test-model")
        with closing(sqlite3.connect(self.database)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM documents").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM chunks").fetchone()[0], original_count)

    def test_failed_reindex_preserves_existing_searchable_content(self):
        from fortytwo.library import index_library

        index_library(self.directory, self.database, LocalEmbeddings(), "test-model")
        write_pdf(self.pdf, ["Groundwork for the Metaphysic of Morals by Immanuel Kant"])
        with self.assertRaisesRegex(RuntimeError, "Embedding service unavailable"):
            index_library(self.directory, self.database, FailingEmbeddings(), "test-model")

        with closing(sqlite3.connect(self.database)) as db:
            self.assertGreater(db.execute(
                "SELECT COUNT(*) FROM chunks_fts WHERE chunks_fts MATCH '\"The Will to Believe\"'"
            ).fetchone()[0], 0)
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM chunks_fts WHERE chunks_fts MATCH '\"Groundwork for the Metaphysic of Morals\"'"
            ).fetchone()[0], 0)

        index_library(self.directory, self.database, LocalEmbeddings(), "test-model")
        with closing(sqlite3.connect(self.database)) as db:
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM chunks_fts WHERE chunks_fts MATCH '\"The Will to Believe\"'"
            ).fetchone()[0], 0)
            self.assertGreater(db.execute(
                "SELECT COUNT(*) FROM chunks_fts WHERE chunks_fts MATCH '\"Groundwork for the Metaphysic of Morals\"'"
            ).fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
