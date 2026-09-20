---
name: form-fill
description: "Use when filling a fixed form or template with existing material - application/declaration forms, expense sheets, annual review tables, bid response tables, PDF forms, Excel templates with fixed cells. \"填一下这个申报表\", \"把这些资料填进表格\", \"填报销单\", \"按招标要求逐项填响应表\". NOT for writing free-form documents (doc-draft), NOT for computing the numbers that go into the form (data-report first), NOT for converting the form's file format (file-ops)."
---
# Form Fill — data into fixed slots, traceably

A form is the inverse of a draft: the structure is fixed and non-negotiable, and the work is mapping **material → fields** without invention. The core artifact is not the filled form — it is the **mapping table** that says where every value came from.

## Step 1 — Read the empty form first

Inventory the form before touching any data: every field, its format requirement (date style, 千分位, currency unit, character limits, required/optional), and every instruction on the form (填表说明 count as fields). A form half-read is a form half-filled with wrong assumptions.

## Step 2 — Build the mapping table (the real deliverable)

```
字段 | 要求 | 填入值 | 来源（文件/单元格/页码）| 状态
```

- Every value traceable to a source file or a prior verified product (`data-report` output, `doc-intake` product). Values with no source → **not guessed**: ask the user or mark `[待补]`.
- Ambiguous field meaning ("编号" — which number?) → ask; a wrong guess in an official form costs a resubmission.
- 响应式表格 (bids, 评审表): the form's/评分项's own structure **is** the outline — respond point-by-point in the form's order, never reorganize it to your taste.

## Step 3 — Fill on a working copy

Copy the original form; fill the copy. Route by form type: Excel templates and PDF forms via the document skills' Python route; a form inside an open WPS document → the Skill tool with "wps-cli"; scanned paper forms → `file-ops` OCR first, then treat as a normal form (and expect lower field confidence).

## Step 4 — Verify field by field

Read the filled form back and check **every field** against the mapping table — value matches source, format matches the form's requirement (dates, units, decimals). Key fields — amounts, dates, ID/证号, names — get a second independent check. Then the standard gate: call the Skill tool with "verify-output" before the form is submitted or printed. Submitting an official form is delivery; unverified delivery is how resubmissions happen.

## Rationalizations

| Excuse | Reality |
|--------|---------|
| "这个字段大概填这个不会错" | Official forms have no "大概". Unsourceable values wait for the user or stay `[待补]`. |
| "格式要求应该不严格" | Date style and 千分位 rejections are the most common resubmission reason. The form told you its rules — obey them. |
| "映射表太啰嗦，直接填快" | The mapping table is what makes the form auditable and the next one fast. Skipping it saves 2 minutes and loses the only record of where numbers came from. |
| "漏了一个字段，空着也行吧" | A required field left empty bounces the whole form. Every required field filled or explicitly flagged to the user. |

## Downstream

Numbers for the form need computing/checking → `data-report`. Form is a scanned paper → `file-ops` first. Pre-submission gate → `verify-output`. This form type recurs every quarter → `doc-asset` (save the mapping conventions, not just the form).
