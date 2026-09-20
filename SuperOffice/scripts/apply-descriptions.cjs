#!/usr/bin/env node
// Apply canonical descriptions from scripts/descriptions.json to every SKILL.md.
//
//   node scripts/apply-descriptions.cjs            # dry run: report only
//   node scripts/apply-descriptions.cjs --write    # rewrite the description lines
//
// Enforced before any write:
//   * every skill directory in every pack has an entry (no stale/short spec)
//   * the Chinese trigger anchors END before `maxChineseAt` characters, because
//     ZCode injects only the first 250 chars of a description into the model
//     context; past that the trigger words never reach the model
//   * total length <= `maxTotal` (keeps DSH's 500-char cap non-binding)
//   * the value opens with a "Use when/BEFORE/while" trigger phrase
//   * the value contains Chinese
// The description is written as one double-quoted, backslash-escaped YAML line.

const fs = require('fs');
const path = require('path');

// Self-contained: this pack owns scripts/descriptions.json (the single source of\n// truth for the LONG descriptions - full triggers, exclusions and cross-skill\n// pointers). The text is applied to this pack's own skills/; the only derived\n// short form is ZCode's, generated at build time by build-agent-skills.cjs.\n// Length policy: total <= maxTotal (1024, the tightest vendor cap); the Chinese\n// trigger anchors do NOT have to sit in the first 250 chars here - ZCode reads a\n// derived text instead.
const PACK_DIR = path.resolve(__dirname, '..');
const OWN_PACK = path.basename(PACK_DIR);
const SKILLS_DIR = path.join(PACK_DIR, 'agents-skills');   // the canonical source
const spec = JSON.parse(fs.readFileSync(path.join(__dirname, 'descriptions.json'), 'utf8'));

// Accept both "skill-name" and "Pack/skill-name" keys so one spec file can be
// shared or split without editing.
const desc = {};
for (const [k, v] of Object.entries(spec.descriptions)) {
    desc[k.includes('/') ? k : OWN_PACK + '/' + k] = v;
}
const WRITE = process.argv.includes('--write');

const CJK = /[\u4e00-\u9fff]/;
const problems = [];
const changed = [];

function chineseEnd(text) {
    let end = 0;
    for (const m of text.matchAll(/[\u4e00-\u9fff][\u4e00-\u9fff\w，。、（）「」：·…%-]*/g)) {
        end = Math.max(end, m.index + m[0].length);
    }
    return end;
}

function yamlQuote(value) {
    return '"' + value.replace(/\\/g, '\\\\').replace(/"/g, '\\"') + '"';
}

// ---- 1. spec validation ----
const seen = new Set();
for (const name of fs.readdirSync(SKILLS_DIR)) {
    const file = path.join(SKILLS_DIR, name, 'SKILL.md');
    if (!fs.existsSync(file)) continue;
    const id = OWN_PACK + '/' + name;
    seen.add(id);
    const next = desc[id];
    if (!next) { problems.push('NO-SPEC-ENTRY: ' + id); continue; }
    if (next.length > spec.maxTotal) problems.push(`TOO-LONG ${next.length}>${spec.maxTotal}: ${id}`);
    const cEnd = chineseEnd(next);
    if (cEnd === 0) problems.push('NO-CHINESE: ' + id);
    else if (cEnd > spec.maxChineseAt) problems.push(`CHINESE-ENDS-AT-${cEnd}>${spec.maxChineseAt}: ${id}`);
    if (!/^Use (when|BEFORE|while)/.test(next)) problems.push('NO-TRIGGER-PHRASE: ' + id);
}
for (const id of Object.keys(desc)) {
    if (!seen.has(id)) problems.push('SPEC-ENTRY-WITHOUT-SKILL: ' + id);
}

if (problems.length) {
    console.log(problems.join('\n'));
    console.log('--- ' + problems.length + ' spec problem(s); nothing written');
    process.exit(1);
}

// ---- 2. apply ----
{
    for (const name of fs.readdirSync(SKILLS_DIR)) {
        const file = path.join(SKILLS_DIR, name, 'SKILL.md');
        if (!fs.existsSync(file)) continue;
        const id = OWN_PACK + '/' + name;
        const next = desc[id];
        const raw = fs.readFileSync(file, 'utf8');
        const eol = raw.includes('\r\n') ? '\r\n' : '\n';
        const fm = raw.match(/^---\r?\n([\s\S]*?)\r?\n---/);
        if (!fm) { problems.push('NO-FRONTMATTER: ' + id); continue; }

        const lines = fm[1].split(/\r?\n/);
        let i = lines.findIndex(l => /^description\s*:/.test(l));
        if (i < 0) { problems.push('NO-DESCRIPTION-LINE: ' + id); continue; }
        let end = i + 1;
        while (end < lines.length && !/^[A-Za-z][A-Za-z0-9_-]*\s*:/.test(lines[end])) end++;

        const current = lines.slice(i, end).join(' ')
            .replace(/^description\s*:\s*/, '')
            .replace(/\\"/g, '"')
            .replace(/^"(.*)"$/, '$1')
            .replace(/\s+/g, ' ')
            .trim();

        if (current === next) continue;

        lines.splice(i, end - i, 'description: ' + yamlQuote(next));
        const rebuilt = raw.slice(0, fm.index) +
            '---' + eol + lines.join(eol) + eol + '---' +
            raw.slice(fm.index + fm[0].length);

        changed.push(`${id}  ${current.length} -> ${next.length}`);
        if (WRITE) fs.writeFileSync(file, rebuilt, 'utf8');
    }
}

console.log(changed.join('\n'));
console.log(`--- ${changed.length} description(s) ${WRITE ? 'written' : 'would change'} (spec: ${Object.keys(desc).length} entries, total cap ${spec.maxTotal}, total <=${spec.maxTotal})`);
