# MCP Catalog — vetted entries for office work

Companion reference for `office-mcp-setup`. Status as of 2026-09. Entries marked **Pending** are vetted but intentionally not configured in v1.0.0 — configure only on explicit user request.

## 1. Control a running office app

The only reason to reach for this category: computing formulas, refreshing fields/TOC/page numbers, or operating a document that is currently open. Plain closed-file read/write needs no MCP.

| Entry | Covers | Mechanics | Notes |
|---|---|---|---|
| **wps-cli** (github.com/jjchen17/wps-cli, ~50★) | WPS Writer/Calc/Impress/PDF | Windows COM driving a real WPS instance; 76 commands; JSON output; built-in MCP server; resident mode makes consecutive ops 5–10× faster | Preferred when WPS is installed. CLI usage has its own `wps-cli` skill (adopted from upstream). One-command MCP registration: `wps mcp install --target <agent>`; verify install with `wps version`, registration with `wps mcp status` |
| **OfficeMCP** (github.com/OfficeMCP) | Word, Excel, PowerPoint, Access, OneNote, Visio, Project, WPS | Windows COM automation of the real applications | Preferred for MS Office environments; broadest app coverage. ⚠ upstream ships an unrestricted `RunPython` tool — audit before enabling |

**Do not use for this category:** python-docx/openpyxl-based servers (see "Rejected" below) — they cannot touch a running instance or compute formulas.

## 2. Parse files into context

| Entry | Covers | Mechanics | Notes |
|---|---|---|---|
| **markitdown-mcp** (Microsoft official) | Office docs, PDF, images → Markdown | MCP wrapper around Microsoft's markitdown converter | The parser for `doc-intake` and `doc-asset` batch ingestion. Single files: read directly, no MCP |
| **glmocr-table** (zai-org/GLM-OCR official skill, ~7.4k★) | scanned pages / photo tables → Markdown / Excel, merged cells handled | GLM-OCR API key (智谱开放平台) | The OCR engine `file-ops` routes to; set the key before first use |

## 3. External service channels — **Pending, v1.0.0 does not configure**

| Entry | Covers | Credential | When the user asks |
|---|---|---|---|
| **lark-openapi-mcp** (larksuite official, github.com/larksuite/lark-openapi-mcp) | Feishu/Lark: cloud docs, calendar, messages, groups, Bitable | Feishu open-platform app (App ID/Secret) | "接飞书" — official, covers the whole platform |
| **wecom-cli** (WecomTeam official, github.com/WecomTeam/wecom-cli, ~3.1k★, very active) | WeCom: mail send/reply/search, meetings (book/minutes/transcript), calendar, docs, online sheets | WeCom open-platform bot (Bot ID/Secret) | "接企业微信" — ships its own agent skill; adopt it, don't rewrite |
| **claude-code-dingtalk-mcp** (github.com/sfyyy/claude-code-dingtalk-mcp) | DingTalk group robot: one-way text/Markdown/link notifications | Webhook token | Only "往钉钉群发通知"; no read/inbox capability |

## Rejected (with reasons — do not admit later without new evidence)

- **GongRzhe/Office-Word-MCP-Server, Office-PowerPoint-MCP-Server** (the community's most visible office MCPs) — python-docx/python-pptx tool surfaces, fully redundant with the document skills already installed. Admitting them buys zero capability and costs a permanent failure surface.
- **rcarmo/python-office-mcp-server** — self-described sanitized prototype.
- **ForLegalAI/mcp-ms-office-documents, jenstangen1/pptx-xlsx-mcp** — same overlap class, small communities.
- **lc2panda/wps-skills (~607★)** — capable (224 tools) but requires a WPS add-in plus WebSocket bridge; the heaviest dependency chain in the space. Revisit only if wps-cli's COM route proves insufficient.
- **Composio gmail/outlook suites** — require the Composio platform account and API keys; the privacy/local-control tradeoff is wrong for office documents.

## Selection quick-reference

```
单位 IM 是飞书？         → lark-openapi-mcp        (Pending)
单位 IM 是企业微信？     → wecom-cli               (Pending)
要操控打开中的文档/重算？ → WPS→wps-cli；MS Office→OfficeMCP
只发钉钉群通知？         → claude-code-dingtalk-mcp (Pending)
批量解析旧文档喂上下文？  → markitdown-mcp
以上都不是              → 不配；document-skills + Python 库已覆盖
```

## Credential rules

Keys and secrets live only in the MCP config file or an env file it references. Never in conversation, never in documents, never in `docs/环境清单.md` — the register records credential **locations** (paths), never values.
