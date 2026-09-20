---
name: grilling
description: "Use when the user wants their plan, decision, or idea stress-tested through relentless questioning - \"帮我挑刺\", \"这个方案行不行\" open the full interview; casual settle-it asks (\"该选哪个\", \"值不值\", \"帮我参谋\") get a recommendation first, interview optional. Rounds continue until no assumption is left silently standing. NOT for gathering requirements for work that doesn't exist yet - just ask directly in that case."
---
# Grilling

## Purpose

Stress-test a plan or decision through rounds of questioning until no assumption survives silently — with a fast lane for casual decisions.

## When to Use / Not Use

- Use: the user wants their plan, decision, or idea pressure-tested.
- Do NOT use: gathering requirements for work that doesn't exist yet — just ask directly in that case.

## Capability Boundary

- CAN: build the decision tree, work the frontier in rounds, dispatch fact-finding, give a recommendation-first answer for casual decisions.
- CANNOT: act on conclusions before the user confirms shared understanding; open an interrogation for a casual ask.
- Depends on: a sub-agent/background tool for fact-finding (optional but preferred).

## Input Contract

- Required: the plan/decision/idea to be stress-tested.
- Optional: known constraints.
- Missing behavior: too formless to interrogate → say so and ask directly instead.

## Output Contract

- **Casual decisions** (该选哪个 / 值不值 / 帮我参谋): a recommendation with reasons FIRST, in one message — then offer the full interview if the user wants it.
- **Full interview**: question rounds covering the whole frontier —
  `❓ **Q<n> — <title>**: <body, may offer choices>` followed by `➡️ <recommended answer>` —
  terminating only when the frontier is empty AND the user confirms shared understanding. No action before that confirmation.

## Constraints and Prohibitions

- **A casual ask that ends in an interrogation is a failed route** even when the route was correct — recommend first, interview only on request.
- Work a **design tree**: every decision branches into the decisions hanging off it. The **frontier** = every decision whose prerequisites are settled — ask it whole in one round, then WAIT for the answers before recomputing.
- A question depending on another question still open in this round belongs to a later round.
- **Facts are your job; decisions are the user's.** Environmental facts get a sub-agent dispatch — never ask the user what you could look up. Don't block the round on it: only downstream questions wait.
- The user's answers reshape the tree: settled decisions push the frontier outward.
- Prohibited: acting on conclusions without the confirmation; asking the user for look-up-able facts; front-loading questions whose prerequisites are unsettled.

## Acceptance Criteria

- Casual ask → recommendation first; full interview → ends only with an empty frontier AND the user's confirmation.
- Self-check: is any surviving assumption unstated? Did a round contain a question with unsettled prerequisites?

## Failure and Escalation

- User disengages mid-interview → record the open frontier and stop; do not proceed on partial answers.
- Facts contradict the plan → surface the contradiction as a frontier question.
- The decision turns out to be already made → stop; there is nothing to test.

## Cost and Latency Budget

- Casual: one message. Interview: rounds continue while the frontier is non-empty; fact-finding dispatches run in parallel. Over budget: deliver the remaining frontier and stop.

## Examples

- Positive: "该选哪个" → recommendation + three reasons in one message → user asks "再帮我把把关" → the full interview opens.
- Negative: a one-line price question answered with a five-question intake form.
- Edge: mid-interview the user reveals a settled constraint → tree reshaped; downstream questions unblocked next round.

## Evaluation and Observability

- Metrics: silently-assumed items discovered after the interview (target 0), interrogations opened on casual asks (target 0), fact-questions wrongly asked of the user.
- Log: the final shared understanding stays in chat (daily lane) or the project docs (project mode).
