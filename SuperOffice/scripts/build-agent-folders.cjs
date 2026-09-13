#!/usr/bin/env node
// One canonical source, two derived folders.
//
//   node scripts/build-agent-folders.cjs            # rebuild derived folders
//   node scripts/build-agent-folders.cjs --check    # verify, write nothing
//
//   agents-skills/   THE SOURCE. Long descriptions, name + description only.
//                    Feed it to every harness that reads SKILL.md: DSH, Claude
//                    Code, Codex, Cursor, Qoder, Gemini CLI, opencode, CodeBuddy,
//                    Kimi, Grok. Several of them scan the shared ~/.agents/skills
//                    root, so this one folder covers the whole non-ZCode surface.
//                    Edit skills here (or in scripts/descriptions.json, then run
//                    apply-descriptions.cjs), never in the derived folders.
//   zcode-skills/    derived: the same skills with a short description, because
//                    ZCode documents that per-turn metadata injects only the first
//                    250 chars of each description. Generated, never hand-edited.
//   codex-skills/    derived: the same skills plus the Codex-only
//                    agents/openai.yaml (UI metadata + invocation policy). Codex
//                    has no SKILL.md key that other harnesses lack.
//
// Safety: derived folders are rebuilt in place; entries not listed in
// bundle.json are reported and left untouched.

const fs = require('fs');
const path = require('path');

const PACK_DIR = path.resolve(__dirname, '..');
const SRC_DIR = path.join(PACK_DIR, 'agents-skills');
const bundle = JSON.parse(fs.readFileSync(path.join(PACK_DIR, 'bundle.json'), 'utf8'));
const skillNames = [...bundle.skills, ...(bundle.optional || [])];
const CHECK = process.argv.includes('--check');

const ZCODE_LIMIT = bundle.zcodeDescriptionLimit || 250;
const EXPLICIT_ONLY = new Set(bundle.codexExplicitOnly || []);
const SHORT = bundle.codexShortDescriptions || {};
const DISPLAY = { tdd: 'TDD', 'wps-cli': 'WPS CLI', 'doc-index': 'Doc Index', api: 'API' };

const problems = [];
const report = [];

