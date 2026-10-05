---
name: research
description: "Use when the user wants a topic investigated against high-trust primary sources - official docs, API facts, current best practices (\"查一下文档\", \"这个 API 怎么用\"). Delegates the reading to a background agent and captures findings with citations as a Markdown file in the repo. NOT for questions you can answer from the codebase itself or already know."
---
# Research

## Purpose

Answer research questions from primary sources with citations — delegated to a background agent so the session keeps working.

## When to Use / Not Use

- Use: topics needing official docs, API facts, standards, current best practices (「查一下文档」「这个 API 怎么用」).
- Do NOT use: questions answerable from the codebase itself or already known; project-internal empirical data (that belongs in `docs/实验/` per doc-index).

## Capability Boundary

- CAN: dispatch a background investigation, enforce primary-source discipline, capture cited findings in the right docs location.
- CANNOT: produce final deliverables (that's writing's job); accept uncited claims.
- Depends on: a background/sub-agent tool; doc-index registration.

## Input Contract

- Required: the research question, scoped enough to investigate.
- Optional: depth/scope hints, known candidate sources.
- Missing behavior: question too broad → narrow it with the user in one exchange before dispatching.

## Output Contract

- A single Markdown file where every claim carries a citation to its owning source (official docs, source code, specs, first-party APIs — never a secondary write-up of them).
- Destination by conclusion type: authoritative sources / standards / API facts → a section appended to `docs/技术依据.md`; a design-shaped conclusion → `docs/设计/YYYY-MM-DD-<主题>.md`. Registered in 文档导航 (create the index via doc-index if missing).

## Constraints and Prohibitions

- **Primary sources only**: follow every claim back to the source that owns it; a blog summarizing the docs is not the docs.
- The background agent's job is exactly three things: investigate against primary sources; write findings with per-claim citations; save to the destination above.
- Prohibited: presenting uncited findings; copying web content wholesale; conflating project-internal experiments with external research.

## Acceptance Criteria

- Findings saved to the correct location, every claim cited, registered in 文档导航.
- Self-check: does every claim trace to a primary source? Is the destination matched to the conclusion type?

## Failure and Escalation

- No background-agent tool → do the investigation inline, stating the context cost.
- Source contradicts another source → report both with citations; do not silently pick.
- Question turns out answerable from the codebase → stop and answer directly.

## Cost and Latency Budget

- One background dispatch per question (parallel dispatches allowed for independent questions). Over budget: return the best-cited partial findings plus the open tail.

## Examples

- Positive: "does library X support TLS 1.3?" → background agent reads X's official docs/changelog → cited answer appended to `docs/技术依据.md`.
- Negative: pasting an LLM-generated summary without source links as the finding.
- Edge: the answer depends on our own benchmark data → that's `docs/实验/` material, not this skill.

## Evaluation and Observability

- Metrics: uncited claims (target 0), secondary-source citations, user follow-ups caused by wrong facts.
- Log: citations in the findings file are the record; registration in 文档导航 is the completeness signal.
