---
name: find-extensions
description: Helps users discover and install agent extensions — skills, plugins, MCP servers — when they ask "how do I do X", "find a skill/plugin/MCP for X", "is there a skill that can...", or express interest in extending agent capabilities.
---

# Find Agent Extensions

## Step 1 — Search

Before searching, scan the [skills.sh leaderboard](https://skills.sh/) — prefer high-install or official-publisher skills to avoid low-quality results. Official publishers: `vercel-labs`, `anthropics`, `modelcontextprotocol`, `microsoft`. Use specific keywords ("react testing" not "testing") to reduce noise.

`node references/search.mjs <skills|mcp|plugins> "<query>"` → JSON array. **Always append `--table`** unless piping to `merge`/`enrich` (Markdown table is ~10x smaller than JSON, ~1KB vs ~15KB per query). Flags: `--max N` (default 10), `--table` (Markdown, saves context), `--owner <o>` (skills only), `--pages N` (MCP only). Slim JSON omits `null` fields; `--full` keeps all.

Multi-word queries: watch stderr for weak-match warnings — verify relevance before recommending. `enrich` is idempotent (auto-skips repos that already have `stars`).

Multi-channel pipeline (dedupe + enrich in one go; `$( … )` grouping works in both PowerShell and bash):

```bash
$( node references/search.mjs skills "x"; node references/search.mjs mcp "x"; node references/search.mjs plugins "x" ) | node references/search.mjs merge | node references/search.mjs enrich --table
```

If the pipeline errors (`merge` is not robust to empty/malformed channel output), run each channel separately.

Enrichment fills `stars`/`updatedAt` from GitHub API (60 req/hour without token, 5000 with `GITHUB_TOKEN`). On rate-limit it keeps fetched values, leaves rest `null` — then rely on `installCount` and official publishers (list above) instead of stars. Manual fallbacks (GitHub topics, awesome lists): `references/channels.md`.

## Step 2 — Rank into two tiers

| Tier | Criteria |
| --- | --- |
| **Recommended** | 1K+ installs · 100+ stars · official publisher · MCP updated within last year |
| **Worth a try** | Below the bar but matches query — separate subsection, each row gets a one-line risk note |

Don't silently drop low-popularity matches: when every result is below the bar (common in niche searches), *Worth a try* is the main output.

**Pre-install check**: does the MCP demand broad permissions? Is there shell/filesystem write beyond the stated task? Does the skill rely on `allowed-tools`/hooks (support varies by agent — see `references/compatibility.md`)?

## Step 3 — Present & Install

Markdown table per tier: `Name | What it does | Source · popularity | Install | Link`. Top 8 per tier. `installCommand` defaults to Claude Code syntax; if agent is Codex/Cursor/OpenCode/Hermes, substitute from `references/install-matrix.md`.

Detect installed agents first: `command -v claude codex cursor opencode hermes` (PowerShell: `Get-Command`).

Install: `npx skills add <pkg>@<skill> -a <agent>` (`-g` user-level, `-y` skip prompts). Skills use agent-agnostic `npx`.

If no results: tell the user no existing extension fits, offer to help directly or scaffold with `npx skills init`.

## Type guidance (when unsure)

- **Skill** — teach the agent a workflow/domain (reviews, docs, best-practices)
- **Plugin** — a capability kit bundling tools together
- **MCP server** — give the agent access to an external API/service

When unsure about the type, ask the user which of the three they want.

A plugin may bundle skills/MCP — if one channel returns empty, search the others.
