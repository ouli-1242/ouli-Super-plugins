---
name: writing-skills
description: Use when creating a new skill, editing an existing skill, or verifying a skill works before deployment - "加个 skill", "写个 skill", "改一下这个 skill 的触发", "optimize the description". Applies TDD to skill documents - test the trigger first, then write. NOT for writing project docs, READMEs, or prompt templates for one-off use.
---

# Writing Skills

## Overview

**Writing skills IS Test-Driven Development applied to process documentation.**

You write test cases (pressure scenarios), watch them fail (baseline behavior without the skill), write the skill, watch tests pass, and refactor to close loopholes.

**Core principle:** If you didn't watch an agent fail without the skill, you don't know if the skill teaches the right thing.

**Background:** the red → green → refactor cycle is defined by the `tdd` skill — call the Skill tool with "tdd" if the cycle itself is unclear.

## What a Skill Is

A **skill** is a reference guide for proven techniques, patterns, or tools that future agents can find and apply.

- **Are:** reusable techniques, patterns, reference guides
- **Are NOT:** narratives about how you solved something once

**Create when:** the technique wasn't obvious, you'd reuse it across projects, it applies broadly.
**Don't create for:** one-offs, standard practices documented elsewhere, project-specific conventions (those go in the project's instructions), mechanical constraints (automate with validation instead — save documentation for judgment calls).

## The Iron Law

```
NO SKILL WITHOUT A FAILING TEST FIRST
```

This applies to NEW skills AND EDITS to existing skills. Write a skill before testing it? Delete it and start over. Edit without testing? Same violation. "Simple additions" and "just a section" are not exceptions — they're rationalizations.

## The Description Is the Product (SDO)

Agents see only `name + description` until they load the skill. The description IS the discovery mechanism.

### 1. Triggering conditions only — NEVER summarize the workflow

**Critical:** when a description summarizes the skill's workflow, agents follow the description instead of reading the skill body. A description saying "code review between tasks" made an agent do ONE review even though the skill's flowchart required TWO. Changing it to pure triggering conditions fixed it. A workflow summary is a shortcut that makes the body documentation agents skip.

```yaml
# BAD: summarizes workflow — agents follow this instead of reading
description: Use when executing plans - dispatches subagent per task with code review between tasks

# GOOD: triggering conditions only
description: Use when executing implementation plans with independent tasks
```

### 2. Description rules

- Start with "Use when..." (or "Use BEFORE..."); third person
- Concrete triggers, symptoms, situations — describe the *problem*, not language-specific symptoms unless the skill is language-specific
- Include Chinese trigger phrases for Chinese-language users (SuperWork convention)
- Negative exclusions: name the neighboring skill that handles the cases you DON'T want ("NOT for bug reports (use diagnosing-bugs)")
- `name`: verb-first, hyphens only (`executing-plans`, not `plan-execution`)
- Frontmatter ≤ 1024 characters; body ≤ 8 KB (hard truncation on some harnesses — push depth into `references/`)

### 3. Token efficiency

Skills load into conversations on demand — every token counts. Target < 500 words for the body; cross-reference neighboring skills instead of repeating them (`Call the Skill tool with "tdd"`, never force-loading `@`-links).

## Match the Form to the Failure

Before writing guidance, classify the baseline failure — the form that bulletproofs one failure type measurably backfires on another:

| Baseline failure | Right form | Wrong form |
|---|---|---|
| Skips a rule under pressure (knows better, does it anyway) | Prohibition + rationalization table + red flags | Soft guidance ("prefer...", "consider...") |
| Output has the wrong shape (bloated, buried verdict) | Positive recipe: state what the output IS, its parts in order | Prohibition list ("don't restate", "never narrate") |
| Omits a required element | Structural: REQUIRED slot in the template they fill | Prose reminders near the template |
| Behavior should depend on a condition | Conditional on an observable predicate ("if the brief exists, reference it") | Unconditional rule + exemption clauses |

**Rules for whichever form:** no nuance clauses ("don't X unless it matters" reopens negotiation); exemption clauses don't scope — restructure instead.

**SuperWork application:** this is why the lifecycle skills use HARD-GATE + red-flag tables (discipline failures) while writing-plans uses a full template with REQUIRED slots (shaping failures).

## Bulletproofing Discipline Skills

Skills that enforce discipline must resist rationalization. Agents find loopholes under pressure.

- **Close every loophole explicitly** — state the rule, then forbid the specific workarounds ("Delete means delete — don't keep it as reference, don't adapt it")
- **Cut off spirit-vs-letter arguments** — "Violating the letter of this rule is violating the spirit of this rule" early in the skill
- **Build a rationalization table** — every excuse observed in baseline testing goes in, with its counter
- **Add a red-flags list** — make self-checking easy ("All of these mean: stop and start over")

## RED-GREEN-REFACTOR for Skills

**RED — baseline:** run the pressure scenario WITHOUT the skill (fresh sub-agent or fresh conversation). Document verbatim what the agent does and the exact rationalizations it uses. If the no-guidance control doesn't fail, there is nothing to fix — stop, don't write the skill.

**GREEN — minimal skill:** write only what addresses the observed failures. Don't add content for hypothetical cases. Re-run the same scenario; the agent should now comply.

**REFACTOR — close loopholes:** new rationalization observed → add the counter → re-test. Iterate until stable.

**Micro-test wording first:** full scenarios are slow. Before running them, test the wording itself — 5+ fresh-context samples per variant against a no-guidance control, reading every sample manually. If five samples give five different interpretations, the wording isn't binding; tighten it.

**Test by skill type:** discipline skills → pressure scenarios (combined time/sunk-cost/exhaustion pressures). Technique skills → application + variation scenarios. Reference skills → retrieval scenarios (can they find and apply the right info?).

## Common Rationalizations

| Excuse | Reality |
|--------|---------|
| "Skill is obviously clear" | Clear to you ≠ clear to other agents. Test it. |
| "Testing is overkill" | Untested skills have issues. Always. |
| "I'll test if problems emerge" | Problems = agents can't use the skill. Test BEFORE deploying. |
| "Academic review is enough" | Reading ≠ using. Test application scenarios. |
| "No time to test" | Deploying untested wastes more time later. |

## Checklist

- [ ] Baseline observed failing WITHOUT the skill (RED)
- [ ] Description: triggering conditions only, no workflow summary
- [ ] Description: "Use when..." + Chinese triggers + negative exclusions to neighbors
- [ ] Name: verb-first, hyphens only
- [ ] Form matches failure type (prohibition vs recipe vs structure vs conditional)
- [ ] Body ≤ 8 KB; depth pushed to `references/`
- [ ] Cross-references use Skill tool calls, not `@`-links
- [ ] Verified WITH the skill (GREEN); loopholes closed (REFACTOR)
- [ ] Skill registered in every plugin manifest (`plugin.json` × 3, marketplace.json) and the `superwork` router's route table if it owns a lifecycle stage
- [ ] Run `scripts/validate.ps1` before committing

## STOP After Each Skill

Do not batch-create skills without testing each. Deploying untested skills = deploying untested code.
