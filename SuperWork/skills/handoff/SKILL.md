---
name: handoff
description: Compact the current conversation into a handoff document for another agent to pick up. Manual-trigger only - the user explicitly asks for a handoff or session transfer ("/handoff", "交接一下", "压缩会话"); do not auto-trigger this on ordinary task endings.
argument-hint: "What will the next session be used for?"
disable-model-invocation: true
---

Write a handoff document summarising the current conversation so a fresh agent can continue the work. Save it to `docs/交接/YYYY-MM-DD-交接与剩余任务.md` **in the workspace** (not a temp dir) — handoffs must be greppable and survive across sessions. If `docs/文档导航.md` is missing, create it via the doc-index skill first; register the handoff row in the 交接 table.

Include a "suggested skills" section in the document, which suggests skills that the agent should invoke.

Do not duplicate content already captured in other artifacts (specs, plans, decisions, logs, commits, diffs). Reference them by path — the 文档导航 index and 决策记录 are the recovery anchors, not this doc.

## Required slots

1. **立即接续命令** — exact shell commands to reproduce state (git status, the test command). Durable run commands (setup/run/test/deploy) live in `docs/运行.md` — reference it, don't re-derive here.
2. **今日交付** — what shipped, with commit SHAs and key artifacts.
3. **剩余任务** — what the next session should do, in priority order.
4. **诚实边界** — what was NOT done / unverified / blocked, stated plainly. Required, not optional.
5. **suggested skills** — which SuperWork skills the next agent should invoke and why.

Redact any sensitive information — API keys, passwords, PII. If the user passed arguments, treat them as a description of what the next session will focus on and tailor the doc accordingly.
