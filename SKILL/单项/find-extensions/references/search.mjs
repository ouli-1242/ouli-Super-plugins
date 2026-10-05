#!/usr/bin/env node
// find-extensions skill 的搜索/解析/补全助手。
// 零依赖：仅用 node:https，兼容 Node 14+（不依赖全局 fetch）。
// 跨平台：Windows / Git Bash / POSIX 均可运行。
//
// 用法:
//   node search.mjs skills  <query> [--owner <owner>] [--max M]
//   node search.mjs mcp     <query> [--pages N] [--max M]
//   node search.mjs plugins <query> [--max M]        # plugin（marketplace.json）
//   node search.mjs enrich                        # 从 stdin 读 JSON 数组，补 stars/updatedAt
//   node search.mjs merge                         # 从 stdin 读多渠道 JSON，跨渠道去重
//
// 管道示例:
//   node search.mjs skills "testing" | node search.mjs enrich
//   node search.mjs mcp "github" --pages 2 | node search.mjs enrich
//   ( node search.mjs skills "x"; node search.mjs mcp "x"; node search.mjs plugins "x" ) | node search.mjs merge | node search.mjs enrich
//
// 输出: stdout 一个 JSON 数组，每个元素遵循统一 schema:
//   { type, name, description, source, repo, stars, installCount,
//     version, updatedAt, url, installCommand }
// slim 模式（默认）省略值为 null 的字段以省上下文；--full 保留全部字段（含 null）。
// 内部 normalize() 仍以 null 填充，便于 enrich 等下游统一处理。

import https from 'node:https';
import { URL } from 'node:url';

const nullIfEmpty = (v) => (v == null ? null : v);

// 统一 schema 构造器：保证字段集合稳定
function normalize(partial) {
  return {
    type: partial.type ?? null,
    name: partial.name ?? null,
    description: partial.description ?? null,
    source: partial.source ?? null,
    repo: partial.repo ?? null,
    stars: nullIfEmpty(partial.stars),
    installCount: nullIfEmpty(partial.installCount),
    version: partial.version ?? null,
    updatedAt: partial.updatedAt ?? null,
    url: partial.url ?? null,
    installCommand: partial.installCommand ?? null,
  };
}

// GET JSON，支持重定向、超时、自定义 headers
function getJson(url, { timeout = 30000, headers = {} } = {}) {
  return new Promise((resolve, reject) => {
    const u = new URL(url);
    const req = https.get(
      {
        hostname: u.hostname,
        path: u.pathname + u.search,
        headers: { Accept: 'application/json', 'User-Agent': 'find-extensions/1.0', ...headers },
        timeout,
      },
      (res) => {
        // 跟随重定向
        if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
          res.resume();
          return resolve(getJson(res.headers.location, { timeout, headers }));
        }
        if (res.statusCode !== 200) {
          res.resume();
          return reject(new Error(`HTTP ${res.statusCode} for ${url}`));
        }
        let data = '';
        res.setEncoding('utf8');
        res.on('data', (c) => (data += c));
        res.on('end', () => {
          try {
            resolve(JSON.parse(data));
          } catch (e) {
            reject(new Error(`Invalid JSON from ${url}: ${e.message}`));
          }
        });
      }
    );
    req.on('timeout', () => req.destroy(new Error(`timeout after ${timeout}ms: ${url}`)));
    req.on('error', reject);
  });
}

// 带重试的 GET JSON：仅对网络错误/超时重试（非 4xx），指数退避 1s→3s，默认重试 1 次。
// 用于 skills.sh/mcp 搜索，缓解上游偶发不稳定。
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function getJsonRetry(url, opts = {}, retries = 1) {
  try {
    return await getJson(url, opts);
  } catch (e) {
    if (retries <= 0) throw e;
    const wait = 1000 * (2 - retries); // retries=1 → 1000ms
    await sleep(wait);
    return getJsonRetry(url, opts, retries - 1);
  }
}

// GET JSON 同时返回 response headers（用于 GitHub 限流检测）
function getJsonWithHeaders(url, { timeout = 10000, headers = {} } = {}) {
  return new Promise((resolve, reject) => {
    const u = new URL(url);
    const req = https.get(
      {
        hostname: u.hostname,
        path: u.pathname + u.search,
        headers: { Accept: 'application/json', 'User-Agent': 'find-extensions/1.0', ...headers },
        timeout,
      },
      (res) => {
        if (res.statusCode !== 200) {
          res.resume();
          return resolve({ status: res.statusCode, headers: res.headers, body: null });
        }
        let data = '';
        res.setEncoding('utf8');
        res.on('data', (c) => (data += c));
        res.on('end', () => {
          try {
            resolve({ status: 200, headers: res.headers, body: JSON.parse(data) });
          } catch (e) {
            reject(new Error(`Invalid JSON from ${url}: ${e.message}`));
          }
        });
      }
    );
    req.on('timeout', () => req.destroy(new Error(`timeout after ${timeout}ms: ${url}`)));
    req.on('error', reject);
  });
}

// 容错的嵌套取值：按点号分割路径，但 key 内部的 '/' 视为普通字符
function pick(obj, ...keyPaths) {
  for (const path of keyPaths) {
    let cur = obj;
    for (const seg of path.split('.')) {
      if (cur == null || typeof cur !== 'object') {
        cur = undefined;
        break;
      }
      cur = cur[seg];
    }
    if (cur != null) return cur;
  }
  return undefined;
}

