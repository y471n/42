from typing import TypedDict

from langchain_ollama import ChatOllama, OllamaEmbeddings
from langgraph.graph import END, START, StateGraph

from museum.library import search_index

class State(TypedDict, total=False):
    question: str
    passages: list[dict]
    response: str


def build_graph(llm=None, embeddings=None):
    model = llm or ChatOllama(model="qwen3.5:4b", temperature=0, reasoning=False)
    embeddings = embeddings or OllamaEmbeddings(model="nomic-embed-text")

    def retrieve(state: State):
        passages = search_index(state["question"], embeddings)
        return {"passages": passages}

    def answer(state: State):
        message = model.invoke([
            ("system", "Offer a concise philosophical perspective. Do not prescribe a decision."),
            ("human", state["question"]),
        ])
        return {"response": message.content}

    graph = StateGraph(State)
    graph.add_node("retrieve", retrieve)
    graph.add_node("answer", answer)
    
    graph.add_edge(START, "retrieve")
    graph.add_edge("retrieve", "answer")
    graph.add_edge("answer", END)
    return graph.compile()
