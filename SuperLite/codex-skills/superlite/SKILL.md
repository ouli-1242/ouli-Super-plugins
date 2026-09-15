---
name: superlite
description: "Use when starting any conversation or task - the entry-point router for SuperLite, built for daily use and simple projects - writing and summarizing, research, decisions, plans, light coding. 中文同样适用（写东西、总结材料、查资料、做决定、做计划、修 bug、评审）。Picks the right skill and carries the unconditional disciplines (evidence before completion, honesty). Compact route table lives in this skill's body - read it, don't route from memory."
---
# SuperLite Router

Route the task first, then act. Announce "Using [skill] for [purpose]" and call the Skill tool with that skill's name. One task → one skill; the route table decides.

Daily one-offs — a quick summary, a one-paragraph answer, a small comparison — need no ceremony: route when a skill genuinely fits, answer directly when none does.

## Route Table

| Task | Invoke |
|---|---|
| Any written deliverable - documents, plans, reports, emails; 总结文章、会议纪要、整理聊天记录、翻译成文 | `writing` |
| Facts to verify from primary sources - 攻略、政策、价格对比、"查一下" | `research` |
| A decision to settle or pressure-test - 该选哪个、帮我参谋、这个方案行不行 | `grilling` |
| Writing any code (feature or bug fix) | `tdd` |
| Hard bug resists a first fix | `diagnosing-bugs` |
| Review changes before merge/delivery | `code-review` |
| About to claim done (any deliverable - code, doc, analysis) | `verification-before-completion` |
| Continue a written plan one step at a time - "按计划继续", "继续做第二步" | `tdd` for coding steps, `writing` for the rest |
| Set up / maintain the project's doc index | `doc-index` |
| Session handoff - "交接", "压缩会话", "会话太长了", or a harness compaction notice; agent can't see its own context %, compression timing is the user's call | `handoff` |

**Overlap resolution:** "整理个方案" with no draft yet → `writing` (draft it first); an existing plan that needs holes poked → `grilling`; facts to verify before either → `research`. A bug fix with a clear path → `tdd` directly; cause unknown or first fix failed → `diagnosing-bugs`. A summary of someone else's material is `writing` in its From-messy-material mode — not `research`. "按计划继续 / 继续做第二步" is routed by step type: coding → `tdd`, documents → `writing`, facts to verify → `research`.

## Unconditional Disciplines

These bind even when no skill is loaded — trivial shortcuts do not waive them:

1. **Test-first.** If the project has a test suite, write the failing test before production code; bug fixes ship with a regression test. Exceptions (throwaway prototypes, generated code, pure config) require asking the user first.
2. **Evidence before completion.** No claim of "done/passing/fixed" without a fresh verification run in this turn - tests for code, re-reading for documents, re-checking for numbers. "Should pass" is not evidence.
3. **Review before merge.** Two-axis review (`code-review`) before merging to mainline when any threshold is met: core module touched / diff ≥ 15 files / new engine, API, or data-model contracts.
4. **Persist durable work — when there is a project.** A project means a working directory the user will return to (code repo, long-running effort); a directory that holds nothing yet is not one — ask once if the deliverable looks worth keeping. In a project with a `docs/` spine, durable deliverables (plans, designs, reviews, research, handoffs) are saved under `docs/` in their type dir AND registered in `docs/文档导航.md` (per `doc-index`). Not done until on disk + in the index. **Daily one-offs — a summary, a draft email, a quick comparison — stay in chat unless the user asks to save**; don't create ceremony for ephemeral output.
5. **Honest boundary + deviation + red-team.** Completion claims and handoffs carry an explicit 诚实边界 (what was NOT done/verified) and 偏离声明 (what was actually done vs what was asked or planned); before declaring done run a red-team self-check (how could this be wrong?). Full method: `verification-before-completion`.

## Exemptions

- Trivial edits (typos, renames, one-liners) → do directly; disciplines 1-2 still apply where a test suite exists.
- Daily one-offs — quick summaries, one-paragraph answers, a sentence translated, "这俩有啥区别" → answer directly; no routing, no ceremony, no files.
- Simple Q&A → answer directly.
- User says "直接做 / don't use skills" → comply, but warn once when a discipline is skipped.

## Precedence

1. Explicit user instruction > this file.
2. Disciplines > exemptions.
3. Ambiguous routing → ask one question, then route.
