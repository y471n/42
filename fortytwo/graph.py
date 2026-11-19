"""Assemble the subgraphs and the human-review workflow."""

import json
import os
import re
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama, OllamaEmbeddings
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from fortytwo import prompts
from fortytwo.futures import build_future_graph
from fortytwo.models import Critic, LocalAssessment, FortyTwoState, PathPlan, Reflection, Topic
from fortytwo.research import THINKERS, build_research_graph, discover_thinkers, mentions_thinker, tavily_extract, tavily_search
from fortytwo.retrieval import validate_citations, validate_letter
from fortytwo.roundtable import build_roundtable_graph


def build_graph(llm=None, embeddings=None, checkpointer=None, search=None, extract=None, library_db=None):
    llm = llm or ChatOllama(model="qwen3.5:4b", temperature=0, reasoning=False, num_ctx=16384, num_predict=1800)
    embeddings = embeddings or OllamaEmbeddings(model="nomic-embed-text")
    search = search or tavily_search
    extract = extract or tavily_extract

    def ask(schema, instruction, data):
        result = llm.with_structured_output(schema).invoke([
            SystemMessage(content=prompts.SYSTEM + "\n" + instruction),
            HumanMessage(content=json.dumps(data, ensure_ascii=False)),
        ])
        if result is None:
            raise RuntimeError(f"Model returned no structured {schema.__name__}.")
        return result

    research_graph = build_research_graph(search, extract, embeddings, ask, library_db)
    roundtable_graph = build_roundtable_graph(ask, embeddings)
    future_graph = build_future_graph(ask, embeddings)

    def understand_paths(state):
        messages = [] if state.get("messages") else [{"role": "user", "content": state["dilemma"]}]
        if state.get("option_a") and state.get("option_b"):
            return {"paths_clear": True, "question_kind": "decision", "messages": messages}
        plan = ask(PathPlan, prompts.PATHS, {
            "dilemma": state["dilemma"], "clarification": state.get("clarification", "")
        })
        if plan.kind == "decision":
            a, b = plan.option_a.strip(), plan.option_b.strip()
            if not a or not b or a.casefold() == b.casefold():
                raise ValueError("The model did not provide two distinct paths.")
            return {"option_a": a, "option_b": b, "paths_clear": True,
                    "question_kind": "decision", "messages": messages}
        if plan.kind == "general":
            return {"option_a": "", "option_b": "", "paths_clear": True,
                    "question_kind": "general", "messages": messages}
        if not plan.question.strip():
            raise ValueError("The model did not provide a clarification question.")
        question = plan.question.strip()
        return {"paths_clear": False, "clarification_question": question,
                "messages": messages + [{"role": "assistant", "content": question}]}

    def clarify_paths(state):
        response = interrupt({"kind": "clarification", "question": state["clarification_question"]})
        if not isinstance(response, dict) or not isinstance(response.get("clarification"), str) or not response["clarification"].strip():
            raise ValueError("Clarification must not be empty.")
        clarification = response["clarification"].strip()
        return {"clarification": clarification,
                "dilemma": state["dilemma"] + "\nAdditional context: " + clarification,
                "messages": [{"role": "user", "content": clarification}]}

    def select_topic(state):
        topic = ask(Topic, prompts.TOPIC, {
            "dilemma": state["dilemma"], "option_a": state["option_a"], "option_b": state["option_b"]
        })
        return {"topic": topic.topic, "research_round": 0, "revision_round": 0,
                "found": [], "evidence": [], "thinkers": [], "warnings": [], "review_notes": ""}

    def conduct_roundtable(state):
        result = roundtable_graph.invoke({
            "dilemma": state["dilemma"], "option_a": state["option_a"], "option_b": state["option_b"],
            "evidence": state["evidence"], "thinkers": state["thinkers"],
            "discussion_round": 0, "discussion_turns": [], "review_notes": state.get("review_notes", ""),
        })
        return {**{key: result[key] for key in ("discussion_round", "discussion_turns", "distillation")},
                "messages": [{"role": "assistant", "turns": result["discussion_turns"],
                              "distillation": result["distillation"]}]}

    def assess_follow_up(state):
        question = state["follow_up_question"].strip()
        if not question:
            raise ValueError("Follow-up question must not be empty.")
        history = []
        if not state.get("messages"):
            history = [{"role": "user", "content": state["dilemma"]},
                       {"role": "assistant", "turns": state.get("discussion_turns", []),
                        "distillation": state.get("distillation", "")}]
        history.append({"role": "user", "content": question})
        evidence = state.get("evidence", [])
        if not evidence:
            return {"follow_up_needs_research": True, "messages": history}
        assessment = ask(LocalAssessment, prompts.LOCAL_ASSESSMENT, {
            "dilemma": question, "option_a": state["option_a"], "option_b": state["option_b"],
            "passages": [{**source, "content": source["content"][:1200]} for source in evidence],
        })
        known = {source["id"] for source in evidence}
        if not set(assessment.relevant_source_ids) <= known or not assessment.reason.strip():
            raise ValueError("The follow-up evidence assessment was invalid.")
        relevant = [source for source in evidence if source["id"] in assessment.relevant_source_ids]
        thinkers = discover_thinkers(relevant)
        missing = [name for name in THINKERS if mentions_thinker(question, name) and name not in thinkers]
        enough = len(thinkers) >= 2 and not missing
        reason = assessment.reason
        if missing:
            reason += " Requested thinkers missing from relevant sources: " + ", ".join(missing) + "."
        return {"follow_up_needs_research": not enough, "local_reason": reason, "messages": history}

    def research_follow_up(state):
        topic = ask(Topic, prompts.TOPIC, {
            "dilemma": state["follow_up_question"], "option_a": state["option_a"], "option_b": state["option_b"]
        })
        result = research_graph.invoke({
            "dilemma": state["follow_up_question"], "option_a": state["option_a"], "option_b": state["option_b"],
            "topic": topic.topic, "research_round": 0, "found": [], "evidence": [], "thinkers": [], "warnings": [],
        })
        evidence = list(state.get("evidence", []))
        existing_urls = {source["url"] for source in evidence}
        for source in result["evidence"]:
            if source["url"] not in existing_urls:
                evidence.append({**source, "id": f"F{len(state.get('messages', []))}-{source['id']}"})
                existing_urls.add(source["url"])
        return {"evidence": evidence, "warnings": state.get("warnings", []) + result.get("warnings", [])}

    def discuss_follow_up(state):
        result = roundtable_graph.invoke({
            "dilemma": state["follow_up_question"], "option_a": state["option_a"], "option_b": state["option_b"],
            "evidence": state["evidence"], "thinkers": state["thinkers"],
            "original_question": state["dilemma"],
            "discussion_round": 0, "discussion_turns": [], "previous_turns": state.get("discussion_turns", [])[-12:],
        })
        return {"discussion_turns": result.get("discussion_turns", []), "distillation": result["distillation"],
                "messages": [{"role": "assistant", "turns": result.get("discussion_turns", []),
                              "distillation": result["distillation"]}]}

    def future_worker(state, choice):
        other = "option_b" if choice == "option_a" else "option_a"
        result = future_graph.invoke({"dilemma": state["dilemma"], "option": state[choice],
                                      "other_option": state[other], "evidence": state["evidence"],
                                      "review_notes": state.get("review_notes", ""), "distillation": state["distillation"]})
        return {f"future_{choice[-1]}": result["letter"]}

    def criticize(state):
        issues = []
        for key in ("future_a", "future_b"):
            if state.get(key):
                issues.extend(validate_letter(state[key], state["evidence"]))
        critic = ask(Critic, prompts.CRITIC, {
            key: state.get(key) for key in ("dilemma", "option_a", "option_b", "future_a", "future_b", "evidence", "discussion_turns", "distillation")
        })
        issues.extend(critic.issues)
        needs_revision = bool(issues) or critic.needs_revision
        revision_round = state["revision_round"] + 1
        return {"critique": {"needs_revision": needs_revision, "issues": issues},
                "automatic_revision": needs_revision and state.get("question_kind") != "general" and revision_round < 2,
                "revision_round": revision_round, "review_notes": "\n".join(issues)}

    def critique_route(state):
        return "revise" if state["automatic_revision"] else "curate"

    def curate(state):
        reflection = ask(Reflection, prompts.CURATOR_GENERAL if state.get("question_kind") == "general" else prompts.CURATOR, {
            key: state.get(key) for key in ("dilemma", "option_a", "option_b", "future_a", "future_b", "critique", "discussion_turns", "distillation")
        })
        return {"reflection": reflection.model_dump(), "exhibit": render_exhibit(state, reflection.model_dump())}

    def review(state):
        decision = interrupt({"exhibit": state["exhibit"], "instructions": "Approve or provide revision notes."})
        if not isinstance(decision, dict) or decision.get("action") not in ("approve", "revise", "discuss"):
            raise ValueError("Review must specify approve, revise, or discuss.")
        if decision["action"] == "approve":
            return {"approved": True, "review_action": "approve"}
        if decision["action"] == "discuss":
            question = decision.get("question", "")
            if not isinstance(question, str) or not question.strip():
                raise ValueError("Follow-up question must not be empty.")
            return {"review_action": "discuss", "follow_up_question": question.strip(),
                    "follow_up_return_to_review": True}
        notes = decision.get("notes", "")
        if not isinstance(notes, str) or not notes.strip():
            raise ValueError("Revision notes must not be empty.")
        return {"approved": False, "review_action": "revise", "review_notes": notes.strip(), "revision_round": 0}

    graph = StateGraph(FortyTwoState)
    graph.add_node("understand_paths", understand_paths)
    graph.add_node("clarify_paths", clarify_paths)
    graph.add_node("select_topic", select_topic)
    graph.add_node("research", research_graph)
    graph.add_node("roundtable", conduct_roundtable)
    graph.add_node("assess_follow_up", assess_follow_up)
    graph.add_node("research_follow_up", research_follow_up)
    graph.add_node("discuss_follow_up", discuss_follow_up)
    graph.add_node("future_a", lambda state: future_worker(state, "option_a"))
    graph.add_node("future_b", lambda state: future_worker(state, "option_b"))
    graph.add_node("critic", criticize)
    graph.add_node("revise", lambda _: {})
    graph.add_node("curate", curate)
    graph.add_node("review", review)
    graph.add_conditional_edges(START, lambda state: "assess_follow_up" if state.get("entry_action") == "followup"
                                else "understand_paths", ["assess_follow_up", "understand_paths"])
    graph.add_conditional_edges("understand_paths", lambda state: "select_topic" if state["paths_clear"] else "clarify_paths",
                                ["select_topic", "clarify_paths"])
    graph.add_edge("clarify_paths", "understand_paths")
    graph.add_edge("select_topic", "research")
    graph.add_edge("research", "roundtable")
    graph.add_conditional_edges("roundtable", lambda state: ["critic"] if state.get("question_kind") == "general"
                                else ["future_a", "future_b"], ["critic", "future_a", "future_b"])
    graph.add_edge(["future_a", "future_b"], "critic")
    graph.add_conditional_edges("critic", critique_route, {"revise": "revise", "curate": "curate"})
    graph.add_conditional_edges("revise", lambda state: ["roundtable"] if state.get("question_kind") == "general"
                                else ["future_a", "future_b"], ["roundtable", "future_a", "future_b"])
    graph.add_edge("curate", "review")
    graph.add_conditional_edges("review",
                                lambda state: END if state["review_action"] == "approve" else (
                                    "assess_follow_up" if state["review_action"] == "discuss" else "revise"
                                ), [END, "assess_follow_up", "revise"])
    graph.add_conditional_edges("assess_follow_up",
                                lambda state: "research_follow_up" if state["follow_up_needs_research"] else "discuss_follow_up",
                                ["research_follow_up", "discuss_follow_up"])
    graph.add_edge("research_follow_up", "discuss_follow_up")
    graph.add_conditional_edges("discuss_follow_up",
                                lambda state: "review" if state.get("follow_up_return_to_review") else END,
                                ["review", END])
    return graph.compile(checkpointer=checkpointer)


