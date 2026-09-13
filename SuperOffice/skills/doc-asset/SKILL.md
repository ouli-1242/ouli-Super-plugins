---
name: doc-asset
description: Use when the user wants the agent to remember their organization's or personal document conventions - extracting a reusable profile from a real template or past document, saving terminology and title conventions, building a stock-phrase library, "记住我们单位的模板", "以后都按这个格式", "把这份样例存下来", "记一下我们的术语". NOT for one-off drafting (doc-draft, which consults assets), NOT for summarizing a document for reading (doc-intake).
---

# Doc Asset — where specialization lives

SuperOffice ships generic on purpose. Everything specific to a unit or a person — the红头 format, the boss's title, the forbidden phrases, the report skeleton that always gets approved — lives here, as **assets extracted from real artifacts** and reused by every other skill. One good profile beats a hundred improvised drafts.

## Asset types

| Type | What it holds | Fed to |
|---|---|---|
| **模板 profile** | Structure skeleton, fonts/sizes/margins, heading numbering, 称谓与落款, date format | `doc-draft`, `doc-revise` |
| **术语与称谓表** | 机构全称/简称, 领导职务, 系统与项目正式名称, 固定译名 | everything that writes |
| **措辞库** | Stock phrases, 禁用词 (words the unit never uses), approved formulations | `doc-draft`, `doc-revise` |
| **样例登记** | Paths to past approved documents (the raw material), not copies | profile extraction |

## Building a profile — extraction, not invention

Input: 1–3 real artifacts the user confirms are representative. Extract each dimension separately, then confirm:

1. **结构骨架** — section list in order, what each section contains, typical length.
2. **格式参数** — font/size per role (标题/正文/表格), line spacing, margins, header/footer, page numbering. Read these from the file with tools; never guess a parameter you can measure.
3. **用语特征** — 称谓 (who is called what), 落款 form, date format, recurring phrases, noticeable taboos.
4. **适用边界** — which document types this profile applies to; one unit often has several (内部周报 ≠ 上报公文).

Write the profile with REQUIRED slots: `适用场景 / 结构骨架 / 格式参数表 / 称谓与落款 / 用语特征 / 样例路径`. Then **show the extracted profile to the user for confirmation** — an asset is recorded only after the user says it matches. Extraction without confirmation is assumption with a file extension.

## Where assets live

Workspace-local, in `docs/办公资产/`:

```
docs/办公资产/
├── 索引.md            # one line per asset: name, type, applies-to, updated date
├── profiles/          # one profile per file, named 模板-<场景>.md
├── 术语表.md
└── 措辞库.md
```

Every asset lands on disk **and** in `索引.md` — not registered is not saved (same spine as all SuperOffice artifacts).

## Using assets — the contract other skills rely on

- `doc-draft` consults `索引.md` before asking the user for a template; an existing profile **wins over** generic structure primitives.
- Assets are **default, not law**: when the user overrides, the instruction wins; offer to update the profile if the change looks permanent.
- Stale profiles are worse than none — when the user's feedback contradicts a profile ("现在不用这个抬头了"), update the asset in the same turn.

## Privacy rule

Assets contain internal names, titles, and business details. They stay in the workspace, never leave it — not into reports, not into examples for other people, not into cloud services. Redact titles/names when a profile excerpt must be shown somewhere else.

## Rationalizations

| Excuse | Reality |
|--------|---------|
| "先记在对话里，回头再存" | Conversation is not storage. Unsaved by end of turn = lost. |
| "格式参数我看一眼就能写出来" | Measure, don't recall. Fonts and margins guessed from memory are wrong in ways nobody notices until printing. |
| "这份样例应该有代表性" | "Should be" is the user's call, not yours. One confirmation question buys months of correct drafts. |
