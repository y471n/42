import tempfile
import unittest
from pathlib import Path

from fortytwo.library import index_library
from test_library import LocalEmbeddings, write_pdf


class LocalResearchTest(unittest.TestCase):
    def test_explicit_thinker_missing_from_local_sources_triggers_targeted_search(self):
        from fortytwo.research import build_research_graph

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            library = root / "library"
            library.mkdir()
            write_pdf(library / "mill.pdf", ["Freedom by John Stuart Mill"])
            write_pdf(library / "kant.pdf", ["Freedom by Immanuel Kant"])
            database = root / "library.sqlite"
            index_library(library, database, LocalEmbeddings(), "test-model")
            queries = []

            def search(query):
                queries.append(query)
                return [{"url": "https://example.org/nietzsche", "title": "Friedrich Nietzsche"},
                        {"url": "https://example.net/kant", "title": "Immanuel Kant"}]

            graph = build_research_graph(
                search, lambda urls: [{"url": url, "content": "Friedrich Nietzsche and Immanuel Kant."}
                                      for url in urls], LocalEmbeddings(),
                lambda schema, instruction, data: schema(
                    relevant_source_ids=[source["id"] for source in data["passages"]], reason="Relevant."
                ), database
            )
            graph.invoke({"dilemma": "What does Friedrich Nietzsche think about freedom?",
                          "option_a": "", "option_b": "", "topic": "free_will", "research_round": 0,
                          "found": [], "thinkers": [], "warnings": []})
            self.assertTrue(any("Friedrich Nietzsche" in query for query in queries))

    def test_changed_pdf_is_not_served_as_if_it_matched_the_index(self):
        from fortytwo.library import search_library

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            library = root / "library"
            library.mkdir()
            pdf = library / "mill.pdf"
            write_pdf(pdf, ["Freedom by John Stuart Mill"])
            database = root / "library.sqlite"
            index_library(library, database, LocalEmbeddings(), "test-model")
            write_pdf(pdf, ["A different document by Immanuel Kant"])
            with self.assertRaisesRegex(ValueError, "reindex"):
                search_library(database, "freedom", LocalEmbeddings())

    def test_one_author_mentioning_other_thinkers_does_not_skip_web_search(self):
        from fortytwo.research import build_research_graph

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            library = root / "library"
            library.mkdir()
            write_pdf(library / "mill.pdf", ["Freedom by John Stuart Mill",
                                             "Kant and Aristotle discuss freedom and choice"])
            database = root / "library.sqlite"
            index_library(library, database, LocalEmbeddings(), "test-model")
            queries = []

            def search(query):
                queries.append(query)
                return [{"url": "https://example.org/kant", "title": "Immanuel Kant"},
                        {"url": "https://example.net/aristotle", "title": "Aristotle"}]

            graph = build_research_graph(
                search, lambda urls: [{"url": url, "content": "Immanuel Kant and Aristotle."} for url in urls],
                LocalEmbeddings(),
                lambda schema, instruction, data: schema(
                    relevant_source_ids=[source["id"] for source in data["passages"]], reason="Relevant."
                ), database
            )
            graph.invoke({"dilemma": "Freedom and choice", "option_a": "Stay", "option_b": "Leave",
                          "topic": "change", "research_round": 0, "found": [], "thinkers": [], "warnings": []})
            self.assertTrue(queries)

    def test_sufficient_local_passages_skip_web_search(self):
        from fortytwo.research import build_research_graph

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            library = root / "library"
            library.mkdir()
            write_pdf(library / "mill.pdf", ["Freedom and Choice by John Stuart Mill"])
            write_pdf(library / "kant.pdf", ["Freedom and Choice by Immanuel Kant"])
            database = root / "library.sqlite"
            index_library(library, database, LocalEmbeddings(), "test-model")

            def assess(schema, instruction, data):
                return schema(relevant_source_ids=[item["id"] for item in data["passages"]],
                              reason="Both passages address freedom.")

            def no_web(query):
                raise AssertionError("Web search should not run when local evidence is sufficient")

            graph = build_research_graph(no_web, lambda urls: [], LocalEmbeddings(), assess, database)
            result = graph.invoke({"dilemma": "How do I choose freedom?", "option_a": "Stay",
                                   "option_b": "Leave", "topic": "change", "research_round": 0,
                                   "found": [], "thinkers": [], "warnings": []})
            self.assertEqual(len(result["thinkers"]), 2)
            self.assertTrue(all(source["url"].endswith("#page=1") for source in result["evidence"]))
            self.assertTrue(all(source["id"].startswith("L") for source in result["evidence"]))

    def test_weak_local_evidence_is_kept_and_supplemented_without_private_queries(self):
        from fortytwo.research import build_research_graph

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            library = root / "library"
            library.mkdir()
            write_pdf(library / "mill.pdf", ["Freedom and Choice by John Stuart Mill"])
            database = root / "library.sqlite"
            index_library(library, database, LocalEmbeddings(), "test-model")
            queries = []

            def assess(schema, instruction, data):
                return schema(relevant_source_ids=[item["id"] for item in data["passages"]],
                              reason="Only one thinker is available locally.")

            def search(query):
                queries.append(query)
                return [{"url": "https://example.org/kant", "title": "Immanuel Kant"},
                        {"url": "https://example.net/aristotle", "title": "Aristotle"}]

            graph = build_research_graph(
                search, lambda urls: [{"url": url, "content": "Immanuel Kant and Aristotle on freedom."}
                                      for url in urls], LocalEmbeddings(), assess, database
            )
            result = graph.invoke({"dilemma": "PRIVATE_DETAILS and freedom", "option_a": "Stay",
                                   "option_b": "Leave", "topic": "change", "research_round": 0,
                                   "found": [], "thinkers": [], "warnings": []})
            self.assertTrue(any(source["id"].startswith("L") for source in result["evidence"]))
            self.assertTrue(any(source["id"].startswith("S") for source in result["evidence"]))
            self.assertTrue(queries)
            self.assertNotIn("PRIVATE_DETAILS", " ".join(queries))


if __name__ == "__main__":
    unittest.main()
