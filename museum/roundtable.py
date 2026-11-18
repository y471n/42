import json
import operator
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph
from langchain_core.messages import SystemMessage, HumanMessage

class Discussion(TypedDict, total=False):
    question: str
    passages: list[dict]
    turns: Annotated[list[dict], operator.add]
    summary: str
    response: str

def build_roundtable(model):
    def speak(name):
        def node(state: Discussion):
            result = model.invoke([
                SystemMessage(content=f"""Give a concise fictional interpretation inspired by {name}.
                 Use the passages and respond to earlier turns.
                 """),
                HumanMessage(content=json.dumps({
                    "question": state.get("question", ""),
                    "passages": state.get("passages", []),
                    "earlier_turns": state.get("turns", []),
                }))
            ])
            return {"turns": [{"speaker": name, "text": result.content}]}
        
        return node

    def moderate(state: Discussion):
        result = model.invoke([
            SystemMessage(content="Moderate the discussion by summarizing key points and ensuring relevance."),
            HumanMessage(content=json.dumps(state.get("turns", [])))
        ])
        return {"summary": result.content}

    graph = StateGraph(Discussion)
    graph.add_node("first", speak("Aristotle"))
    graph.add_node("second", speak("Plato"))
    graph.add_node("moderator", moderate)

    graph.add_edge(START, "first")
    graph.add_edge("first", "second")
    graph.add_edge("second", "moderator")
    graph.add_edge("moderator", END)

    return graph.compile()