// ---------- description helpers ----------
function readDescription(skill) {
    const raw = fs.readFileSync(path.join(SRC_DIR, skill, 'SKILL.md'), 'utf8');
    const fm = raw.match(/^---\r?\n([\s\S]*?)\r?\n---/);
    const line = fm[1].split(/\r?\n/).find(l => /^description\s*:/.test(l));
    return line.replace(/^description\s*:\s*/, '').replace(/\\"/g, '"').replace(/^"(.*)"$/, '$1').trim();
}

function setDescription(raw, value) {
    const fm = raw.match(/^---\r?\n([\s\S]*?)\r?\n---/);
    const eol = raw.includes('\r\n') ? '\r\n' : '\n';
    const lines = fm[1].split(/\r?\n/);
    const i = lines.findIndex(l => /^description\s*:/.test(l));
    let end = i + 1;
    while (end < lines.length && !/^[A-Za-z][A-Za-z0-9_-]*\s*:/.test(lines[end])) end++;
    lines.splice(i, end - i, 'description: "' + value.replace(/\\/g, '\\\\').replace(/"/g, '\\"') + '"');
    return raw.slice(0, fm.index) + '---' + eol + lines.join(eol) + eol + '---' + raw.slice(fm.index + fm[0].length);
}

const QUOTED = /[「“"']([^」”"']{1,40})[」”"']/g;
const PAREN = /[（(]([^）)]{0,80})[）)]/g;
function anchors(full) {
    const out = [];
    for (const m of full.matchAll(QUOTED)) if (/[\u4e00-\u9fff]/.test(m[1])) out.push(m[0]);
    if (!out.length) {
        for (const m of full.matchAll(PAREN)) {
            for (const part of m[1].split(/[、,，]/)) {
                const t = part.trim();
                if (/[\u4e00-\u9fff]/.test(t)) out.push(t);
            }
        }
    }
    return out;
}

// Keep the opening trigger sentence + the Chinese anchors, then degrade.
function zcodeDescription(full, limit = ZCODE_LIMIT) {
    const first = full.match(/^[^。]*?\.\s/);
    const head = (first ? first[0] : full).trim();
    const headShort = head.replace(/\s+-\s+.*$/, '.');
    const phrases = anchors(full);
    const marker = /中文触发/.test(full) ? '中文触发：' : '中文信号：';
    const join = list => list.map((p, i) => (i && !/^[「“"']/.test(p) ? '、' : '') + p).join('');
    const candidates = [];
    for (const h of [head, headShort]) {
        for (let n = phrases.length; n >= 1; n--) candidates.push(h + ' ' + marker + join(phrases.slice(0, n)));
    }
    for (let n = phrases.length; n >= 1; n--) candidates.push(marker + join(phrases.slice(0, n)));
    candidates.push(head);
    for (const c of candidates) {
        const s = c.replace(/\s+/g, ' ').trim();
        if (s.length <= limit && /[\u4e00-\u9fff]/.test(s)) return s;
    }
    const fallback = (headShort + ' ' + marker + join(phrases)).replace(/\s+/g, ' ').trim();
    let out = fallback.slice(0, limit);
    const sp = out.lastIndexOf(' ');
    if (sp > 100) out = out.slice(0, sp);
    return out.replace(/[\s,;:，、-]+$/, '');
}

function codexYaml(skill) {
    const name = DISPLAY[skill] || skill.split('-').map(w => (w ? w[0].toUpperCase() + w.slice(1) : w)).join(' ');
    const lines = ['interface:', '  display_name: "' + name + '"', '  short_description: "' + (SHORT[skill] || name) + '"'];
    if (EXPLICIT_ONLY.has(skill)) lines.push('policy:', '  allow_implicit_invocation: false');
    return lines.join('\n') + '\n';
}

function copySkill(skill, dst, transform) {
    const src = path.join(SRC_DIR, skill);
    fs.mkdirSync(dst, { recursive: true });
    for (const entry of fs.readdirSync(src, { withFileTypes: true })) {
        const from = path.join(src, entry.name);
        const to = path.join(dst, entry.name);
        if (entry.isDirectory()) {
            if (entry.name === 'agents') continue;   // codex-skills owns agents/openai.yaml
            fs.cpSync(from, to, { recursive: true, force: true });
        }
        else if (entry.name === 'SKILL.md' && transform) fs.writeFileSync(to, transform(fs.readFileSync(from, 'utf8')), 'utf8');
        else fs.copyFileSync(from, to);
    }
}

// ---------- validate the source first ----------
const sources = {};
for (const skill of skillNames) {
    const file = path.join(SRC_DIR, skill, 'SKILL.md');
    if (!fs.existsSync(file)) { problems.push('MISSING-SKILL: ' + skill); continue; }
    const desc = readDescription(skill);
    sources[skill] = desc;
    if (!/^Use (when|BEFORE|while)/.test(desc)) problems.push('NO-TRIGGER-PHRASE: ' + skill);
    if (desc.length > 1024) problems.push(`OVER-1024 ${desc.length}: ${skill}`);
    const z = zcodeDescription(desc);
    if (z.length > ZCODE_LIMIT) problems.push(`ZCODE-OVER-${ZCODE_LIMIT} ${z.length}: ${skill}`);
    if (!/[\u4e00-\u9fff]/.test(z)) problems.push('ZCODE-SHORT-WITHOUT-CHINESE: ' + skill);
}
if (problems.length) {
    console.log(problems.join('\n'));
    console.log('--- ' + problems.length + ' source problem(s); nothing written');
    process.exit(1);
}

// ---------- build the derived folders ----------
for (const target of ['zcode-skills', 'codex-skills']) {
    const dir = path.join(PACK_DIR, target);
    if (!CHECK) fs.mkdirSync(dir, { recursive: true });
    let n = 0;
    for (const skill of skillNames) {
        const dst = path.join(dir, skill);
        if (CHECK) { n++; continue; }
        if (target === 'zcode-skills') {
            copySkill(skill, dst, raw => setDescription(raw, zcodeDescription(sources[skill])));
        }
        else {
            copySkill(skill, dst, null);
            const agentsDir = path.join(dst, 'agents');
            fs.mkdirSync(agentsDir, { recursive: true });
            fs.writeFileSync(path.join(agentsDir, 'openai.yaml'), codexYaml(skill), 'utf8');
        }
        n++;
    }
    if (fs.existsSync(dir)) {
        for (const entry of fs.readdirSync(dir)) {
            if (!skillNames.includes(entry)) report.push(`EXTRA   ${target}/${entry} (not in bundle.json - left untouched)`);
        }
    }
    report.push(`${CHECK ? 'CHECKED' : 'BUILT  '} ${target}/  ${n} skill(s)`);
}

// ---------- staleness of the source itself ----------
for (const entry of fs.readdirSync(SRC_DIR)) {
    if (!skillNames.includes(entry)) report.push(`EXTRA   agents-skills/${entry} (not in bundle.json - left untouched)`);
}

console.log(report.join('\n'));
console.log(`--- source: agents-skills/  derived: zcode-skills/ (short form <=${ZCODE_LIMIT}), codex-skills/ (+ agents/openai.yaml)` + (CHECK ? ' [check only]' : ''));
