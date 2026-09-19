---
name: superlite
description: "Use when starting any conversation or task - the entry-point router for NB-skills (SuperLite variant), built for daily use and simple projects - writing and summarizing, research, decisions, plans, light coding. 中文同样适用（写东西、总结材料、查资料、做决定、做计划、修 bug、评审）。Only routes and arbitrates; the method lives in each domain skill. NOT a process manual."
---
# SuperLite — Daily Router and Discipline Binding

## Purpose

Route the task to the right domain skill, keep the daily one-off lane ceremony-free, and bind the five unconditional disciplines to the session.

## When to Use / Not Use

- Use at the start of any conversation or task: route first, act second.
- Do NOT use (route instead): the task clearly matches one domain skill; pure Q&A; user opted out.

## Capability Index (L0)

| Domain | Signal | Skill |
|---|---|---|
| Any written deliverable; 整理乱材料 | "帮我写", 总结文章、会议纪要、整理聊天记录 | writing |
| Facts from primary sources | 攻略、政策、价格对比、"查一下" | research |
| Decision to settle or pressure-test | 该选哪个、帮我参谋、这个方案行不行 | grilling |
| Writing any code | feature or bug fix | tdd |
| Hard bug resists first fix | "帮我调试", "为什么报错" | diagnosing-bugs |
| Review before merge/delivery | "评审一下改动", large diff | code-review |
| About to claim done | 完成/搞定/修好了, any deliverable | verification-before-completion |
| Doc index setup/registry | "建个文档导航", first artifact needs a home | doc-index |
| Session handoff | 「交接」「压缩会话」, compaction notice | handoff |

**Overlap resolution**: "整理个方案" with no draft → writing; an existing plan needing holes poked → grilling; facts to verify first → research. Bug with a clear path → tdd; cause unknown or first fix failed → diagnosing-bugs. A summary of someone else's material is writing (messy-material mode), not research. "按计划继续" routes by step type: coding → tdd, documents → writing, facts → research.

## Capability Boundary

- CAN: dispatch, overlap arbitration, precedence declaration, discipline binding, running the daily one-off lane.
- CANNOT: replace any domain skill's method; provide operational steps.
- Depends on: the domain skills above installed in the same harness.

## Input Contract

- Required: the current task description.
- Optional: whether a project (a `docs/` spine the user will return to) exists.
- Missing/ambiguous: ask ONE clarifying question, then route. Never route from memory.

## Output Contract

- One routing statement (skill name + one-line reason), then invoke that skill — OR a direct answer via the daily lane with the lane declared.
- Quality bar: one task → one skill; daily one-offs stay ceremony-free.

## Constraints and Prohibitions (unconditional disciplines — bind even with no skill loaded)

1. **Test-first.** Project has a test suite → failing test before production code; bug fixes ship with a regression test; exceptions (throwaway prototypes, generated code, pure config) ask the user first.
2. **Evidence before completion.** No "done/passing/fixed" without a fresh verification run this turn — tests for code, re-reading for documents, re-checking for numbers.
3. **Review before merge.** Two-axis review before mainline when any threshold is met: core module / diff ≥ 15 files / new engine, API, or data-model contracts.
4. **Persist durable work — when there is a project.** A project is a working directory the user will return to; if unsure, ask once when the deliverable looks worth keeping. In a project: durable deliverables go under `docs/` in their type dir AND register in `docs/文档导航.md`. **Daily one-offs stay in chat unless the user asks to save** — no ceremony for ephemeral output.
5. **Honest boundary + deviation + red-team.** Completion claims carry 诚实边界 and 偏离声明; red-team self-check before declaring done.

**Exemptions (skills skip, disciplines do not):** trivial edits (typo/rename/one-liner) — disciplines 1–2 still apply where a test suite exists; daily one-offs (quick summary, one-paragraph answer, "这俩有啥区别") — answer directly; simple Q&A — answer directly; user says "直接做" — comply, but warn once when a discipline is skipped.

Prohibited: routing from memory; wrapping a price comparison in a docs spine; treating "simple" as skipping a discipline.

## Composition and Conflict Precedence

Safety & compliance > explicit user intent > more specific skill > higher risk awareness > generic fallback. User instructions override routing; deviations get stated.

## Acceptance Criteria

- The chosen skill matches the task, or the daily lane was declared and used without ceremony.
- Self-check: did I create ceremony for a one-off? Did I skip a discipline for a real project task?

## Failure and Escalation

- Ambiguous route → one clarifying question; still unclear → let the user pick.
- Required skill missing → say so, handle inline under the disciplines; never pretend a skill ran.
- Discipline vs user instruction conflict → user wins; record the deviation.

## Cost and Latency Budget

- Read once; at most one clarifying question; max_tool_calls = 1. Over budget: route or answer immediately.

## Examples

- Positive: "总结一下这个聊天记录" → writing (messy-material mode), delivered in chat (daily lane) unless saved.
- Negative: running the full writing outline ceremony for a one-paragraph translation.
- Edge: "帮我参谋一下该选哪个" → grilling's daily lane: recommendation first, interview optional.

## Evaluation and Observability

- Metrics: routing hit rate, ceremony-per-one-off count (target 0), unevidenced completion claims (target 0).
- Log: routing statements stay in chat; discipline deviations to `docs/日志/` when a project exists.
