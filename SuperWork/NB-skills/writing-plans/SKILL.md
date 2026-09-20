---
name: writing-plans
description: "Use when a design or spec has been approved and needs to be broken into a bite-sized implementation plan, before any code is written. \"拆任务\", \"做个实施计划\". This is the step after brainstorming approves a design. NOT for vague ideas that still need design (brainstorming first), NOT for small single-file tasks that can be implemented directly (tdd)."
---
# Writing Plans

## Purpose

Decompose an approved spec into a plan a context-free engineer can execute task by task, with every step testable and every name pinned.

## When to Use / Not Use

- Use: an approved design/spec needs to become an implementation plan, before any code.
- Do NOT use: ideas that still need design (brainstorming); small single-file tasks implementable directly (tdd).

## Capability Boundary

- CAN: map file structure, size tasks, write the plan document, self-review it against the spec.
- CANNOT: implement anything; write a plan for a design that was never approved.
- Depends on: the approved spec; doc-index (persistence); executing-plans consumes the output.

## Input Contract

- Required: an approved spec (path or conversation of record).
- Optional: existing repo conventions, worktree setup (mention only if the user already has one).
- If the spec is missing or unapproved → stop and route back to brainstorming. If the spec spans multiple independent subsystems → propose one plan per subsystem, each shippable on its own.

## Output Contract

- One plan document at `docs/计划/YYYY-MM-DD-<feature-name>.md`, registered in 文档导航 (create the index via doc-index if missing). User-specified locations override.
- **Plan header (mandatory):** `**Status:** draft` line (→ `approved` on user approval, → `completed` when all boxes are checked — kept greppable as the first content line), then `**Goal:**` (one sentence), `**Architecture:**` (2–3 sentences), `**Tech Stack:**`, `**Spec:**` (path executors read), and a `## Global Constraints` section quoting the spec's project-wide requirements verbatim, one line each.
- **Task skeleton (mandatory per task):** `**Files:**` (create/modify paths), `**Interfaces:**` (consumes from earlier tasks — exact signatures; produces for later tasks — names, param & return types), then checkbox steps: failing test (actual code) → run to see it fail (command + expected failure) → minimal implementation (actual code) → run to see it pass (command + expected pass) → commit (actual git commands).
- Quality bar: each step is one action (2–5 minutes); each task ends in an independently testable deliverable.

## Constraints and Prohibitions

- **No placeholders — these are plan failures:** "TBD"/"TODO"/"implement later"; "add appropriate error handling"; "write tests for the above" without test code; "similar to Task N" (repeat the code — tasks may be read out of order); references to types/functions not defined in any task.
- Fold setup/config/scaffolding into the task whose deliverable needs them; split tasks only where a reviewer could reject one while approving its neighbor.
- DRY, YAGNI, TDD, frequent commits; follow established repo file-size patterns — do not unilaterally restructure, but folding in a justified split is reasonable.
- Prohibited: writing the plan before the spec is approved; describing what to do without showing how.

## Acceptance Criteria

Self-review the finished plan against the spec, fix inline, then confirm:
1. **Spec coverage** — every spec requirement maps to a task; gaps listed and closed.
2. **Placeholder scan** — none of the prohibited patterns remain.
3. **Type consistency** — signatures/property names match across tasks (`clearLayers()` in Task 3 vs `clearFullLayers()` in Task 7 is a bug).

## Failure and Escalation

- Spec unapproved or missing → stop, back to brainstorming.
- Spec covers multiple subsystems → propose splitting; ask if unclear.
- A requirement cannot be turned into testable steps → surface the gap to the user instead of inventing scope.

## Cost and Latency Budget

- File-structure mapping before tasks; plan written in one pass, then one self-review cycle. Exploration ≤ 10 tool calls; no implementation of any kind.

## Examples

- Positive: Task 5 consumes `parseConfig(): Result<Config>` exactly as Task 3's Interfaces block produced it; every step shows real code.
- Negative: "Step 2: implement the parser (see Task 3)" — placeholders shift the thinking to the executor.
- Edge: a spec requirement with no natural test → still gets a task with a verifiable check, or the gap goes back to the user.

## Evaluation and Observability

- Metrics: executor questions per plan (target: few), placeholder occurrences (target: 0), spec-coverage gaps at execution time.
- Log: coverage gaps and deviations discovered during execution go to `docs/日志/` and feed back into the next plan.

## References (L2, load on demand)

- Worked task example with real code: `references/task-example.md`
