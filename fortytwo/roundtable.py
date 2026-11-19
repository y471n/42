"""Sequential philosopher-inspired perspectives and a bounded moderator loop."""

from langgraph.graph import END, START, StateGraph

from fortytwo import prompts
from fortytwo.models import Moderator, FortyTwoState, Perspective
from fortytwo.research import mentions_thinker
from fortytwo.retrieval import retrieve_passages, validate_citations, validate_letter

MAX_DISCUSSION_TURNS = 4


def build_roundtable_graph(ask, embeddings):
    def dispatch(state):
        return "philosopher" if len(state["thinkers"]) >= 2 else "skip"

    def philosopher(task):
        thinker = task["thinkers"][task["discussion_index"]]
        relevant = [source for source in task["evidence"] if mentions_thinker(
            source["title"] + "\n" + source["content"], thinker)]
        passages = retrieve_passages(relevant, f"{thinker} {task['dilemma']} freedom choice responsibility", embeddings, 3)
        perspective = ask(Perspective, prompts.PHILOSOPHER, {
            "thinker": thinker, "dilemma": task["dilemma"], "option_a": task["option_a"],
            "option_b": task["option_b"],
            "original_question": task.get("original_question", task["dilemma"]),
            "review_notes": task.get("review_notes", ""),
            "prior_turns": task.get("previous_turns", []) + task["discussion_turns"], "passages": passages,
        })
        citations = [item.model_dump() for item in perspective.citations]
        verified = [citation for citation in citations if not validate_citations([citation], relevant)]
        inline_issues = validate_letter({"text": perspective.text, "citations": verified}, relevant)
        return {"discussion_turns": [{"thinker": thinker, "round": task["discussion_round"] + 1,
                                      "text": perspective.text, "citations": verified,
                                      "unverified": len(verified) != len(citations) or not verified or bool(inline_issues)}],
                "discussion_index": task["discussion_index"] + 1}

    def next_speaker(state):
        more_speakers = state["discussion_index"] < min(3, len(state["thinkers"]))
        return "philosopher" if more_speakers and len(state["discussion_turns"]) < MAX_DISCUSSION_TURNS else "moderator"

    def moderate(state):
        result = ask(Moderator, prompts.MODERATOR, {
            "dilemma": state["dilemma"], "turns": state["discussion_turns"]
        })
        return {"discussion_round": state.get("discussion_round", 0) + 1,
                "distillation": result.summary, "discussion_ready": result.ready,
                "discussion_limit_reached": len(state["discussion_turns"]) >= MAX_DISCUSSION_TURNS}

    def route(state):
        return END if state["discussion_ready"] or state["discussion_limit_reached"] else "dispatch"

    graph = StateGraph(FortyTwoState)
    graph.add_node("dispatch", lambda _: {"discussion_index": 0})
    graph.add_node("philosopher", philosopher)
    graph.add_node("moderator", moderate)
    graph.add_node("skip", lambda _: {"discussion_round": 0, "distillation": "Not enough distinct source-linked perspectives for a roundtable."})
    graph.add_edge(START, "dispatch")
    graph.add_conditional_edges("dispatch", dispatch, ["philosopher", "skip"])
    graph.add_conditional_edges("philosopher", next_speaker, ["philosopher", "moderator"])
    graph.add_conditional_edges("moderator", route, ["dispatch", END])
    graph.add_edge("skip", END)
    return graph.compile()
