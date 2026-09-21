---
name: doc-review
description: "Use when assessing someone else's material and giving feedback - reviewing a contract, a subordinate's proposal, a draft before it goes out, checking a report for problems, annotating a document with comments. \"看看这个方案行不行\", \"审一下这份合同\", \"给我提提意见\", \"帮我批注\", \"这报告有没有问题\". NOT for editing the text on the user's behalf (doc-revise), NOT for verifying your own deliverable before handing it over (verify-output)."
---
# Doc Review — assess, don't rewrite

## Purpose

Read material someone else produced and produce **findings**, not edits — problems located precisely enough that fixing them is easy.

## When to Use / Not Use

- Use: reviewing a contract, proposal, outgoing draft, report; annotating a document with comments.
- Do NOT use: editing on the user's behalf (doc-revise); verifying your own deliverable (verify-output).

## Capability Boundary

- CAN: fix the review contract, review four axes after a full read, produce four-element findings, write native comments.
- CANNOT: silently fix what it finds; skip unread sections (an unread clause is exactly the one needing a finding).
- Depends on: the document skills' Python route or wps-cli for native comment writing; doc-asset format profiles.

## Input Contract

- Required: the material to review.
- Optional: the review contract (what rides on it — legal exposure / approval decision / unit format).
- Missing behavior: contract unstated ("看看") → state your default: all four axes, severity-ordered — then proceed.

## Output Contract

- A findings list, severity-ordered (重大 before 建议), every finding in four elements:
  `位置`（页码/节/条，能点到）· `原文`（引用原句）· `问题`（一句话为什么是问题）· `依据`（事实核对结果 / 模板条款 / 规范出处 / "无法核实，需对账"）.
- No praise padding: if the document is solid, one line says so and the list ends.
- Delivery by the ask: 提意见 → findings in conversation or a saved Markdown report; 帮我批注 → **native comments** anchored to the quoted text (never inline-edited text — the author accepts or rejects); "顺便修了" → hand the findings to doc-revise as the work order.

## Constraints and Prohibitions

- **Read the entire artifact once before flagging anything** — a problem on page 8 may recontextualize page 2.
- Four axes: **事实准确** (numbers that don't sum, conflicting dates, wrong names/titles, impossible citations), **逻辑结构** (conclusions unsupported, sections answering a different question, contradictions), **格式规范** (departure from the unit's template, missing required elements, numbering/TOC breaks), **风险措辞** (unqualified commitments 「保证/确保无遗漏」, ambiguous scope 「等等」, missing deadlines/owners, counterparty-exploitable wording).
- State uncertainty as uncertainty — "无法核实此数字" is a finding; a guess is not.
- **Rationalizations kill the rule** — the observed excuses, failure patterns and their counters: `references/rationalizations.md`.
- Prohibited: silently "fixing" a probable typo (reviewers locate; owners correct — the author may have intended that version); skipping a clause because it's hard to understand (「条款含义不明，建议请法务确认」 IS the deliverable); inline-editing text under the guise of review.

## Acceptance Criteria

- Full read done; findings in the four-element format; severity order; delivery matches the ask (report vs native comments).
- Self-check: can every finding be located and verified by its 位置+原文? Did I edit anything instead of flagging it?

## Failure and Escalation

- Cannot verify a factual claim → the finding says so ("无法核实，需对账").
- A finding requires a specialist (legal/finance) → state that in the finding's 依据.

## Cost and Latency Budget

- One full read + axis pass; findings as they arise. Over budget: deliver partial findings with the explicitly unreviewed sections named.

## Examples

- Positive: contract review flags "第7条『确保无遗漏』为无保留承诺" with position, quote, risk, and the suggested rewording left to the owner.
- Negative: "整体感觉还行，没大问题" — "感觉" is not a finding.
- Edge: an unreadable clause → finding 「条款含义不明，建议请法务确认」, not a skipped section.

## Evaluation and Observability

- Metrics: findings later disputed (false-positive rate), missed issues found by later readers, inline-edit occurrences (target 0).
- Log: the findings list is the record; accepted findings become doc-revise work orders.

## References (L2, load on demand)

- Observed excuses and red flags with counters: `references/rationalizations.md`
