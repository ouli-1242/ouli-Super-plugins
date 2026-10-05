---
name: data-report
description: "Use when aggregating, checking, or analyzing spreadsheet data - merging multiple sheets or files, cross-checking totals, pivot tables, statistics, charts from tabular data, \"汇总这几个表\", \"核对数据\", \"做个透视\", \"统计一下\", \"画个图表\". NOT for filling forms with existing data (form-fill), NOT for converting file formats (file-ops), NOT for reading a single small table into context (just read it), NOT for recalculating stale formula results in an existing file (wps-cli)."
---
# Data Report — aggregate, verify, only then report

Every number you output will be quoted in a meeting. The skill's core is not computation — tools compute — it is **traceability and cross-checking**: every figure traceable to its source, every total verified before it is spoken.

## Step 1 — Inventory inputs and declare the口径

Before touching data: which files/sheets, what period, what counts as a record, what gets excluded. Write the **口径声明** (scope, period, rules) — it ships with the report. Most wrong reports are right numbers with a wrong口径.

## Step 2 — Choose the tool route

| Situation | Route |
|---|---|
| Closed files, plain read/aggregation | Python (openpyxl / pandas) — simplest |
| Formulas must be **computed** (values needed, not cached) | The Skill tool with "wps-cli" — openpyxl writes formulas but never computes them |
| File is open in WPS / user watches | "wps-cli" |
| Files are PDF/scans | "file-ops" first |

Never work in the user's only copy: copy to a working file, output to a new file.

## Step 3 — Aggregate with the tool, not your head

All arithmetic — sums, rates, unit conversions, date differences — goes through the tool. Mental arithmetic in a report is how 87.5% becomes 78.5% in front of the leadership. Keep the script/pipeline; it is the traceability artifact.

## Step 4 — Cross-check before reporting (mandatory)

- **Total check**: re-derive each reported total a second way (different grouping, or sum the parts). Parts must reconcile to the whole.
- **Spot check**: pick 2–3 random detail rows; trace a reported figure back to source cells.
- **Sanity check**: period covered, record counts before/after cleaning, exclusions counted and stated. Data "cleaned" without a count of what was dropped is data hidden.
- Check fails → **stop and report the discrepancy**. Never "adjust" a number to make totals agree; the disagreement is the finding.

## Step 5 — Output with traceability

Report structure: 口径声明 → results (table) → notable findings → **来源清单** (which file, which sheet/range feeds which figure). Charts follow the data relationship (trend→line, compare→bar, share→pie, and only when a chart answers a question — decoration is not analysis). Chart numbers must equal table numbers.

## Rationalizations

| Excuse | Reality |
|--------|---------|
| "大概对得上就行了" | The total check is the whole point of the skill. "大概" is how 1.2 million becomes 2.1 million. |
| "口径 obvious 了，不用写" | 口径 is the difference between "sales fell" and "sales fell excluding the returned batch". Ship it. |
| "直接在原表上改快一些" | The original is the source of truth. Work on a copy, always. |
| "公式算过了，不用读回" | openpyxl caches, WPS computes. Uncomputed cells show stale values that look real. |

## Downstream

Filling declared forms with verified figures → `form-fill`. Deliverable handover check → `verify-output`. Recurring aggregation rules worth saving → `doc-asset`.
