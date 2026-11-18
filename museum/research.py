"""Discover public sources and source-mentioned thinkers in up to two rounds."""

import re
import unicodedata
from urllib.parse import urlparse

from langchain_tavily import TavilyExtract, TavilySearch
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from museum import prompts
from museum.library import search_library
from museum.models import LocalAssessment, ResearchState, Source


TOPIC_QUERIES = {
    "general": ("philosophy meaning wisdom ethics human life", "philosophy fundamental questions truth meaning",
                "philosophy philosophical inquiry and human experience", "philosophy major traditions and ideas"),
    "meaning": ("philosophy meaning of life purpose existentialism", "philosophy happiness meaning good life",
                "philosophy meaning absurdity existence", "philosophy virtue flourishing human life"),
    "ethics": ("philosophy morality ethics good and evil", "philosophy moral responsibility right wrong",
               "philosophy virtue ethics consequences duty", "philosophy moral values reasoning"),
    "free_will": ("philosophy free will determinism freedom", "philosophy free will moral responsibility",
                  "philosophy determinism agency choice", "philosophy freedom causation human action"),
    "knowledge": ("philosophy knowledge truth skepticism", "philosophy belief evidence epistemology",
                  "philosophy knowing truth certainty", "philosophy knowledge reason experience"),
    "reality": ("philosophy reality existence metaphysics", "philosophy appearance reality ontology",
                "philosophy nature of existence reality", "philosophy metaphysics perception world"),
    "consciousness": ("philosophy consciousness mind subjective experience", "philosophy mind body awareness",
                      "philosophy self consciousness identity", "philosophy mental states physical reality"),
    "death": ("philosophy death mortality meaning", "philosophy mortality life death",
              "stoicism death finitude acceptance", "existentialism death meaning existence"),
    "politics": ("philosophy justice society political freedom", "political philosophy equality rights power",
                 "philosophy democracy authority justice", "philosophy individual society obligations"),
    "religion": ("philosophy religion faith reason", "philosophy god belief religious experience",
                 "philosophy religion meaning existence", "philosophy faith doubt argument"),
    "career": ("philosophy meaningful work vocation freedom", "philosophy career choices authenticity uncertainty",
               "existentialism choice responsibility work", "stoicism work ambition meaningful life"),
    "relationships": ("philosophy relationships autonomy commitment", "philosophy love freedom responsibility",
                      "existentialism relationships freedom ethics", "philosophy friendship commitment meaning"),
    "identity": ("philosophy personal identity authenticity choice", "philosophy self identity becoming",
                 "existentialism authenticity self creation", "philosophy identity values change"),
    "change": ("philosophy change uncertainty life decisions", "philosophy courage change stability",
               "stoicism uncertainty change control", "existentialism freedom responsibility uncertainty"),
}

# Names are a privacy-safe catalog, not proof that a source accurately represents a thinker.
THINKERS = (
    "Simone de Beauvoir", "Jean-Paul Sartre", "Søren Kierkegaard",
    "Friedrich Nietzsche", "Socrates", "Plato", "Aristotle", "Epictetus", "William James",
    "Martha Nussbaum", "Albert Camus", "Hannah Arendt", "Confucius",
    "Laozi", "Zhuangzi", "Mencius", "Nāgārjuna", "Shantideva",
    "Rabindranath Tagore", "B. R. Ambedkar", "Mahatma Gandhi",
    "bell hooks", "W. E. B. Du Bois", "Audre Lorde", "Iris Murdoch",
    "Mary Wollstonecraft", "John Stuart Mill", "Immanuel Kant",
    "Baruch Spinoza", "Marcus Aurelius", "Seneca", "Viktor Frankl",
    "David Hume", "Michel de Montaigne", "Sophie de Grouchy", "Arthur Schopenhauer",
)

ALIASES = {
    "Søren Kierkegaard": ("Soren Kierkegaard", "Kierkegaard"),
    "Laozi": ("Lao Tzu", "Lao Tse"),
    "Jean-Paul Sartre": ("Jean Paul Sartre", "Sartre"),
    "B. R. Ambedkar": ("B R Ambedkar", "B. R. Ambedkar"),
    "Baruch Spinoza": ("Benedict Spinoza", "Spinoza"),
    "Friedrich Nietzsche": ("Nietzsche",),
    "Immanuel Kant": ("Kant",),
    "Arthur Schopenhauer": ("Schopenhauer",),
    "Michel de Montaigne": ("Montaigne",),
}


