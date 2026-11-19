"""Local FastAPI wrapper around the checkpointed museum graph."""

import json
import logging
import os
import re
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command
from pydantic import BaseModel, StringConstraints, model_validator

from museum.graph import build_graph, save_exhibit
from museum.trace import describe_event


LOG = logging.getLogger(__name__)
DATA_DIR = Path(__file__).resolve().parent / ".data"
ORIGINS = {"http://localhost:5173", "http://127.0.0.1:5173",
           "http://localhost:8000", "http://127.0.0.1:8000"}
STAGES = {
    "understand_paths": "Understanding the choices",
    "select_topic": "Question understood",
    "research": "Research complete",
    "roundtable": "Roundtable complete",
    "assess_follow_up": "Checking sources for your follow-up",
    "research_follow_up": "Additional research complete",
    "discuss_follow_up": "Follow-up discussion complete",
    "future_a": "One future drafted",
    "future_b": "One future drafted",
    "critic": "Critique complete",
    "curate": "Exhibit prepared",
    "review": "Review received",
}

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]


class NewSession(BaseModel):
    dilemma: Text
    option_a: Text | None = None
    option_b: Text | None = None

    @model_validator(mode="after")
    def require_both_options(self):
        if bool(self.option_a) != bool(self.option_b):
            raise ValueError("Provide both paths or neither.")
        return self


class Clarification(BaseModel):
    clarification: Text


class FollowUp(BaseModel):
    question: Text


class Review(BaseModel):
    action: Literal["approve", "revise"]
    notes: Annotated[str, StringConstraints(strip_whitespace=True, max_length=4000)] = ""

    @model_validator(mode="after")
    def require_notes_for_revision(self):
        if self.action == "revise" and not self.notes:
            raise ValueError("Revision notes are required.")
        return self


