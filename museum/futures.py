"""Retrieve relevant passages and write one fictional future."""

from langgraph.graph import END, START, StateGraph

from museum import prompts
from museum.models import FutureState, Letter
from museum.retrieval import retrieve_passages


def build_future_graph(ask, embeddings):
    def retrieve(state: FutureState):
        query = f"{state['dilemma']}\nOption: {state['option']}"
        return {"passages": retrieve_passages(state["evidence"], query, embeddings, 4)}

    def write(state: FutureState):
        letter = ask(Letter, prompts.FUTURE, {
            key: state[key] for key in ("dilemma", "option", "other_option", "review_notes", "passages", "distillation")
        })
        return {"letter": letter.model_dump()}

    graph = StateGraph(FutureState)
    graph.add_node("retrieve", retrieve)
    graph.add_node("write", write)
    graph.add_edge(START, "retrieve")
    graph.add_edge("retrieve", "write")
    graph.add_edge("write", END)
    return graph.compile()
