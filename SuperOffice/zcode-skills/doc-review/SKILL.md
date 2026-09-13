---
name: doc-review
description: "Use when assessing someone else's material and giving feedback - reviewing a contract, a subordinate's proposal, a draft before it goes out, checking a report for problems, annotating a document with comments. 中文信号：\"看看这个方案行不行\"\"审一下这份合同\"\"给我提提意见\"\"帮我批注\""
---
# Doc Review — assess, don't rewrite

You are reading material someone else produced and answering one question: what would a careful reviewer flag before this goes further? The product is **findings**, not edits. You do not fix the text; you locate its problems precisely enough that fixing them is easy.

## Step 1 — Fix the review contract

One question, before reading: **what rides on this review** — legal exposure (contract), approval decision (proposal), the unit's format (outgoing document)? The contract decides which axes get deep attention. If the user just says "看看", state your default: all four axes, severity-ordered.

## Step 2 — Review on four axes, read fully first

Read the entire artifact once before flagging anything — a problem on page 8 may recontextualize page 2.

| Axis | What you hunt for |
|---|---|
| **事实准确** | Numbers that don't sum, dates that conflict, names/titles/机构名 wrong, citations that can't be real (superoffice discipline #1 applies to the reviewed text too) |
| **逻辑结构** | Conclusions not supported by the body, sections that answer a different question, missing prerequisites, contradictions between sections |
| **格式规范** | Departure from the unit's template (doc-asset profile if one exists), missing required elements, numbering/TOC breaks |
| **风险措辞** | Unqualified commitments ("保证", "确保无遗漏"), ambiguous scope ("等等", "相关问题"), missing deadlines/owners, anything a counterparty could exploit |

## Step 3 — Findings, not vibes

Every finding states four things:

```
位置：页码/节/条（能点到）
原文：引用原句
问题：一句话说清为什么是问题
依据：事实核对结果 / 模板条款 / 规范出处 / "无法核实，需对账"
```

Severity-order the list: **重大**（事实错误、风险承诺、缺失必需要素）before **建议**（表达、格式优化）。State uncertainty as uncertainty — "无法核实此数字" is a finding; a guess is not. No praise padding: if the document is solid, say so in one line and stop.

## Step 4 — Deliver according to the ask

- "提意见" → the findings list in conversation, as a Markdown report saved where the user wants.
- "帮我批注" → write **native comments** into the document (Word comment range anchored to the quoted text, via the document skills' Python route or wps-cli when the file is open in WPS) — never inline-edited text. The author accepts or rejects; the reviewer's job ends at the anchor.
- "顺便修了" → that is a different skill: call the Skill tool with "doc-revise" and hand over the findings as the work order.

## Rationalizations

| Excuse | Reality |
|--------|---------|
| "整体感觉还行，没大问题" | "感觉" is not a finding. Name what you checked and what you could not. |
| "这个数字大概是笔误，直接改掉吧" | Reviewers locate; owners correct. A silently "fixed" number may be the version the author intended. |
| "合同条款看不太懂，跳过了" | Exactly the clause that needs a finding: "条款含义不明，建议请法务确认" is the deliverable. |

## Downstream

Accepted findings become a work order for `doc-revise`. The unit's own quality bar belongs in `doc-asset` profiles. Verifying **your own** deliverable is never this skill — it is `verify-output`.
