"""Turn completed graph updates into concise, locally stored activity."""


def describe_event(namespace, node, output):
    group = namespace[0].split(":")[0] if namespace else node
    group = {"research_follow_up": "research", "discuss_follow_up": "roundtable"}.get(group, group)
    data = output if isinstance(output, dict) else {}
    title = None
    details = []

    def add(label, value):
        if value:
            details.append({"label": label, "value": str(value)})

    if node == "understand_paths" and not namespace:
        title = ("Question understood" if data.get("paths_clear") else "Clarification needed")
        add("Question", data.get("clarification_question"))
        if data.get("paths_clear"):
            add("Mode", "Open discussion" if data.get("question_kind") == "general" else "Explore two choices")
            add("Paths", " / ".join(value for value in (data.get("option_a"), data.get("option_b")) if value))
    elif node == "clarify_paths" and not namespace:
        title = "Clarification received"
    elif node == "select_topic" and not namespace:
        title = "Question classified"
        add("Research topic", data.get("topic"))
    elif node == "assess_follow_up" and not namespace:
        title = "Follow-up evidence assessed"
        add("Decision", "Researching more" if data.get("follow_up_needs_research") else "Reusing existing evidence")
        add("Reason", data.get("local_reason"))
    elif group == "research" and node == "retrieve_local":
        title = "Local library searched"
        add("Passages found", len(data.get("local_candidates", [])) or "None")
        add("Note", data.get("local_reason"))
    elif group == "research" and node == "assess_local":
        title = "Local evidence assessed"
        add("Decision", "Local evidence sufficient" if data.get("local_sufficient") else "Supplementing with web search")
        add("Reason", data.get("local_reason"))
        add("Useful passages", len(data.get("local_evidence", [])) or "None")
    elif group == "research" and node == "research_worker":
        title = "Research worker"
        add("Query", ", ".join(data.get("trace_queries", [])))
        add("Sources extracted", "\n".join(item["title"] for item in data.get("found", [])) or "None")
    elif group == "research" and node == "assess":
        title = f"Research round {data['research_round']} assessed"
        add("Sources", len(data.get("evidence", [])) or "None")
        add("Source list", "\n".join(f"{item['id']}: {item['title']} — {item['url']}"
                                     for item in data.get("evidence", [])))
        add("Thinkers found", ", ".join(data.get("thinkers", [])) or "None")
        add("Limitations", "\n".join(data.get("warnings", [])))
    elif group == "roundtable" and node == "philosopher":
        turn = data["discussion_turns"][0]
        title = f"Round {turn['round']} · {turn['thinker']}"
        add("Thinker", turn["thinker"])
        add("Perspective", turn["text"])
        add("Verified excerpts", len(turn["citations"]) or "None")
        if turn["unverified"]:
            add("Verification", "Some citations or inline quotations could not be verified.")
    elif group == "roundtable" and node == "moderator":
        title = f"Round {data['discussion_round']} moderated"
        add("Distillation", data.get("distillation"))
        decision = "Discussion ready" if data.get("discussion_ready") else "Another round requested"
        if not data.get("discussion_ready") and data.get("discussion_limit_reached"):
            decision = "Four-turn limit reached"
        add("Decision", decision)
    elif group == "roundtable" and node == "skip":
        title = "Roundtable skipped"
        add("Reason", data.get("distillation"))
    elif group in ("future_a", "future_b") and node == "retrieve":
        title = "Passages retrieved"
        passages = data.get("passages", [])
        add("Retrieved", f"{len(passages)} passages")
        add("Source IDs", ", ".join(dict.fromkeys(item["source_id"] for item in passages)) or "None")
    elif group in ("future_a", "future_b") and node == "write":
        title = "Future letter drafted"
        text = data["letter"]["text"]
        add("Draft excerpt", text[:1200] + ("…" if len(text) > 1200 else ""))
    elif node == "critic" and not namespace:
        title = f"Critique · pass {data['revision_round']}"
        critique = data["critique"]
        decision = "Revision requested" if critique["needs_revision"] else "No revision requested"
        if critique["needs_revision"] and data["revision_round"] >= 2:
            decision = "Revision limit reached; concerns remain"
        elif critique["needs_revision"] and data.get("automatic_revision") is False:
            decision = "Concerns for human review"
        add("Decision", decision)
        add("Issues", "\n".join(critique["issues"]) or "None")
    elif node == "revise" and not namespace:
        title = "Revision loop entered"
        add("Next", "Both futures will be rewritten.")
    elif node == "curate" and not namespace:
        title = "Exhibit curated"
        reflection = data["reflection"]
        add("Shared values", ", ".join(reflection["shared_values"]))
        add("Questions", "\n".join(reflection["questions"]))
    elif node == "review" and not namespace:
        title = "Human review received"
        add("Decision", "Approved" if data.get("approved") else "Revision requested")

    return {"group": group, "node": node, "title": title, "details": details} if title else None