// 按 type:name 去重，保留先出现者
function dedupe(items) {
  const seen = new Set();
  const out = [];
  for (const it of items) {
    const k = `${it.type}:${String(it.name).toLowerCase()}`;
    if (seen.has(k)) continue;
    seen.add(k);
    out.push(it);
  }
  return out;
}

// 跨源去重：按 parseOwnerRepo(repo)+name 优先（同 GitHub repo 的同 名条目合并），
// fallback 到 type:name。同 key 保留非空字段更多的条目（richness 高者优先），
// 这样 claudemarketplaces.com（自带 stars+installs）能补全 skills.sh 的空缺，反之亦然。
const RICH_FIELDS = ['stars', 'installCount', 'description', 'updatedAt', 'version', 'url', 'installCommand'];
function richness(it) {
  let n = 0;
  for (const k of RICH_FIELDS) if (it[k] != null && it[k] !== '') n++;
  return n;
}
function dedupeRich(items) {
  const map = new Map();
  for (const it of items) {
    const ownerRepo = parseOwnerRepo(it.repo);
    const key = ownerRepo
      ? `repo:${ownerRepo}:${String(it.name).toLowerCase()}`
      : `${it.type}:${String(it.name).toLowerCase()}`;
    const prev = map.get(key);
    if (!prev || richness(it) > richness(prev)) map.set(key, it);
  }
  return [...map.values()];
}

