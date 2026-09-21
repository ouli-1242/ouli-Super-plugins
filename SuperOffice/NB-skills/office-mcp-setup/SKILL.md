---
name: office-mcp-setup
description: "Use when the user asks to configure or install MCP servers or CLI tool integrations for office work - \"配置MCP\", \"装个office MCP\", \"让AI能操控WPS\", \"配置文档解析\", \"需要装什么才能让AI操作WPS\", or on first-time setup of SuperOffice on a machine. Diagnoses whether an MCP is needed at all (most document tasks are not), then selects from the vetted catalog (`references/mcp-catalog.md`). NOT for using an already-configured tool (verb skills, wps-cli), NOT for software development work (use the SuperWork pack)."
---
# Office MCP Setup

## Purpose

Get the office environment ready so the verb skills can do real work — starting from the diagnosis that **most office tasks need no MCP at all**.

## When to Use / Not Use

- Use: the user asks to configure/install MCP servers or CLI integrations for office work; first-time setup on a machine.
- Do NOT use: using an already-configured tool (the verb skills, wps-cli); software development work (the SuperWork pack).

## Capability Boundary

- CAN: diagnose the need, inventory the environment, select from the vetted catalog, write configs, verify connections, register the setup.
- CANNOT: configure on a hunch ("以后肯定用得上"); report "配置好了" on an unverified entry; echo credentials into the conversation.
- Depends on: the vetted catalog (`references/mcp-catalog.md`); the agent's own MCP config format; wps-cli installation when selected.

## Input Contract

- Required: what the user actually wants to do.
- Optional: OS/Office versions, target agent, existing MCP entries.
- Missing behavior: ask what task the tool should enable BEFORE configuring — the task decides the tool, never the reverse.

## Output Contract

- Only when one of the three qualifying cases holds: a configured entry in the agent's own config format, a verified connection (tool listing + one real minimal operation), and a row in `docs/环境清单.md` (date, machine, agent, entries, credential **paths only**, never values). Otherwise the deliverable is the statement "no MCP is needed for this".

## Constraints and Prohibitions

- **Only three cases where an MCP wins:**
  1. **Control a running office app** — recalculate Excel formulas (openpyxl writes formulas but never computes them), refresh Word fields/TOC/page numbers, operate the document the user has open, export via the app's engine → WPS-control MCPs. Closed file + plain read/write → no MCP.
  2. **Parse many old files into context** — batch-convert Office/PDF archives → markitdown-mcp. Single file → no MCP, read it directly.
  3. **Talk to an external service** (IM channels, mail, cloud docs — Feishu/WeCom/DingTalk). **Pending: intentionally not configured in v1.0.0**; configure only when the user explicitly asks.
  Anything else → tell the user no MCP is needed and stop.
- **Inventory before configuring**: OS and Office suite/version; which agent this configures (each has its own config format and registration CLI — confirm before writing); existing MCP servers (list before adding; never duplicate a working entry).
- **Selection quick-reference** (full catalog: `references/mcp-catalog.md`): WPS installed + live control → **wps-cli** (COM, JSON output, built-in MCP); MS Office + live control → **OfficeMCP**; batch parsing → **markitdown-mcp**.
- **Credentials**: keys go only into the config file or an env file it references — never into the conversation.
- **A configured MCP is not a working MCP**: after every entry, trigger the server's tool listing through the agent and run one real minimal operation (scratch document, tiny conversion). Verification fails → check the server's log, fix, re-verify. Never report "配置好了" on an unverified entry.
- **Rationalizations kill the rule** — the observed excuses, failure patterns and their counters: `references/rationalizations.md`.
- Prohibited: "MCP 多配几个总没错" (every entry is a permanent failure surface and a discovery-slot cost — configure the need, not the catalog).

## Acceptance Criteria

- Configured entries correspond 1:1 to diagnosed needs; every entry verified by tool listing + one real operation; setup registered in `docs/环境清单.md`.
- Self-check: does each entry trace to one of the three qualifying cases? Did I run one real operation through it?

## Failure and Escalation

- Verification fails after a fix attempt → remove the entry or leave it disabled and say so; a broken entry is worse than none.
- Prerequisite missing (wps-cli itself, Python/pywin32) → install or route to the wps-cli skill's environment section first.

## Cost and Latency Budget

- One diagnosis, one config write, one verification per entry. Over budget: configure the highest-value entry first; the rest wait for need.

## Examples

- Positive: user wants live formula recalculation in open workbooks → wps-cli selected → installed → MCP registered → tool listing confirmed → a scratch workbook recalculated → logged in 环境清单.
- Negative: "先把飞书 MCP 配上，以后发消息用" — pending category, not configured without an explicit ask.
- Edge: "帮我解析这份 PDF" (one file) → no MCP needed; read it directly.

## Evaluation and Observability

- Metrics: entries without a diagnosed need (target 0), unverified "配置好了" claims (target 0), duplicate entries.
- Log: `docs/环境清单.md` is the registry — it makes the setup reproducible on a new machine.

## References (L2, load on demand)

- Observed excuses and red flags with counters: `references/rationalizations.md`
