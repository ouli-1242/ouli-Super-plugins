---
name: executing-plans
description: "Use when a written implementation plan exists and the user wants it executed or resumed - \"把计划做了\", \"继续做计划\", \"执行计划到第几步\", picking up a plan mid-way. The plan is followed as written; deviations and blockers go back to the user, not improvised. NOT for writing a plan (writing-plans), NOT for direct instructions with no plan document (tdd directly)."
---
# Executing Plans

## Purpose

Execute an approved plan task by task with fresh verification per step, restoring progress from disk after any interruption — never improvising around the plan.

## When to Use / Not Use

- Use: a written plan exists and the user wants it executed or resumed mid-way.
- Do NOT use: writing a plan (writing-plans); direct instructions with no plan document (tdd).

## Capability Boundary

- CAN: gate on the plan's status, review it critically, execute tasks through the red-green loop, check off boxes, resume from disk, write the completion log.
- CANNOT: redesign the plan mid-flight; skip verifications; force through blockers.
- Depends on: the plan document; tdd per task; code-review + verification-before-completion + finishing-a-development-branch at the finish; doc-index.

## Input Contract

- Required: the plan file path (default location `docs/计划/`).
- Optional: user's pointer to a specific task/step.
- Missing behavior: no plan on disk → this skill does not apply; route to tdd or writing-plans.

## Output Contract

- All of the plan's checkboxes checked, `**Status:**` updated to `completed`, and one work log at `docs/日志/YYYY-MM-DD-<主题>.md` with exactly these sections in order: 今日做了什么（含提交 SHA）/ 证据（测试命令 + 新鲜输出）/ 偏离声明（实际与计划不符处）/ 诚实边界（未做、未验证、受阻项）— registered in 文档导航.

## Constraints and Prohibitions

- **Status line gates execution**: `draft` → get approval before executing anything; `approved` → proceed; `completed` → confirm with the user what to reopen before touching anything.
- Review the plan critically first — a plan is a hypothesis, not a contract. Raise concerns BEFORE starting.
- Read each task's **Interfaces** block and use those exact names; a task's implementer sees only that task. Never invent names that differ from it.
- Follow the plan's steps exactly — deviation decisions were already made in the plan. A step without fresh verification evidence is not done.
- **Resume from disk only**: position = plan's checked boxes + git log. Never from memory. Re-read the current task before continuing.
- Prohibited: implementing on main/master without explicit user consent; batch-checking boxes without running the verifications.

## Acceptance Criteria

- Every task checked off with fresh verification evidence; plan status `completed`; log written and registered.
- Self-check: does every ✓ correspond to a command I ran this session? Does the log's 诚实边界 name what I did not verify?

## Failure and Escalation

- Blocker (missing dependency, failing test, unclear instruction) → STOP, ask; a guessed step poisons every step after it.
- Critical plan gap → stop and surface; the fix is a revised plan, not improvisation.
- Verification fails repeatedly → stop and report with evidence.
- Approach fundamentally wrong → back to the user for a new plan.

## Cost and Latency Budget

- One task in flight at a time; verification commands per the plan only (no extra sweeps mid-task). Sub-agent mode: one fresh sub-agent per task, reviewed between tasks. Over budget: finish the current task, report state, ask.

## Examples

- Positive: plan task says "run `npm test` and see 5 passing" — the box gets checked only after that output is read.
- Negative: session interrupted → "reconstructing" progress from memory instead of the plan file + git log.
- Edge: plan step's Interfaces reference no longer matches the code → stop and raise; do not silently adapt.

## Evaluation and Observability

- Metrics: deviations per plan, blocker escalations, boxes checked without evidence (target 0).
- Log: the required work log IS the observability record; deviations feed back to writing-plans.
