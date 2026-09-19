---
name: file-ops
description: "Use when converting, merging, splitting, extracting, or recovering office files - docx/pdf/md format conversion, PDF merge or split, scanned pages or image tables into editable data, batch renaming, extracting text or tables from a document. \"转成PDF/Word\", \"合并这几个PDF\", \"拆分一下\", \"把扫描件转成表格\", \"提取这页的数据\", \"批量重命名\". NOT for computing or aggregating the extracted data (data-report), NOT for reading one small file into context (just read it), NOT for editing an open document in WPS (wps-cli)."
---
# File Ops — surgery on office files

## Purpose

Convert, merge, split, extract, and recover office files with the discipline in **fidelity checking** — a converted file that looks fine but lost a table column is worse than a failed conversion, because nobody re-opens it.

## When to Use / Not Use

- Use: format conversion, PDF merge/split, scanned-page/image-table OCR into editable data, batch renaming, text/table extraction.
- Do NOT use: computing/aggregating the extracted data (data-report); reading one small file into context (just read it); editing an open document in WPS (wps-cli).

## Capability Boundary

- CAN: fix fidelity requirements, route by operation, trial single-then-batch, verify fidelity against the contract.
- CANNOT: silently fall back to a lower-fidelity route when the right engine is missing; batch before a single-file proof.
- Depends on: markitdown-mcp (batch parsing), GLM-OCR glmocr-table (OCR), document-skills routes, wps-cli (layout-critical export) — engines cataloged in the office-mcp-setup skill's catalog.

## Input Contract

- Required: the file(s) and the operation.
- Optional: the fidelity contract (what must survive exactly).
- Missing behavior: ask or state what must survive **exactly** — tables and column structure? page layout for printing? searchable text? images? "转个 PDF" for archiving and "转个 PDF" for emailing are different fidelity contracts.

## Output Contract

- The operated file(s) plus a **fidelity statement**: what was verified (with numbers both sides), what sits on the 人工确认清单 (OCR amounts/dates/IDs), what was lost or approximated (if anything). Batch jobs ship a per-file success list + failure list, never one aggregate claim.

## Constraints and Prohibitions

- **Route by operation**: Office/PDF → Markdown text → markitdown-mcp if configured, else the document skills' Python route; scanned/photo table → GLM-OCR glmocr-table (handles merged cells) then data-report for the numbers; PDF merge/split/extract → PDF tooling (document skills' pdf route or wps-cli pdf); docx↔pdf layout-critical → wps-cli export (WPS renders as the user's WPS would print); batch rename → **dry-run listing first** (old → new), show the user, then execute.
- **Trial single, then batch**: run the operation on one file, verify it fully, then scale with per-file success checks and a failure list. Batch without a single-file proof converts 60 files into 60 broken files.
- **Verify fidelity, not existence** — "a file came out" proves nothing. Against the Step-1 contract: structure (page/sheet/row counts match, stated both sides); tables (spot-check 2–3 rows, merged cells survived or flagged); **OCR**: every recognized table spot-checked against the original image; amounts, dates, ID numbers go on the 人工确认清单 even when recognition looks confident — handwriting and low scans lie convincingly, and recognition confidence is a hint, never an assertion; layout-critical → rendered evidence.
- Prohibited: silent fallback to lower fidelity when a needed engine is missing (say so and offer office-mcp-setup); renaming without a dry-run; trusting "转换成功了，内容肯定没变".

## Acceptance Criteria

- Fidelity contract stated up front; single-file proof before batch; fidelity statement with the delivery.
- Self-check: does every claimed attribute trace to a check I ran (counts, spot-checks, previews)? Is the 人工确认清单 non-empty where OCR was involved?

## Failure and Escalation

- Required engine not configured → say so, offer office-mcp-setup; do not degrade silently.
- OCR confidence low across the board → deliver with the whole table flagged for manual confirmation.
- Batch failures > trivial → stop the batch, report the failure list, fix the cause before re-running.

## Cost and Latency Budget

- One single-file run + verification, then batch. Over budget: complete the single-file proof and deliver the batch plan instead of an unverified bulk run.

## Examples

- Positive: 12 scanned invoices → GLM-OCR → each table spot-checked against its image → amounts/dates/IDs on the 人工确认清单 → data-report consumes the verified Excel.
- Negative: 60-file rename executed directly from "a clear pattern" — the dry-run listing is one command.
- Edge: "转个PDF" for emailing → searchable text matters; for archiving → layout fidelity matters; the contract decides the route.

## Evaluation and Observability

- Metrics: fidelity failures found after delivery (target 0), OCR fields requiring manual correction, batches run without single-file proof (target 0).
- Log: fidelity statement per job; recurring conversion needs → office-mcp-setup / doc-asset.
