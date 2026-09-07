---
name: research
description: Use when the user wants a topic investigated against high-trust primary sources - official docs, API facts, current best practices ("查一下文档", "这个 API 怎么用", "research X", "look up the docs"). Delegates the reading to a background agent and captures findings with citations as a Markdown file in the repo. NOT for questions you can answer from the codebase itself or already know.
---

Spin up a **background agent** to do the research, so you keep working while it reads.

Its job:

1. Investigate the question against **primary sources** — official docs, source code, specs, first-party APIs — not a secondary write-up of them. Follow every claim back to the source that owns it.
2. Write the findings to a single Markdown file, citing each claim's source.
3. Save it where the repo already keeps such notes; match the existing convention, and if there is none, put it somewhere sensible and say where.
