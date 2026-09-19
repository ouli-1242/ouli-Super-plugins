---
name: doc-asset
description: "Use when the user wants the agent to remember their organization's or personal document conventions - extracting a reusable profile from a real template or past document, saving terminology and title conventions, building a stock-phrase library, \"记住我们单位的模板\", \"以后都按这个格式\", \"把这份样例存下来\", \"记一下我们的术语\". NOT for one-off drafting (doc-draft, which consults assets), NOT for summarizing a document for reading (doc-intake)."
---
# Doc Asset — where specialization lives

## Purpose

Persist the organization's/personal document conventions as **assets extracted from real artifacts** — profiles, terminology, phrasing — so every drafting/revision skill gets smarter with use. One good profile beats a hundred improvised drafts.

## When to Use / Not Use

- Use: the user wants the agent to remember unit/personal conventions — extract a profile from a real template, save terminology/titles, build a stock-phrase library, register a past sample.
- Do NOT use: one-off drafting (doc-draft consults assets); summarizing a document for reading (doc-intake).

## Capability Boundary

- CAN: extract profiles from representative artifacts, confirm with the user, store and index assets, update stale ones in-turn.
- CANNOT: record an asset the user has not confirmed; recall format parameters from memory (measure them).
- Depends on: file-reading tooling to measure format parameters; `docs/办公资产/` storage spine.

## Input Contract

- Required: 1–3 real artifacts the user confirms are representative (template, past approved document).
- Optional: terminology lists, forbidden-phrase lists.
- Missing behavior: no representative artifact → ask for one; extraction without a real source is invention with a file extension.

## Output Contract

- Assets in `docs/办公资产/`, workspace-local:
  ```
  docs/办公资产/
  ├── 索引.md            # one line per asset: name, type, applies-to, updated date
  ├── profiles/          # one profile per file, named 模板-<场景>.md
  ├── 术语表.md
  └── 措辞库.md
  ```
- **Profile required slots:** `适用场景 / 结构骨架 / 格式参数表 / 称谓与落款 / 用语特征 / 样例路径`.
- Asset types: 模板 profile (structure skeleton, fonts/sizes/margins, heading numbering, 称谓与落款, date format) → doc-draft/doc-revise; 术语与称谓表 (机构全称/简称, 领导职务, 系统与项目正式名称, 固定译名) → everything that writes; 措辞库 (stock phrases, 禁用词, approved formulations); 样例登记 (paths to past approved documents, not copies).

## Constraints and Prohibitions

- **Extraction, not invention**: extract each dimension separately — structure skeleton (section list, contents, typical length); format parameters **measured with tools from the file** (font/size per role, line spacing, margins, header/footer, page numbering — never guess a parameter you can measure); language traits (称谓, 落款 form, date format, recurring phrases, taboos); **applicability boundary** (which document types — one unit often has several; 内部周报 ≠ 上报公文).
- **An asset is recorded only after the user confirms it matches** — show the extracted profile; extraction without confirmation is assumption with a file extension.
- Every asset lands on disk **and** in `索引.md` — not registered is not saved.
- **Assets are default, not law**: the user's instruction wins; offer to update the profile when the change looks permanent. **Stale profiles are worse than none** — contradicting feedback updates the asset in the same turn.
- **Privacy rule**: assets contain internal names, titles, business details — they stay in the workspace, never into reports, examples for others, or cloud services; redact when an excerpt must be shown elsewhere.
- Prohibited: "先记在对话里，回头再存" (conversation is not storage); "这份样例应该有代表性" (that is the user's call — one confirmation question buys months of correct drafts).

## Acceptance Criteria

- Asset on disk + indexed, user-confirmed, measured parameters (not recalled), applicability boundary stated.
- Self-check: was every format parameter measured from the file? Did the user confirm before recording?

## Failure and Escalation

- User rejects the extracted profile → discard the extraction, ask what is wrong; do not record a "probably right" version.
- Profile contradicted by feedback → update in the same turn.

## Cost and Latency Budget

- One extraction pass per artifact, one confirmation round. Over budget: extract structure + terminology first (highest reuse), format parameters next.

## Examples

- Positive: 红头文件 profile extracted from last year's approved document → fonts measured via openpyxl/docx inspection → user confirms → indexed → doc-draft uses it for every future 公文.
- Negative: profile written from memory of "what the unit's documents look like".
- Edge: the boss says "现在不用这个抬头了" → profile updated in the same turn, 索引.md date bumped.

## Evaluation and Observability

- Metrics: drafts deviating from a confirmed profile (target 0), unconfirmed assets on disk (target 0), stale-profile corrections.
- Log: 索引.md is the registry; updates dated per asset.
