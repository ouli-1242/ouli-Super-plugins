---
name: handoff
description: "Use when the user wants to compress, transfer, or continue the session elsewhere - 「交接」「handoff」「压缩会话」「会话太长了」「开新会话」「换个会话继续」 - or when a harness compaction notice appears in the conversation. The agent writes a handoff doc so the next session can continue losslessly (compaction itself is the harness's: auto compact / /summarize / /compact / /compress). NOT at ordinary task endings - finish the task and claim completion instead."
---
# Handoff

## Purpose

Keep a session losslessly resumable: maintain a handoff document that any fresh session (or post-compaction self) can continue from — on real triggers only, kept current as work progresses.

## When to Use / Not Use

- Use: exactly three agent-visible signals — (1) user asks (「交接」「压缩会话」「开新会话」「会话太长了」); (2) a harness compaction/summarize notice appears in context (write immediately after); (3) a new session discovers an existing handoff doc under `docs/交接/` (read it before doing anything).
- Do NOT use: at ordinary task endings — finish the task and claim completion instead.

## Capability Boundary

- CAN: write and continuously maintain the handoff doc, tailor it to the next session's purpose, redact sensitive data.
- CANNOT: compress its own context (that's the harness's: auto compact / /compact / /compress); estimate its own context percentage.
- Depends on: `docs/交接/`, `docs/文档导航.md`, `docs/运行.md` for durable run commands.

## Input Contract

- Required: a trigger signal (above).
- Optional: user's description of what the next session will focus on (treat arguments as that description).
- Missing behavior: before writing, ask ONE question — what will the next session be used for? The answer decides which state is worth carrying.

## Output Contract

- `docs/交接/YYYY-MM-DD-交接与剩余任务.md` (in the workspace, not a temp dir — greppable and cross-session) with exactly five required slots:
  1. **立即接续命令** — exact shell commands to reproduce state (git status, test command). Durable run commands live in `docs/运行.md` — reference, don't re-derive.
  2. **今日交付** — what shipped, with commit SHAs and key artifacts.
  3. **剩余任务** — next session's work in priority order.
  4. **诚实边界与偏离声明** — what was NOT done / unverified / blocked, plus what was actually done vs what was asked or planned. Required, not optional.
  5. **suggested skills** — which skills the next agent should invoke and why.
- Registered in 文档导航 (交接 table); doc kept current through the session.

## Constraints and Prohibitions

- **Only real triggers.** The agent cannot see its own context percentage — any "trigger at X%" design is void. Compaction timing is unpredictable, so the doc is maintained continuously: after each deliverable unit (commit, green test, feature point, one verification) update 今日交付 / 剩余任务. Don't wait for the trigger.
- Do not duplicate content already captured in other artifacts (specs, plans, decisions, logs, commits) — reference them by path; 文档导航 and 决策记录 are the recovery anchors, not this doc.
- **Redact** every API key, password, PII before writing.
- Prohibited: pretending compaction happened or deleting context; inventing a percentage-based self-trigger; treating task endings as handoff triggers.

## Acceptance Criteria

- The doc exists, is current, has all five slots, is registered, and a fresh session could resume from it without asking the user anything the doc should have answered.
- Self-check: could I resume from this doc alone? Is every sensitive value redacted?

## Failure and Escalation

- User requests handoff mid-task → record exact in-progress state including the half-done step; do not finish the task first unless asked.
- Harness compaction notice arrives with no doc → write it immediately from what is still reconstructible; state the gap in 诚实边界.

## Cost and Latency Budget

- One doc, five slots; maintenance updates are two-slot appends. Over budget: write 立即接续命令 + 剩余任务 + 诚实边界 first — those carry the resumption.

## Examples

- Positive: after each green test run, 今日交付 gains the SHA; a 3 a.m. auto-compact loses nothing.
- Negative: "context feels long, better hand off" — not a real trigger; the agent can't measure that.
- Edge: compaction notice → write the doc immediately, including "the test run output was lost to compaction" in 诚实边界.

## Evaluation and Observability

- Metrics: next-session questions answerable only by asking the user (target 0), compactions with a stale doc, sensitive leaks in handoffs (target 0).
- Log: the handoff doc IS the record; staleness signals feed the maintenance habit.