def _normalize(text: str) -> str:
    return "".join(char for char in unicodedata.normalize("NFKD", text.casefold())
                   if not unicodedata.combining(char))


def mentions_thinker(text: str, name: str) -> bool:
    normalized = _normalize(text)
    return any(re.search(rf"(?<!\w){re.escape(_normalize(alias))}(?!\w)", normalized)
               for alias in (name, *ALIASES.get(name, ())))


def discover_thinkers(evidence: list[Source]) -> list[str]:
    scores = {name: sum(2 * mentions_thinker(item["title"], name) +
                        mentions_thinker(item["content"], name) for item in evidence)
              for name in THINKERS}
    return sorted((name for name in THINKERS if scores[name]), key=lambda name: -scores[name])


def search_queries(topic: str, round_number: int, thinkers: list[str]) -> list[str]:
    queries = TOPIC_QUERIES[topic]
    known = list(dict.fromkeys(name for name in thinkers if name in THINKERS))[:2]
    if round_number == 0:
        if known:
            return ([f"{name} {queries[0]}" for name in known] + list(queries[:2]))[:2]
        return list(queries[:2])
    if known:
        targeted = [f"{name} philosophy freedom responsibility primary source" for name in known]
        return (targeted + list(queries[2:]))[:2]
    return list(queries[2:])


def tavily_search(query: str) -> list[dict]:
    response = TavilySearch(max_results=3).invoke({"query": query})
    if not isinstance(response, dict) or response.get("error") or not isinstance(response.get("results"), list):
        raise RuntimeError(f"Tavily search failed: {response}")
    return response["results"]


def tavily_extract(urls: list[str]) -> list[dict]:
    response = TavilyExtract().invoke({"urls": urls})
    if not isinstance(response, dict) or response.get("error"):
        raise RuntimeError(f"Tavily extract failed: {response}")
    if response.get("failed_results"):
        raise RuntimeError(f"Tavily could not extract sources: {response['failed_results']}")
    results = response.get("results")
    if not isinstance(results, list):
        raise RuntimeError("Tavily extract returned an invalid response.")
    return [{"url": item["url"], "content": item.get("raw_content", "")} for item in results]


