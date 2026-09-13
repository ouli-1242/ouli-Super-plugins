---
name: file-ops
description: Use when converting, merging, splitting, extracting, or recovering office files - docx/pdf/md format conversion, PDF merge or split, scanned pages or image tables into editable data, batch renaming, extracting text or tables from a document. "转成PDF/Word", "合并这几个PDF", "拆分一下", "把扫描件转成表格", "提取这页的数据", "批量重命名". NOT for computing or aggregating the extracted data (data-report), NOT for reading one small file into context (just read it), NOT for editing an open document in WPS (wps-cli).
---

# File Ops — surgery on office files

Format conversion, merge/split, extraction, OCR. The work is mechanical; the discipline is in **fidelity checking** — a converted file that looks fine but lost a table column is worse than a failed conversion, because nobody re-opens it.

## Step 1 — Fix fidelity requirements before choosing a route

Ask or state: what must survive the operation **exactly** — tables and their column structure? Page layout for printing? Searchable text? Images? "转个 PDF" for archiving and "转个 PDF" for emailing are different fidelity contracts.

## Step 2 — Route by operation

| Operation | Route |
|---|---|
| docx/xlsx/pptx/pdf → Markdown text (for reading into context, intake) | **markitdown-mcp** if configured (office-mcp-setup), else document skills' Python route |
| Scanned page / photo table → editable Excel | OCR: **GLM-OCR glmocr-table** (tables incl. merged cells) or markitdown; then `data-report` for the numbers |
| pdf merge / split / extract pages | PDF tooling (document skills' pdf route, or wps-cli pdf subcommands) |
| docx ↔ pdf via WPS engine (layout-critical) | The Skill tool with "wps-cli" export — WPS renders it as the user's WPS would print it |
| Batch rename | Script a **dry-run listing first** (old → new), show the user, then execute |

Engines referenced above are cataloged in the `office-mcp-setup` skill's MCP catalog; if a needed engine is missing, say so and offer to set it up — do not silently fall back to a lower-fidelity route.

## Step 3 — Trial single, then batch

Run the operation on **one file**, verify it fully (Step 4), then scale to batch with per-file success checks and a failure list. Batch without a single-file proof converts 60 files into 60 broken files.

## Step 4 — Verify fidelity, not existence

"A file came out" proves nothing. Check against the fidelity contract from Step 1:

- **Structure**: page count / sheet count / row counts match the source (state the numbers both sides).
- **Tables**: spot-check 2–3 rows against the source; merged cells survived or are flagged.
- **OCR specifically**: every recognized table gets a spot-check against the original image; amounts, dates, ID numbers go on a **人工确认清单** even when recognition looks confident — handwriting and low scans lie convincingly. Recognition confidence is a hint, never an assertion.
- **Layout-critical conversions**: render/preview evidence, not a description.

Deliver with the fidelity statement: what was verified, what the 人工确认清单 contains, what was lost or approximated (if anything).

## Rationalizations

| Excuse | Reality |
|--------|---------|
| "转换成功了，内容肯定没变" | Format conversion is translation; only reading the output back tells you what survived. |
| "OCR 结果看起来没问题" | Confident OCR errors on amounts and dates are the classic silent failure. The 人工确认清单 exists for exactly these. |
| "60 个文件逐个验证太慢" | Verify the first fully, then per-file structural checks in the loop — slow is still faster than re-doing 60. |
| "重命名直接跑，反正规律很清楚" | Dry-run listing is one command. The regex that eats 40 filenames also looks clear. |

## Downstream

Numbers extracted from tables → `data-report` for aggregation and checking. Parsed text feeding a draft → `doc-draft`. Converted deliverable ready to hand over → `verify-output`.
