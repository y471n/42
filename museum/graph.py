from typing import TypedDict

from langchain_ollama import ChatOllama, OllamaEmbeddings
from langgraph.graph import END, START, StateGraph

from museum.futures import build_futures
from museum.library import search_index
from museum.roundtable import build_roundtable


class State(TypedDict, total=False):
    question: str
    passages: list[dict]
    turns: list[dict]
    response: str
    kind: str
    option_a: str
    option_b: str
    future_a: str
    future_b: str


def build_graph(llm=None, embeddings=None):
    model = llm or ChatOllama(model="qwen3.5:4b", temperature=0.4)
    vectors = embeddings or OllamaEmbeddings(model="nomic-embed-text")
    roundtable = build_roundtable(model)
    futures = build_futures(model)

    def retrieve(state):
        return {"passages": search_index(state["question"], vectors)}

    def discuss(state):
        result = roundtable.invoke({"question": state["question"], "passages": state["passages"], "turns": []})
        return {"turns": result["turns"], "response": result["summary"]}

    def imagine(state):
        result = futures.invoke({"question": state["question"], "response": state["response"]})
        return {key: result[key] for key in ("kind", "option_a", "option_b", "future_a", "future_b") if key in result}

    graph = StateGraph(State)
    graph.add_node("retrieve", retrieve)
    graph.add_node("discuss", discuss)
    graph.add_node("imagine", imagine)
    graph.add_edge(START, "retrieve")
    graph.add_edge("retrieve", "discuss")
    graph.add_edge("discuss", "imagine")
    graph.add_edge("imagine", END)
    return graph.compile()
