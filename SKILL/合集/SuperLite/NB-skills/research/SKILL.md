---
name: research
description: "Use when the user wants a topic investigated against high-trust primary sources - official docs, API facts, current best practices, 攻略、政策、价格对比 (\"查一下文档\", \"查一下攻略\"). Delegates the reading to a background agent and captures findings with citations - as a Markdown file in the repo for project work, or in chat for daily one-off questions. NOT for questions you can answer from the codebase itself or already know, and NOT for producing the deliverable itself - hand findings to writing."
---
# Research

## Purpose

Answer research questions from primary sources with citations — delegated to a background agent, delivered as a file for project work or in chat for daily one-offs.

## When to Use / Not Use

- Use: topics needing official docs, API facts, standards, best practices, 攻略/政策/价格对比 (「查一下文档」「查一下攻略」).
- Do NOT use: questions answerable from the codebase or already known; producing the final deliverable itself (hand findings to writing); project-internal empirical data (`docs/实验/`).

## Capability Boundary

- CAN: dispatch a background investigation, enforce primary-source discipline, capture cited findings in the right place.
- CANNOT: accept uncited claims; deliver the final written product.
- Depends on: a background/sub-agent tool; doc-index registration for project work.

## Input Contract

- Required: the research question, scoped enough to investigate.
- Optional: depth/scope hints, candidate sources.
- Missing behavior: question too broad → narrow it with the user in one exchange before dispatching.

## Output Contract

- A single body of findings where every claim carries a citation to its owning source (official docs, source code, specs, first-party APIs — never a secondary write-up).
- **Destination:** project work → Markdown file (authoritative sources/standards/API facts → section in `docs/技术依据.md`; design-shaped conclusion → `docs/设计/YYYY-MM-DD-<主题>.md`), registered in 文档导航. **Daily one-off questions are the exception** → answer in chat with citations; skip the file unless the user asks to save or the work belongs to a project.

## Constraints and Prohibitions

- **Primary sources only**: follow every claim back to the source that owns it; a blog summarizing the docs is not the docs.
- The background agent's job is exactly three things: investigate primary sources; write findings with per-claim citations; save/deliver to the destination above.
- Prohibited: presenting uncited findings; copying web content wholesale; producing the deliverable (that's writing's job); conflating project-internal experiments with external research.

## Acceptance Criteria

- Findings delivered with every claim cited, in the right destination (file or chat), registered when project work.
- Self-check: does every claim trace to a primary source? Was the file/stream choice right for the question's weight?

## Failure and Escalation

- No background-agent tool → do the investigation inline, stating the context cost.
- Source contradicts another source → report both with citations; do not silently pick.
- Question turns out answerable from the codebase → stop and answer directly.

## Cost and Latency Budget

- One background dispatch per question (parallel for independent questions). Over budget: return the best-cited partial findings plus the open tail.

## Examples

- Positive: "这个 API 支持分页吗？" → background agent reads the official docs → cited answer in chat (daily one-off).
- Negative: pasting an LLM-generated summary without source links as the finding.
- Edge: the research belongs to an ongoing project with a docs spine → file it under `docs/技术依据.md` and register, even if the user asked casually.

## Evaluation and Observability

- Metrics: uncited claims (target 0), secondary-source citations, files created for one-offs (target 0 unless asked).
- Log: citations in the findings are the record; registration in 文档导航 for project work.
