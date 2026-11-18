from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import BaseModel

from museum.graph import build_graph

app = FastAPI()


class Question(BaseModel):
    dilemma: str


@app.post("/question")
def question(data: Question):
    graph = build_graph(checkpointer=InMemorySaver(), library_db=Path(".data/library.sqlite"))
    result = graph.invoke({"dilemma": data.dilemma}, {"configurable": {"thread_id": uuid4().hex}})
    return {"discussion": result.get("distillation"), "exhibit": result.get("exhibit"),
            "paused": bool(result.get("__interrupt__"))}
