---
name: doc-draft
description: "Use when creating a new office document from scratch or from material - reports, notices, proposals, weekly reports, plans, letters, slides outlines, any \"帮我写一份…\". 中文信号：\"帮我写一份…\"\"写个报告\"\"起草一份通知\"\"写个周报\"\"做个方案\"\"写封邮件\""
---
# Doc Draft — the universal drafting frame

One skill drafts every office document, because every document answers the same four questions. The variety of documents lives in **templates and assets**, not in this skill. What lives here is the frame and the honesty rules.

## Step 1 — Answer the four questions before writing

| Question | Why it matters |
|---|---|
| **给谁看** — who reads it, at what seniority, with what attitude | Decides tone, jargon, and what needs justifying |
| **什么目的** — what should the reader do, believe, or approve after reading | Decides the ask; a document with no ask is a diary entry |
| **什么结构** — which template/asset or which structure primitive | Decides the skeleton (Step 2) |
| **素材在哪** — which files, data, or past documents supply the content | Decides what you may state and what stays `[待核实]` |

Missing answers: ask **one message** covering all gaps — not one question per round. For an email or one-page notice, answering from context is fine; for anything longer, ask.

## Step 2 — Get the skeleton from a template, never from imagination

Priority order:

1. **doc-asset profiles** — call the Skill tool with "doc-asset" if the unit's format may exist there.
2. **A past sample from the user** — "有往届的方案发我参考一份" is one sentence and prevents the most expensive failure: a well-written document in the wrong format.
3. **A structure primitive** (below), confirmed with the user in one outline message before drafting long documents — show the section skeleton, get a yes, then write.

| Primitive | Use for |
|---|---|
| 总分总（现状—分析—结论/建议） | 报告、总结、汇报 |
| 问题—方案—论证（含成本与风险） | 方案、立项、可研 |
| 评分响应式（逐点对应评审项/招标要求） | 标书、申报、答复质疑 |
| 时间线—进展（本期做了/下期要做/风险） | 周报、月报、阶段汇报 |
| 对比—选择（选项—优劣—建议） | 比选、决策请示 |
| 指令—步骤（要求+步骤+责任+时限） | 通知、说明、SOP |
| IMRaD（目的—方法—结果—结论） | 实验、研究、测试报告 |

## Step 3 — Draft from material only

- Every number and quotation comes from the materials gathered in Step 1's fourth answer — or it is marked `[待核实]`. Invent nothing, not even plausible-sounding figures. (superoffice discipline #1)
- Where the unit's conventions are unknown (称谓、落款、日期格式), follow the template if you have one; if not, use a neutral standard form and flag it for confirmation.
- Write for the reader of Step 1: conclusions first for senior readers; the ask stated where it cannot be missed.

## Step 4 — Verify, then deliver with the gaps visible

If the product is a file, read it back (verify-output method). Deliver with a **three-line note**: what structure was used, what is marked `[待核实]`, what needs the user's confirmation (称谓/数据/收件人). A draft with visible gaps is done; a draft with hidden gaps is a trap.

## Rationalizations

| Excuse | Reality |
|--------|---------|
| "内容简单，四问可以跳过" | The four questions cost one message; a wrong audience costs a rewrite. |
| "这种文体我熟，不用找模板" | Your memory of a format is not the unit's current format. Templates drift; ask. |
| "素材不够，先编着凑个完整的" | `[待核实]` marks are the deliverable's honest edges — a full-looking draft with invented numbers is worse than a gapped one. |
| "大纲确认太啰嗦，直接写全文" | For long documents, the outline yes is the cheapest checkpoint you will ever get. |

## Downstream

After drafting: user says 改 → `doc-revise`; user says 检查 → `verify-output`; user says "以后都按这个格式" → `doc-asset`. Filling a fixed form is not drafting — `form-fill`. Slides: the outline is drafted here; the deck file itself is produced afterwards with the document skills' pptx route or wps-cli impress.
