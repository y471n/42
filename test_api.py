import tempfile
import threading
import time
import unittest
import sqlite3
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient


class FakeGraph:
    def __init__(self, states, fail=False):
        self.states = states
        self.fail = fail

    def stream(self, data, config, stream_mode, subgraphs=False):
        if self.fail:
            raise RuntimeError("Model unavailable")
        session_id = config["configurable"]["thread_id"]
        if isinstance(data, dict):
            self.states[session_id] = {
                **data, "exhibit": "# Your exhibit", "approved": False,
                "discussion_turns": [], "evidence": [], "reflection": {},
            }
            yield ((), {"research": {}})
        else:
            self.states[session_id]["approved"] = data.resume["action"] == "approve"
            yield ((), {"review": {}})

    def get_state(self, config):
        return SimpleNamespace(values=self.states[config["configurable"]["thread_id"]])


def wait_for(client, session_id, wanted):
    for _ in range(100):
        data = client.get(f"/api/sessions/{session_id}").json()
        if data["status"] == wanted:
            return data
        time.sleep(0.01)
    raise AssertionError(f"Session did not reach {wanted}: {data}")


class ApiTest(unittest.TestCase):
    def test_threads_are_listed_and_follow_ups_persist_across_restart(self):
        from api import create_app
        from langgraph.checkpoint.sqlite import SqliteSaver
        from museum.graph import build_graph
        from test_graph import FakeEmbeddings, FakeModel

        class FollowUpModel(FakeModel):
            def with_structured_output(self, schema):
                if schema.__name__ == "LocalAssessment":
                    class Runner:
                        def invoke(self, messages):
                            data = json.loads(messages[-1].content)
                            return schema(relevant_source_ids=[source["id"] for source in data["passages"]],
                                          reason="The existing sources are relevant.")
                    return Runner()
                return super().with_structured_output(schema)

        def factory(connection):
            return build_graph(
                FollowUpModel(), FakeEmbeddings(), SqliteSaver(connection),
                lambda query: [{"url": "https://example.org/a", "title": "Aristotle"},
                               {"url": "https://example.net/b", "title": "Immanuel Kant"}],
                lambda urls: [{"url": url, "content": "Aristotle and Immanuel Kant discuss freedom."}
                              for url in urls],
            )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with TestClient(create_app(root, graph_factory=factory), base_url="http://localhost:8000") as client:
                session_id = client.post("/api/sessions", json={
                    "dilemma": "Where should I live?", "option_a": "Stay", "option_b": "Move"
                }).json()["id"]
                wait_for(client, session_id, "review")
                response = client.post(f"/api/sessions/{session_id}/follow-up", json={"question": "What about regret?"})
                self.assertEqual(response.status_code, 202)
                result = wait_for(client, session_id, "review")
                self.assertTrue(any(message.get("content") == "What about regret?" for message in result["messages"]))
                client.post(f"/api/sessions/{session_id}/review", json={"action": "approve"})
                wait_for(client, session_id, "approved")

            with TestClient(create_app(root, graph_factory=factory), base_url="http://localhost:8000") as client:
                threads = client.get("/api/sessions").json()
                self.assertTrue(any(thread["id"] == session_id and "Where should I live?" in thread["question"]
                                    for thread in threads))
                response = client.post(f"/api/sessions/{session_id}/follow-up", json={"question": "And courage?"})
                self.assertEqual(response.status_code, 202)
                result = wait_for(client, session_id, "approved")
                self.assertTrue(any(message.get("content") == "And courage?" for message in result["messages"]))

    def test_local_pdf_links_serve_only_library_files(self):
        from api import create_app
        from test_library import write_pdf

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            library = root / "library"
            library.mkdir()
            write_pdf(library / "work.pdf", ["Freedom by Immanuel Kant"])
            (root / "private.txt").write_text("private")
            with TestClient(create_app(root, library_dir=library), base_url="http://localhost:8000") as client:
                response = client.get("/api/library/work.pdf")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.headers["content-type"], "application/pdf")
                self.assertEqual(client.get("/api/library/%2e%2e/private.txt").status_code, 404)

    def test_single_question_clarification_survives_restart(self):
        from api import create_app
        from langgraph.checkpoint.sqlite import SqliteSaver
        from museum.graph import build_graph
        from test_graph import FakeEmbeddings, FakeModel

        class ClarifyingModel(FakeModel):
            def with_structured_output(self, schema):
                if schema.__name__ == "PathPlan":
                    class Runner:
                        def invoke(self, messages):
                            data = json.loads(messages[-1].content)
                            if data.get("clarification"):
                                return schema(kind="decision", option_a="Stay", option_b="Move", question="")
                            return schema(kind="clarification", option_a="", option_b="", question="Which paths?")
                    return Runner()
                return super().with_structured_output(schema)

        def factory(connection):
            return build_graph(ClarifyingModel(), FakeEmbeddings(), SqliteSaver(connection),
                               lambda query: [{"url": "https://example.org/a", "title": "Aristotle"}],
                               lambda urls: [{"url": urls[0], "content": "Aristotle on freedom."}])

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with TestClient(create_app(root, graph_factory=factory), base_url="http://localhost:8000") as client:
                response = client.post("/api/sessions", json={"dilemma": "What should I do?"})
                self.assertEqual(response.status_code, 202)
                session_id = response.json()["id"]
                result = wait_for(client, session_id, "clarification")
                self.assertEqual(result["clarification_question"], "Which paths?")
            with TestClient(create_app(root, graph_factory=factory), base_url="http://localhost:8000") as client:
                self.assertEqual(client.get(f"/api/sessions/{session_id}").json()["status"], "clarification")
                response = client.post(f"/api/sessions/{session_id}/clarify",
                                       json={"clarification": "Stay here or move"})
                self.assertEqual(response.status_code, 202)
                result = wait_for(client, session_id, "review")
                self.assertEqual(result["option_a"], "Stay")

    def test_create_review_resume_and_save(self):
        from api import create_app

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            states = {}
            app = create_app(root, graph_factory=lambda connection: FakeGraph(states))
            with TestClient(app, base_url="http://localhost:8000") as client:
                response = client.post("/api/sessions", json={"dilemma": "A choice", "option_a": "Stay", "option_b": "Go"})
                self.assertEqual(response.status_code, 202)
                session_id = response.json()["id"]
                result = wait_for(client, session_id, "review")
                self.assertEqual(result["exhibit"], "# Your exhibit")

            app = create_app(root, graph_factory=lambda connection: FakeGraph(states))
            with TestClient(app, base_url="http://localhost:8000") as client:
                self.assertEqual(client.get(f"/api/sessions/{session_id}").json()["status"], "review")
                response = client.post(f"/api/sessions/{session_id}/review", json={"action": "approve"})
                self.assertEqual(response.status_code, 202)
                wait_for(client, session_id, "approved")
                self.assertEqual((root / "exhibits" / f"exhibit-{session_id}.md").read_text(), "# Your exhibit")

    def test_api_uses_real_checkpointed_graph(self):
        from api import create_app
        from langgraph.checkpoint.sqlite import SqliteSaver
        from museum.graph import build_graph
        from test_graph import FakeEmbeddings, FakeModel

        def search(query):
            return [{"url": "https://example.org/a", "title": "Aristotle"}]

        def extract(urls):
            return [{"url": urls[0], "content": "Aristotle. Freedom is a task that calls for responsibility."}]

        def graph_factory(connection):
            return build_graph(FakeModel(), FakeEmbeddings(), SqliteSaver(connection), search, extract)

        with tempfile.TemporaryDirectory() as directory:
            app = create_app(Path(directory), graph_factory=graph_factory)
            with TestClient(app, base_url="http://localhost:8000") as client:
                session_id = client.post("/api/sessions", json={"dilemma": "A choice", "option_a": "Stay", "option_b": "Go"}).json()["id"]
                result = wait_for(client, session_id, "review")
                self.assertIn("A choice", result["exhibit"])
                self.assertEqual(result["sources"][0]["id"], "S1")
                client.post(f"/api/sessions/{session_id}/review", json={"action": "approve"})
                wait_for(client, session_id, "approved")

    def test_trace_shows_nested_work_and_survives_approval(self):
        from api import create_app
        from langgraph.checkpoint.sqlite import SqliteSaver
        from museum.graph import build_graph
        from test_graph import FakeEmbeddings, FakeModel

        class ContinueModel(FakeModel):
            def with_structured_output(self, schema):
                if schema.__name__ == "Moderator":
                    class Runner:
                        def invoke(self, messages):
                            return schema(ready=False, summary="Both choices involve responsibility.")
                    return Runner()
                return super().with_structured_output(schema)

        def search(query):
            return [{"url": "https://example.org/a", "title": "Aristotle"},
                    {"url": "https://example.net/b", "title": "Simone de Beauvoir"}]

        def extract(urls):
            return [{"url": url, "content": "Aristotle and Simone de Beauvoir. PRIVATE_SOURCE_BODY"} for url in urls]

        def graph_factory(connection):
            return build_graph(ContinueModel(), FakeEmbeddings(), SqliteSaver(connection), search, extract)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = create_app(root, graph_factory=graph_factory)
            with TestClient(app, base_url="http://localhost:8000") as client:
                session_id = client.post("/api/sessions", json={"dilemma": "A choice", "option_a": "Stay", "option_b": "Go"}).json()["id"]
                result = wait_for(client, session_id, "review")
                trace = result["trace"]
                self.assertTrue(any(event["node"] == "research_worker" and
                                    "philosophy meaningful work vocation freedom" in str(event["details"])
                                    for event in trace))
                self.assertTrue(any(event["node"] == "philosopher" and
                                    "Aristotle" in str(event["details"]) for event in trace))
                self.assertEqual(len([event for event in trace if event["node"] == "moderator"]), 2)
                self.assertTrue(any(event["node"] == "moderator" and
                                    "Four-turn limit reached" in str(event["details"]) for event in trace))
                self.assertTrue(any(event["node"] == "philosopher" and "Round 2" in event["title"] for event in trace))
                self.assertTrue(any(event["node"] == "retrieve" for event in trace))
                self.assertTrue(any(event["node"] == "critic" for event in trace))
                self.assertTrue(any(event["node"] == "revise" for event in trace))
                self.assertNotIn("PRIVATE_SOURCE_BODY", str(trace))
                client.post(f"/api/sessions/{session_id}/review", json={"action": "approve"})
                approved = wait_for(client, session_id, "approved")
                self.assertGreaterEqual(len(approved["trace"]), len(trace))
            app = create_app(root, graph_factory=graph_factory)
            with TestClient(app, base_url="http://localhost:8000") as client:
                self.assertEqual(client.get(f"/api/sessions/{session_id}").json()["trace"], approved["trace"])

    def test_trace_is_available_before_run_finishes(self):
        from api import create_app

        release = threading.Event()
        class PausedGraph(FakeGraph):
            def stream(self, data, config, stream_mode, subgraphs=False):
                self.states[config["configurable"]["thread_id"]] = {**data, "exhibit": "draft"}
                yield (("research:worker",), {"research_worker": {
                    "trace_queries": ["public query"], "found": []}})
                if not release.wait(5):
                    raise TimeoutError("Test did not release the graph.")

        with tempfile.TemporaryDirectory() as directory:
            app = create_app(Path(directory), graph_factory=lambda connection: PausedGraph({}))
            with TestClient(app, base_url="http://localhost:8000") as client:
                try:
                    session_id = client.post("/api/sessions", json={"dilemma": "A choice", "option_a": "Stay", "option_b": "Go"}).json()["id"]
                    for _ in range(100):
                        result = client.get(f"/api/sessions/{session_id}").json()
                        if result["trace"]:
                            break
                        time.sleep(0.01)
                    self.assertEqual(result["status"], "running")
                    self.assertEqual(result["trace"][0]["details"][0]["value"], "public query")
                finally:
                    release.set()

    def test_rejects_bad_input_and_untrusted_origin(self):
        from api import create_app

        with tempfile.TemporaryDirectory() as directory:
            app = create_app(Path(directory), graph_factory=lambda connection: FakeGraph({}))
            with TestClient(app, base_url="http://localhost:8000") as client:
                self.assertEqual(client.post("/api/sessions", json={"dilemma": "", "option_a": "A", "option_b": "B"}).status_code, 422)
                response = client.post("/api/sessions", headers={"Origin": "https://attacker.example"}, json={"dilemma": "A choice", "option_a": "A", "option_b": "B"})
                self.assertEqual(response.status_code, 403)

    def test_background_failure_is_visible(self):
        from api import create_app

        with tempfile.TemporaryDirectory() as directory:
            app = create_app(Path(directory), graph_factory=lambda connection: FakeGraph({}, fail=True))
            with TestClient(app, base_url="http://localhost:8000") as client:
                session_id = client.post("/api/sessions", json={"dilemma": "A choice", "option_a": "A", "option_b": "B"}).json()["id"]
                result = wait_for(client, session_id, "error")
                self.assertIn("Model unavailable", result["error"])

    def test_database_connections_are_closed_after_requests(self):
        from api import create_app

        connections = []
        real_connect = sqlite3.connect
        def track_connect(*args, **kwargs):
            connection = real_connect(*args, **kwargs)
            connections.append(connection)
            return connection

        with tempfile.TemporaryDirectory() as directory:
            with patch("api.sqlite3.connect", side_effect=track_connect):
                app = create_app(Path(directory), graph_factory=lambda connection: FakeGraph({}))
                with TestClient(app, base_url="http://localhost:8000") as client:
                    self.assertEqual(client.get("/api/sessions/" + "a" * 32).status_code, 404)
            self.assertTrue(connections)
            for connection in connections:
                with self.assertRaises(sqlite3.ProgrammingError):
                    connection.execute("SELECT 1")


if __name__ == "__main__":
    unittest.main()
