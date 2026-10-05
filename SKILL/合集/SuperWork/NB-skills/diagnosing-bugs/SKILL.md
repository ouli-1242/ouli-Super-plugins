---
name: diagnosing-bugs
description: "Use when a bug resists a first fix attempt, or the user reports something broken, throwing, failing, or slow - \"debug\", \"帮我调试\", \"为什么报错\", \"这个 bug 怎么回事\", performance regressions. Builds a tight feedback loop BEFORE hypothesizing or fixing anything. NOT for trivial one-line errors with an obvious cause - fix those directly. NOT for new feature work (use brainstorming). NOT for just explaining what an error means when no fix is asked - answer that directly."
---
# Diagnosing Bugs

## Purpose

Find hard-bug causes through a tight, red-capable feedback loop built BEFORE any hypothesis or fix — no speculative repairs.

## When to Use / Not Use

- Use: a bug resists the first fix attempt; anything broken/throwing/failing/slow; performance regressions.
- Do NOT use: trivial one-line errors with an obvious cause (fix directly); new feature work (brainstorming); explaining an error when no fix is asked (answer directly).

## Capability Boundary

- CAN: build reproduction loops, minimize repros, generate and test falsifiable hypotheses, instrument, fix with regression tests, run post-mortems.
- CANNOT: hypothesize before a red-capable loop exists; attempt fix #4 without an architectural discussion.
- Depends on: shell, debugger/REPL, profiler, headless browser as needed; `scripts/hitl-loop.ps1` (or `.sh` template) for human-in-the-loop signals; `技术依据.md` glossary + `决策记录.md` for context.

## Input Contract

- Required: the symptom as the user described it (exact error/output/timing) and where it occurs.
- Optional: suspected area, recent changes, environment details.
- Missing behavior: symptom too vague to act on → ask for the concrete failure evidence first; do not start from a guess.

## Output Contract

- One named, agent-runnable loop command (script/test/curl) that has already run red at least once; a minimized repro; a ranked hypothesis list; a fix with a regression test (or a documented no-correct-seam finding); a post-mortem stating the confirmed cause; all captured output redacted.

## Constraints and Prohibitions

- **Redact first.** Every secret becomes `<REDACTED>`; build loops against env vars so credentials stay in the environment; quote only signal-bearing lines of artifacts with auth headers. Redacted output insufficient to diagnose → say so and ask.
- **No red-capable command, no hypothesis.** The loop is done when ONE command you have already run (show invocation + redacted output) is: red-capable (asserts the user's exact symptom), deterministic, fast (seconds), agent-runnable. Reading code to build a theory before this command exists is the exact failure this skill prevents.
- **Reproduce, then minimize.** The loop must produce the failure the user described (not a nearby one), reproducibly, with the symptom captured. Shrink one element at a time, re-running each cut; done when every remaining element is load-bearing.
- **3–5 ranked, falsifiable hypotheses before testing any.** Format: "If X is the cause, then changing Y makes it disappear / changing Z makes it worse." No prediction → not a hypothesis. Show the list to the user before testing (proceed if they are away).
- **One variable per probe.** Debugger/REPL > targeted logs > never "log everything and grep". Tag every debug log with a unique prefix (e.g. `[DEBUG-a4f2]`) so cleanup is one grep. Performance bugs: measure a baseline first (profiler, query plan, timing harness), then bisect — logs are usually the wrong tool.
- **Regression test before the fix, only at a correct seam** — one exercising the real bug pattern as it occurs at the call site. **No correct seam is itself a finding**: document it; the architecture is preventing the bug from being locked down.
- **3 failed fixes = stop.** Return to loop analysis for attempts 1–2. After 3, stop fixing and question the architecture with the user — never attempt fix #4 without that discussion.
- Prohibited: fixing without a loop; "trying" an unranked hunch.

## Acceptance Criteria (pre-completion checklist)

- Original repro no longer reproduces (loop re-run); regression test passes (or seam absence documented); all `[DEBUG-…]` instrumentation removed; throwaway prototypes deleted or moved to a marked debug location; the confirmed hypothesis is stated in the commit/PR message.
- Self-check: did the loop assert the user's exact symptom? Can the regression test catch this bug if reverted?

## Failure and Escalation

- Genuinely cannot build a loop → stop and ask; never hypothesize without one.
- Fix fails twice → back to loop analysis with the new information. Third failure → architectural escalation (see above).
- Bug is actually a requirements problem → route to brainstorming and say why.

## Cost and Latency Budget

- Spend disproportionate effort on the loop — that is where the leverage is. Instrumentation ≤ ~6 probes; if the hypothesis list is exhausted, return to the loop rather than inventing hypotheses.

## Examples

- Positive: pinned curl script reproducing the 500 in 2 seconds → minimized to one header → 4 hypotheses ranked → breakpoint confirms #2 → regression test at the handler seam → fix → loop green.
- Negative: reading the module for 20 minutes, then "fixing" the most suspicious line — no loop, no hypothesis discipline.
- Edge: the only available seam cannot replicate the multi-caller chain → document "no correct seam" as the finding and raise the architectural follow-up after the fix.

## Evaluation and Observability

- Metrics: fixes reaching attempt #3+ (escalation rate), redacted-output leaks (target 0), regression tests written before fixes.
- Log: post-mortem (cause + prevention finding) into the commit/PR and `docs/日志/`; architectural findings become follow-up tasks.

## References (L2, load on demand)

- Ordered loop methods and tightening techniques: `references/feedback-loop-methods.md`
- Architecture-level failure patterns: `references/architectural-problems.md`
- Human-in-the-loop harness: `scripts/hitl-loop.ps1` / `scripts/hitl-loop.template.sh`
