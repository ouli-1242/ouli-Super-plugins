---
name: verify-output
description: Use BEFORE claiming any office deliverable is ready, or before sending, printing, or submitting it - "文件做好了吗", "检查一下能不能交", before emailing an attachment, printing, or submitting a form. NOT for reviewing someone else's material (doc-review), NOT for mid-work format checks (that belongs to the verb skill doing the work).
---

# Verify Output — evidence before handover

The office version of an unfalsifiable claim is "文件做好了". This skill is the gate: every deliverable gets fresh, tool-run evidence — read back, rendered, counted — before the word 交 is allowed. **"I wrote it" is not evidence; "I reopened it and saw it" is.**

## The evidence table

| Artifact | Fresh evidence required |
|---|---|
| **docx** | Reopens without error; page count as expected; key content present (search for it); layout-critical → **print preview / rendered screenshot shown to user**; TOC page numbers refreshed after content changed |
| **xlsx** | Recomputed (formula cells show computed values, not stale caches — via wps-cli when formulas matter); totals cross-checked (per `data-report` Step 4); no broken references (#REF!) |
| **pptx** | Slide count; no text overflow off slide edges; images render; fonts present or embedded (missing 中文字体 = broken deck) |
| **pdf** | Page count matches source; text searchable (not accidentally an image); scans upright and legible |
| **form** (any filled) | Every field read back against the mapping table (`form-fill`) |
| **batch** | Per-file success list + failure list, not one aggregate claim |

Run the checks **in this turn**, as commands with visible output. "我检查过了" without saying when, how, and what the output was, is an unverified claim.

## The residual-gaps note

Deliverables ship with an honest edge: a short list of what remains `[待核实]` (data the user must confirm, names to double-check, OCR spots on the 人工确认清单). A deliverable with declared gaps is complete; a deliverable that hides its gaps is a liability with a clean surface. Check there are no **undeclared** `[待核实]` markers left from drafting that should have been resolved or declared.

## Deliver step (when the ask includes sending)

- **Email**: draft it — recipient, subject, attachment names checked against the verified files — but sending happens on the user's explicit go unless they said otherwise. Attachment names match the verified artifacts exactly (yesterday's version is the classic failure).
- **Print**: print settings (range, copies, duplex, paper) confirmed with the user for anything beyond trivial.
- **IM channels** (Feishu/WeCom/DingTalk): only if configured — pending in this version of the catalog; sending still needs the user's go.

## Red flags — all of these mean: stop and actually verify

| Thought | Reality |
|---------|---------|
| "应该没问题" | Should is not evidence. Open it. |
| "我刚生成的，内容我确定" | Generation is not verification. Conversion bugs, font substitutions, and stale formula caches are invisible at write time. |
| "用户马上要用，先交了再说" | A wrong file handed over on time is worse than a right file handed over late by five minutes. The check takes minutes. |
| "改了最后一处，其他地方之前验证过" | Last-minute edits invalidate prior evidence. Re-run the checks on the final file. |

## Downstream

Findings that mean the work is not done → back to the verb skill that produced the artifact (`doc-draft` / `doc-revise` / `data-report` / `form-fill`). Repeated verification pain on the same artifact type → propose a `doc-asset` profile entry so it stops recurring.
