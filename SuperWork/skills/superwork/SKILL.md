---
name: superwork
description: Use when starting any conversation or receiving any coding task - the entry-point router that decides which SuperWork skill applies, by lifecycle stage, BEFORE any other action including clarifying questions. 中文任务同样适用（加功能、修 bug、写代码、做计划、执行计划、评审、合并、查文档）。Covers every stage from idea to integration; loading this first prevents choosing the wrong skill. The full route table, unconditional disciplines, and exemptions live in this skill's body - read them, don't route from memory.
---

# SuperWork Router

Decide **which skill** the current task needs, then invoke it by name. One task stage → one skill; the stages are mutually exclusive. When two skills seem to apply, the lifecycle stage decides — the earlier stage wins.

## The Rule

Route the task first, then act. Announce: "Using [skill] for [purpose]" and call the Skill tool with that skill's name. If it turns out wrong for the situation, you don't have to follow it — but the check comes first.

The Skill tool takes one skill per call. A stage needing two skills is two calls — say so explicitly ("call the Skill tool twice, with X and with Y").

## Lifecycle Route Table

| Stage (in order) | User signal (EN / 中文) | Invoke |
|---|---|---|
| 1. Underspecified idea | "build me something that…", "加个功能", "我想做个…", new project, requirements not yet settled | `brainstorming` |
| 2. Approved design, needs plan | "拆任务", "做个实施计划", "write the implementation plan" | `writing-plans` |
| 3. Executing a written plan | "execute the plan", "把计划做了", "继续做计划", "implement task N of the plan", resuming a plan mid-way | `executing-plans` |
| 4. Writing any code | "implement", "实现", "开写", "fix this" (with a clear fix path) | `tdd` |
| 5. Hard bug resists first fix | "debug this", "帮我调试", "为什么报错", broken/throwing/failing/slow | `diagnosing-bugs` |
| 6. About to claim done | "done", "完成", "搞定", "修好了", before commit/PR | `verification-before-completion` |
| 7. Before merge/delivery | "review", "评审一下改动", large diff (see discipline #3) | `code-review` |
| 7b. Received review findings | "fix these findings", "处理评审意见" | `receiving-code-review` |
| 8. Work done, integrate it | "合并分支", "提个 PR", "merge this back", "收尾这个分支" | `finishing-a-development-branch` |
| — Merge/rebase conflict in progress | "解决冲突", "merge conflict", "rebase 卡住了" | `resolving-merge-conflicts` |
| — Stress-test a settled plan | "grill me", "帮我挑刺", "这个方案行不行" | `grilling` |
| — Terminology / ADR | "统一术语", "记个架构决策", ubiquitous language | `domain-modeling` |
| — Research primary sources | "查一下文档", "这个 API 怎么用", "research X" | `research` |
| — Create/edit a skill | "加个 skill", "改一下这个 skill 的触发", "new skill" | `writing-skills` |
| — Session handoff | "交接", "handoff", "压缩会话" (user-invoked: `/handoff`) | user runs it |

Manual-trigger only (never auto-invoke): `handoff`. `grilling`'s With-Docs Mode (grill + domain-modeling together) also fires only on explicit user request.

**Stage overlap resolution:** a bug report that is really a feature request in disguise routes to `brainstorming`; a "review my approach" question before any code exists routes to `grilling`; stages 3 and 4 split on whether a plan document exists — a written plan routes to `executing-plans` (which calls `tdd` inside each task), a direct instruction with no plan routes to `tdd` directly; stage 4 never skips because the task "seems simple" — simplicity scales the ceremony inside the skill, not the routing decision.

## Unconditional Disciplines

These bind even when no skill is loaded:

1. **Test-first.** If the project has a test suite, write the failing test before production code; bug fixes ship with a regression test. Exceptions (throwaway prototypes, generated code, pure config) require asking the user first. Full method: `tdd`.
2. **Evidence before completion.** No claim of "done/passing/fixed" without a fresh verification command run and read in this turn. "Should pass" is not evidence. Full method: `verification-before-completion`.
3. **Review before merge.** Standards + Spec two-axis review before merging back to mainline when any threshold is met: core module touched / diff ≥ 15 files / new engine, API, or data-model contracts. Full method: `code-review`.

Disciplines are process rules — the exemptions below never waive them.

## Handoffs Between Skills

Skills pass control to the next stage with an explicit call, never a bare `/name` mention:

- `brainstorming` (architectural path, spec approved) → call the Skill tool with `"writing-plans"`
- `brainstorming` (bounded/spike path, design approved) → call the Skill tool with `"tdd"`
- `writing-plans` (plan written and approved) → call the Skill tool with `"executing-plans"`
- `executing-plans` (per task) → call the Skill tool with `"tdd"`; (all tasks done) → call the Skill tool with `"code-review"`, then `"verification-before-completion"`, then `"finishing-a-development-branch"` to integrate the work
- `code-review` (report produced) → call the Skill tool with `"receiving-code-review"`
- `tdd` (loop finished, cleanup time) → call the Skill tool with `"code-review"`
- `verification-before-completion` (change verified; user signals integration or the change was large per discipline #3) → call the Skill tool with `"finishing-a-development-branch"`
- `finishing-a-development-branch` (merge hits conflicts) → call the Skill tool with `"resolving-merge-conflicts"`

If a conversation was interrupted and you are resuming mid-flow, re-derive the stage from the artifacts on disk (spec status lines, plan checkboxes, git log) and re-enter the route table at that stage.

## Red Flags

| Thought | Reality |
|---------|---------|
| "This is just a simple question" | Questions are tasks. Check the route table. |
| "I need more context first" | Routing comes BEFORE exploring the codebase. |
| "The task is too simple for a skill" | Simple scales the ceremony down, never skips the route. |
| "I'll just start coding" | Stage 4 (`tdd`) applies the moment code is written. |
| "It's basically done" | That's a stage-6 claim — verify first. |
| "I remember what that skill says" | Skills evolve. Invoke and read the current version. |

## Exemptions (what skips skills — disciplines still apply)

- Trivial edits: copy changes, renames, one-line fixes, README tweaks → do directly.
- Pure execution ("把计划第 2 项做了") → if a written plan exists, enter at stage 3 (`executing-plans`); if it's a direct instruction with no plan document, enter at stage 4 (`tdd`). Either way, skip stages 1-2 (brainstorming/writing-plans).
- Simple Q&A and explanation requests → answer directly, no skill.
- User explicitly says "直接做 / don't use skills" → comply, but warn once when a discipline is being skipped.

## Precedence

1. Explicit user instruction > everything in this file.
2. Unconditional disciplines > exemptions.
3. When routing is ambiguous, ask the user which stage they're in — one question, then route.
