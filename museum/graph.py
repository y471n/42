from typing import TypedDict

from langchain_ollama import ChatOllama
from langgraph.graph import END, START, StateGraph


class State(TypedDict, total=False):
    question: str
    response: str


def build_graph(llm=None):
    model = llm or ChatOllama(model="qwen3.5:4b", temperature=0, reasoning=False)

    def answer(state: State):
        message = model.invoke([
            ("system", "Offer a concise philosophical perspective. Do not prescribe a decision."),
            ("human", state["question"]),
        ])
        return {"response": message.content}

    graph = StateGraph(State)
    graph.add_node("answer", answer)
    graph.add_edge(START, "answer")
    graph.add_edge("answer", END)
    return graph.compile()
