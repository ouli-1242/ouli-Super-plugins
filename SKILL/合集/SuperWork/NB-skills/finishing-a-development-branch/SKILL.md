---
name: finishing-a-development-branch
description: "Use when implementation is complete and tests pass, to decide how to integrate the work - \"合并分支\", \"提个 PR\", \"收尾这个分支\". The integration choice (merge / PR / keep) belongs to the user; branch deletion requires typed confirmation. NOT before tests pass (verification-before-completion first), NOT for reviewing the code itself (code-review first), NOT while merge conflicts are unresolved (resolving-merge-conflicts)."
---
# Finishing a Development Branch

## Purpose

Turn a finished, verified branch into an integration decision owned by the user — merge, PR, or keep — and never lose work.

## When to Use / Not Use

- Use: implementation complete and the full suite passes; the user asks how to wrap up the branch.
- Do NOT use: before tests pass (verification-before-completion); reviewing the code (code-review); while conflicts are unresolved (resolving-merge-conflicts).

## Capability Boundary

- CAN: run the full suite, confirm the base branch, present the integration menu, execute the chosen option, clean up the branch.
- CANNOT: choose an integration option for the user; discard work without a typed confirmation.
- Depends on: git; the forge's PR tooling (its CLI or the creation URL it prints on push); the project's full test command.

## Input Contract

- Required: the feature branch to integrate.
- Optional: the intended base branch (from the plan, conversation, or branch upstream).
- Missing behavior: base branch unknown → state your best guess and ask ("this branch split from <guess> — correct?") BEFORE merging. Wrong-base merges are expensive to undo.

## Output Contract

- The chosen option executed: **Merge locally** (checkout base → pull → merge → full suite on the merged result → `git branch -d <feature>` once green) or **Push + PR** (`git push -u origin <feature>` → PR against the base, following the repo's PR template → report the URL) or **Keep as-is** ("Keeping branch <name>.").

## Constraints and Prohibitions

- The menu comes only after a green full-suite run on THIS tree; failures → show them and stop.
- Present the menu exactly as written, every option, and wait:
  `1. Merge back to <base> locally / 2. Push and create a Pull Request / 3. Keep the branch as-is`
- **Discard path exists only on an explicit user request to throw the work away**, and requires the exact typed word `discard` after showing what will be permanently deleted (branch + commit list). "Yeah, get rid of it" is not the confirmation. Discard executes `git branch -D`.
- Merged result fails tests → stop everything, branch stays in place, investigate; nothing has been pushed, the merge is local and recoverable.
- Merge hits conflicts → resolving-merge-conflicts owns them (both intents, never invent behavior, never `--abort`); resume this skill's remaining steps after.
- **Rationalizations kill the rule** — the observed excuses, failure patterns and their counters: `references/rationalizations.md`.
- Prohibited: force-push without the user's explicit request (a rejected push means the remote moved — investigate first); worktree cleanup beyond the branch (belongs to whatever created the worktree).

## Acceptance Criteria

- The user's explicit choice executed; merged result green (for merge); branch deleted only per the option table.
- Self-check: did the menu come after a fresh full-suite run on the tree being integrated? Was the base branch confirmed?

## Failure and Escalation

- Tests fail → report failures and stop; the menu waits for a green suite.
- Merged-result tests fail → stop, leave the branch, investigate, report.
- Rejected push → investigate the remote state; force-push only on explicit request.

## Cost and Latency Budget

- One full suite run before the menu, one after a merge (option 1). No re-review loops here — code-review already happened.

## Examples

- Positive: suite green → base confirmed as `main` → user picks 2 → PR URL reported → branch kept until PR merges.
- Negative: "they obviously want it merged" — the integration decision is never inferred.
- Edge: user asks to throw the work away → show the commit list, wait for the typed word `discard`, then `git branch -D`.

## Evaluation and Observability

- Metrics: integrations without a fresh green suite (target 0), unintended discards (target 0), wrong-base merges (target 0).
- Log: the integration choice and resulting SHAs/URL into `docs/日志/`.

## References (L2, load on demand)

- Observed excuses and red flags with counters: `references/rationalizations.md`
