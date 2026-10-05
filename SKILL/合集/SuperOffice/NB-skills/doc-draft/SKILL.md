---
name: doc-draft
description: "Use when creating a new office document from scratch or from material - reports, notices, proposals, weekly reports, plans, letters, slides outlines, any \"帮我写一份…\". \"写个报告\", \"起草一份通知\", \"写个周报\", \"做个方案\", \"写封邮件\". NOT for turning messy input into material (doc-intake first, then hand the material here), NOT for revising or polishing an existing text (doc-revise), NOT for filling fixed forms (form-fill)."
---
# Doc Draft — the universal drafting frame

## Purpose

Draft any office document through one frame: four questions, a template-derived skeleton, material-only content, gaps delivered visibly. Document variety lives in templates and assets, not in this skill.

## When to Use / Not Use

- Use: creating any new office document — reports, notices, proposals, weekly reports, plans, letters, slide outlines.
- Do NOT use: turning messy input into material (doc-intake first); revising/polishing existing text (doc-revise); filling fixed forms (form-fill).

## Capability Boundary

- CAN: fix audience/purpose/structure/materials, derive the skeleton from assets or primitives, draft from material only, deliver with visible gaps.
- CANNOT: invent an organization's format; state a number the material does not supply.
- Depends on: doc-asset profiles; user-provided past samples; the gathered material.

## Input Contract

- Required: the drafting request.
- Optional: template/profile, past samples, data files.
- Missing behavior: ask **one message** covering all gaps in the four questions — not one question per round. Email or one-page notice → answering from context is fine; anything longer → ask. Long documents → outline confirmation before drafting.

## Output Contract

- The document, drafted from material only, plus a **three-line delivery note**: what structure was used · what is marked `[待核实]` · what needs the user's confirmation (称谓/数据/收件人). A draft with visible gaps is done; a draft with hidden gaps is a trap.
- Slides: the outline is drafted here; the deck file itself goes through the document skills' pptx route or wps-cli impress afterwards.

## Constraints and Prohibitions

- **The four questions before writing**: 给谁看 (decides tone/jargon/justification) · 什么目的 (the ask — a document with no ask is a diary entry) · 什么结构 (which template or primitive) · 素材在哪 (what you may state vs what stays `[待核实]`).
- **Skeleton priority**: doc-asset profile → a past sample from the user ("有往届的方案发我参考一份" prevents the most expensive failure) → a structure primitive confirmed with the user in one outline message (总分总 / 问题—方案—论证 / 评分响应式 / 时间线—进展 / 对比—选择 / 指令—步骤 / IMRaD — pick by document type).
- **Draft from material only.** Every number and quotation comes from the gathered material or is marked `[待核实]` — invent nothing, not even plausible figures. Unknown unit conventions (称谓、落款、日期格式) → follow the template, else neutral standard form + flag for confirmation.
- Write for the reader of question 1: conclusions first for senior readers; the ask stated where it cannot be missed.
- **Rationalizations kill the rule** — the observed excuses, failure patterns and their counters: `references/rationalizations.md`.
- Prohibited: skipping the four questions ("内容简单"); trusting memory of a format ("这种文体我熟" — formats drift); padding a full-looking draft over invented numbers.

## Acceptance Criteria

- Four questions answered (or explicitly assumed); skeleton from asset/sample/confirmed primitive; every number sourced or marked; delivery note present.
- Self-check: does any number lack a source? Would the reader's first question already be answered on page 1?

## Failure and Escalation

- No template and user unavailable → neutral standard form, flagged — never an invented institutional format.
- Material insufficient for a required section → `[待核实]` + tell the user what is needed; never paper over.
- User says 改 → doc-revise; 检查 → verify-output; "以后都按这个格式" → doc-asset.

## Cost and Latency Budget

- Four-question round-trip (one message), skeleton confirmation for long documents, one drafting pass, one read-back. Over budget: deliver the outline + open questions instead of an unconfirmed full draft.

## Examples

- Positive: weekly report on the 时间线—进展 primitive → 本期做了/下期要做/风险, every figure from the tracking sheet, delivery note flags the missing Q3 headcount.
- Negative: "先编着凑个完整的" — an invented revenue figure in a draft that reads complete.
- Edge: a bid response is NOT free drafting — the 评分项 structure is fixed → form-fill, not this skill.

## Evaluation and Observability

- Metrics: drafts with unsourced numbers (target 0), wrong-format rewrites (template-first adherence), `[待核实]` resolution rate.
- Log: recurring drafting conventions worth keeping → doc-asset profile proposal.

## References (L2, load on demand)

- Observed excuses and red flags with counters: `references/rationalizations.md`