def render_exhibit(state: FortyTwoState, reflection: dict) -> str:
    sources = {item["id"]: item for item in state["evidence"]}

    def letter_block(key):
        letter = state[key]
        verified = [c for c in letter["citations"] if not validate_citations([c], state["evidence"])]
        quotes = "\n".join(f"- “{c['quote']}” — [{c['source_id']}]({sources[c['source_id']]['url']})" for c in verified)
        return letter["text"] + ("\n\n" + quotes if quotes else "\n\n*No verified excerpts cited.*")

    warnings = list(state.get("warnings", []))
    if state["critique"]["needs_revision"]:
        warnings.extend(state["critique"]["issues"] or ["The critic identified unresolved concerns."])
    thinkers = ", ".join(state["thinkers"]) or "None identified from the catalog."
    ledger = "\n".join(f"- [{item['id']}] [{item['title']}]({item['url']})" for item in state["evidence"]) or "- No sources retrieved."
    turns = []
    for turn in state.get("discussion_turns", []):
        quotes = " ".join(f"“{c['quote']}” [{c['source_id']}]({sources[c['source_id']]['url']})"
                          for c in turn["citations"])
        status = ""
        if turn["unverified"]:
            status = (" *Some proposed citations or inline quotations were unverified.*" if turn["citations"]
                      else " *No verified supporting excerpt; inline quotations may also be unverified.*")
        turns.append(f"- **Round {turn['round']} — inspired by {turn['thinker']}:** {turn['text']}{status}" +
                     (f"\n  - Source excerpt: {quotes}" if quotes else ""))
    discussion = "\n".join(turns) if turns else "*No roundtable: insufficient distinct source-linked perspectives.*"
    has_futures = bool(state.get("future_a") and state.get("future_b"))
    sections = [
        "# 42",
        "> Philosophical voices are AI-generated interpretations, not the thinkers' own statements. Source quotations are checked for exact text, not for whether the interpretation is correct.",
        f"## The question\n\n{state['dilemma']}",
        "## Philosophers' roundtable\n\n*AI-generated interpretations, not statements or endorsements by the thinkers.*\n\n"
        + discussion + f"\n\n**Moderator's distillation:** {state['distillation']}",
    ]
    if has_futures:
        sections.extend([
            "> These letters are fiction, not predictions or professional advice.",
            f"## Future A: {state['option_a']}\n\n{letter_block('future_a')}",
            f"## Future B: {state['option_b']}\n\n{letter_block('future_b')}",
        ])
    sections.extend([
        "## Philosophers mentioned in retrieved sources\n\n" + thinkers + "\n\n*Mentions do not establish authorship or endorsement.*",
        ("## What survives in both lives\n\n" if has_futures else "## Themes to consider\n\n")
        + "\n".join(f"- {item}" for item in reflection["shared_values"]),
        "## Questions from the curator\n\n" + "\n".join(f"- {item}" for item in reflection["questions"]),
        f"## An optional experiment\n\n{reflection['experiment']}",
        "## Evidence limitations\n\n" + ("\n".join(f"- {item}" for item in warnings) if warnings else "- Interpretations and source relevance require human review."),
        f"## Sources\n\n{ledger}",
    ])
    return "\n\n".join(sections) + "\n"


def save_exhibit(exhibit: str, session_id: str, directory: Path = Path("exhibits")) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", session_id):
        raise ValueError("Invalid session ID.")
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = directory / f"exhibit-{session_id}.md"
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as file:
        file.write(exhibit)
    return path
