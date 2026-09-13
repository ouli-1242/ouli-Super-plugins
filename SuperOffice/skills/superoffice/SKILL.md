---
name: superoffice
description: Use when any office-document task starts - drafting reports, memos, letters, slides, meeting notes; summarizing messy input; reviewing someone's material; filling forms; spreadsheet work; or any Word/Excel/PPT/PDF task. 中文同样适用（写报告、做PPT、改格式、整理会议记录、审材料、填表、做表格）。The entry router that picks the right verb skill BEFORE acting, and carries the office disciplines (data truthfulness, template first, evidence before delivery, credential safety). Read the body - don't route from memory.
---

# SuperOffice Router

Decide **which verb** the current task needs, then invoke that skill by name. One task → one verb skill; the verbs are mutually exclusive. When two seem to apply, the workflow position decides: input comes before drafting, drafting before revision, revision before review.

## The Rule

Route the task first, then act. Announce: "Using [skill] for [purpose]" and call the Skill tool with that skill's name. If it turns out wrong for the situation, you don't have to follow it — but the check comes first.

## Verb Route Table

| Verb | User signal (EN / 中文) | Invoke |
|---|---|---|
| 整理输入 | "整理一下这个录音/聊天记录/邮件串", "做个会议纪要", "总结这份材料" | `doc-intake` |
| 起草 | "写个报告/通知/方案/周报", "起草", "帮我写一份…" | `doc-draft` |
| 修改 | "润色", "改短一点", "换个风格", "排版乱了帮我修", "改一下措辞" | `doc-revise` |
| 审阅 | "看看这个方案行不行", "审一下合同", "给点意见", "帮我批注" | `doc-review` |
| 数据 | "汇总这几个表", "核对数据", "做个透视", "算一下", "图表" | `data-report` |
| 文件手术 | "转成PDF/Word", "合并/拆分", "把扫描件转成表格", "提取这页的数据" | `file-ops` |
| 填表 | "填一下这个申报表", "把资料填进这个模板" | `form-fill` |
| 验证交付 | "检查一下文件对不对", "能不能打印", deliverable ready to hand over | `verify-output` |
| 沉淀资产 | "记住我们单位的模板", "以后都按这个格式", "把这份样例存下来" | `doc-asset` |
| 配置环境 | "配置MCP", "装个office MCP", "让AI能操控WPS", first-time setup on a machine | `office-mcp-setup` |
| 驱动WPS | "用wps-cli", "操控WPS", "WPS重算", "WPS导出PDF" | `wps-cli` |

## Availability (v1.0.0)

All verb skills are shipped. If a named skill is missing from the installed set (someone copied only part of the pack), say so explicitly and handle the task inline under the disciplines below — do not pretend a skill ran.

## Unconditional Disciplines

These bind even when no skill is loaded:

1. **数字与引用真实性。** Every number comes from a user-provided file or a tool computation — never invented, never estimated silently. Every citation/reference must come from real retrieval, never generated. Missing data → mark `[待核实]` and ask. Full method lands with `data-report` / `doc-draft`.
2. **模板优先。** Before drafting any document, ask for or look up the unit's/personal template or a past sample (this is `doc-asset`'s purpose). No template → confirm the structure with the user before writing. Never invent an organization's format from imagination.
3. **证据交付。** No "文件做好了" without reading the file back and verifying it opens and looks right (page count, key content, print preview for layout-critical work). Method lands with `verify-output`.
4. **凭证安全。** API keys, secrets, and account credentials go only into config files — never into conversation, documents, or logs. Say where a credential was stored.

Disciplines 1–3 never have exemptions; discipline 4 never has exemptions. Trivial one-line edits (fix a typo, rename a file) may skip routing entirely.

## Stage Overlap Resolution

A "review my report" request before anything is written routes to `doc-draft`, not `doc-review` — review needs an existing artifact. A "整理并写份纪要" request is two verbs: call `doc-intake` first, then `doc-draft` with the intake product — two Skill tool calls, said explicitly. A file that needs reformatting before its data can be extracted is `file-ops` then `data-report`.
