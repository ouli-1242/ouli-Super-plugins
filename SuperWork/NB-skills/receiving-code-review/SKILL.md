---
name: receiving-code-review
description: "Use when receiving code review feedback or findings - from the user, a reviewer, or the code-review skill's report - before implementing any of it (\"处理评审意见\", \"按评审意见改\"). Verify each suggestion against the codebase first; requires technical rigor, not performative agreement or blind implementation. Push back with technical reasoning when a finding is wrong."
---
# Code Review Reception

## Purpose

Handle review feedback with technical evaluation: verify before implementing, ask before assuming, push back when a finding is wrong.

## When to Use / Not Use

- Use: receiving findings from the user, an external reviewer, or the code-review report — before implementing any of them.
- Do NOT use: producing the review itself (code-review); postmorteming bugs (diagnosing-bugs).

## Capability Boundary

- CAN: verify each finding against the codebase, sort items, implement in the right order, push back with reasoning, reply in review threads.
- CANNOT: implement any item before understanding all of them; agree performatively.
- Depends on: the codebase itself; `gh` CLI for GitHub thread replies.

## Input Contract

- Required: the review feedback (list of findings).
- Optional: reviewer identity/source, related prior decisions.
- Missing behavior: any item unclear → STOP, do not implement anything yet; items may be related, and partial understanding produces wrong implementation. Ask for clarification on the unclear items first.

## Output Contract

- Implemented fixes, one item at a time, each tested individually with no regressions; or a technically reasoned pushback per rejected finding; or a stated verification limit ("I can't verify this without X — investigate, ask, or proceed?").

## Constraints and Prohibitions

- **Verify before implementing.** Check each suggestion against codebase reality before touching code. Trust is not verification.
- **Forbidden responses:** "You're absolutely right!", "Great point!", "Thanks for catching that!" — any gratitude or performative agreement. Acknowledging correct feedback: state the fix ("Fixed. <what changed>") or just fix it and show it in the code.
- **External reviewers get five checks** before implementation: technically correct for THIS codebase? breaks existing functionality? is there a reason for the current implementation? works on all platforms/versions? does the reviewer have full context? If it conflicts with the user's prior decisions → stop and discuss with the user first.
- **YAGNI check** for "implement this properly" suggestions: grep for actual usage. Unused → propose removal instead ("this endpoint isn't called — remove it (YAGNI)?").
- **Implementation order:** clarify everything unclear first, then blocking issues (breaks/security) → simple fixes → complex fixes; test each fix individually, then verify no regressions.
- **Push back when:** it breaks functionality, the reviewer lacks context, it violates YAGNI, it's technically wrong for this stack, legacy/compat reasons exist, or it conflicts with the user's architectural decisions. Push back with technical reasoning and specific questions — not defensiveness.
- If you pushed back and were wrong: state the correction factually ("You were right — I checked X and it does Y. Implementing now.") and move on. No long apologies, no defending the pushback.
- GitHub inline comments: reply in the comment thread (`gh api repos/{owner}/{repo}/pulls/{pr}/comments/{id}/replies`), not as a top-level PR comment.

## Acceptance Criteria

- Every finding is either implemented-and-tested or answered with technical reasoning; nothing implemented while any item was unclear.
- Self-check: did I verify each item against the codebase before implementing? Did any gratitude or performative agreement slip into a reply?

## Failure and Escalation

- Cannot verify a finding → state the limitation and ask for direction; never proceed on hope.
- Feedback conflicts with user's prior decisions → stop, surface the conflict.
- Wrong pushback discovered later → correct factually and implement.

## Cost and Latency Budget

- One verification pass per finding before implementation; batch clarifications into one question round. Over budget: deliver the sorted plan (verified/rejected/unclear) before implementing.

## Examples

- Positive: "Checking… build target is 10.15+, this API needs 13+. Need legacy for backward compat — fix the bundle ID or drop pre-13 support?"
- Negative: "You're absolutely right! Let me remove that legacy code…" — performative and unverified.
- Edge: "Fix 1–6" with 4 and 5 unclear → "I understand 1, 2, 3, 6. Need clarification on 4 and 5 before proceeding." Nothing implemented yet.

## Evaluation and Observability

- Metrics: performative-agreement occurrences (target 0), findings implemented without verification (target 0), pushbacks later confirmed correct.
- Log: rejected findings and their reasoning into the PR thread / `docs/日志/`.
