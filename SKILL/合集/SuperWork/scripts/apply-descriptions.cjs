#!/usr/bin/env node
// 将 scripts/descriptions.json 中的规范描述应用到每个 SKILL.md。
//
//   node scripts/apply-descriptions.cjs            # 干跑：只报告
//   node scripts/apply-descriptions.cjs --write    # 重写 description 行
//
// 写盘前强制校验：
//   * 每个包的每个 skill 目录都有对应条目（不允许缺失/过期的 spec）
//   * 中文触发锚点必须结束于 `maxChineseAt` 字符之前——ZCode 每轮只把描述的
//     前 250 字符注入模型上下文，超过部分触发词永远到不了模型
//   * 总长 <= `maxTotal`（保证 DSH 的 500 字符上限不起约束）
//   * 值以 "Use when/BEFORE/while" 触发短语开头
//   * 值包含中文
// 描述以单行双引号、转义反斜杠的 YAML 行写入。

const fs = require('fs');
const path = require('path');

// 自包含：本包拥有 scripts/descriptions.json（长描述的唯一事实源——完整触发词、
// 排除项与跨 skill 指针）。文本只应用到本包自己的 agents-skills/；唯一的派生
// 短版是 ZCode 的，由 build-agent-folders.cjs 在构建时生成。
// 长度策略：总长 <= maxTotal（1024，各端最紧的公布上限）；中文触发锚点在此
// 不必落进前 250 字符——ZCode 读的是派生文本。
const PACK_DIR = path.resolve(__dirname, '..');
const OWN_PACK = path.basename(PACK_DIR);
const SKILLS_DIR = path.join(PACK_DIR, 'agents-skills');   // 规范源
const spec = JSON.parse(fs.readFileSync(path.join(__dirname, 'descriptions.json'), 'utf8'));

// 同时接受 "skill-name" 与 "Pack/skill-name" 两种键，一个 spec 文件即可共享或拆分。
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

// ---- 1. spec 校验 ----
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

// ---- 2. 应用 ----
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
