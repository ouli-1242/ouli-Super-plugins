---
name: grilling
description: "Use when the user wants their plan, decision, or idea stress-tested through relentless questioning - \"帮我挑刺\", \"这个方案行不行\". Interviews in rounds until no assumption is left silently standing. NOT for gathering requirements for new work whose design doesn't exist yet (brainstorming first). When the user explicitly asks for the documented variant (\"grill-with-docs\", \"/grill-with-docs\", \"追问并落盘 ADR\"), use this skill's With-Docs Mode."
---
# Grilling

## Purpose

Stress-test a plan or decision through rounds of questioning until no assumption survives silently — then stop until the user confirms shared understanding.

## When to Use / Not Use

- Use: the user wants their plan, decision, or idea pressure-tested (「帮我挑刺」「这个方案行不行」).
- Do NOT use: gathering requirements for work whose design doesn't exist yet (brainstorming).

## Capability Boundary

- CAN: build the decision tree, work the frontier in rounds, dispatch fact-finding, format questions with recommendations.
- CANNOT: act on conclusions before the user confirms shared understanding; self-enable With-Docs Mode.
- Depends on: a sub-agent/background tool for fact-finding (optional but preferred).

## Input Contract

- Required: the plan/decision/idea to be stress-tested.
- Optional: known constraints, prior decisions (`决策记录.md`).
- Missing behavior: the subject is too formless to interrogate → say so and route to brainstorming.

## Output Contract

- Question rounds, each covering the whole frontier:
  `❓ **Q<n> — <title>**: <body, may offer choices>` followed by `➡️ <recommended answer>`.
- Termination: the frontier is empty — every branch visited, nothing silently assumed — and the user has confirmed the shared understanding. No action before that confirmation.

## Constraints and Prohibitions

- Work a **design tree**: every decision branches into the decisions hanging off it. The **frontier** = every decision whose prerequisites are already settled — ask the whole frontier in one round, then WAIT for the answers before recomputing.
- A question depending on another question still open in this round belongs to a later round, not this one.
- **Facts are your job; decisions are the user's.** A frontier question needing an environmental fact gets a sub-agent dispatch — never ask the user what you could look up. Don't block the round on it: only questions downstream of the running exploration wait.
- The user's answers reshape the tree: settled decisions push the frontier outward.
- **With-Docs Mode** (explicit request only — user names "grill-with-docs", "/grill-with-docs", or asks for docs alongside the interview): also invoke domain-modeling and capture terminology/decisions (`技术依据.md` glossary + `决策记录.md`) as they crystallise. Never enable on an ordinary grill request — the doc side effects require the explicit ask.
- Prohibited: acting on conclusions without the confirmation; asking the user for look-up-able facts; front-loading questions whose prerequisites are unsettled.

## Acceptance Criteria

- The interview ends only with an empty frontier AND the user's confirmation.
- Self-check: is any surviving assumption unstated? Did any round contain a question whose prerequisites were still open?

## Failure and Escalation

- User disengages mid-interview → record the open frontier and stop; do not proceed on partial answers.
- Facts contradict the plan → surface the contradiction as a frontier question.
- The decision under grilling turns out to be already made → stop; there is nothing to test.

## Cost and Latency Budget

- Rounds continue while the frontier is non-empty; each round is one message. Fact-finding dispatches run in parallel with the round. Over budget: deliver the remaining frontier and stop.

## Examples

- Positive: round 1 asks Q1–Q4 (all prerequisites settled) with recommended answers; user's Q2 answer unblocks Q5–Q7 for round 2.
- Negative: asking "what database?" before "is this multi-tenant?" is answered — prerequisite unsettled, wrong round.
- Edge: user says "grill-with-docs" → With-Docs Mode: same rounds, plus glossary/ADR capture via domain-modeling.

## Evaluation and Observability

- Metrics: silently-assumed items discovered after the interview (target 0), rounds to empty frontier, fact-questions wrongly asked of the user.
- Log: the final shared understanding (and With-Docs artifacts) into the docs per their owning skills.
