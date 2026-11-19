# 42 — manual evaluation

Unit tests check software contracts. They do not prove that the local model gives
faithful or useful interpretations. This directory is a small, human-scored
evaluation set — **not a validated quality benchmark**. No benchmark ships with
the project.

## Files

- `questions.csv` — questions, expected routing, relevant passages from `library/`,
  and reviewer notes. One row per scenario.
- `results.csv` — one row per run. Fill this in while reviewing; keep scores and
  notes explicit rather than treating a passing test suite as proof of quality.

## How to run

Start Ollama with both models, then the API and frontend:

```bash
uv run --env-file .env uvicorn api:app --host 127.0.0.1 --port 8000
cd frontend && npm run dev
```

For each row in `questions.csv`, submit the question through the UI at
`http://127.0.0.1:5173` and record the outcome in `results.csv`.

## What to check

1. An open question has no future letters. A two-choice question has two letters
   labeled as fiction.
2. A vague question may trigger clarification. Provide it and continue.
3. Inspect the trace. Local evidence can skip web search only when relevance and
   author-diversity checks pass; otherwise look at the broad web queries.
4. Open a source and compare it with a cited passage and interpretation. An exact
   match does not establish attribution or context.
5. Revise and approve a session, reopen it, and ask a follow-up. Follow-ups must
   not regenerate the original future letters.
6. Restart the API during an active run and confirm it reports an error. Restart
   while a different session is paused for review and resume it.

## Scoring columns

Use `0` = failing, `1` = partial/uncertain, `2` = good. Leave blank if not
applicable, and explain any score below 2 in `notes`.

- **retrieval_relevance** — do the retrieved passages address the question?
- **citation_accuracy** — do the cited excerpts actually appear in, and support,
  the named source?
- **interpretation_quality** — are the AI-generated voices plausible and clearly
  framed as interpretations, not the thinkers' own statements?
- **latency_seconds** — rough end-to-end time from submit to review pause.
- **failure** — error text, if any; otherwise empty.

## Privacy

Personal input goes to local Ollama. Tavily receives fixed topic queries,
catalogued names, and selected URLs, which can still disclose information.
Checkpoints, source text, drafts, trace events, and approved exhibits are stored
unencrypted in `.data/` and `exhibits/`. Treat the results file the same way —
do not commit personal questions or reviewer notes.

For dependency and service problems, see the troubleshooting list in
`BUILD_THE_UNCHOSEN_LIFE.md`, section 8.
