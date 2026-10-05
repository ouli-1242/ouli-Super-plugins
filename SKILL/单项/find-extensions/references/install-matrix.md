# Install & Verify Matrix by Agent

Detect which agents the user has installed first (see SKILL.md), then target only those with each agent's native mechanism. `npx skills add <pkg>@<skill> -a <agent>` targets the correct path automatically; `-g` = user-level, `-y` = skip prompts.

## Install Matrix

| Agent | Skills | MCP servers | Plugins |
| --- | --- | --- | --- |
| **Claude Code** | `npx skills add <pkg>@<skill> -a claude-code` (→ `.claude/skills/` project, `~/.claude/skills/` user) | `claude mcp add <name> <cmd> [args]` (stdio) or `claude mcp add --transport http <name> <url>` | `claude plugin marketplace add <owner/repo>` + `claude plugin install <name>@<marketplace>` |
| **Codex CLI** | `npx skills add <pkg>@<skill> -a codex`; skills CLI installs to `.agents/skills/` (project) / `~/.codex/skills/` (global with `-g`), while Codex docs also scan `~/.agents/skills/` — verify the path Codex actually scans | add a `[mcp_servers.<name>]` table to `~/.codex/config.toml` (or project-scoped `.codex/config.toml`) | OpenAI plugin system (universal plugin directory) |
| **Cursor** | `npx skills add <pkg>@<skill> -a cursor` (→ `.agents/skills/` project, `~/.cursor/skills/` user) | add an `mcpServers` entry to `~/.cursor/mcp.json` (user) or `.cursor/mcp.json` (project): `command`/`args` for stdio, `url` for streamable-http | in-app Marketplace (Extensions view) |
| **OpenCode** | `npx skills add <pkg>@<skill> -a opencode`; also `.agents/skills/` project, `~/.config/opencode/skills/` user | add an `mcp` block to `opencode.json` (project or `~/.config/opencode/opencode.json`) | — |
| **Hermes** | `npx skills add <pkg>@<skill> -a hermes-agent` (→ `.hermes/skills/` project, `~/.hermes/skills/` user); browse installed ones with `/skills` | `hermes mcp` (interactive) / `hermes mcp install <name>`; config lives in `~/.hermes/config.yaml` under `mcp_servers` | — |

Notes:
- Hermes is compatible with the agentskills.io standard.
- Codex skills must have both `name` and `description` frontmatter to be picked up.

## Verify It Works (per Agent)

Confirm the extension actually loaded before closing the loop:

| Agent | How to verify |
| --- | --- |
| **Claude Code** | `claude mcp list`; `/plugin list` in REPL; skill files present under `.claude/skills/` |
| **Codex CLI** | restart Codex — skills appear in the `$`/`/skills` selector; MCP server shows as a `[mcp_servers.<name>]` table in `~/.codex/config.toml` and its tools load at startup |
| **Cursor** | Settings → Skills / MCP / Agents pages; MCP shows connected, then run one real invocation as a smoke test |
| **OpenCode** | `opencode` TUI: agents listed in the `@` menu, MCP tools appear in the tool list |
| **Hermes** | `/skills` lists the skill; `hermes mcp` shows the server as `enabled`; trigger the tool once |

If something is missing, check the agent's skill/plugin load path before assuming the install failed.