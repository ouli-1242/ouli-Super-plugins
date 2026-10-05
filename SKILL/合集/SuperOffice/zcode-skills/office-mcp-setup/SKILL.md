---
name: office-mcp-setup
description: "Use when the user asks to configure or install MCP servers or CLI tool integrations for office work - \"配置MCP\", \"装个office MCP\", \"让AI能操控WPS\", \"配置文档解析\", \"需要装什么才能让AI操作WPS\", or on first-time setup of SuperOffice on a machine. 中文信号：\"配置MCP\"\"装个office MCP\""
---
# Office MCP Setup

Get the office environment ready so the verb skills can do real work. The most important step is the first one: **most office tasks need no MCP at all** — reading and writing docx/xlsx/pptx files is handled by document skills through Python libraries. An MCP earns its place only when a Python library cannot reach the target.

## Step 1 — Diagnose whether an MCP is needed

Ask what the user actually wants to do, then match against the only three cases where an MCP wins:

1. **Control a running office app** — recalculate Excel formulas (libraries like openpyxl write formulas but do not compute them), refresh Word fields/TOC/page numbers, operate the document the user has open, export via the app's own engine → WPS-control MCPs. If the file is closed and plain read/write is enough: no MCP.
2. **Parse many old files into context** — batch-convert Office/PDF archives to Markdown for intake or asset-building → `markitdown-mcp`. For a single file: no MCP, read it directly.
3. **Talk to an external service** — IM channels, mail, cloud docs (Feishu, WeCom, DingTalk). **Pending: intentionally not configured in v1.0.0.** The catalog keeps the vetted entries; configure them only when the user explicitly asks.

Anything else → tell the user no MCP is needed and stop. Over-configuring wastes discovery slots and adds failure surfaces.

## Step 2 — Inventory the environment

- OS and Office suite: WPS or Microsoft Office, which version.
- Which agent this configures (ZCode / Claude Code / Codex / other) — each has its own MCP config format and its own CLI for registration. Confirm before writing anything.
- Existing MCP servers (list before adding; never duplicate a working entry).

## Step 3 — Select from the vetted catalog

Selection quick-reference (full catalog with verify commands: `references/mcp-catalog.md`):

| Need | Pick | Credential |
|---|---|---|
| WPS installed, need live control | **wps-cli** (COM, JSON output, built-in MCP; its CLI usage has its own `wps-cli` skill) | none |
| MS Office installed, need live control | **OfficeMCP** (COM, covers Word/Excel/PPT/WPS) | none |
| Batch parse old Office/PDF files | **markitdown-mcp** (Microsoft official) | none |

## Step 4 — Configure

Write the MCP entry into the agent's config in that agent's format. Install prerequisites first (e.g. wps-cli itself — see the `wps-cli` skill's environment section). For entries needing credentials: put keys **only** into the config file or an env file it references; never echo them into the conversation.

## Step 5 — Verify the connection

A configured MCP is not a working MCP. After every entry: trigger the server's tool listing through the agent (e.g. restart the session / run the agent's MCP list command) and confirm the expected tools appear. Then run one real minimal operation (open a scratch document, convert a tiny file). If verification fails: check the server's log, fix, re-verify. Never report "配置好了" on an unverified entry.

## Step 6 — Register

Record what was configured — date, machine, agent, entries, credential locations (paths only, never values) — in the workspace's `docs/环境清单.md` (create it if missing). This is what makes the setup reproducible on a new machine.

## Rationalizations

| Excuse | Reality |
|--------|---------|
| "MCP 多配几个总没错" | Every entry is a permanent failure surface and a discovery-slot cost. Configure the need, not the catalog. |
| "先配上以后肯定用得上" | Unverified-unused entries rot silently. Configure when the need arrives. |
| "配置完就算完成" | An unverified config is a guess. Step 5 is part of the task. |
