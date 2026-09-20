---
name: verification-before-completion
description: "Use BEFORE claiming any work is complete, fixed, or passing - before commits, PRs, or saying \"完成\" / \"搞定\" / \"修好了\". Requires running fresh verification commands and confirming output before any success claim; evidence before assertions always. Pairs with code-review - review first, then verify."
---
# Verification Before Completion

## Purpose

Guarantee that no success claim is made without fresh verification evidence — evidence before assertions, always.

## When to Use / Not Use

- Use: before ANY completion/success claim (exact phrase, paraphrase, or implication), before commits/PRs, before moving to the next task, before trusting a delegated agent's "success".
- Do NOT use as a substitute for review — review the change first when thresholds are met (core module / diff ≥ 15 files / new contracts), then verify.

## Capability Boundary

- CAN: define what evidence a claim requires, run the verification, read the output honestly, red-team the result.
- CANNOT: convert stale or partial checks into evidence.
- Depends on: the project's own test/lint/build/verification commands.

## Input Contract

- Required: the claim about to be made ("tests pass", "bug fixed", "requirements met").
- Optional: the specific commands the plan/spec prescribes.
- Missing behavior: no command exists that can prove the claim → that fact is itself the report; do not claim.

## Output Contract

- A completion statement that carries its evidence: command run this turn, exit code, failure counts — plus 诚实边界 (what was NOT done/verified) and 偏离声明 (reality vs plan) when they are non-empty.
- Quality bar: the word "should" never appears in a status claim.

## Constraints and Prohibitions

```
THE IRON LAW
NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE
```

- If you haven't run the verification command in this turn, you cannot claim it passes.
- Claim → required evidence (not sufficient: a previous run, "should pass", a partial check, an agent's success report):
  - Tests pass → test output showing 0 failures.
  - Build succeeds → build exit 0 (linter passing proves nothing about compilation).
  - Bug fixed → the original symptom, re-tested.
  - Regression test works → red-green verified (passes once proves nothing).
  - Agent/delegated work done → VCS diff inspected, not the agent's report.
  - Requirements met → line-by-line checklist against the spec.
- Red-team self-check before "done", answered out loud: How could this be wrong? What did I NOT verify (→ 诚实边界)? What actually happened vs what was planned (→ 偏离声明)? What would break in production?
- An honest "I don't know" goes into the log — never buried.
- Prohibited: expressing satisfaction ("Great!", "Done!") before verification; "just this once"; assuming different wording exempts the rule (violating the letter is violating the spirit).

## Acceptance Criteria

- Every success statement in the session is traceable to a fresh command output.
- Self-check: for each claim, can I point to the exact command and output from this turn? Is the 诚实边界 non-empty when something was skipped?

## Failure and Escalation

- Verification fails → state the actual status with evidence; the failure is the report.
- No available command proves the claim → say what evidence is missing and ask how to obtain it.
- Milestone closure → hand the 诚实边界 list to the work log (`docs/日志/`).

## Cost and Latency Budget

- Re-run full commands, not cached summaries; the cost is in the run, not the prose. If a full suite is prohibitively slow, run the relevant subset and say exactly what was not covered.

## Examples

- Positive: "All tests pass: 34/34 (`pytest -q`, exit 0, this turn). 诚实边界: perf suite not run."
- Negative: "Should pass now" / "Looks correct" / trusting a sub-agent's "success" without checking the diff.
- Edge: huge suite → run the affected subset, state precisely which parts were not exercised.

## Evaluation and Observability

- Metrics: unevidenced completion claims (target 0), 诚实边界 presence rate, user-caught false claims.
- Log: evidence + 诚实边界 + 偏离声明 into `docs/日志/` at milestones.