// 从 repo URL 或 owner/repo 简写中解析出 owner/repo
function parseOwnerRepo(repo) {
  if (!repo) return null;
  const s = String(repo).trim();
  // owner/repo 简写（无斜杠路径，无协议）
  let m = s.match(/^([a-zA-Z0-9][\w.-]*)\/([a-zA-Z0-9][\w.-]*)(?:\.git)?$/);
  if (m) return `${m[1]}/${m[2]}`;
  // github URL：https://github.com/owner/repo 或 git+https://... 或 ssh
  m = s.match(/github\.com[/:]([\w.-]+)\/([\w.-]+?)(?:\.git)?(?:[/?#]|$)/i);
  if (m) return `${m[1]}/${m[2]}`;
  return null;
}

// ─── claudemarketplaces.com skills 目录（23K+ skills，自带 installs+stars，免 enrich） ───
// 全量拉取（无服务端 search 参数），客户端按 name/description 过滤。
async function fetchClaudeMarketplacesSkills(query, { max = 10 } = {}) {
  const body = await getJsonRetry('https://claudemarketplaces.com/api/skills', { timeout: 30000 });
  const skills = Array.isArray(body) ? body : [];
  const terms = String(query).toLowerCase().split(/\s+/).filter(Boolean);
  const cap = Math.max(max * 2, 20);
  const out = [];
  for (const s of skills) {
    const name = pick(s, 'name');
    if (!name) continue;
    const nm = String(name).toLowerCase();
    const desc = String(pick(s, 'description') || '').toLowerCase();
    // 客户端过滤：任一 term 命中 name 或 description（宽匹配，由 richness 排序兜底）
    const hit = terms.length === 0 || terms.some((t) => nm.includes(t) || desc.includes(t));
    if (!hit) continue;
    const repo = pick(s, 'repo');
    const id = pick(s, 'id'); // owner/repo/skill-name
    out.push(
      normalize({
        type: 'skill',
        name,
        description: pick(s, 'description'),
        source: 'claudemarketplaces.com',
        repo: repo ? `https://github.com/${repo}` : null,
        stars: pick(s, 'stars'),
        installCount: pick(s, 'installs'),
        version: null,
        updatedAt: pick(s, 'lastUpdated'),
        url: id ? `https://claudemarketplaces.com/skills/${id}` : null,
        installCommand: pick(s, 'installCommand'),
      })
    );
    if (out.length >= cap) break;
  }
  return out;
}

// ─── skills 搜索：skills.sh + claudemarketplaces.com 双源合并 ───
// skills.sh 为主源；claudemarketplaces.com 为补充源（覆盖更广 23K+，自带 stars+installs，免 enrich）。
// --owner 仅作用于 skills.sh（claudemarketplaces 无 owner 过滤，避免引入噪音）。
async function searchSkills(query, { owner, max = 10 } = {}) {
  const limit = Math.min(Math.max(max, 1), 100);
  const params = new URLSearchParams({ q: query, limit: String(limit) });
  if (owner) params.set('owner', owner);
  const shUrl = `https://skills.sh/api/search?${params.toString()}`;

  const [shRes, cmRes] = await Promise.all([
    getJsonRetry(shUrl, { timeout: 30000 })
      .then((body) => {
        const skills = pick(body, 'skills') || [];
        const out = [];
        for (const s of skills) {
          const name = pick(s, 'name', 'skillId');
          if (!name) continue;
          const slug = pick(s, 'id', 'slug');
          const source = pick(s, 'source') || '';
          out.push(
            normalize({
              type: 'skill',
              name,
              description: pick(s, 'description'), // API 通常不返回，留 null
              source: 'skills.sh',
              repo: source ? `https://github.com/${source}` : null,
              stars: null, // 需 enrich
              installCount: pick(s, 'installs'),
              version: null,
              updatedAt: null, // 需 enrich
              url: slug ? `https://skills.sh/${slug}` : null,
              installCommand: source ? `npx skills add ${source}@${name}` : null,
            })
          );
        }
        return out;
      })
      .catch((e) => {
        console.error(`[find-extensions] skills.sh: ${e.message}`);
        return [];
      }),
    owner
      ? Promise.resolve([]) // --owner 模式仅查 skills.sh
      : fetchClaudeMarketplacesSkills(query, { max }).catch((e) => {
          console.error(`[find-extensions] claudemarketplaces.com/skills: ${e.message}`);
          return [];
        }),
  ]);

  return dedupeRich([...shRes, ...cmRes]).slice(0, max);
}

// ─── MCP 官方 registry：自动翻页 + active/isLatest 过滤 + 字段容错 ───
// fetchMcpServers：单次 query 的翻页抓取 + 过滤，返回未去重的条目数组。
async function fetchMcpServers(query, { pages = 2, max = 10 } = {}) {
  const out = [];
  let cursor = null;
  for (let p = 0; p < pages; p++) {
    let url = `https://registry.modelcontextprotocol.io/v0/servers?search=${encodeURIComponent(query)}`;
    if (cursor) url += `&cursor=${encodeURIComponent(cursor)}`;
    const body = await getJsonRetry(url);
    const servers = pick(body, 'servers') || [];
    for (const entry of servers) {
      // entry 形如 { server: {...}, _meta: {...}, isLatest }
      // 兼容未嵌套的旧结构
      const s = pick(entry, 'server') || entry;
      const meta = pick(entry, '_meta') || {};
      // status key 含 '/'：必须作为对象 key 访问，不能用 JSONPath。
      // 同时尝试嵌套与扁平结构，兼容 registry 未来可能的字段调整。
      const official =
        pick(meta, 'io.modelcontextprotocol.registry/official') ||
        meta['io.modelcontextprotocol.registry/official'] ||
        {};
      const status = official.status ?? pick(meta, 'status');
      const isLatest = pick(entry, 'isLatest', 'is_latest');
      if (status && status !== 'active') continue;
      if (isLatest === false) continue;
      const name = pick(s, 'name');
      if (!name) continue;
      const repo = pick(s, 'repository.url', 'repository');
      out.push(
        normalize({
          type: 'mcp',
          name,
          description: pick(s, 'description'),
          source: 'modelcontextprotocol registry',
          repo,
          stars: null, // 需 enrich
          installCount: null,
          version: pick(s, 'version'),
          updatedAt: official.statusChangedAt ?? pick(meta, 'statusChangedAt', 'updatedAt'),
          url: repo || `https://registry.modelcontextprotocol.io/v0/servers/${encodeURIComponent(name)}`,
          // installCommand 留空：MCP 安装依赖目标 agent，见 install-matrix.md
          installCommand: null,
        })
      );
      if (out.length >= max) break;
    }
    cursor = pick(body, 'metadata.nextCursor', 'nextCursor');
    if (!cursor) break;
  }
  return out;
}

// ─── glama.ai MCP directory API（公开 JSON，无需 token；50K+ servers，是 registry 的超集） ───
async function fetchGlamaServers(query, { max = 10 } = {}) {
  const out = [];
  let cursor = null;
  const cap = Math.max(max * 2, 20); // 多取一些用于去重后仍有足够数量
  for (let page = 0; page < 1; page++) {
    let url = `https://glama.ai/api/mcp/v1/servers?query=${encodeURIComponent(query)}`;
    if (cursor) url += `&cursor=${encodeURIComponent(cursor)}`;
    let body;
    try {
      body = await getJsonRetry(url, { timeout: 20000 });
    } catch (e) {
      console.error(`[find-extensions] glama: fetch failed (page ${page + 1}): ${e.message}`);
      break;
    }
    const servers = pick(body, 'servers') || [];
    for (const s of servers) {
      const name = pick(s, 'name');
      if (!name) continue;
      const repo = pick(s, 'repository.url', 'repository');
      out.push(
        normalize({
          type: 'mcp',
          name,
          description: pick(s, 'description'),
          source: 'glama',
          repo,
          stars: null,
          installCount: null,
          version: null,
          updatedAt: null,
          url: pick(s, 'url') || repo,
          installCommand: null,
        })
      );
      if (out.length >= cap) break;
    }
    cursor = pick(body, 'pageInfo.endCursor', 'endCursor');
    const hasNext = pick(body, 'pageInfo.hasNextPage', 'hasNextPage');
    if (!cursor || !hasNext) break;
    if (out.length >= cap) break;
  }
  return out;
}

// ─── claudemarketplaces.com MCP 目录（12.7K servers，自带 effectiveStars，免 enrich） ───
// API 无服务端 search、无分页，固定返回按 rank 排序的前 1000 条热门 MCP。
// 客户端按 displayName+summary+installLabel 过滤（不用 searchText：它含 "io.github." 前缀，
//   宽词如 "github" 会匹配所有 MCP 的 name 前缀，产生噪音）。
// name 用 io.github.xxx 格式（与 registry 一致），便于 dedupeRich 跨源去重。
async function fetchClaudeMarketplacesMcp(query, { max = 10 } = {}) {
  const body = await getJsonRetry('https://claudemarketplaces.com/api/mcp-servers', { timeout: 15000 });
  const servers = pick(body, 'servers') || [];
  const terms = String(query).toLowerCase().split(/\s+/).filter(Boolean);
  const cap = Math.max(max * 2, 20);
  const out = [];
  for (const s of servers) {
    const name = pick(s, 'name'); // io.github.<owner>/<repo> 格式，与 registry 对齐
    if (!name) continue;
    const dn = String(pick(s, 'displayName') || '').toLowerCase();
    const sm = String(pick(s, 'summary') || '').toLowerCase();
    const il = String(pick(s, 'installLabel') || '').toLowerCase();
    const matchText = `${dn} ${sm} ${il}`;
    const hit = terms.length === 0 || terms.some((t) => matchText.includes(t));
    if (!hit) continue;
    const sourceRepo = pick(s, 'sourceRepo'); // owner/repo
    const repo = sourceRepo ? `https://github.com/${sourceRepo}` : null;
    out.push(
      normalize({
        type: 'mcp',
        name,
        description: pick(s, 'summary'),
        source: 'claudemarketplaces.com',
        repo,
        stars: pick(s, 'effectiveStars'),
        installCount: null,
        version: null,
        updatedAt: pick(s, 'createdAt'),
        url: `https://claudemarketplaces.com/mcp/${encodeURIComponent(pick(s, 'slug') || sourceRepo || name)}`,
        // installCommand 留空：MCP 安装依赖目标 agent，见 install-matrix.md
        installCommand: null,
      })
    );
    if (out.length >= cap) break;
  }
  return out;
}

// 意图过滤：多词查询时，三源的 server-side/client-side 匹配都是 OR 语义（任一词命中即返回），
// 会混入只沾一个词的 false positive（如 "browser testing" 匹配 Scrapling——它是 scraping 不是 testing）。
// 收紧为：description 同时含 ≥2 个 term 的为 strong；有 strong 则只保留 strong。
// 排序（函数内完成，searchMcp 不再覆盖）：
//   strong — 按 stars 降序，让热门 strong match 排前
//   weak   — 按 name 命中 term 数降序，让 name 含 query 词的排前，纯 description 命中的沉后，
//            避免 Scrapling(name 不含 browser/testing) 因 stars 高霸占首位
function intentFilterMcp(items, words) {
  const terms = words.map((w) => w.toLowerCase());
  const strong = items.filter((it) => {
    const desc = String(it.description || '').toLowerCase();
    return terms.filter((t) => desc.includes(t)).length >= 2;
  });
  if (strong.length > 0) {
    strong.sort((a, b) => (b.stars ?? -1) - (a.stars ?? -1));
    console.error(
      `[find-extensions] mcp: kept ${strong.length} strong match(es) (description hits ≥2 terms, sorted by stars)`
    );
    return strong;
  }
  // 无 strong：按 name 命中 term 数降序排序（稳定排序：同分保持原序）
  const nameHits = (it) => {
    const n = String(it.name || '').toLowerCase();
    return terms.filter((t) => n.includes(t)).length;
  };
  const sorted = [...items].sort((a, b) => nameHits(b) - nameHits(a));
  console.error(
    `[find-extensions] mcp: no strong matches; keeping ${items.length} weak matches (sorted by name-hit count, verify relevance) — consider using a concrete tool name like "playwright" instead of multi-word queries`
  );
  return sorted;
}

// searchMcp：合并 registry + glama + claudemarketplaces.com 三个源，按 repo+name 去重(保留 rich)。
// 多词查询时总是做意图过滤（不仅限于 0 结果）；0 结果时按空格拆词 auto-expand 后再意图过滤。
async function searchMcp(query, { pages = 2, max = 10 } = {}) {
  const [registry, glama, cm] = await Promise.all([
    fetchMcpServers(query, { pages, max }).catch((e) => {
      console.error(`[find-extensions] registry: ${e.message}`);
      return [];
    }),
    fetchGlamaServers(query, { max }).catch((e) => {
      console.error(`[find-extensions] glama: ${e.message}`);
      return [];
    }),
    fetchClaudeMarketplacesMcp(query, { max }).catch((e) => {
      console.error(`[find-extensions] claudemarketplaces.com/mcp: ${e.message}`);
      return [];
    }),
  ]);
  let out = dedupeRich([...registry, ...glama, ...cm]);
  const words = query.trim().split(/\s+/).filter((w) => w.length > 1);
  const isMulti = words.length > 1;

  if (isMulti) {
    out = intentFilterMcp(out, words);
  }

  if (out.length === 0 && isMulti) {
    console.error(
      `[find-extensions] mcp: 0 results for "${query}", expanding to per-word search: ${words.join(', ')}`
    );
    const perWord = await Promise.all(
      words.map(async (w) => {
        const [r, g, c] = await Promise.all([
          fetchMcpServers(w, { pages, max }).catch(() => []),
          fetchGlamaServers(w, { max }).catch(() => []),
          fetchClaudeMarketplacesMcp(w, { max }).catch(() => []),
        ]);
        return [...r, ...g, ...c];
      })
    );
    out = intentFilterMcp(dedupeRich(perWord.flat()), words);
  }
  // 单词查询：按 stars 降序，让 claudemarketplaces.com 补全的热门 MCP 浮上来，
  // 避免被先入数组的 registry 冷门条目挤出 slice。
  // 多词查询：排序已在 intentFilterMcp 内完成（strong=stars, weak=name-hit），不覆盖。
  if (!isMulti) {
    out.sort((a, b) => (b.stars ?? -1) - (a.stars ?? -1));
  }
  return out.slice(0, max);
}

// 查询匹配：所有 term（按空格拆分）都必须命中任一指定字段（AND 语义）。
// 字段值若是数组（如 keywords），任一元素命中即算该字段命中。大小写不敏感。
function matchesQuery(item, query, fields) {
  const terms = String(query)
    .toLowerCase()
    .split(/\s+/)
    .filter(Boolean);
  if (terms.length === 0) return true;
  return terms.every((t) =>
    fields.some((f) => {
      const v = pick(item, f);
      if (v == null) return false;
      if (Array.isArray(v)) return v.some((x) => String(x).toLowerCase().includes(t));
      return String(v).toLowerCase().includes(t);
    })
  );
}

// plugin 专用打分：收紧 false positive + 提供排序信号。
// 多词查询分级 fallback（从严到宽，只取第一个有命中的层级）：
//   T1 nameHitAll —— name 含所有 term（如 "react-testing" 匹配 "react testing"），最强信号
//   T2 descHitAll && nameHitAny —— description 含所有 term 且 name 至少命中一个词，
//      过滤掉 name 完全不沾边、仅 description 随口提到的（如 cassiiopeia 描述里提到 react+testing）
//   T3 kwsHitAll —— keywords 含所有 term（categories 级别）
//   都无则不匹配。
// 单词查询时 T1===T2(nameHitAll===nameHitAny)，退化为 name/desc/keywords 任一命中。
// 打分：T1 > T2 > T3，同层级内 name 精确等于 +30。
function scorePlugin(p, query) {
  const terms = String(query).toLowerCase().split(/\s+/).filter(Boolean);
  if (terms.length === 0) return { matched: true, score: 0 };
  const name = String(pick(p, 'name') || '').toLowerCase();
  const desc = String(pick(p, 'description') || '').toLowerCase();
  const kws = (pick(p, 'keywords') || []).map((k) => String(k).toLowerCase());

  const nameHitAll = terms.every((t) => name.includes(t));
  const nameHitAny = terms.some((t) => name.includes(t));
  const descHitAll = terms.every((t) => desc.includes(t));
  const kwsHitAll = terms.every((t) => kws.some((k) => k.includes(t)));

  let tier = 0; // 0=不匹配, 3=T1, 2=T2, 1=T3
  if (nameHitAll) tier = 3;
  else if (descHitAll && nameHitAny) tier = 2;
  else if (kwsHitAll) tier = 1;
  if (tier === 0) return { matched: false, score: 0 };

  // tier 权重远大于同层级加分，保证 T1 全排在 T2 前
  let score = tier * 100;
  if (nameHitAll) score += 50;
  else if (nameHitAny) score += 25;
  if (descHitAll) score += 20;
  if (kwsHitAll) score += 15;
  // name 精确等于某 term（强信号）
  if (terms.some((t) => name === t)) score += 30;
  return { matched: true, score };
}

// ─── plugins：marketplace.json + pluginmarketplace.ai + claudemarketplaces.com 三类源 ───
// marketplace.json 来源：official + community + wshobson/agents；raw 失败回退 jsDelivr CDN。
// pluginmarketplace.ai：独立 JSON API，有 installCount（marketplace.json 没有）。
// claudemarketplaces.com/api/marketplaces：marketplace 仓库目录（2.6K+ 仓库，带 stars+pluginCount），
//   返回的是仓库级而非单个 plugin，用 categories 匹配（不用 pluginKeywords，太聚合易误匹配），installCommand 为 add <repo>。
async function searchPlugins(query, { max = 10 } = {}) {
  const sources = [
    [
      'anthropics/claude-plugins-official',
      'https://raw.githubusercontent.com/anthropics/claude-plugins-official/main/.claude-plugin/marketplace.json',
      'https://cdn.jsdelivr.net/gh/anthropics/claude-plugins-official@main/.claude-plugin/marketplace.json',
    ],
    [
      'anthropics/claude-plugins-community',
      'https://raw.githubusercontent.com/anthropics/claude-plugins-community/main/.claude-plugin/marketplace.json',
      'https://cdn.jsdelivr.net/gh/anthropics/claude-plugins-community@main/.claude-plugin/marketplace.json',
    ],
    [
      'wshobson/agents',
      'https://raw.githubusercontent.com/wshobson/agents/main/.claude-plugin/marketplace.json',
      'https://cdn.jsdelivr.net/gh/wshobson/agents@main/.claude-plugin/marketplace.json',
    ],
  ];
  const scored = []; // {item, score}
  let fetched = 0;
  // 硬上限防内存爆炸；不再让早期源阻断后期源（修复 pluginmarketplace.ai 被 cap 截断的 bug）。
  const hardCap = Math.max(max * 5, 100);

  // ── marketplace.json 源 ──
  for (const [srcName, raw, cdn] of sources) {
    let body;
    try {
      try {
        body = await getJsonRetry(raw, { timeout: 20000 });
      } catch (e) {
        body = await getJsonRetry(cdn, { timeout: 20000 });
      }
      fetched++;
    } catch (e) {
      continue;
    }
    const plugins = pick(body, 'plugins') || [];
    for (const p of plugins) {
      const pname = pick(p, 'name');
      const repo = pick(p, 'source.url', 'repository.url', 'source', 'repository', 'repo');
      const link = repo || raw;
      const ownerRepo = parseOwnerRepo(repo);
      const installCmd = ownerRepo ? `claude plugin marketplace add ${ownerRepo}` : null;
      if (pname) {
        const { matched, score } = scorePlugin(p, query);
        if (matched) {
          scored.push({
            item: normalize({
              type: 'plugin',
              name: pname,
              description: pick(p, 'description'),
              source: srcName,
              repo,
              stars: null,
              installCount: null,
              version: pick(p, 'version'),
              updatedAt: null,
              url: link,
              installCommand: installCmd,
            }),
            score,
          });
        }
      }
      if (scored.length >= hardCap) break;
    }
    if (scored.length >= hardCap) break;
  }

  // ── pluginmarketplace.ai API（有 installCount，marketplace.json 没有） ──
  try {
    const body = await getJsonRetry('https://pluginmarketplace.ai/api/plugins', { timeout: 20000 });
    fetched++;
    const plugins = Array.isArray(body) ? body : [];
    for (const p of plugins) {
      const pname = pick(p, 'name');
      if (!pname) continue;
      const repo = pick(p, 'githubUrl', 'homepageUrl');
      const ownerRepo = parseOwnerRepo(repo);
      // pluginmarketplace.ai 的 installCommand 已含完整命令
      const installCmd = pick(p, 'installCommand') || (ownerRepo ? `claude plugin marketplace add ${ownerRepo}` : null);
      // 用 tags 作为 keywords 供 scorePlugin 匹配
      const fakeItem = { name: pname, description: pick(p, 'description'), keywords: pick(p, 'tags') || [] };
      const { matched, score } = scorePlugin(fakeItem, query);
      if (matched) {
        scored.push({
          item: normalize({
            type: 'plugin',
            name: pname,
            description: pick(p, 'description'),
            source: 'pluginmarketplace.ai',
            repo,
            stars: null,
            installCount: pick(p, 'installCount'),
            version: null,
            updatedAt: pick(p, 'updatedAt'),
            url: pick(p, 'homepageUrl') || repo || `https://pluginmarketplace.ai/plugin/${encodeURIComponent(pick(p, 'slug') || pname)}`,
            installCommand: installCmd,
          }),
          score,
        });
      }
      if (scored.length >= hardCap) break;
    }
  } catch (e) {
    console.error(`[find-extensions] pluginmarketplace.ai: ${e.message}`);
  }

  // ── claudemarketplaces.com/api/marketplaces（marketplace 仓库目录，2.6K+，带 stars） ──
  // 仓库级结果：name 用 repo，installCommand 为 add <repo>（添加整个 marketplace 获取其下所有 plugin）。
  try {
    const body = await getJsonRetry('https://claudemarketplaces.com/api/marketplaces', { timeout: 30000 });
    fetched++;
    const markets = Array.isArray(body) ? body : [];
    for (const m of markets) {
      const repo = pick(m, 'repo');
      if (!repo) continue;
      const desc = pick(m, 'description');
      const cats = pick(m, 'categories') || [];
      // keywords 只用 categories（约 10 个分类），不用 pluginKeywords（聚合了仓库内所有 plugin 的
      // 关键词，可达数百个，导致多词查询的 kwsHitAll 几乎总是成立，产生大量 false positive）。
      const fakeItem = { name: repo, description: desc, keywords: cats };
      const { matched, score } = scorePlugin(fakeItem, query);
      if (matched) {
        const ownerRepo = parseOwnerRepo(repo) || repo;
        scored.push({
          item: normalize({
            type: 'plugin',
            name: repo,
            description: desc,
            source: 'claudemarketplaces.com',
            repo,
            stars: pick(m, 'stars'),
            installCount: null, // pluginCount 是仓库内插件数，非安装数，不放此字段
            version: null,
            updatedAt: pick(m, 'lastUpdated'),
            url: `https://claudemarketplaces.com/marketplaces/${encodeURIComponent(pick(m, 'slug') || repo)}`,
            installCommand: `claude plugin marketplace add ${ownerRepo}`,
          }),
          score,
        });
      }
      if (scored.length >= hardCap) break;
    }
  } catch (e) {
    console.error(`[find-extensions] claudemarketplaces.com/marketplaces: ${e.message}`);
  }

  if (fetched === 0) {
    console.error(
      `[find-extensions] plugins: all marketplace sources unreachable (tried ${sources.length} + 2 APIs)`
    );
  }
  // 按 score 降序排（高相关在前），再去重取 top max
  scored.sort((a, b) => b.score - a.score);
  const out = scored.map((s) => s.item);
  return dedupe(out).slice(0, max);
}

// ─── merge：从 stdin 读多个渠道的 JSON 数组，跨渠道去重后输出 ───
// 用途：`(node s.mjs skills "x"; node s.mjs mcp "x"; node s.mjs plugins "x") | node s.mjs merge`
// 容忍三种输入：单个 JSON 数组、多个 JSON 数组拼接（][ 之间）、NDJSON（每行一个 JSON 对象或数组）。
// 去重键：优先 parseOwnerRepo(repo)（同一 GitHub repo 跨 type 合并），fallback 到 type:name。
// 同键保留信息更全的条目（stars/installCount/description 非空优先）。
function parseStdinArrays(raw) {
  const s = raw.trim();
  if (!s) return [];
  // 多个 JSON 数组拼接（如 `][` 跨行）：合并成单个数组
  if (s.startsWith('[') && /\]\s*\[/.test(s)) {
    const merged = '[' + s.slice(1, -1).replace(/\]\s*\[/g, ',') + ']';
    return JSON.parse(merged);
  }
  if (s.startsWith('[')) return JSON.parse(s);
  // NDJSON：每行一个 JSON（对象或数组）
  const out = [];
  for (const line of s.split(/\r?\n/)) {
    const t = line.trim();
    if (!t) continue;
    const v = JSON.parse(t);
    if (Array.isArray(v)) out.push(...v);
    else out.push(v);
  }
  return out;
}

function mergeDedupe(items) {
  const byRepo = new Map();
  const byName = new Map();
  const out = [];
  const score = (x) =>
    (x.stars != null ? 1 : 0) + (x.installCount != null ? 1 : 0) + (x.description ? 1 : 0);
  for (const it of items) {
    const ownerRepo = parseOwnerRepo(it.repo);
    const key = ownerRepo || `${it.type}:${String(it.name).toLowerCase()}`;
    const map = ownerRepo ? byRepo : byName;
    const existing = map.get(key);
    if (!existing) {
      map.set(key, it);
      out.push(it);
    } else if (score(it) > score(existing)) {
      const idx = out.indexOf(existing);
      if (idx >= 0) out[idx] = it;
      map.set(key, it);
    }
  }
  return out;
}

async function mergeFromStdin(opts = {}) {
  const chunks = [];
  await new Promise((resolve) => {
    process.stdin.setEncoding('utf8');
    process.stdin.on('data', (c) => chunks.push(c));
    process.stdin.on('end', resolve);
    process.stdin.on('error', resolve);
  });
  const raw = chunks.join('').trim();
  if (!raw) {
    console.error('[find-extensions] merge: stdin is empty');
    process.exit(1);
  }
  let items;
  try {
    items = parseStdinArrays(raw);
  } catch (e) {
    console.error(`[find-extensions] merge: invalid input: ${e.message}`);
    process.exit(1);
  }
  const before = items.length;
  const merged = mergeDedupe(items);
  if (merged.length < before) {
    console.error(
      `[find-extensions] merge: ${before} → ${merged.length} rows (deduped by repo / type:name)`
    );
  }
  process.stdout.write(formatOutput(merged, opts) + '\n');
}

// ─── enrich：从 stdin 读 JSON 数组，用 GitHub API 补 stars/updatedAt ───
// 对 owner/repo 去重（同一 repo 的多个条目只查一次）。
// 处理无 token 限流（60次/小时）：遇 403/429 即停止，已查到的填入，其余保持 null。
// 若设置了 GITHUB_TOKEN / GH_TOKEN 环境变量，自动用于提高限额（5000次/小时）。
async function enrichFromStdin(opts = {}) {
  const chunks = [];
  await new Promise((resolve) => {
    process.stdin.setEncoding('utf8');
    process.stdin.on('data', (c) => chunks.push(c));
    process.stdin.on('end', resolve);
    process.stdin.on('error', resolve);
  });
  const raw = chunks.join('').trim();
  if (!raw) {
    console.error('[find-extensions] enrich: stdin is empty, expected a JSON array');
    process.exit(1);
  }
  let items;
  try {
    items = JSON.parse(raw);
  } catch (e) {
    console.error(`[find-extensions] enrich: invalid JSON on stdin: ${e.message}`);
    process.exit(1);
  }
  if (!Array.isArray(items)) {
    console.error('[find-extensions] enrich: stdin must be a JSON array');
    process.exit(1);
  }

  // 收集去重后的 owner/repo 列表。跳过已有 stars 的条目（claudemarketplaces.com /
  // pluginmarketplace.ai 已带 stars，无需重复发 GitHub API 请求，省 quota + 降延迟）。
  const repoMap = new Map(); // ownerRepo -> { stars, updatedAt }
  let skipped = 0;
  for (const it of items) {
    const ownerRepo = parseOwnerRepo(it.repo);
    if (!ownerRepo) continue;
    if (it.stars != null) {
      // 已有 stars，保留原值，不发 API 请求
      repoMap.set(ownerRepo, { stars: it.stars, updatedAt: it.updatedAt ?? null, _preexisting: true });
      skipped++;
      continue;
    }
    if (!repoMap.has(ownerRepo)) repoMap.set(ownerRepo, null);
  }
  if (skipped > 0) {
    console.error(`[find-extensions] enrich: skipped ${skipped} repo(s) already having stars (no GitHub API call)`);
  }

  const headers = { Accept: 'application/vnd.github+json' };
  const token = process.env.GITHUB_TOKEN || process.env.GH_TOKEN;
  if (token) headers.Authorization = `Bearer ${token}`;
  const tokenNote = token ? ' (with token)' : ' (no token, 60 req/hour limit)';

  let queried = 0;
  let rateLimited = false;
  for (const [ownerRepo] of repoMap) {
    if (rateLimited) break;
    try {
      const { status, headers: respHeaders, body } = await getJsonWithHeaders(
        `https://api.github.com/repos/${ownerRepo}`,
        { timeout: 10000, headers }
      );
      if (status === 200 && body) {
        repoMap.set(ownerRepo, {
          stars: body.stargazers_count ?? null,
          updatedAt: body.updated_at ?? body.pushed_at ?? null,
        });
      } else if (status === 403 || status === 429) {
        rateLimited = true;
        const remaining = respHeaders['x-ratelimit-remaining'];
        console.error(
          `[find-extensions] enrich: GitHub rate limit hit${tokenNote}, stopped after ${queried} repos (remaining: ${remaining ?? '?'}). ` +
            'Set GITHUB_TOKEN / GH_TOKEN env var to raise the limit. Unenriched rows keep stars=null.',
          process.stderr
        );
        break;
      }
      queried++;
    } catch (e) {
      // 单个 repo 查询失败不中断整体，保持 null
      console.error(`[find-extensions] enrich: failed for ${ownerRepo}: ${e.message}`, process.stderr);
    }
  }

  // 合并回原条目
  const out = items.map((it) => {
    const ownerRepo = parseOwnerRepo(it.repo);
    const info = ownerRepo ? repoMap.get(ownerRepo) : null;
    if (info) {
      return { ...it, stars: info.stars ?? it.stars, updatedAt: info.updatedAt ?? it.updatedAt };
    }
    return it;
  });

  process.stdout.write(formatOutput(out, opts) + '\n');
}

function parseArgs(argv) {
  const [cmd, ...rest] = argv;
  const opts = {};
  let query = null;
  for (let i = 0; i < rest.length; i++) {
    const a = rest[i];
    if (a === '--pages') opts.pages = parseInt(rest[++i], 10);
    else if (a === '--timeout') opts.timeout = parseInt(rest[++i], 10);
    else if (a === '--max') opts.max = parseInt(rest[++i], 10);
    else if (a === '--owner') opts.owner = rest[++i];
    else if (a === '--table') opts.table = true;
    else if (a === '--full') opts.full = true;
    else if (!query && !a.startsWith('-')) query = a;
  }
  return { cmd, query, opts };
}

// 默认精简字段集（省上下文，但保留 repo/updatedAt 供 enrich 与 ranking 使用）；--full 输出全部字段
const SLIM_FIELDS = ['type', 'name', 'description', 'source', 'repo', 'installCount', 'stars', 'updatedAt', 'url', 'installCommand'];
const ALL_FIELDS = [
  'type', 'name', 'description', 'source', 'repo', 'stars',
  'installCount', 'version', 'updatedAt', 'url', 'installCommand',
];

function formatCount(n) {
  if (n == null) return '-';
  if (n >= 1e6) return `${(n / 1e6).toFixed(1).replace(/\.0$/, '')}M`;
  if (n >= 1e3) return `${(n / 1e3).toFixed(1).replace(/\.0$/, '')}K`;
  return String(n);
}

function formatTable(items) {
  if (!items.length) return '_No results_';
  const rows = items.map((it) => {
    const installs = formatCount(it.installCount);
    const stars = formatCount(it.stars);
    const install = it.installCommand || '-';
    const url = it.url || '';
    return `| ${it.name || '-'} | ${it.type || '-'} | ${installs} | ${stars} | ${install} | ${url} |`;
  });
  return ['| Name | Type | Installs | Stars | Install | Link |', '| --- | --- | --- | --- | --- | --- |', ...rows].join('\n');
}

function formatOutput(items, { table, full } = {}) {
  if (table) return formatTable(items);
  const fields = full ? ALL_FIELDS : SLIM_FIELDS;
  // slim 模式省略值为 null 的字段（省上下文）；--full 保留全部字段（含 null，schema 稳定）。
  const slim = items.map((it) => {
    const o = {};
    for (const f of fields) {
      const v = it[f] ?? null;
      if (full || v !== null) o[f] = v;
    }
    return o;
  });
  return JSON.stringify(slim, null, 2);
}

async function main() {
  const { cmd, query, opts } = parseArgs(process.argv.slice(2));
  if (!cmd) {
    console.error(
      'Usage: node search.mjs <skills|mcp|plugins> <query> [flags]\n       node search.mjs <enrich|merge>   (reads JSON from stdin)'
    );
    process.exit(2);
  }

  // enrich / merge 从 stdin 读，不需要 query
  if (cmd === 'enrich') {
    return enrichFromStdin(opts);
  }
  if (cmd === 'merge') {
    return mergeFromStdin(opts);
  }

  if (!query) {
    console.error('Usage: node search.mjs <skills|mcp|plugins> <query> [flags]');
    process.exit(2);
  }

  let result;
  try {
    if (cmd === 'skills') result = await searchSkills(query, opts);
    else if (cmd === 'mcp') result = await searchMcp(query, opts);
    else if (cmd === 'plugins' || cmd === 'plugin') result = await searchPlugins(query, opts);
    else throw new Error(`unknown command: ${cmd}`);
  } catch (e) {
    console.error(`[find-extensions] ${cmd} search failed: ${e.message}`);
    process.exit(1);
  }
  process.stdout.write(formatOutput(result, opts) + '\n');
}

main();
