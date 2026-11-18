import json
from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel

from langchain_core.messages import SystemMessage, HumanMessage
from langchain_ollama import ChatOllama

class Plan(BaseModel):
    kind: Literal["general", "decision"]
    option_a: str
    option_b: str


class FutureState(TypedDict, total=False):
    question: str
    response: str
    kind: str
    option_a: str
    option_b: str
    future_a: str
    future_b: str

def build_futures(model):

    classifier = model.model_copy(update={"reasoning": False, "temperature": 0.0}) if isinstance(model, ChatOllama) else model
    def classify(state: FutureState):
        plan = classifier.with_structured_output(Plan).invoke([
            SystemMessage(content=(
                "Classify the question. If it asks the user to choose between two "
                "alternatives, set kind to decision and extract those alternatives "
                "into option_a and option_b. Otherwise set kind to general and both "
                "options to empty strings. Do not invent personal facts. "
                "Examples: Should I take the train or drive? -> decision, train, drive. "
                "What makes a life meaningful? -> general, empty, empty."
            )),
            HumanMessage(content=state['question'])
        ])

        if plan is None:
            raise ValueError("Failed to classify the state")

        if plan.kind == "general":
            return {"kind": "general", "option_a": "", "option_b": ""}
        a,b = plan.option_a, plan.option_b

        if not a or not b or a.casefold() == b.casefold():
            raise ValueError("Invalid options for decision")

        return {"kind": "decision", "option_a": a, "option_b": b}

    def write(option, output):
        def node(state):
            letter = model.invoke([
                SystemMessage(content=f"Write a short fictional future letter with gains and losses.\n"
                              "It is not a prediction or advice. Do not include personal facts."),
                HumanMessage(content=json.dumps({"question": state['question'], "option": option, "discussion": state["response"]}))
            ])
            return {output: letter.content}
        return node

    graph = StateGraph(FutureState)
    graph.add_node("classify", classify)
    graph.add_node("future_a", write("option_a", "future_a"))
    graph.add_node("future_b", write("option_b", "future_b"))

    graph.add_edge(START, "classify")
    graph.add_conditional_edges(
        "classify", lambda state: ["future_a", "future_b"] if state.get("kind") == "decision" else [END],
        ["future_a", "future_b", END],
    )
    graph.add_edge(["future_a", "future_b"], END)
    return graph.compile()
