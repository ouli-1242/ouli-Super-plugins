---
name: writing-plans
description: Use when a design or spec has been approved and needs to be broken into a bite-sized implementation plan, before any code is written. "拆任务", "做个实施计划", "write the implementation plan", "how should we implement this". This is the step after brainstorming approves a design. NOT for vague ideas that still need design (brainstorming first), NOT for small single-file tasks that can be implemented directly (tdd).
---

# Writing Plans

## Overview

Write comprehensive implementation plans assuming the engineer has zero context for our codebase and questionable taste. Document everything they need to know: which files to touch for each task, code, testing, docs they might need to check, how to test it. Give them the whole plan as bite-sized tasks. DRY. YAGNI. TDD. Frequent commits.

Assume they are a skilled developer, but know almost nothing about our toolset or problem domain. Assume they don't know good test design very well.

**Announce at start:** "I'm using the writing-plans skill to create the implementation plan."

**Context:** If working in an isolated worktree (SuperWork does not manage worktrees; only mention this when the user already has one set up).

**Save plans to:** `docs/计划/YYYY-MM-DD-<feature-name>.md` — and register it in 文档导航 (per doc-index). If `docs/文档导航.md` is missing, create it via the doc-index skill first.
- (User preferences for plan location override this default)

## Scope Check

If the spec covers multiple independent subsystems, it should have been broken into sub-project specs during brainstorming. If it wasn't, suggest breaking this into separate plans — one per subsystem. Each plan should produce working, testable software on its own.

## File Structure

Before defining tasks, map out which files will be created or modified and what each one is responsible for. This is where decomposition decisions get locked in.

- Design units with clear boundaries and well-defined interfaces. Each file should have one clear responsibility.
- You reason best about code you can hold in context at once, and your edits are more reliable when files are focused. Prefer smaller, focused files over large ones that do too much.
- Files that change together should live together. Split by responsibility, not by technical layer.
- In existing codebases, follow established patterns. If the codebase uses large files, don't unilaterally restructure - but if a file you're modifying has grown unwieldy, including a split in the plan is reasonable.

This structure informs the task decomposition. Each task should produce self-contained changes that make sense independently.

## Task Right-Sizing

A task is the smallest unit that carries its own test cycle and is worth a fresh reviewer's gate. When drawing task boundaries: fold setup, configuration, scaffolding, and documentation steps into the task whose deliverable needs them; split only where a reviewer could meaningfully reject one task while approving its neighbor. Each task ends with an independently testable deliverable.

## Bite-Sized Task Granularity

**Each step is one action (2-5 minutes):** "Write the failing test" / "Run it to see it fail" / "Implement minimal code" / "Run tests to see them pass" / "Commit".

## Plan Document Header

**Every plan MUST start with this header:**

```markdown
# [Feature Name] Implementation Plan

> **Status:** draft — set to `approved` once the user approves the plan, and
> `completed` once every task below is checked off. Keep it as the first
> content line under the title so it stays greppable (`grep -l "Status: completed" docs/计划/`).

> Steps use checkbox (`- [ ]`) syntax for tracking; check each box off as it completes.

**Goal:** [One sentence describing what this builds]
**Architecture:** [2-3 sentences about approach]
**Tech Stack:** [Key technologies/libraries]
**Spec:** [path to the spec/design doc this plan implements — executors read both]

## Global Constraints

[The spec's project-wide requirements — version floors, dependency limits, naming/copy rules, platform requirements — one line each, verbatim from the spec. Every task implicitly includes this section.]

---
```

## Task Structure

Each task follows this skeleton (full worked example with real code: `references/task-example.md`):

````markdown
### Task N: [Component Name]

**Files:** Create / Modify (path:lines) / Test paths.
**Interfaces:** Consumes (from earlier tasks — exact signatures) · Produces (what later tasks rely on — names, param & return types; an implementer sees only their own task, so this is how they learn neighboring names/types).

- [ ] **Step 1: Write the failing test** — actual test code
- [ ] **Step 2: Run test to verify it fails** — command + expected failure
- [ ] **Step 3: Write minimal implementation** — actual code
- [ ] **Step 4: Run test to verify it passes** — command + expected pass
- [ ] **Step 5: Commit** — actual git commands
````

Steps are one action (2-5 min) each; every code step shows actual code — no placeholders.

## No Placeholders

Every step must contain the actual content an engineer needs. These are **plan failures** — never write them:
- "TBD", "TODO", "implement later", "fill in details"
- "Add appropriate error handling" / "add validation" / "handle edge cases"
- "Write tests for the above" (without actual test code)
- "Similar to Task N" (repeat the code — the engineer may be reading tasks out of order)
- Steps that describe what to do without showing how (code blocks required for code steps)
- References to types, functions, or methods not defined in any task

## Self-Review

After writing the complete plan, look at the spec with fresh eyes and check the plan against it (a self-checklist, not a subagent dispatch):

1. **Spec coverage:** can you point to a task for each spec requirement? List gaps.
2. **Placeholder scan:** any of the "No Placeholders" patterns above? Fix them.
3. **Type consistency:** do types/signatures/property names in later tasks match earlier ones? `clearLayers()` in Task 3 but `clearFullLayers()` in Task 7 is a bug.

Fix issues inline; no re-review. If a spec requirement has no task, add it.

## Execution Handoff

After saving the plan, offer execution choice:

**"Plan complete and saved to `docs/计划/<filename>.md`. Two execution options:**

**1. Inline Execution (recommended)** - Execute the tasks here in this session, one at a time, checking off each `- [ ]` box as it completes, pausing at checkpoints for your review. When every task is checked off, update the plan's `Status:` line to `completed`.

**2. Sub-agent Execution** - If the environment has a sub-agent tool (e.g. opencode's Task tool), dispatch a fresh sub-agent per task for isolated context, reviewing between tasks.

**Which approach?"**

Either way, call the Skill tool with "executing-plans" — it is the execution discipline for both modes (per-task red-green loop, check-off cadence, stop-at-blocker rules, finish sequence).

## Execution Notes

- Each task is implemented through the red-green loop the plan's steps already encode; `executing-plans` calls `tdd` per task at execution time.
- After the last task, the execution skill calls the Skill tool three times — "code-review", then "verification-before-completion", then "finishing-a-development-branch" — and writes a `docs/日志/` entry (per executing-plans' finish step).