def build_research_graph(search, extract, embeddings=None, ask=None, library_db=None):
    def retrieve_local(state):
        if library_db is None or not library_db.is_file():
            return {"local_candidates": [], "local_reason": "No local index is available."}
        query = "\n".join((state["dilemma"], state["option_a"], state["option_b"]))
        matches = search_library(library_db, query, embeddings)
        candidates = []
        authors = {}
        for number, item in enumerate(matches, 1):
            names = discover_thinkers([{"id": "", "title": "", "url": "", "content": item["first_page"]}])
            title = f"{', '.join(names) or item['path']} — {item['path']}, page {item['page']}"
            candidates.append({"id": f"L{number}", "title": title, "url": item["url"],
                               "content": item["content"]})
            authors[f"L{number}"] = names
        return {"local_candidates": candidates, "local_authors": authors, "local_reason": ""}

    def assess_local(state):
        candidates = state.get("local_candidates", [])
        if not candidates:
            return {"local_evidence": [], "local_sufficient": False,
                    "local_reason": state.get("local_reason") or "No local passages were found."}
        result = ask(LocalAssessment, prompts.LOCAL_ASSESSMENT, {
            "dilemma": state["dilemma"], "option_a": state["option_a"], "option_b": state["option_b"],
            "passages": candidates,
        })
        known = {item["id"] for item in candidates}
        if not set(result.relevant_source_ids) <= known:
            raise ValueError("Local assessment referenced unknown source IDs.")
        relevant = [item for item in candidates if item["id"] in result.relevant_source_ids]
        thinkers = discover_thinkers(relevant)
        authors = {name for item in relevant for name in state.get("local_authors", {}).get(item["id"], [])}
        requested = {name for name in THINKERS if mentions_thinker(state["dilemma"], name)}
        missing = requested - authors
        thinkers = [name for name in thinkers if name in requested] + [
            name for name in thinkers if name not in requested
        ]
        enough = len(authors) >= 2 and not missing
        reason = result.reason.strip()
        if not reason:
            raise ValueError("Local assessment did not explain its decision.")
        if missing:
            reason += " Requested thinkers missing from relevant local sources: " + ", ".join(sorted(missing)) + "."
        elif len(authors) < 2:
            reason += " Fewer than two identified local authors were found."
        return {"local_evidence": relevant, "evidence": relevant, "thinkers": thinkers,
                "local_sufficient": enough, "local_reason": reason}

    def dispatch(state):
        explicit = [name for name in THINKERS if mentions_thinker(state["dilemma"], name)]
        return [Send("research_worker", {"query": query}) for query in
                search_queries(state["topic"], state["research_round"], explicit + state.get("thinkers", []))]

    def worker(task):
        results = search(task["query"])
        titles = {}
        for item in results:
            url = item.get("url", "")
            if urlparse(url).scheme in ("http", "https") and urlparse(url).netloc:
                titles[url] = item.get("title") or url
        if not titles:
            return {"found": [], "trace_queries": [task["query"]]}
        pages = extract(list(titles)[:2])
        found = []
        for page in pages:
            url = page.get("url", "")
            content = (page.get("content") or "").strip()
            if url in titles and content:
                found.append({"url": url, "title": titles[url], "content": content[:6000]})
        return {"found": found, "trace_queries": [task["query"]]}

    def assess(state):
        unique = {}
        for item in state["found"]:
            unique.setdefault(item["url"].rstrip("/"), item)
        evidence = list(state.get("local_evidence", [])) + [
            {"id": f"S{i}", **item} for i, item in enumerate(unique.values(), 1)
        ]
        thinkers = discover_thinkers(evidence)
        requested = [name for name in thinkers if mentions_thinker(state["dilemma"], name)]
        thinkers = requested + [name for name in thinkers if name not in requested]
        domains = {domain for item in evidence if (domain := urlparse(item["url"]).netloc)}
        missing = [name for name in THINKERS if mentions_thinker(state["dilemma"], name) and name not in thinkers]
        enough = len(domains) >= 2 and len(thinkers) >= 2 and not missing
        round_number = state["research_round"] + 1
        warnings = []
        if not enough and round_number >= 2:
            if len(domains) < 2 or len(thinkers) < 2:
                warnings.append("Limited evidence: fewer than two web source domains or two catalogued thinkers found. Names are mentions, not verified endorsements.")
            if missing:
                warnings.append("No sources mentioned the requested thinkers: " + ", ".join(missing) + ".")
        return {"evidence": evidence, "thinkers": thinkers, "research_round": round_number, "warnings": warnings}

    def route(state):
        domains = {domain for item in state["evidence"] if (domain := urlparse(item["url"]).netloc)}
        missing = any(mentions_thinker(state["dilemma"], name) and name not in state["thinkers"] for name in THINKERS)
        return "dispatch" if state["research_round"] < 2 and (len(domains) < 2 or len(state["thinkers"]) < 2 or missing) else END

    graph = StateGraph(ResearchState)
    if library_db is not None:
        graph.add_node("retrieve_local", retrieve_local)
        graph.add_node("assess_local", assess_local)
    graph.add_node("dispatch", lambda _: {})
    graph.add_node("research_worker", worker)
    graph.add_node("assess", assess)
    if library_db is None:
        graph.add_edge(START, "dispatch")
    else:
        graph.add_edge(START, "retrieve_local")
        graph.add_edge("retrieve_local", "assess_local")
        graph.add_conditional_edges("assess_local", lambda state: END if state["local_sufficient"] else "dispatch",
                                    [END, "dispatch"])
    graph.add_conditional_edges("dispatch", dispatch, ["research_worker"])
    graph.add_edge("research_worker", "assess")
    graph.add_conditional_edges("assess", route, ["dispatch", END])
    return graph.compile()
