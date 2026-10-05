# Search Channels & Manual Commands

Reference for SKILL.md Step 1. Read this when the scripted path (`search.mjs`) is unavailable, or for deep fallbacks (GitHub code search, awesome lists) the script doesn't cover.

## Skills — dual source (skills.sh + claudemarketplaces.com)

`search.mjs skills` queries **both** sources in parallel, merges by repo+name, and keeps the entry with more non-null fields (so claudemarketplaces' `stars`/`installs` fill skills.sh's gaps):

1. **skills.sh** (primary): `https://skills.sh/api/search?q=<q>&limit=<n>[&owner=<o>]` — the same endpoint the `npx skills` CLI uses, without the fzf TUI. Supports `--owner` filtering.
2. **claudemarketplaces.com** (supplementary): `https://claudemarketplaces.com/api/skills` — 23,600+ skills, **ships with `installs` + `stars`** (no `enrich` step needed). No server-side search param, so the script pulls the full list (~13MB) and filters client-side by name/description term match. `--owner` skips this source to avoid noise.

Check the [skills.sh leaderboard](https://skills.sh/) first for well-known skills (e.g. `vercel-labs/agent-skills`, `anthropics/skills`). The [claudemarketplaces.com/skills](https://claudemarketplaces.com/skills) page is the broader directory (23K+ vs skills.sh's smaller curated set).

Manual fallback (when script unavailable):

```bash
npx skills find [query] [--owner <owner>]   # fzf TUI — may hang in non-TTY
# Or hit the API directly:
curl -s "https://skills.sh/api/search?q=<q>&limit=20" | node -e "let d='';process.stdin.on('data',c=>d+=c).on('end',()=>console.log(JSON.stringify(JSON.parse(d).skills,null,2)))"
```

Other useful `npx skills` commands: `add <package>` (install), `list` (installed), `use <source>` (use without installing), `update`, `init [name]` (scaffold).

## MCP Servers — three sources (registry + glama.ai + claudemarketplaces.com)

`search.mjs mcp` queries **all three** sources in parallel, merges by repo+name (keeping the entry with more non-null fields), and sorts by `stars` descending so popular MCPs surface first:

1. **Official registry** (primary): `https://registry.modelcontextprotocol.io/v0/servers?search=<query>` — keyless JSON, filters to `active` + `isLatest: true`. Supports server-side search.
2. **glama.ai API** (supplementary): `https://glama.ai/api/mcp/v1/servers?query=<query>` — public JSON (no token), 50K+ servers, superset of registry + awesome-mcp + community submissions. Supports server-side search. Fills gaps when the registry returns 0.
3. **claudemarketplaces.com** (`https://claudemarketplaces.com/api/mcp-servers`): 12,700+ servers, **ships with `effectiveStars`** (no `enrich` step needed). No server-side search/pagination — returns the top 1000 by rank; the script filters client-side by `displayName`+`summary`+`installLabel` (not `searchText`, which contains the `io.github.` name prefix and would match every MCP on broad queries like "github"). `name` uses the `io.github.<owner>/<repo>` format (same as registry) for cross-source dedupe.

**Recall caveat**: the registry matches keywords literally, not semantically — broad queries like "css design system" or "browser testing" often return 0 results. Prefer concrete tool/protocol names ("playwright", "filesystem", "github"). The script (`search.mjs mcp`) auto-expands multi-word queries that return 0: it splits on whitespace, searches each term across all three sources, applies intent filtering (keeps results whose `description` hits ≥2 of the original terms), and merges. Check stderr for the log. If still empty, try synonyms.

**Manual fallback** (when script unavailable):

```bash
curl -s "https://registry.modelcontextprotocol.io/v0/servers?search=<q>" | node -e "let d='';process.stdin.on('data',c=>d+=c).on('end',()=>{const j=JSON.parse(d);const out=(j.servers||[]).filter(e=>{const m=e._meta||{};const o=m['io.modelcontextprotocol.registry/official']||{};return (o.status||m.status)==='active' && e.isLatest!==false;});console.log(JSON.stringify(out,null,2))})"
```

**Pagination**: the registry returns 30 items/page via `metadata.nextCursor`. Append `&cursor=<nextCursor>` from the previous response and loop until `nextCursor` is absent.

**Field-path caveat**: the status key contains a `/` — `io.modelcontextprotocol.registry/official.status`. Access it as a **plain object key** (`m['io.modelcontextprotocol.registry/official'].status`), never as a JSONPath string — `/` is a path separator in JSONPath libraries and will silently misparse.

## Plugins — three source types

`search.mjs plugins "<query>"` fetches all three source types, scores each candidate (name hit 100, description same-field-AND 20, keywords 15, name-exact +30), and returns results **sorted by score descending**. All sources are collected before slicing (no early cap), so a busy first source can't starve the later ones.

1. **marketplace.json** (per-plugin entries): three repos — `anthropics/claude-plugins-official`, `anthropics/claude-plugins-community`, `wshobson/agents`. Raw GitHub first, jsDelivr CDN mirror on failure. Each entry is a single plugin; `installCommand` = `claude plugin marketplace add <owner/repo>` (`.git` stripped).
2. **pluginmarketplace.ai API** (`https://pluginmarketplace.ai/api/plugins`): ~50 curated plugins, **ships with `installCount`** (marketplace.json lacks it). `installCommand` taken verbatim from the API when present.
3. **claudemarketplaces.com** (`https://claudemarketplaces.com/api/marketplaces`): 2,600+ **marketplace repositories** (repo-level, not single plugins), **ships with `stars`** + `pluginCount` + `categories` + `pluginKeywords`. `name` = repo, `installCommand` = `claude plugin marketplace add <repo>` (adds the whole marketplace to access all its plugins). Matched via repo name + description + pluginKeywords + categories.

Manual / deep fallbacks (when script unavailable or for marketplaces the script doesn't index):

1. **Official marketplace**: fetch `https://raw.githubusercontent.com/anthropics/claude-plugins-official/main/.claude-plugin/marketplace.json`, scan `plugins[]`. (Community: `anthropics/claude-plugins-community`. Third bundle: `wshobson/agents`.)
   - **CN/slow-network backup**: if `raw.githubusercontent.com` times out, use the jsDelivr CDN mirror — replace `https://raw.githubusercontent.com/<owner>/<repo>/<branch>/<path>` with `https://cdn.jsdelivr.net/gh/<owner>/<repo>@<branch>/<path>`. Example: `https://cdn.jsdelivr.net/gh/anthropics/claude-plugins-official@main/.claude-plugin/marketplace.json`.
   - **Marketplace schema**: each plugin has `{name, description, author, category, source, homepage}`; the repo URL lives in `source.url` (`source` is an object `{source, url, [path, ref], sha}`), **not** a top-level `repository` field. There is no `agents[]` field in the official marketplace.
2. **Browse the directories directly**: [pluginmarketplace.ai](https://pluginmarketplace.ai/) (per-plugin, with install counts), [claudemarketplaces.com/marketplaces](https://claudemarketplaces.com/marketplaces) (marketplace repos, with stars), [claudemarketplaces.com/plugins](https://claudemarketplaces.com/plugins).
3. **GitHub code search**: `path:.claude-plugin/marketplace.json` to discover community marketplaces, then fetch each candidate's `marketplace.json` and filter by description/keywords.
4. **Curated bundles** (e.g. `obra/superpowers`) ship skills + hooks as one-stop kits. `npx skills find` also surfaces skills inside plugin manifests — run it for plugin-adjacent searches too.

## Deep fallbacks — GitHub topics, awesome lists

When the three scripted channels (skills / MCP / plugins) don't surface enough, expand to:

- **GitHub topics** (sorted by stars): `https://github.com/topics/mcp-server`, `https://github.com/topics/claude-plugins`, `https://github.com/topics/agent-skills`.
- **Awesome lists**: search `awesome-mcp`, `awesome-claude-skills`, etc.
- **Other MCP directories** (not scripted, manual browse): https://mcp.so/search?q=<query>, https://smithery.ai/.

## Cross-platform parsing rules

- All manual JSON parsing uses `node` (available wherever `npx skills` runs). Do **not** use `python3` (absent on Windows) or `grep -P` (PCRE support is unstable in Git Bash).
- On pure PowerShell without curl, replace `curl -s <url>` with `Invoke-WebRequest -Uri <url> -UseBasicParsing | Select -ExpandProperty Content`.
