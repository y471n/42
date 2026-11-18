import json
import tempfile
import unittest
from pathlib import Path

from langchain_core.embeddings import Embeddings
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command


class FakeEmbeddings(Embeddings):
    def embed_documents(self, texts):
        return [[1.0, float(len(text) % 13 + 1)] for text in texts]

    def embed_query(self, text):
        return [1.0, float(len(text) % 13 + 1)]


class FakeModel:
    def with_structured_output(self, schema):
        class Runner:
            def invoke(self, messages):
                name = schema.__name__
                if name == "Topic":
                    return schema(topic="career")
                if name == "Letter":
                    return schema(text="A possible future, not a prediction.", citations=[{
                        "source_id": "S1",
                        "quote": "Freedom is a task that calls for responsibility.",
                    }])
                if name == "Critic":
                    return schema(needs_revision=False, issues=[])
                if name == "Reflection":
                    return schema(shared_values=["Freedom"], questions=["What matters most?"], experiment="Try a small project.")
                if name == "Perspective":
                    return schema(text="A philosophical perspective.", citations=[])
                if name == "Moderator":
                    return schema(ready=True, summary="Both approaches involve responsibility.")
                raise AssertionError(name)
        return Runner()


class MuseumTest(unittest.TestCase):
    def test_general_question_discusses_without_requiring_paths_or_futures(self):
        from unchosen_lives import build_graph

        class GeneralModel(FakeModel):
            def with_structured_output(self, schema):
                if schema.__name__ == "PathPlan":
                    class Runner:
                        def invoke(self, messages):
                            return schema(kind="general", option_a="", option_b="", question="")
                    return Runner()
                if schema.__name__ == "Letter":
                    raise AssertionError("A general question must not generate imagined futures")
                return super().with_structured_output(schema)

        graph = build_graph(
            GeneralModel(), FakeEmbeddings(), InMemorySaver(),
            lambda query: [{"url": "https://example.org/a", "title": "Aristotle"},
                           {"url": "https://example.net/b", "title": "Immanuel Kant"}],
            lambda urls: [{"url": url, "content": "Aristotle and Immanuel Kant discuss the good life."}
                          for url in urls],
        )
        result = graph.invoke({"dilemma": "What makes a life meaningful?"},
                              {"configurable": {"thread_id": "general"}})
        self.assertIn("__interrupt__", result)
        self.assertTrue(result["discussion_turns"])
        self.assertNotIn("future_a", result)
        self.assertNotIn("Future A:", result["exhibit"])
        self.assertIn("What makes a life meaningful?", result["exhibit"])

    def test_general_question_review_revises_the_discussion(self):
        from unchosen_lives import build_graph

        class GeneralModel(FakeModel):
            def with_structured_output(self, schema):
                if schema.__name__ == "PathPlan":
                    class Runner:
                        def invoke(self, messages):
                            return schema(kind="general", option_a="", option_b="", question="")
                    return Runner()
                if schema.__name__ == "Perspective":
                    class Runner:
                        def invoke(self, messages):
                            data = json.loads(messages[-1].content)
                            return schema(text=data["review_notes"] or "First discussion", citations=[])
                    return Runner()
                return super().with_structured_output(schema)

        graph = build_graph(
            GeneralModel(), FakeEmbeddings(), InMemorySaver(),
            lambda query: [{"url": "https://example.org/a", "title": "Aristotle"},
                           {"url": "https://example.net/b", "title": "Immanuel Kant"}],
            lambda urls: [{"url": url, "content": "Aristotle and Immanuel Kant discuss the good life."}
                          for url in urls],
        )
        config = {"configurable": {"thread_id": "general-revision"}}
        graph.invoke({"dilemma": "What makes a life meaningful?"}, config)
        revised = graph.invoke(Command(resume={"action": "revise", "notes": "Discuss friendship"}), config)
        self.assertIn("__interrupt__", revised)
        self.assertIn("Discuss friendship", revised["exhibit"])
        self.assertNotIn("future_a", revised)

    def test_general_question_critic_reports_concerns_for_human_review(self):
        from museum.trace import describe_event

        event = describe_event((), "critic", {
            "revision_round": 1, "automatic_revision": False,
            "critique": {"needs_revision": True, "issues": ["A concern"]},
        })
        self.assertIn({"label": "Decision", "value": "Concerns for human review"}, event["details"])

    def test_follow_up_continues_prior_roundtable_and_returns_to_review(self):
        from unchosen_lives import build_graph

        calls = []

        class FollowUpModel(FakeModel):
            def with_structured_output(self, schema):
                if schema.__name__ == "LocalAssessment":
                    class Runner:
                        def invoke(self, messages):
                            data = json.loads(messages[-1].content)
                            return schema(relevant_source_ids=[source["id"] for source in data["passages"]],
                                          reason="The sources address the follow-up.")
                    return Runner()
                if schema.__name__ == "Perspective":
                    class Runner:
                        def invoke(self, messages):
                            data = json.loads(messages[-1].content)
                            calls.append(data)
                            return schema(text=f"Perspective from {data['thinker']}", citations=[])
                    return Runner()
                return super().with_structured_output(schema)

        graph = build_graph(
            FollowUpModel(), FakeEmbeddings(), InMemorySaver(),
            lambda query: [{"url": "https://example.org/a", "title": "Aristotle"},
                           {"url": "https://example.net/b", "title": "Immanuel Kant"}],
            lambda urls: [{"url": url, "content": "Aristotle and Immanuel Kant discuss freedom."}
                          for url in urls],
        )
        config = {"configurable": {"thread_id": "continued"}}
        graph.invoke({"dilemma": "A decision", "option_a": "Stay", "option_b": "Move"}, config)
        initial_messages = graph.get_state(config).values["messages"]
        self.assertEqual([message.get("content") for message in initial_messages].count("A decision"), 1)
        first_count = len(calls)
        result = graph.invoke(Command(resume={"action": "discuss", "question": "What about regret?"}), config)
        self.assertIn("__interrupt__", result)
        self.assertLessEqual(len(calls) - first_count, 4)
        self.assertGreater(len(calls), first_count)
        self.assertIn("What about regret?", calls[first_count]["dilemma"])
        self.assertTrue(calls[first_count]["prior_turns"])
        messages = graph.get_state(config).values["messages"]
        self.assertTrue(any(message.get("content") == "What about regret?" for message in messages))
        self.assertTrue(messages[-1]["turns"])

    def test_primary_source_author_aliases_are_discoverable(self):
        from museum.research import discover_thinkers

        evidence = [{"id": "L1", "title": "Benedict Spinoza and David Hume", "url": "/local",
                     "content": "Michel de Montaigne and Sophie de Grouchy."}]
        self.assertTrue({"Baruch Spinoza", "David Hume", "Michel de Montaigne", "Sophie de Grouchy"}
                        <= set(discover_thinkers(evidence)))

    def test_follow_up_researches_a_new_explicit_thinker(self):
        from unchosen_lives import build_graph

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

        queries = []

        def search(query):
            queries.append(query)
            return [{"url": "https://example.org/a", "title": "Aristotle"},
                    {"url": "https://example.net/b", "title": "Immanuel Kant"}]

        graph = build_graph(FollowUpModel(), FakeEmbeddings(), InMemorySaver(), search,
                            lambda urls: [{"url": url, "content": "Aristotle and Immanuel Kant."}
                                          for url in urls])
        config = {"configurable": {"thread_id": "new-thinker"}}
        graph.invoke({"dilemma": "A decision", "option_a": "Stay", "option_b": "Move"}, config)
        queries.clear()
        graph.invoke(Command(resume={"action": "discuss", "question": "What would Nietzsche say?"}), config)
        self.assertTrue(any("Friedrich Nietzsche" in query for query in queries))

    def test_single_question_pauses_for_clarification_and_resumes(self):
        from unchosen_lives import build_graph

        class ClarifyingModel(FakeModel):
            def with_structured_output(self, schema):
                if schema.__name__ == "PathPlan":
                    class Runner:
                        def invoke(self, messages):
                            data = json.loads(messages[-1].content)
                            if data.get("clarification"):
                                return schema(kind="decision", option_a="Stay", option_b="Move", question="")
                            return schema(kind="clarification", option_a="", option_b="",
                                          question="What two choices are you considering?")
                    return Runner()
                return super().with_structured_output(schema)

        graph = build_graph(ClarifyingModel(), FakeEmbeddings(), InMemorySaver(),
                            lambda query: [{"url": "https://example.org/a", "title": "Aristotle"}],
                            lambda urls: [{"url": urls[0], "content": "Aristotle on freedom."}])
        config = {"configurable": {"thread_id": "clarify"}}
        result = graph.invoke({"dilemma": "What should I do?"}, config)
        self.assertEqual(result["__interrupt__"][0].value["kind"], "clarification")
        self.assertEqual(result["__interrupt__"][0].value["question"],
                         "What two choices are you considering?")
        result = graph.invoke(Command(resume={"clarification": "Stay here or move away"}), config)
        self.assertIn("__interrupt__", result)
        self.assertEqual(result["option_a"], "Stay")
        self.assertEqual(result["option_b"], "Move")
        self.assertIn("What should I do?", result["exhibit"])

    def test_discovers_philosophers_from_different_traditions(self):
        from museum.research import discover_thinkers

        evidence = [{"id": "S1", "title": "Perspectives", "url": "https://example.org",
                     "content": "Confucius, bell hooks, Mary Wollstonecraft, and Rabindranath Tagore wrote about life and society."}]
        thinkers = discover_thinkers(evidence)
        self.assertTrue({"Confucius", "bell hooks", "Mary Wollstonecraft", "Rabindranath Tagore"} <= set(thinkers))
        self.assertNotIn("Aristotle", thinkers)

    def test_discovers_common_spelling_variants_and_prioritizes_source_titles(self):
        from museum.research import discover_thinkers

        evidence = [{"id": "S1", "title": "Lao Tzu on change", "url": "https://example.org",
                     "content": "Soren Kierkegaard and Nagarjuna considered change."}]
        thinkers = discover_thinkers(evidence)
        self.assertEqual(thinkers[0], "Laozi")
        self.assertTrue({"Søren Kierkegaard", "Nāgārjuna"} <= set(thinkers))

    def test_quote_checks_reject_invented_and_unknown_sources(self):
        from unchosen_lives import validate_citations

        evidence = [{"id": "S1", "content": "Freedom is a task that calls for responsibility."}]
        self.assertEqual(validate_citations([{"source_id": "S1", "quote": "Freedom is a task that calls for responsibility."}], evidence), [])
        self.assertTrue(validate_citations([{"source_id": "S1", "quote": "Invented quotation"}], evidence))
        self.assertTrue(validate_citations([{"source_id": "S99", "quote": "Freedom is a task that calls for responsibility."}], evidence))

    def test_research_queries_do_not_include_personal_text(self):
        from unchosen_lives import search_queries

        for round_number in (0, 1):
            queries = search_queries("career", round_number, ["Simone de Beauvoir", "PRIVATE_SECRET_NAME"])
            self.assertTrue(queries)
            self.assertNotIn("PRIVATE_SECRET_NAME", " ".join(queries))
        self.assertEqual(len(search_queries("career", 1, ["Aristotle"])), 2)

    def test_public_research_can_target_free_will_and_named_catalogued_thinkers(self):
        from unchosen_lives import search_queries

        self.assertTrue(any("free will" in query for query in search_queries("free_will", 0, [])))
        queries = search_queries("general", 0, ["Immanuel Kant", "PRIVATE_PERSON"])
        self.assertTrue(any("Immanuel Kant" in query for query in queries))
        self.assertNotIn("PRIVATE_PERSON", " ".join(queries))

    def test_inline_quotation_must_have_a_verified_citation(self):
        from unchosen_lives import validate_letter

        evidence = [{"id": "S1", "content": "Freedom is a task that calls for responsibility."}]
        letter = {"text": 'A source says "Freedom is a task that calls for responsibility."', "citations": []}
        self.assertTrue(validate_letter(letter, evidence))
        letter["citations"] = [{"source_id": "S1", "quote": "Freedom is a task that calls for responsibility."}]
        self.assertEqual(validate_letter(letter, evidence), [])

    def test_research_retries_when_only_one_thinker_is_found(self):
        from unchosen_lives import build_graph

        def search(query):
            return [{"url": "https://example.org/a", "title": "Aristotle"},
                    {"url": "https://example.net/b", "title": "Aristotle"}]

        def extract(urls):
            return [{"url": url, "content": "Aristotle. Freedom is a task that calls for responsibility."}
                    for url in urls]

        graph = build_graph(FakeModel(), FakeEmbeddings(), InMemorySaver(), search, extract)
        config = {"configurable": {"thread_id": "one-thinker"}}
        graph.invoke({"dilemma": "A decision", "option_a": "Stay", "option_b": "Leave"}, config)
        self.assertEqual(graph.get_state(config).values["research_round"], 2)

    def test_graph_interrupt_resume_and_weak_evidence(self):
        from unchosen_lives import build_graph

        queries = []
        def search(query):
            queries.append(query)
            return [{"url": "https://example.org/beauvoir", "title": "Simone de Beauvoir"}]

        def extract(urls):
            return [{"url": urls[0], "content": "Simone de Beauvoir. Freedom is a task that calls for responsibility."}]

        graph = build_graph(FakeModel(), FakeEmbeddings(), InMemorySaver(), search, extract)
        config = {"configurable": {"thread_id": "test-case"}}
        paused = graph.invoke({"dilemma": "PRIVATE_SECRET_NAME is deciding", "option_a": "Stay", "option_b": "Leave"}, config)
        self.assertIn("__interrupt__", paused)
        snapshot = graph.get_state(config)
        self.assertEqual(snapshot.values["research_round"], 2)
        self.assertTrue(snapshot.values["warnings"])
        self.assertNotIn("PRIVATE_SECRET_NAME", " ".join(queries))
        result = graph.invoke(Command(resume={"action": "approve"}), config)
        self.assertTrue(result["approved"])
        self.assertIn("fiction", result["exhibit"].lower())
        self.assertIn("https://example.org/beauvoir", result["exhibit"])

    def test_letters_receive_retrieved_passages_not_all_source_text(self):
        from unchosen_lives import build_graph

        class CheckedModel(FakeModel):
            def with_structured_output(self, schema):
                runner = super().with_structured_output(schema)
                if schema.__name__ != "Letter":
                    return runner
                class Runner:
                    def invoke(self, messages):
                        data = json.loads(messages[-1].content)
                        if "evidence" in data or not data.get("passages"):
                            raise AssertionError("Letter should receive retrieved passages, not full sources")
                        return runner.invoke(messages)
                return Runner()

        graph = build_graph(CheckedModel(), FakeEmbeddings(), InMemorySaver(),
                            lambda query: [{"url": "https://example.org/a", "title": "Simone de Beauvoir"}],
                            lambda urls: [{"url": urls[0], "content": "Simone de Beauvoir. Freedom is a task that calls for responsibility."}])
        result = graph.invoke({"dilemma": "A decision", "option_a": "Stay", "option_b": "Leave"},
                              {"configurable": {"thread_id": "retrieval"}})
        self.assertIn("__interrupt__", result)

    def test_revision_loop_is_bounded_and_invalid_quotes_are_not_published(self):
        from unchosen_lives import build_graph

        class FaultyModel(FakeModel):
            def with_structured_output(self, schema):
                if schema.__name__ == "Letter":
                    class Runner:
                        def invoke(self, messages):
                            return schema(text="A possible future.", citations=[{"source_id": "S1", "quote": "A fabricated philosophical quotation."}])
                    return Runner()
                return super().with_structured_output(schema)

        graph = build_graph(FaultyModel(), FakeEmbeddings(), InMemorySaver(),
                            lambda query: [{"url": "https://example.org/a", "title": "Simone de Beauvoir"}],
                            lambda urls: [{"url": urls[0], "content": "Simone de Beauvoir. Freedom is a task that calls for responsibility."}])
        config = {"configurable": {"thread_id": "revision"}}
        result = graph.invoke({"dilemma": "A decision", "option_a": "Stay", "option_b": "Leave"}, config)
        self.assertEqual(graph.get_state(config).values["revision_round"], 2)
        self.assertNotIn("A fabricated philosophical quotation.", result["exhibit"])
        self.assertIn("Unverified quotation", result["exhibit"])

    def test_roundtable_stops_early_or_after_four_turns(self):
        from unchosen_lives import build_graph

        class DiscussionModel(FakeModel):
            def __init__(self, ready):
                self.ready = ready

            def with_structured_output(self, schema):
                if schema.__name__ == "Moderator":
                    ready = self.ready
                    class Runner:
                        def invoke(self, messages):
                            return schema(ready=ready, summary="A trade-off, not a resolution.")
                    return Runner()
                return super().with_structured_output(schema)

        def search(query):
            return [{"url": "https://example.org/a", "title": "Simone de Beauvoir"},
                    {"url": "https://example.net/b", "title": "Aristotle"}]

        def extract(urls):
            return [{"url": url, "content": "Simone de Beauvoir and Aristotle discuss freedom and responsibility."}
                    for url in urls]

        for ready, expected_rounds in [(True, 1), (False, 2)]:
            with self.subTest(ready=ready):
                graph = build_graph(DiscussionModel(ready), FakeEmbeddings(), InMemorySaver(), search, extract)
                config = {"configurable": {"thread_id": f"discussion-{ready}"}}
                result = graph.invoke({"dilemma": "A decision", "option_a": "Stay", "option_b": "Leave"}, config)
                values = graph.get_state(config).values
                self.assertEqual(values["discussion_round"], expected_rounds)
                self.assertEqual(len(values["discussion_turns"]), 2 * expected_rounds)
                self.assertIn("Philosophers' roundtable", result["exhibit"])
                self.assertIn("AI-generated interpretations", result["exhibit"])

    def test_roundtable_each_speaker_sees_every_earlier_turn(self):
        from museum.roundtable import build_roundtable_graph

        calls = []

        def ask(schema, instruction, data):
            if schema.__name__ == "Perspective":
                calls.append((data["thinker"], [turn["text"] for turn in data["prior_turns"]]))
                return schema(text=f"View from {data['thinker']}", citations=[])
            return schema(ready=len(data["turns"]) >= 4, summary="A tension remains.")

        evidence = [{"id": "S1", "title": "Aristotle and Simone de Beauvoir",
                     "url": "https://example.org", "content": "Aristotle and Simone de Beauvoir discuss choice."}]
        graph = build_roundtable_graph(ask, FakeEmbeddings())
        graph.invoke({"dilemma": "A decision", "option_a": "Stay", "option_b": "Leave",
                      "evidence": evidence, "thinkers": ["Aristotle", "Simone de Beauvoir"],
                      "discussion_round": 0, "discussion_turns": []})
        self.assertEqual(calls, [
            ("Aristotle", []),
            ("Simone de Beauvoir", ["View from Aristotle"]),
            ("Aristotle", ["View from Aristotle", "View from Simone de Beauvoir"]),
            ("Simone de Beauvoir", ["View from Aristotle", "View from Simone de Beauvoir", "View from Aristotle"]),
        ])

    def test_roundtable_caps_contributions_even_mid_round(self):
        from museum.roundtable import build_roundtable_graph

        def ask(schema, instruction, data):
            if schema.__name__ == "Perspective":
                return schema(text=f"View from {data['thinker']}", citations=[])
            return schema(ready=False, summary=f"Reviewed {len(data['turns'])} turns.")

        evidence = [{"id": "S1", "title": "Aristotle, Nietzsche, and Simone de Beauvoir",
                     "url": "https://example.org", "content": "Aristotle, Nietzsche and Simone de Beauvoir discuss choice."}]
        graph = build_roundtable_graph(ask, FakeEmbeddings())
        result = graph.invoke({"dilemma": "A decision", "option_a": "Stay", "option_b": "Leave",
                               "evidence": evidence, "thinkers": ["Aristotle", "Nietzsche", "Simone de Beauvoir"],
                               "discussion_round": 0, "discussion_turns": []})
        self.assertEqual([turn["thinker"] for turn in result["discussion_turns"]],
                         ["Aristotle", "Nietzsche", "Simone de Beauvoir", "Aristotle"])
        self.assertEqual(result["distillation"], "Reviewed 4 turns.")

    def test_sqlite_review_survives_reopen(self):
        from langgraph.checkpoint.sqlite import SqliteSaver
        from unchosen_lives import build_graph

        def search(query):
            return [{"url": "https://example.org/beauvoir", "title": "Simone de Beauvoir"}]

        def extract(urls):
            return [{"url": urls[0], "content": "Simone de Beauvoir. Freedom is a task that calls for responsibility."}]

        config = {"configurable": {"thread_id": "durable-case"}}
        with tempfile.TemporaryDirectory() as directory:
            db = str(Path(directory) / "checkpoints.sqlite")
            with SqliteSaver.from_conn_string(db) as checkpointer:
                graph = build_graph(FakeModel(), FakeEmbeddings(), checkpointer, search, extract)
                self.assertIn("__interrupt__", graph.invoke({"dilemma": "A decision", "option_a": "Stay", "option_b": "Leave"}, config))
            with SqliteSaver.from_conn_string(db) as checkpointer:
                graph = build_graph(FakeModel(), FakeEmbeddings(), checkpointer, search, extract)
                result = graph.invoke(Command(resume={"action": "approve"}), config)
                self.assertTrue(result["approved"])

    def test_revision_feedback_returns_to_review(self):
        from unchosen_lives import build_graph

        class RevisionModel(FakeModel):
            def with_structured_output(self, schema):
                if schema.__name__ == "Letter":
                    class Runner:
                        def invoke(self, messages):
                            data = json.loads(messages[-1].content)
                            return schema(text=data["review_notes"] or "First draft", citations=[])
                    return Runner()
                return super().with_structured_output(schema)

        graph = build_graph(RevisionModel(), FakeEmbeddings(), InMemorySaver(),
                            lambda query: [{"url": "https://example.org/a", "title": "Aristotle"}],
                            lambda urls: [{"url": urls[0], "content": "Aristotle on responsibility and choice."}])
        config = {"configurable": {"thread_id": "review-revision"}}
        graph.invoke({"dilemma": "A decision", "option_a": "Stay", "option_b": "Leave"}, config)
        revised = graph.invoke(Command(resume={"action": "revise", "notes": "Make it more hopeful"}), config)
        self.assertIn("__interrupt__", revised)
        self.assertIn("Make it more hopeful", revised["exhibit"])
        self.assertTrue(graph.invoke(Command(resume={"action": "approve"}), config)["approved"])

    def test_roundtable_reports_partially_verified_citations_accurately(self):
        from unchosen_lives import render_exhibit

        source = {"id": "S1", "url": "https://example.org/a", "title": "Aristotle", "content": "Freedom is a task that calls for responsibility."}
        letter = {"text": "A fictional future.", "citations": []}
        state = {"dilemma": "A choice", "option_a": "Stay", "option_b": "Leave",
                 "future_a": letter, "future_b": letter, "evidence": [source], "thinkers": ["Aristotle"],
                 "critique": {"needs_revision": False, "issues": []}, "distillation": "A tension.",
                 "discussion_turns": [{"round": 1, "thinker": "Aristotle", "text": "A view.",
                                       "citations": [{"source_id": "S1", "quote": source["content"]}], "unverified": True}]}
        report = render_exhibit(state, {"shared_values": [], "questions": [], "experiment": "Reflect."})
        self.assertIn("Some proposed citations or inline quotations were unverified", report)
        self.assertNotIn("No verified supporting excerpt", report)

    def test_roundtable_flags_unverified_inline_quotes_even_with_valid_citation(self):
        from museum.roundtable import build_roundtable_graph

        source = {"id": "S1", "title": "Aristotle and Immanuel Kant",
                  "url": "https://example.org", "content": "Freedom is a task that calls for responsibility."}

        def ask(schema, instruction, data):
            if schema.__name__ == "Perspective":
                return schema(text="I believe 'an invented philosophical quotation appears here'.",
                              citations=[{"source_id": "S1", "quote": source["content"]}])
            return schema(ready=True, summary="A discussion.")

        graph = build_roundtable_graph(ask, FakeEmbeddings())
        result = graph.invoke({"dilemma": "A decision", "option_a": "Stay", "option_b": "Move",
                               "evidence": [source], "thinkers": ["Aristotle", "Immanuel Kant"],
                               "discussion_round": 0, "discussion_turns": []})
        self.assertTrue(all(turn["unverified"] for turn in result["discussion_turns"]))

    def test_saved_exhibit_is_visible_and_not_overwritten(self):
        from unchosen_lives import save_exhibit

        with tempfile.TemporaryDirectory() as directory:
            path = save_exhibit("First exhibit", "abc", Path(directory))
            self.assertEqual(path.read_text(), "First exhibit")
            with self.assertRaises(FileExistsError):
                save_exhibit("Replacement", "abc", Path(directory))
            self.assertEqual(path.read_text(), "First exhibit")


if __name__ == "__main__":
    unittest.main()
