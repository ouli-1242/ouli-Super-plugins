---
name: research
description: "Use when the user wants a topic investigated against high-trust primary sources - official docs, API facts, current best practices (\"查一下文档\", \"这个 API 怎么用\"). 中文信号：\"查一下文档\"\"这个 API 怎么用\""
---
# Research

Spin up a **background agent** to do the research, so you keep working while it reads.

Its job:

1. Investigate the question against **primary sources** — official docs, source code, specs, first-party APIs — not a secondary write-up of them. Follow every claim back to the source that owns it.
2. Write the findings to a single Markdown file, citing each claim's source.
3. Save it and register it: if the findings are about authoritative sources / standards / API facts → append a section to `docs/技术依据.md`; if the output is a design-shaped conclusion → `docs/设计/YYYY-MM-DD-<主题>.md`. Register the file in 文档导航 (per doc-index). If `docs/文档导航.md` is missing, create it via the doc-index skill first.

NOT for project-internal empirical data — that goes in `docs/实验/` (structure per doc-index).
