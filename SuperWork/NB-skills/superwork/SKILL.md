---
name: superwork
description: "Use when starting any conversation or receiving any coding task - the entry-point router that decides which NB-skills skill applies BEFORE any other action, and binds the unconditional disciplines to the session. 中文任务同样适用（加功能、修 bug、写代码、做计划、执行计划、评审、合并、查文档）。Only routes and arbitrates; the method lives in each domain skill. NOT a process manual."
---
# SuperWork — Coding Lifecycle Router and Discipline Binding

## Purpose

Route the current task to the right domain skill and bind the five unconditional disciplines to the session. This skill carries no procedure of its own.

## When to Use / Not Use

- Use at the start of any coding session or task: route first, act second.
- Use when several skills seem to apply: it arbitrates the overlap.
- Do NOT use when the task already clearly matches one domain skill (invoke that skill directly), for pure Q&A, trivial one-line edits, or when the user opted out of skills.

## Capability Index (L0)

| Domain | Signal | Skill |
|---|---|---|
| Underspecified idea | "build me something…", "加个功能", new project | brainstorming |
| Approved design, needs plan | "拆任务", "做个实施计划" | writing-plans |
| Executing a written plan | "把计划做了", "继续做计划" | executing-plans |
| Writing production code | "开写", "实现这个功能" | tdd |
| Hard bug resists first fix | "帮我调试", "为什么报错" | diagnosing-bugs |
| About to claim done | "完成", "修好了", before commit/PR | verification-before-completion |
| Review before merge/delivery | "评审一下改动", large diff | code-review |
| Received review findings | "处理评审意见" | receiving-code-review |
| Integration choice | "合并分支", "提个 PR" | finishing-a-development-branch |
| Merge/rebase conflict open | "解决冲突", "rebase 卡住了" | resolving-merge-conflicts |
| Stress-test a decision | "帮我挑刺", "这个方案行不行" | grilling |
| Terminology / ADR records | "统一术语", "记个架构决策" | domain-modeling |
| Primary-source research | "查一下文档", "这个 API 怎么用" | research |
| Create/edit a skill, retro | "加个 skill", 复盘 (explicit request only) | writing-skills |
| Doc index setup/registry | "建个文档导航", first artifact needs a home | doc-index |
| Session handoff | 「交接」「压缩会话」, harness compaction notice | handoff |

## Capability Boundary

- CAN: dispatch, overlap arbitration, precedence declaration, discipline binding.
- CANNOT: replace any domain skill's method; provide operational steps.
- Depends on: the domain skills above installed in the same harness; `docs/文档导航.md` when it exists.

## Input Contract

- Required: the current task description.
- Optional: existing artifact state (spec / plan / review report / handoff doc paths).
- If missing/ambiguous: ask ONE clarifying question, then route. Never route from memory.

## Output Contract

- One routing statement (skill name + one-line reason), then invoke that skill.
- Quality bar: one task stage → one skill; overlaps resolved by the precedence rules and stated.

## Constraints and Prohibitions (unconditional disciplines — bind even with no skill loaded)

1. **Test-first.** If the project has a test suite, write the failing test before production code; exceptions (throwaway prototypes, generated code, pure config) require asking the user first.
2. **Evidence before completion.** No "done/passing/fixed" claim without a fresh verification command run and read in this turn.
3. **Review before merge.** Two-axis review is mandatory when any threshold is met: core module touched / diff ≥ 15 files / new engine, API, or data-model contracts.
4. **Persist and register.** Artifacts are saved under `docs/` in their type directory AND registered in `docs/文档导航.md`. Chat-only is not a deliverable.
5. **Honest boundary.** Completion claims carry what was NOT done/verified plus a deviation statement; red-team self-check ("how could this be wrong?") before declaring done.

Prohibited: skipping the route and picking a skill from memory; treating "the task is simple" as a reason to skip a discipline (simplicity scales the ceremony inside a skill, never the disciplines).

## Composition and Conflict Precedence

Safety & compliance > explicit user intent > more specific skill > higher risk awareness > generic fallback. When stages overlap, the earlier lifecycle stage wins. User instructions override routing, but the deviation must be stated.

## Acceptance Criteria

- The chosen skill matches the task's lifecycle stage; no earlier stage skipped.
- The five disciplines are in effect for the session. Self-check: did I state the route and the reason? Is any earlier stage being skipped?

## Failure and Escalation

- Ambiguous route → ask one clarifying question; still unclear → let the user pick the stage.
- Required skill missing → say so explicitly and handle inline under these disciplines; never pretend a skill ran.
- Discipline vs user instruction conflict → user instruction wins; record the deviation.

## Cost and Latency Budget

- Read once; at most one clarifying question before routing; max_tool_calls = 1. Over budget: route immediately, stop elaborating.

## Examples

- Positive: user says 「把计划做了」 and a plan document exists → executing-plans.
- Negative: picking tdd without checking whether an approved plan exists on disk.
- Edge: a "bug report" that is really a feature request → brainstorming, not diagnosing-bugs.

## Evaluation and Observability

- Metrics: routing hit rate (chosen skill not corrected by the user), clarifications per route, mis-route rework count.
- Log: routing statements stay in chat; major mis-routes go to `docs/日志/`.

## References (L2, load on demand)

- Skill-to-skill transitions and resume-from-disk: `references/handoffs.md`
- Skip-the-route rationalizations: `references/red-flags.md`
- What may skip a skill (never the disciplines): `references/exemptions.md`