def create_app(root: Path = DATA_DIR, graph_factory=None, exhibits_dir: Path | None = None,
               library_dir: Path | None = None) -> FastAPI:
    db_path = root / "sessions.sqlite"
    exhibits_dir = exhibits_dir or root / "exhibits"
    library_dir = (library_dir or Path(__file__).resolve().parent / "library").resolve()
    graph_factory = graph_factory or (
        lambda connection: build_graph(checkpointer=SqliteSaver(connection), library_db=root / "library.sqlite")
    )

    @contextmanager
    def connect():
        db = sqlite3.connect(db_path, timeout=30, check_same_thread=False)
        try:
            with db:
                yield db
        finally:
            db.close()

    @asynccontextmanager
    async def lifespan(app):
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd = os.open(db_path, os.O_CREAT | os.O_RDWR, 0o600)
        os.close(fd)
        with connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, status TEXT NOT NULL, stage TEXT NOT NULL, error TEXT, question TEXT)")
            if "question" not in {row[1] for row in db.execute("PRAGMA table_info(sessions)")}:
                db.execute("ALTER TABLE sessions ADD COLUMN question TEXT")
            db.execute("CREATE TABLE IF NOT EXISTS trace_events (id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL, event TEXT NOT NULL)")
            db.execute("UPDATE sessions SET status='error', error='The server restarted while this run was active. Start a new session.' WHERE status='running'")
        app.state.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="museum")
        try:
            yield
        finally:
            app.state.executor.shutdown(wait=True)

    app = FastAPI(title="Museum of Unchosen Lives", lifespan=lifespan)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1"])
    app.add_middleware(CORSMiddleware, allow_origins=list(ORIGINS), allow_methods=["GET", "POST"], allow_headers=["Content-Type"])

    @app.middleware("http")
    async def restrict_origin(request: Request, call_next):
        origin = request.headers.get("origin")
        if origin and origin not in ORIGINS:
            from fastapi.responses import JSONResponse
            return JSONResponse(status_code=403, content={"detail": "Origin not allowed."})
        return await call_next(request)

    def update(session_id: str, status: str, stage: str, error: str | None = None):
        with connect() as db:
            db.execute("UPDATE sessions SET status=?, stage=?, error=? WHERE id=?", (status, stage, error, session_id))

    def run(session_id: str, data):
        config = {"configurable": {"thread_id": session_id}}
        try:
            with connect() as db:
                graph = graph_factory(db)
                for namespace, event in graph.stream(data, config, stream_mode="updates", subgraphs=True):
                    for node, output in event.items():
                        activity = describe_event(namespace, node, output)
                        if activity:
                            with connect() as trace_db:
                                trace_db.execute("INSERT INTO trace_events (session_id, event) VALUES (?, ?)",
                                                 (session_id, json.dumps(activity, ensure_ascii=False)))
                        if not namespace and node in STAGES:
                            update(session_id, "running", STAGES[node])
                snapshot = graph.get_state(config)
                state = snapshot.values
                interruptions = getattr(snapshot, "interrupts", ())
                if any(isinstance(item.value, dict) and item.value.get("kind") == "clarification"
                       for item in interruptions):
                    update(session_id, "clarification", "Your clarification is needed")
                elif state.get("approved"):
                    if not isinstance(data, dict) or data.get("entry_action") != "followup":
                        save_exhibit(state["exhibit"], session_id, exhibits_dir)
                    update(session_id, "approved", "Exhibit saved")
                elif state.get("exhibit"):
                    update(session_id, "review", "Ready for your review")
                else:
                    raise RuntimeError("The graph ended without an exhibit.")
        except Exception as exc:
            LOG.exception("Session failed: %s", session_id)
            update(session_id, "error", "Unable to complete", str(exc))

    def get_session(session_id):
        if not re.fullmatch(r"[a-f0-9]{32}", session_id):
            raise HTTPException(status_code=404, detail="Session not found.")
        with connect() as db:
            row = db.execute("SELECT status, stage, error FROM sessions WHERE id=?", (session_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Session not found.")
        return row

    @app.get("/api/library/{source_path:path}")
    def library_pdf(source_path: str):
        path = (library_dir / source_path).resolve()
        if not path.is_relative_to(library_dir) or path.suffix.lower() != ".pdf" or not path.is_file():
            raise HTTPException(status_code=404, detail="Source not found.")
        return FileResponse(path, media_type="application/pdf")

    @app.post("/api/sessions", status_code=202)
    def start(data: NewSession):
        session_id = uuid4().hex
        with connect() as db:
            db.execute("INSERT INTO sessions (id, status, stage, question) VALUES (?, 'running', 'Preparing your question', ?)",
                       (session_id, data.dilemma))
        app.state.executor.submit(run, session_id, data.model_dump(exclude_none=True))
        return {"id": session_id}

    @app.get("/api/sessions")
    def list_sessions():
        with connect() as db:
            rows = db.execute("SELECT id, status, stage, question FROM sessions ORDER BY rowid DESC").fetchall()
            results = []
            for session_id, status, stage, question in rows:
                if not question:
                    state = graph_factory(db).get_state({"configurable": {"thread_id": session_id}}).values
                    question = state.get("dilemma") or "Previous reflection"
                results.append({"id": session_id, "status": status, "stage": stage, "question": question})
        return results

    @app.get("/api/sessions/{session_id}")
    def status(session_id: str):
        current, stage, error = get_session(session_id)
        result = {"id": session_id, "status": current, "stage": stage, "error": error}
        with connect() as db:
            rows = db.execute("SELECT event FROM trace_events WHERE session_id=? ORDER BY id", (session_id,)).fetchall()
        result["trace"] = [json.loads(row[0]) for row in rows]
        if current in ("clarification", "review", "approved"):
            with connect() as db:
                state = graph_factory(db).get_state({"configurable": {"thread_id": session_id}}).values
            result.update({key: state.get(key) for key in (
                "dilemma", "option_a", "option_b", "clarification_question", "messages", "discussion_turns", "discussion_round",
                "distillation", "future_a", "future_b", "reflection", "critique", "warnings", "exhibit"
            )})
            result["sources"] = [{"id": item["id"], "title": item["title"], "url": item["url"]}
                                 for item in state.get("evidence", [])]
        return result

    @app.post("/api/sessions/{session_id}/follow-up", status_code=202)
    def follow_up(session_id: str, data: FollowUp):
        current, _, _ = get_session(session_id)
        if current not in ("review", "approved"):
            raise HTTPException(status_code=409, detail="This session is not ready for a follow-up.")
        with connect() as db:
            changed = db.execute(
                "UPDATE sessions SET status='running', stage='Considering your follow-up', error=NULL "
                "WHERE id=? AND status=?", (session_id, current)
            ).rowcount
        if not changed:
            raise HTTPException(status_code=409, detail="This session is no longer ready for a follow-up.")
        command = (Command(resume={"action": "discuss", "question": data.question}) if current == "review"
                   else {"entry_action": "followup", "follow_up_question": data.question,
                         "follow_up_return_to_review": False})
        app.state.executor.submit(run, session_id, command)
        return {"id": session_id}

    @app.post("/api/sessions/{session_id}/clarify", status_code=202)
    def clarify(session_id: str, data: Clarification):
        get_session(session_id)
        with connect() as db:
            changed = db.execute(
                "UPDATE sessions SET status='running', stage='Considering your clarification', error=NULL "
                "WHERE id=? AND status='clarification'", (session_id,)
            ).rowcount
        if not changed:
            raise HTTPException(status_code=409, detail="This session is not awaiting clarification.")
        app.state.executor.submit(run, session_id, Command(resume=data.model_dump()))
        return {"id": session_id}

    @app.post("/api/sessions/{session_id}/review", status_code=202)
    def review(session_id: str, data: Review):
        get_session(session_id)
        with connect() as db:
            changed = db.execute("UPDATE sessions SET status='running', stage='Applying your review', error=NULL WHERE id=? AND status='review'", (session_id,)).rowcount
        if not changed:
            raise HTTPException(status_code=409, detail="This session is not ready for review.")
        app.state.executor.submit(run, session_id, Command(resume=data.model_dump()))
        return {"id": session_id}

    return app


app = create_app(exhibits_dir=Path(__file__).resolve().parent / "exhibits")
