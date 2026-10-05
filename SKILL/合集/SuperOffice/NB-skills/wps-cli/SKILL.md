---
name: wps-cli
description: "Use when documents must be operated through the real WPS engine - live recalculation, field/TOC refresh, format-faithful export, or a document the user has open. 中文触发：「用wps-cli」、WPS重算、公式显示0或结果不更新、刷新目录页码、用WPS引擎导出PDF保真格式、操控已打开的文档。NOT for plain closed-file conversion (file-ops is the default converter), NOT for installing or configuring wps-cli or its MCP server (call office-mcp-setup), NOT when WPS is not installed on this machine."
---
# WPS CLI — drive the real WPS engine

*(Design reference: iOfficeAI/OfficeCLI, Apache 2.0.)*

## Purpose

Operate documents through the real WPS engine — true formatting, true layout — for the four things Python libraries cannot do: live recalculation, field/TOC refresh, format-faithful export, and controlling a document the user has open.

## When to Use / Not Use

- Use: 重算公式（显示 0 或结果不更新）、刷新目录/字段页码、WPS 引擎保真导出 PDF、操控已打开的文档（「用wps-cli」）.
- Do NOT use: plain closed-file conversion (file-ops is the default converter); installing/configuring wps-cli or its MCP server (office-mcp-setup); machines without WPS installed.

## Capability Boundary

- CAN: drive writer/calc/impress/pdf/export/batch subcommands against real WPS, with JSON output and document validation.
- CANNOT: run on non-Windows or without WPS 2019+; use dangerous formula functions; reach UNC paths or symlinks.
- Depends on: Python + pywin32 + Windows COM + WPS Office 2019+; the command surface in `references/commands.md`.

## Input Contract

- Required: the target file(s) and the operation.
- Optional: data payloads for merge/fill, output paths.
- Missing behavior: **help-first** — the authoritative command surface is the CLI on THIS machine; versions drift. Before any workflow run `wps --help`, then `<command> --help` for each command about to be used. If a command named in the references does not exist in the installed version, trust the help output, not the document — and report the drift to the user.

## Output Contract

- Every command returns machine-readable JSON (`--json` / `-j`). **Read-back verification is part of every workflow**: parse the `success`/`status` fields, and after write operations re-open the file or query a key value to confirm persistence. Without read-back evidence, "已保存/已重算/已导出" may not be claimed.
- **Recompute verification loop**: formulas written by openpyxl etc. only compute in WPS — after recalculation, read back computed values with `calc cell-get` (or equivalent) and compare against an independently computed expectation. Until the value is read back, it does not exist.

## Constraints and Prohibitions

- **Working decision tree** (details in `references/patterns.md`): Word → `writer` (view/merge/replace/table-*/get/formfield-*/validate); Excel → `calc` (view/cell-*/formula/chart/conditional-format/data-validation/sparkline/sort); PPT → `impress` (view/slide-*/text-*/image-insert/export-pdf); PDF → `pdf` (merge/split/extract-pages/watermark/info); conversion → `export` (single/batch); multi-step → `batch` (JSON array); environment trouble → `wps doctor`.
- **Six hard constraints:**
  1. Commands are **synchronous and blocking** — each COM operation takes seconds (WPS start + file open); budget for the wait.
  2. **Extension whitelists**: writer `.doc/.docx/.wps/.rtf/.txt/.html`; calc `.xls/.xlsx/.xlsm/.et/.csv`; impress `.ppt/.pptx/.pps/.dps`.
  3. **Formula safety**: `calc cell-formula` forbids SHELL/DDE/HYPERLINK/WEBSERVICE and similar dangerous functions.
  4. **Path limits**: no UNC paths, no symlinks — local absolute/relative only.
  5. **Windows only**: COM/win32com + WPS Office 2019+ installed.
  6. All commands support `--json` for machine-readable output.
- **Diagnosis order**: `wps doctor` (environment) → `wps doctor --fix` (COM registration, needs admin) → `wps doctor --report` (redacted report for issues) → `wps writer|calc|impress validate <file>`.
- **Batch discipline**: prove one file on a draft copy first; per-file `success` field checks in the loop; failures collected into a list, not aborting the batch.
- **Dual-entry rule**: wps-cli also ships a built-in MCP server (`wps mcp install`, see `references/mcp.md`). Command sequences → this skill; WPS-capabilities-as-tools → configured via office-mcp-setup. Never mix the two routes within one task.
- Prohibited: plain closed-file read/write through WPS when a Python library is simpler — this skill exists for the real-engine cases only.

## Acceptance Criteria

- The operation's effect is confirmed by read-back evidence (parsed JSON + re-opened/query values); batch ships per-file results.
- Self-check: did I parse the JSON status rather than assume success? For recalculation, did I read back the computed value and compare it to an independent expectation?

## Failure and Escalation

- Command not found / flag mismatch → trust `--help`, report the version drift to the user.
- `wps doctor` reports broken COM → `--fix` (admin) or escalate; do not work around with guessed flags.
- Result mismatches the independent expectation → re- diagnose; do not ship the number.

## Cost and Latency Budget

- COM operations are seconds each; keep workflows to the minimum command set (batch subcommand for multi-step). Over budget: report progress after the current file completes.

## Examples

- Positive: stale-formula report → `calc cell-formula` set + recalc → `calc cell-get` reads back 1,284.72 matching pandas' independent computation → delivered with evidence.
- Negative: trusting the JSON `success: true` of an export without re-opening the PDF to count pages.
- Edge: user watching a document open in WPS → drive it live via wps-cli (never a side copy that silently diverges).

## Evaluation and Observability

- Metrics: claims without read-back evidence (target 0), recalc values shipped without independent comparison, version-drift surprises.
- Log: command sequences + JSON evidence archived with the job; drift reported to the user.

## References (L2, load on demand)

- Full 76-command quick reference: `references/commands.md`
- Eight usage patterns (template fill, report generation, batch conversion): `references/patterns.md`
- Built-in MCP server + 27 tools: `references/mcp.md`
- JSON output schema, error schema, exit codes: `references/json-schema.md`
