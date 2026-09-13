---
name: handoff
description: Use when the user asks to transfer or compress the session - "交接", "handoff", "压缩会话", "会话太长了" - or when context usage crosses the compression line: around 40% start the handoff unless a task is mid-flight, 60% is the hard ceiling even mid-task. Compresses the conversation into a handoff document another agent can continue from. NOT at ordinary task endings - finish the task and claim completion instead; NOT for summarizing documents or material (writing / doc-intake).
argument-hint: "What will the next session be used for?"
---

## Compression line（上下文压缩线）

- **~40% context**: if no task is mid-flight, run the handoff now — do not wait for the window to close. If a task is mid-flight, finish or checkpoint it first, then hand off.
- **60% context — hard ceiling**: hand off regardless of state. Checkpoint the in-flight task precisely in the document (what is done, what is half-done, the exact next action, any uncommitted changes) so the next session resumes cleanly instead of doing archaeology.

Context usage is estimated from conversation length and intensity, never measured exactly — when in doubt, hand off early. The 40% line exists because a handoff written early is cheap; one written at 90% is triage.

Write a handoff document summarising the current conversation so a fresh agent can continue the work. Save it to `docs/交接/YYYY-MM-DD-交接与剩余任务.md` **in the workspace** (not a temp dir) — handoffs must be greppable and survive across sessions. If `docs/文档导航.md` is missing, create it via the doc-index skill first; register the handoff row in the 交接 table.

Include a "suggested skills" section in the document, which suggests skills that the agent should invoke.

Do not duplicate content already captured in other artifacts (specs, plans, decisions, logs, commits, diffs). Reference them by path — the 文档导航 index and 决策记录 are the recovery anchors, not this doc.

## Required slots

1. **立即接续命令** — exact shell commands to reproduce state (git status, the test command). Durable run commands (setup/run/test/deploy) live in `docs/运行.md` — reference it, don't re-derive here.
2. **今日交付** — what shipped, with commit SHAs and key artifacts.
3. **剩余任务** — what the next session should do, in priority order.
4. **诚实边界与偏离声明** — what was NOT done / unverified / blocked, stated plainly, plus what was actually done vs what was asked or planned. Required, not optional.
5. **suggested skills** — which SuperLite skills the next agent should invoke and why.

Redact any sensitive information — API keys, passwords, PII. If the user passed arguments, treat them as a description of what the next session will focus on and tailor the doc accordingly.
