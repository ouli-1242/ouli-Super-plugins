---
name: superoffice
description: "Use when any office-document task starts - drafting reports, memos, letters, slides, meeting notes; summarizing messy input; reviewing someone's material; filling forms; spreadsheet work; or any Word/Excel/PPT/PDF task. 中文同样适用（写报告、做PPT、改格式、整理会议记录、审材料、填表、做表格）。The entry router that picks the right verb skill BEFORE acting, and carries the office disciplines. NOT for retrieving external information - that is a research task, not an office verb."
---
# SuperOffice — Office Verb Router and Discipline Binding

## Purpose

Pick the right verb skill for an office task and bind the four office disciplines to the session. The verb layer is deliberately finite: verbs cover every office request; specialization lives in assets, not in this router.

## When to Use / Not Use

- Use at the start of any office-document task: route first, act second.
- Do NOT use: retrieving external information (a research task, not an office verb); trivial one-line edits (fix a typo, rename a file) may skip routing entirely.

## Verb Index (L0)

| Verb | Signal | Skill |
|---|---|---|
| 整理输入 | "整理一下这个录音/聊天记录/邮件串", "做个会议纪要" | doc-intake |
| 起草 | "写个报告/通知/方案/周报", "帮我写一份…" | doc-draft |
| 修改 | "润色", "改短一点", "换个语气", "排版乱了帮我修" | doc-revise |
| 审阅 | "看看这个方案行不行", "审一下合同", "帮我批注" | doc-review |
| 数据 | "汇总这几个表", "核对数据", "做个透视", "图表" | data-report |
| 文件手术 | "转成PDF/Word", "合并/拆分", "把扫描件转成表格" | file-ops |
| 填表 | "填一下这个申报表", "把资料填进这个模板" | form-fill |
| 验证交付 | "文件做好了吗", "检查一下能不能交" | verify-output |
| 沉淀资产 | "记住我们单位的模板", "以后都按这个格式" | doc-asset |
| 配置环境 | "配置MCP", first-time setup on a machine | office-mcp-setup (optional) |
| 驱动WPS | "用wps-cli", 公式重算、目录刷新、保真导出 | wps-cli (optional) |

## Capability Boundary

- CAN: dispatch to verb skills, resolve stage overlap, bind disciplines, declare multi-verb chains.
- CANNOT: draft, review, or compute itself; substitute for any verb skill's method.
- Depends on: the verb skills installed in the same harness; document-skills (docx/xlsx/pptx/pdf) as the primary engine; doc-asset profiles.

## Input Contract

- Required: the office task as stated.
- Optional: existing artifacts, templates, the unit's asset index (`docs/办公资产/索引.md`).
- Missing behavior: verb ambiguous → resolve by workflow position (input before drafting, drafting before revision, revision before review); still unclear → ask one question.

## Output Contract

- A routing statement (verb + skill name + reason); multi-verb tasks declared as an explicit chain (e.g. 整理并写纪要 = doc-intake → doc-draft with the intake product).
- Quality bar: one verb at a time; chains stated up front.

## Constraints and Prohibitions (unconditional disciplines — no exemptions)

1. **数字与引用真实性。** Every number comes from a user file or a tool computation — never invented, never silently estimated; every citation comes from real retrieval. Missing data → mark `[待核实]` and ask.
2. **模板优先。** Before drafting, look up the unit's/personal template or a past sample (doc-asset). No template → confirm the structure with the user before writing. Never invent an organization's format.
3. **证据交付。** No "文件做好了" without reading the file back — it opens, page count, key content, print preview for layout-critical work.
4. **凭证安全。** API keys and credentials go only into config files — never into conversation, documents, or logs. Say where a credential was stored.

Stage-overlap rules: "review my report" before anything is written → doc-draft (review needs an artifact); a file needing reformatting before data extraction → file-ops then data-report.

## Acceptance Criteria

- The chosen verb matches the task's workflow position; chains declared; disciplines in effect.
- Self-check: did I pick a verb or actually start doing the verb's job? Is any discipline being waived (none may be)?

## Failure and Escalation

- Required skill missing from the installed set → say so explicitly, handle the task inline under the disciplines; never pretend a skill ran.
- Task turns out to be non-office (research, coding) → say so and route out.

## Cost and Latency Budget

- Read once; one clarifying question at most; max_tool_calls = 1. Over budget: route immediately.

## Examples

- Positive: "整理并写份纪要" → declared chain: doc-intake → doc-draft(intake product).
- Negative: routing "看看这个方案行不行" to doc-review when no draft exists yet → doc-draft.
- Edge: "改一下措辞" on a closed file → doc-revise; on a document open in WPS → doc-revise (which routes to wps-cli).

## Evaluation and Observability

- Metrics: verb hit rate (chosen skill not corrected), discipline violations (target 0), chains declared before work starts.
- Log: routing statements in chat; discipline violations to `docs/日志/` when a project spine exists.
