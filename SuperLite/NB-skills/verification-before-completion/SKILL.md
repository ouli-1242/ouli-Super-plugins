---
name: verification-before-completion
description: "Use BEFORE claiming any work is complete, fixed, or passing - before commits, PRs, or saying \"完成\" / \"搞定\" / \"修好了\" about any deliverable: code, documents, analyses, reports. Requires fresh verification (run the tests, re-read the document, re-check the numbers) before any success claim; evidence before assertions always. Pairs with code-review for code changes: review first, then verify."
---
# Verification Before Completion

## Purpose

Guarantee that no success claim is made without fresh verification evidence — for any deliverable, not just code.

## When to Use / Not Use

- Use: before ANY completion/success claim about code, documents, analyses, or reports — before commits/PRs, before moving on, before trusting a delegated agent's "success".
- Do NOT use as a substitute for review — review the code change first when thresholds are met, then verify.

## Capability Boundary

- CAN: define what evidence a claim requires, run/read the verification, red-team the result.
- CANNOT: convert stale or partial checks into evidence.
- Depends on: the project's test/lint/build commands; the deliverable's source material for non-code claims.

## Input Contract

- Required: the claim about to be made.
- Optional: the specific commands or checks the plan/spec prescribes.
- Missing behavior: no check exists that can prove the claim → that fact is itself the report; do not claim.

## Output Contract

- A completion statement carrying its evidence: command run this turn (code) / re-read against purpose (documents) / re-checked numbers (analyses) — plus 诚实边界 and 偏离声明 when non-empty.
- Quality bar: the word "should" never appears in a status claim.

## Constraints and Prohibitions

```
THE IRON LAW
NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE
```

- If you haven't run the verification in this turn, you cannot claim it passes.
- Claim → required evidence (not sufficient: a previous run, "should pass", a partial check, an agent's success report):
  - Tests pass → test output showing 0 failures.
  - Build succeeds → build exit 0 (linter passing proves nothing about compilation).
  - Bug fixed → the original symptom, re-tested.
  - Regression test works → red-green verified.
  - Agent/delegated work done → VCS diff inspected, not the agent's report.
  - Requirements met → line-by-line checklist against the spec.
- **Non-code deliverables**: the Iron Law applies to any work — re-read the document against its stated purpose and outline; re-check every number in the analysis against its source; confirm the file exists at the path you claim.
- Red-team self-check before "done", answered out loud: How could this be wrong? What did I NOT verify (→ 诚实边界)? What actually happened vs what was planned (→ 偏离声明)? What would break in real use (non-code: the reader who wasn't in the room, the number quoted out of context)?
- An honest "I don't know" goes into the deliverable's or handoff's 诚实边界 — never buried.
- Prohibited: satisfaction before verification; "just this once"; assuming different wording exempts the rule (violating the letter is violating the spirit).

## Acceptance Criteria

- Every success statement is traceable to fresh evidence from this turn.
- Self-check: for each claim, can I point to the exact evidence? Is the 诚实边界 non-empty when something was skipped?

## Failure and Escalation

- Verification fails → state the actual status with evidence; the failure is the report.
- No available check proves the claim → say what evidence is missing and ask how to obtain it.

## Cost and Latency Budget

- Re-run full commands, not cached summaries. If a full suite is prohibitively slow, run the relevant subset and say exactly what was not covered.

## Examples

- Positive: "All tests pass: 34/34 (`pytest -q`, exit 0, this turn). 诚实边界: perf suite not run."
- Negative: "Should pass now" / trusting a sub-agent's "success" without checking the diff.
- Edge: analysis report → every headline number re-checked against its source table before claiming done.

## Evaluation and Observability

- Metrics: unevidenced completion claims (target 0), 诚实边界 presence rate, user-caught false claims.
- Log: evidence + 诚实边界 + 偏离声明 into the deliverable or handoff; discipline deviations to `docs/日志/` when a project exists.
