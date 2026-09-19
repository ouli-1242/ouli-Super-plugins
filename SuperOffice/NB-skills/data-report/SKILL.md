---
name: data-report
description: "Use when aggregating, checking, or analyzing spreadsheet data - merging multiple sheets or files, cross-checking totals, pivot tables, statistics, charts from tabular data, \"汇总这几个表\", \"核对数据\", \"做个透视\", \"统计一下\", \"画个图表\". NOT for filling forms with existing data (form-fill), NOT for converting file formats (file-ops), NOT for reading a single small table into context (just read it), NOT for recalculating stale formula results in an existing file (wps-cli)."
---
# Data Report — aggregate, verify, only then report

## Purpose

Produce spreadsheet aggregates and analyses where every figure is traceable to its source and every total is verified before it is spoken. The core is not computation — tools compute — it is **traceability and cross-checking**.

## When to Use / Not Use

- Use: merging multiple sheets/files, cross-checking totals, pivots, statistics, charts from tabular data.
- Do NOT use: filling forms with existing data (form-fill); converting file formats (file-ops); reading one small table into context; recalculating stale formulas in an existing file (wps-cli).

## Capability Boundary

- CAN: declare the scope (口径), pick the tool route, compute via tools, cross-check totals, deliver with a source list.
- CANNOT: let a number into the report without a traceable source; work in the user's only copy.
- Depends on: Python (openpyxl/pandas) for closed files; wps-cli when formulas must be computed or the file is open in WPS; file-ops for PDF/scan inputs.

## Input Contract

- Required: the data files/sheets and the question to answer.
- Optional: known 口径 (period, inclusions/exclusions), target output format.
- Missing behavior: 口径 unstated → derive it and state it in one message for confirmation BEFORE computing — most wrong reports are right numbers with a wrong 口径.

## Output Contract

- Report structure: **口径声明** (scope, period, rules) → results table → notable findings → **来源清单** (which file, which sheet/range feeds which figure). Charts follow the data relationship (trend→line, compare→bar, share→pie) and only when a chart answers a question; chart numbers must equal table numbers. The compute script/pipeline ships as the traceability artifact.

## Constraints and Prohibitions

- **Declare the 口径 before touching data** and ship it with the report.
- **All arithmetic goes through the tool** — sums, rates, unit conversions, date differences. Mental arithmetic in a report is how 87.5% becomes 78.5% in front of the leadership.
- **Cross-check before reporting (mandatory):**
  - *Total check*: re-derive each reported total a second way (different grouping, or sum the parts) — parts must reconcile to the whole.
  - *Spot check*: 2–3 random detail rows traced back to source cells.
  - *Sanity check*: period covered, record counts before/after cleaning, exclusions counted and stated — data "cleaned" without a count of what was dropped is data hidden.
  - Check fails → **stop and report the discrepancy**. The disagreement is the finding.
- **Never work in the user's only copy**: copy to a working file, output to a new file.
- Route: closed files, plain read/aggregate → Python; formulas must be *computed* (values, not cached) → wps-cli (openpyxl writes formulas but never computes them); file open in WPS or user watching → wps-cli; PDF/scans → file-ops first.
- Prohibited: "大概对得上就行了"; "调数凑平" (adjusting a number to make totals agree); reporting without the 来源清单.

## Acceptance Criteria

- Every reported figure traceable via the 来源清单; every total passed the second-derivation check; 口径声明 ships with the report.
- Self-check: can I trace the largest number in the report to its source cells in one hop? Did any check fail silently?

## Failure and Escalation

- Cross-check fails → report the discrepancy and stop; never reconcile by adjustment.
- Inputs are PDFs/scans → file-ops first; OCR results carry a 人工确认清单.
- Formulas show stale values → wps-cli recompute; uncomputed cells look real but are not.

## Cost and Latency Budget

- One compute pass, one cross-check pass. Over budget: deliver the verified core tables with the unverified parts explicitly listed as unchecked.

## Examples

- Positive: three sheets merged with pandas → each total re-derived by a different grouping → 来源清单 maps every figure to sheet+range → 口径 notes the excluded returned batch.
- Negative: a total that "looks right" inserted without the second derivation.
- Edge: a cleaning step drops 47 rows → the report says 47, what they were, and why.

## Evaluation and Observability

- Metrics: cross-check failures caught before delivery (that's the metric working), figures without source mapping (target 0), user-caught number errors (target 0).
- Log: 口径声明 + 来源清单 in the report; discrepancies reported, never smoothed.
