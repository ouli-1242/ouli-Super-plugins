---
name: executing-plans
description: Use when a written implementation plan exists and the user wants it executed or resumed - "execute the plan", "把计划做了", "继续做计划", "implement task N of the plan", picking up a plan mid-way. The plan is followed as written; deviations and blockers go back to the user, not improvised. NOT for writing a plan (writing-plans), NOT for direct instructions with no plan document (tdd directly).
---

# Executing Plans

## Overview

Load the plan, review it critically, execute its tasks one at a time, verify, report when complete.

**Announce at start:** "I'm using the executing-plans skill to implement this plan."

## Step 1 — Load and Review the Plan

1. Read the plan file (default location: `docs/superwork/plans/`; the user may pass any path).
2. Check the plan's `**Status:**` line:
   - `draft` → ask the user to approve the plan before executing anything.
   - `approved` → proceed.
   - `completed` → confirm with the user what they want reopened before touching anything.
3. Review the plan critically — a plan is a hypothesis, not a contract. Identify questions or concerns (missing dependencies, stale file references, tasks whose Interfaces no longer match reality).
4. If concerns: raise them with your human partner BEFORE starting.
5. If no concerns: create a todo per plan task and proceed.

## Step 2 — Execute Tasks

For each task, in plan order:

1. Mark it in progress.
2. Read the task in full, including its **Interfaces** block — a task's implementer sees only that task; the Interfaces block is where neighboring task names and types come from. Do not invent names that differ from it.
3. Call the Skill tool with "tdd" and run the task's steps through the red → green loop. Follow the plan's steps exactly — they are already bite-sized.
4. Run each verification the plan specifies and read the output. A step without fresh verification evidence is not done.
5. Check off the task's `- [ ]` boxes in the plan file as steps complete.
6. Commit as the plan's steps direct.

**Resuming mid-plan:** if the session was interrupted, re-derive position from the plan file's checked boxes and git log — never from memory. Re-read the current task before continuing.

**Sub-agent execution:** if the user chose sub-agent execution (see writing-plans' handoff options), dispatch one fresh sub-agent per task with the task text pasted in full, review the result between tasks, and apply this skill's discipline yourself as the orchestrator.

## Step 3 — Finish

When every task is checked off:

1. Update the plan's `**Status:**` line to `completed`.
2. Call the Skill tool three times, in order: first with "code-review" to review the whole change, then with "verification-before-completion" before declaring done, then with "finishing-a-development-branch" to decide how to integrate the work.

## When to Stop and Ask

**STOP executing immediately when:**

- Hit a blocker (missing dependency, test fails, instruction unclear)
- The plan has a critical gap preventing the next task
- You don't understand an instruction
- Verification fails repeatedly

Ask for clarification rather than guessing — a guessed step poisons every step after it.

**Return to Step 1 when:**

- Your human partner updates the plan based on your feedback
- The fundamental approach needs rethinking (in which case the fix is a new plan, not improvisation)

Don't force through blockers. Stop and ask.

## Remember

- Review the plan critically first
- Follow plan steps exactly; the plan is where deviation decisions were already made
- Don't skip verifications
- Reference skills when the plan says to
- Stop when blocked, don't guess
- Never start implementation on main/master without explicit user consent
