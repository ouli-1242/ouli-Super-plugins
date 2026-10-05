---
name: form-fill
description: "Use when filling a fixed form or template with existing material - application/declaration forms, expense sheets, annual review tables, bid response tables, PDF forms, Excel templates with fixed cells. \"填一下这个申报表\", \"把这些资料填进表格\", \"填报销单\", \"按招标要求逐项填响应表\". NOT for writing free-form documents (doc-draft), NOT for computing the numbers that go into the form (data-report first), NOT for converting the form's file format (file-ops)."
---
# Form Fill — data into fixed slots, traceably

## Purpose

Fill a fixed form by mapping **material → fields** without invention. The core artifact is not the filled form — it is the **mapping table** that says where every value came from.

## When to Use / Not Use

- Use: application/declaration forms, expense sheets, annual review tables, bid response tables, PDF forms, Excel templates with fixed cells.
- Do NOT use: free-form documents (doc-draft); computing the numbers that go in (data-report first); converting the form's file format (file-ops).

## Capability Boundary

- CAN: inventory the empty form, build the mapping table, fill on a working copy, verify field by field.
- CANNOT: guess an unsourceable value; leave a required field silently empty.
- Depends on: the document skills' Python route (Excel/PDF forms); wps-cli (form inside an open WPS document); file-ops (scanned paper forms → OCR first); verify-output (pre-submission gate).

## Input Contract

- Required: the empty form and the source material.
- Optional: prior verified products (data-report output, doc-intake product) as value sources.
- Missing behavior: read the empty form first — every field, its format requirement (date style, 千分位, currency unit, character limits, required/optional), and every instruction on the form (填表说明 count as fields). A form half-read is a form half-filled with wrong assumptions.

## Output Contract

- The filled form (on a working copy) plus the **mapping table** — the real deliverable:
  `字段 | 要求 | 填入值 | 来源（文件/单元格/页码）| 状态`
  Every value traceable to a source file or a prior verified product; unsourceable values marked `[待补]` or asked, never guessed.
- 响应式表格 (bids, 评审表): respond point-by-point in the form's own order — the form's structure IS the outline; never reorganize it to taste.

## Constraints and Prohibitions

- **Build the mapping table before filling** — it is what makes the form auditable and the next one fast; skipping it saves 2 minutes and loses the only record of where numbers came from.
- Ambiguous field meaning ("编号" — which number?) → ask; a wrong guess in an official form costs a resubmission.
- **Fill on a working copy** of the original; route by form type (Excel/PDF → Python route; open in WPS → wps-cli; scanned paper → file-ops OCR first, expect lower field confidence).
- **Verify field by field** against the mapping table: value matches source, format matches the form's requirement (dates, units, decimals). Key fields — amounts, dates, ID/证号, names — get a second independent check.
- Every required field filled or explicitly flagged to the user — a required field left empty bounces the whole form.
- **Rationalizations kill the rule** — the observed excuses, failure patterns and their counters: `references/rationalizations.md`.
- Prohibited: "这个字段大概填这个不会错" (official forms have no 大概); ignoring format rules the form itself states (date style and 千分位 rejections are the top resubmission reason).

## Acceptance Criteria

- Mapping table complete; every field verified against it; key fields double-checked; verify-output gate passed before submission or printing.
- Self-check: does every value trace to a source? Would the form survive an auditor's spot check?

## Failure and Escalation

- Value has no source → `[待补]` + ask the user; never estimate into an official form.
- Form structure contradicts the material (a required field with no possible source) → surface to the user before filling anything else.

## Cost and Latency Budget

- One form inventory, one mapping-table pass, one field-by-field verification. Over budget: fill the verified fields, deliver the mapping table with `[待补]` rows visible.

## Examples

- Positive: 申报表 → mapping table with 38 rows → every 金额 traced to the ledger cell → amounts double-checked → verify-output gate → delivered.
- Negative: "编号" guessed as the project code when the form meant the 批文号 — one question away from a resubmission.
- Edge: scanned paper form → file-ops OCR first, confidence flagged per field in the mapping table.

## Evaluation and Observability

- Metrics: fields filled without source (target 0), format rejections on submission, resubmissions caused by wrong values (target 0).
- Log: the mapping table archives with the form; recurring form types → doc-asset (save the mapping conventions, not just the form).

## References (L2, load on demand)

- Observed excuses and red flags with counters: `references/rationalizations.md`
