---
name: research
description: "Use when the user wants a topic investigated against high-trust primary sources - official docs, API facts, current best practices, 攻略、政策、价格对比 (\"查一下文档\", \"查一下攻略\"). Delegates the reading to a background agent and captures findings with citations - as a Markdown file in the repo for project work, or in chat for daily one-off questions. NOT for questions you can answer from the codebase itself or already know, and NOT for producing the deliverable itself - hand findings to writing."
---
# Research

Spin up a **background agent** to do the research, so you keep working while it reads.

Its job:

1. Investigate the question against **primary sources** — official docs, source code, specs, first-party APIs — not a secondary write-up of them. Follow every claim back to the source that owns it.
2. Write the findings to a single Markdown file, citing each claim's source. **Daily one-off questions are the exception**: answer in chat with citations and skip the file unless the user asks to save it or the work belongs to a project with a `docs/` spine.
3. Save it and register it: if the findings are about authoritative sources / standards / API facts → append a section to `docs/技术依据.md`; if the output is a design-shaped conclusion → `docs/设计/YYYY-MM-DD-<主题>.md`. Register the file in 文档导航 (per doc-index). If `docs/文档导航.md` is missing, create it via the doc-index skill first.

NOT for project-internal empirical data — that goes in `docs/实验/` (structure per doc-index).
