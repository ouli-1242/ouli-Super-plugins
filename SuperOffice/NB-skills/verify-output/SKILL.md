---
name: verify-output
description: "Use BEFORE claiming any office deliverable is ready, or before sending, printing, or submitting it - \"文件做好了吗\", \"检查一下能不能交\", before emailing an attachment, printing, or submitting a form. NOT for reviewing someone else's material (doc-review), NOT for mid-work format checks (that belongs to the verb skill doing the work)."
---
# Verify Output — evidence before handover

## Purpose

Gate every office deliverable behind fresh, tool-run evidence — read back, rendered, counted — before the word 交 is allowed. "I wrote it" is not evidence; "I reopened it and saw it" is.

## When to Use / Not Use

- Use: before claiming any deliverable is ready (「文件做好了吗」「检查一下能不能交」); before emailing an attachment, printing, or submitting a form.
- Do NOT use: reviewing someone else's material (doc-review); mid-work format checks (the doing skill verifies its own step).

## Capability Boundary

- CAN: run the per-artifact evidence checks, compile the residual-gaps note, gate the deliver step.
- CANNOT: convert intent-to-check into evidence; send/print without the user's explicit go (unless previously given).
- Depends on: wps-cli for xlsx recomputation; rendered previews for layout-critical artifacts; the mapping table for forms.

## Input Contract

- Required: the deliverable artifact(s) and the intended handover (hand over / email / print / submit).
- Optional: the fidelity/mapping contracts from the producing skill.
- Missing behavior: no evidence check exists for the artifact type → construct one (reopen, count, spot-check) before any claim.

## Output Contract

- **Evidence table (fresh, run this turn, visible output):**
  | Artifact | Required evidence |
  |---|---|
  | docx | Reopens without error; page count as expected; key content found by search; layout-critical → print preview / rendered screenshot shown to user; TOC page numbers refreshed after content changes |
  | xlsx | Recomputed (formula cells show computed values, not stale caches — wps-cli when formulas matter); totals cross-checked (per data-report); no #REF! |
  | pptx | Slide count; no text overflow off slide edges; images render; fonts present or embedded (missing 中文字体 = broken deck) |
  | pdf | Page count matches source; text searchable (not accidentally an image); scans upright and legible |
  | form | Every field read back against the mapping table (form-fill) |
  | batch | Per-file success list + failure list, never one aggregate claim |
- **Residual-gaps note**: the honest edge shipped with the deliverable — what remains `[待核实]` (user-confirmable data, names to double-check, OCR spots). Also confirm no **undeclared** `[待核实]` markers survive from drafting.

## Constraints and Prohibitions

- Checks run **in this turn**, as commands with visible output; "我检查过了" without when/how/output is an unverified claim.
- Last-minute edits invalidate prior evidence — re-run the checks on the final file.
- **Deliver step**: email drafted (recipient, subject, attachment names checked against the verified files — yesterday's version is the classic failure) but sending happens on the user's explicit go; print settings (range, copies, duplex, paper) confirmed for anything beyond trivial; IM channels only if configured, and still need the user's go.
- Prohibited: "应该没问题" (should is not evidence — open it); "我刚生成的，内容我确定" (generation is not verification — conversion bugs, font substitutions, and stale formula caches are invisible at write time); "用户马上要用，先交了再说" (a wrong file on time is worse than a right file five minutes late).

## Acceptance Criteria

- Evidence table complete for the artifact type; residual-gaps note present; handover gated on the user's go where sending is involved.
- Self-check: did I run every check in this turn on the final file? Is every remaining gap declared rather than hidden?

## Failure and Escalation

- Any check fails → back to the producing verb skill (doc-draft / doc-revise / data-report / form-fill) with the finding; not done.
- Repeated verification pain on the same artifact type → propose a doc-asset profile entry so it stops recurring.

## Cost and Latency Budget

- One evidence pass per deliverable; batch = per-file loop. Over budget: verify the highest-risk artifacts first (amounts, layout, recipients) and name what remains unchecked.

## Examples

- Positive: xlsx → wps-cli recompute → totals cross-checked → no #REF! → gaps note lists the two figures awaiting user confirmation → delivered.
- Negative: "改了最后一处，其他地方之前验证过" — the final file never got re-opened.
- Edge: email handover → attachment names checked character-for-character against the verified files; send waits for the go.

## Evaluation and Observability

- Metrics: handovers without fresh evidence (target 0), undeclared gaps discovered by the user, wrong-attachment sends (target 0).
- Log: evidence table + gaps note archived with the delivery; recurring pain → doc-asset proposal.
