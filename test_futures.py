import unittest
from unittest.mock import patch

from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_ollama import ChatOllama

from fortytwo.futures import build_futures


class FutureTests(unittest.TestCase):
    def test_classifier_disables_reasoning_without_changing_letter_model(self):
        calls = []

        def generate(model, messages, stop=None, run_manager=None, **kwargs):
            structured = "format" in kwargs
            calls.append((structured, model.reasoning))
            if structured:
                content = (
                    '{"kind":"decision","option_a":"train","option_b":"drive"}'
                    if "train" in messages[-1].content.casefold()
                    else '{"kind":"general","option_a":"","option_b":""}'
                )
            else:
                content = "A fictional future."
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content=content))])

        model = ChatOllama(model="qwen3.5:4b", reasoning=True)
        with patch.object(ChatOllama, "_generate", autospec=True, side_effect=generate):
            graph = build_futures(model)
            general = graph.invoke({"question": "What matters?", "response": "Discussion"})
            decision = graph.invoke({"question": "Train or drive?", "response": "Discussion"})

        self.assertEqual(general["kind"], "general")
        self.assertEqual(decision["kind"], "decision")
        self.assertEqual(calls.count((True, False)), 2)
        self.assertEqual(calls.count((False, True)), 2)
        self.assertTrue(model.reasoning)


if __name__ == "__main__":
    unittest.main()
