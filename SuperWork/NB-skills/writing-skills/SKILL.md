---
name: writing-skills
description: "Use when creating a new skill, editing an existing skill, verifying a skill works before deployment, or the user explicitly requests a session retrospective - \"加个 skill\", \"写个 skill\", \"改一下这个 skill 的触发\", \"优化 description\", \"复盘这次会话\". NOT for postmorteming a bug (diagnosing-bugs) or re-reviewing a diff (code-review), NOT for writing project docs, READMEs, or prompt templates for one-off use."
---
# Writing Skills

## Purpose

Apply test-driven development to process documentation: observe the failure, write the minimal skill that fixes it, close the loopholes — one tested skill at a time.

## When to Use / Not Use

- Use: creating or editing any skill; verifying a skill before deployment; session retrospective (explicit request only — Retro Mode).
- Do NOT use: bug postmortems (diagnosing-bugs); diff re-reviews (code-review); project docs/READMEs; one-off prompt templates.

## Capability Boundary

- CAN: run baselines, write skill text in the right form, bulletproof against rationalization, micro-test wording, register the skill.
- CANNOT: write or edit a skill without a failing baseline; batch-create untested skills.
- Depends on: fresh sub-agent or fresh conversation for baselines; this pack's constraints (frontmatter = name + description only; single H1; body ≤ 8 KB; description ≤ 1024 chars with Chinese trigger anchors).

## Input Contract

- Required: the skill idea/defect to fix, or the retro request.
- Optional: neighboring skills for exclusion wording.
- Missing behavior: no observed failure to fix → do not write the skill (a no-failure control means there is nothing to teach).

## Output Contract

- A skill (new or edited) that changes the failing behavior, with:
  - **Description (SDO)**: triggering conditions only — never a workflow summary; opens "Use when/BEFORE..."; concrete triggers with the user's actual speech as exemplars (Chinese primary + code-switched tech terms; 1 exclusive anchor word + 2–3 short phrases); negative exclusions naming the neighboring skill; frontmatter ≤ 1024 chars.
  - **Body** in the form the failure type demands (see below), ≤ 8 KB, depth pushed into `references/`.
  - Registration: lifecycle-stage skills are added to the `superwork` router's capability index.

## Constraints and Prohibitions

```
THE IRON LAW
NO SKILL WITHOUT A FAILING TEST FIRST
```
Applies to NEW skills AND EDITS. No baseline, no skill. "Simple additions" and "just a section" are rationalizations.

- **Create when**: the technique wasn't obvious, is reusable across projects, applies broadly. **Don't create for**: one-offs, standards documented elsewhere, project conventions (project instructions), mechanical constraints (automate with validation instead).
- **Form follows the baseline failure type** — the right form for one failure measurably backfires on another:
  | Baseline failure | Right form | Wrong form |
  |---|---|---|
  | Skips a rule under pressure | Prohibition + rationalization table + red flags | Soft "prefer/consider" guidance |
  | Output has the wrong shape | Positive recipe stating what the output IS | Prohibition list |
  | Omits a required element | REQUIRED slot in a template | Prose reminders |
  | Behavior should be conditional | Condition on an observable predicate | Unconditional rule + exemptions |
  No nuance clauses ("don't X unless it matters" reopens negotiation); exemption clauses don't scope — restructure instead.
- **Bulletproofing**: close every loophole explicitly; cut off spirit-vs-letter arguments early ("violating the letter is violating the spirit"); every baseline-observed excuse gets a counter; add a red-flags list for self-checking.
- **Micro-test wording first**: 5+ fresh-context samples per variant against a no-guidance control; five different interpretations = the wording isn't binding — tighten it. Then test by skill type: discipline skills → pressure scenarios; technique skills → application + variation; reference skills → retrieval.
- **Retro Mode** (explicit request only): improves the agent's environment for future runs, not the code; approved changes are implemented as skill/AGENTS.md edits — the Iron Law applies to them too.
- Prohibited: deploying untested skills; `@`-link force-loading instead of cross-references by name.

## Acceptance Criteria

- Baseline observed failing WITHOUT the skill (RED); behavior compliant WITH it (GREEN); observed loopholes closed (REFACTOR); frontmatter/H1/size constraints pass.
- Self-check: does the description summarize workflow anywhere (a defect)? Did I stop after each skill?

## Failure and Escalation

- Control scenario doesn't fail → stop; there is nothing to fix.
- Skill fails under new pressure → add the counter, re-test (that's REFACTOR, not a rewrite).
- Conflicts with a neighboring skill's scope → resolve exclusions in both descriptions or escalate to the user.

## Cost and Latency Budget

- One skill per test cycle; STOP after each. Micro-tests before full scenarios. Over budget: deliver the baseline findings and the draft skill without deploying.

## Examples

- Positive: baseline shows the agent does ONE review where the flow needs TWO → the description is rewritten to triggers only; the workflow stays in the body.
- Negative: "Add appropriate error handling" in a plan template — the exact placeholder class the skill exists to kill.
- Edge: retro reveals a recurring env annoyance → fix lands as an AGENTS.md line or skill edit, through this skill's own discipline.

## Evaluation and Observability

- Metrics: skills deployed without baseline (target 0), description-trigger hit/miss rates, loophole re-openings after deployment.
- Log: baseline transcripts (redacted) kept alongside the skill's development; failures feed `references/rationalizations.md`.

## References (L2, load on demand)

- SDO description BAD/GOOD example: `references/sdo-example.md`
- Agent-doc writing rules: `references/agent-docs.md`
- Rationalization counters: `references/rationalizations.md`
- Retro Mode process + checklist: `references/retro.md`
