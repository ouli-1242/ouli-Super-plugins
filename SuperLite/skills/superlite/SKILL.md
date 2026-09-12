---
name: superlite
description: Use when starting any conversation or task - the entry-point router for SuperLite that decides which skill applies, and carries the unconditional disciplines (test-first, evidence before completion) that bind even when no other skill loads. 中文任务同样适用（写东西、修 bug、查资料、做计划、评审）。Compact route table and disciplines live in this skill's body - read them, don't route from memory.
---

# SuperLite Router

Route the task first, then act. Announce "Using [skill] for [purpose]" and call the Skill tool with that skill's name. One task → one skill; the route table decides.

## Route Table

| Task | Invoke |
|---|---|
| Writing any code (feature or bug fix) | `tdd` |
| Hard bug resists a first fix | `diagnosing-bugs` |
| Review changes before merge/delivery | `code-review` |
| About to claim done (any deliverable - code, doc, analysis) | `verification-before-completion` |
| Any written deliverable - documents, plans, reports, emails, configs | `writing` |
| Facts needed from primary sources - docs, APIs, research | `research` |
| Stress-test a decision or plan through questioning | `grilling` |
| Set up / maintain the project's doc index | `doc-index` |
| Session handoff | user runs `/handoff` (manual only) |

**Overlap resolution:** "整理个方案" with no draft yet → `writing` (draft it first); an existing plan that needs holes poked → `grilling`; facts to verify before either → `research`. A bug fix with a clear path → `tdd` directly; cause unknown or first fix failed → `diagnosing-bugs`.

## Unconditional Disciplines

These bind even when no skill is loaded — trivial shortcuts do not waive them:

1. **Test-first.** If the project has a test suite, write the failing test before production code; bug fixes ship with a regression test. Exceptions (throwaway prototypes, generated code, pure config) require asking the user first.
2. **Evidence before completion.** No claim of "done/passing/fixed" without a fresh verification run in this turn - tests for code, re-reading for documents, re-checking for numbers. "Should pass" is not evidence.
3. **Review before merge.** Two-axis review (`code-review`) before merging to mainline when any threshold is met: core module touched / diff ≥ 15 files / new engine, API, or data-model contracts.
4. **Persist and register.** Durable deliverables (plans, designs, reviews, research, handoffs) are saved under `docs/` in their type dir AND registered in `docs/文档导航.md` (per `doc-index`). Not done until on disk + in the index; chat-only is not a deliverable.
5. **Honest boundary + red-team.** Completion claims and handoffs carry an explicit 诚实边界 (what was NOT done/verified); before declaring done run a red-team self-check (how could this be wrong?). Full method: `verification-before-completion`.

## Exemptions

- Trivial edits (typos, renames, one-liners) → do directly; disciplines 1-2 still apply where a test suite exists.
- Simple Q&A → answer directly.
- User says "直接做 / don't use skills" → comply, but warn once when a discipline is skipped.

## Precedence

1. Explicit user instruction > this file.
2. Disciplines > exemptions.
3. Ambiguous routing → ask one question, then route.
