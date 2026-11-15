from typing import TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import StateGraph, START, END
from langgraph.types import Command, interrupt

class State(TypedDict, total=False):
    question: str
    draft: str
    approved: bool

def draft(state: State):
    return {"draft": f"Consider more than one view of {state['question']}"}

def review(state: State):
    answer = interrupt({"draft": state["draft"], "question": "Approve?"})
    return {"approved": answer.get("approved", False)}

builder = StateGraph(State)
builder.add_node("draft", draft)
builder.add_node("review", review)

builder.add_edge(START, "draft")
builder.add_edge("draft", "review")
builder.add_edge("review", END)

graph = builder.compile(checkpointer=InMemorySaver())
CONFIG = {"configurable": {"thread_id": "lesson-1"}}

paused = graph.invoke({"question": "What makes work meaningful?"}, CONFIG)
print("PAUSED:", paused["__interrupt__"][0].value)
finished  = graph.invoke(Command(resume={"approved": True}), CONFIG)
print("APPROVED:", finished["approved"])