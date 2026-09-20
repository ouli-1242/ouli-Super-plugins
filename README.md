# Ouli Super Plugins

Ouli 的个人插件合集（源码托管 / 备份仓库），包含 Claude Code skill 插件、MCP Server 与 Agent Skill。

## 插件列表

### Skill 插件（Agent Plugin）

| 子目录 | 插件名 | 说明 |
|---|---|---|
| [`SuperWork/`](SuperWork/) | `superwork` | 全量精选 skill 组合包（17 个 skill）：TDD/debugging/code review/grilling/domain-modeling/verification + spec→plan→execute 全链条 + 文档导航 spine（docs/ 中文约定） |
| [`SuperLite/`](SuperLite/) | `superlite` | 日常轻量包（10 个 skill）：写作/总结/查证/决策 + TDD/debugging/review/verification + handoff/doc-index；日常一次性任务零仪式，固定成本约 SuperWork 的 53% |
| [`SuperOffice/`](SuperOffice/) | `superoffice` | 通用办公产物包（12 个 skill）：整理输入/起草/修改/审阅/数据汇总/文件手术/填表/产物验证/模板资产 + WPS CLI 与办公 MCP 使能；动词层架构，数字与引用真实性纪律 |


### MCP Server（Python 包，同步自各自独立仓库）

| 子目录 | 包名 | 版本 | 独立仓库 | 说明 |
|---|---|---|---|---|
| [`FastGraph-MCP/`](FastGraph-MCP/) | `fastgraph-mcp` | 0.2.0 | [ouli-1242/FastGraph-mcp](https://github.com/ouli-1242/FastGraph-mcp) | 轻量实时代码智能 MCP：AST + 增量索引 + 代码图，无 embedding、低内存、低 context；提供项目级检索、调用图与影响分析 |
| [`Dhole-MCP/`](Dhole-MCP/) | `dhole-mcp` | 14.0 | [ouli-1242/dhole-mcp](https://github.com/ouli-1242/dhole-mcp) | 让 AI 代理访问互联网：抓取、爬取、反爬绕过、PDF（含扫描件）解析、无密钥网页搜索，共 8 个工具（二创自 [dondai1234/master-fetch](https://github.com/dondai1234/master-fetch)） |
| [`DeepEye-MCP/`](DeepEye-MCP/) | `deepeye-mcp` | 0.2.0 | [ouli-1242/deepeye-mcp](https://github.com/ouli-1242/deepeye-mcp) | 为纯文本大模型提供视觉能力：图像描述 / OCR / 视觉问答 / 布局分析（二创自 [Favio8/deepeye](https://github.com/Favio8/deepeye)） |

### Agent Skill

| 子目录 | 名称 | 说明 |
|---|---|---|
| [`chaoxing-tasker/`](chaoxing-tasker/) | `chaoxing-tasker` | 超星学习通任务助手：通过浏览器自动化完成作业、考试、签到、课点/视频、讨论任务，并汇报待办清单与完成结果 |
| [`find-extensions/`](find-extensions/) | `find-extensions` | 扩展发现助手：按 skills / mcp / plugins 多渠道检索并按流行度分层推荐，给出各客户端对应的安装命令 |

### 提示词配置（Prompt 配置）

| 文件 | 适用客户端 | 说明 |
|---|---|---|
| [`提示词/CLAUDE.md`](提示词/CLAUDE.md) | Claude Code | 全局 CLAUDE.md 配置 |
| [`提示词/codex-AGENTS.md`](提示词/codex-AGENTS.md) | Codex | 全局 AGENTS.md 配置 |
| [`提示词/dsh-AGENTS.md`](提示词/dsh-AGENTS.md) | DSH | 全局 AGENTS.md 配置 |
| [`提示词/opencode-AGENTS.md`](提示词/opencode-AGENTS.md) | OpenCode | 全局 AGENTS.md 配置 |
| [`提示词/hermesSOUL.md`](提示词/hermesSOUL.md) | Hermes | 身份与判断准则（SOUL） |
| [`提示词/hermesWORK.md`](提示词/hermesWORK.md) | Hermes | 默认操作流程（WORK） |
| [`提示词/RULE.md`](提示词/RULE.md) | 通用 | 通用编码与 Agent 行为规则源（纯 Markdown，可套用至各 agent；Rule.mdc 为 Cursor 应用版） |
| [`提示词/Rule.mdc`](提示词/Rule.mdc) | Cursor | Cursor 规则应用版（`.mdc`，`alwaysApply: true`） |
| [`提示词/1bs.md`](提示词/1bs.md) | 通用 | 第一性原理 + 对抗性审阅提示词 |
| [`提示词/2unc.md`](提示词/2unc.md) | 通用 | 不确定性枚举与验证方式提示词 |

## 说明

- **提示词配置**：`提示词/` 为各客户端全局规则 / 提示词源文件，按需复制到对应客户端的配置路径（如 `~/.claude/CLAUDE.md`、`~/.codex/AGENTS.md`、`~/.dsh/AGENTS.md`）。
- **Skill 插件**：`SuperWork/`、`SuperLite/`、`SuperOffice/` 各是独立 skill 包。每个包内是**一个通用源 + 两个派生文件夹 + 一个前沿模型变体**，直接复制进对应 agent 的 skills 目录即可用：
  - `agents-skills/` — **通用源**（长描述，frontmatter 仅 `name` + `description`），适配 DSH / Claude Code / Codex / Cursor / ZCode / Qoder / Gemini CLI / opencode / CodeBuddy / Kimi / Grok；其中多家直接扫描共享根 `~/.agents/skills/`，装一次多端可见。
  - `codex-skills/` — 派生：同内容 + Codex 专属的 `agents/openai.yaml`（UI 元数据与 `policy.allow_implicit_invocation`）。
  - `zcode-skills/` — 派生：短描述（≤250 字符，保留中文触发锚点），因为 ZCode 每轮只把描述的前 250 字符注入上下文。
  - `NB-skills/` — **前沿模型专用变体**（能力合同版），**给前沿模型使用**：同名单单独成套（与父包同名路由 + 域 skill），正文为英文，把过程菜谱改写为结果约束 / 边界约束 / 安全约束 / 验收约束（目标 + 能力边界 + 输入输出契约 + 失败升级 + 成本预算 + 停止条件），每个 skill 附 `contract.yaml`（`risk_level`、`permissions`、`acceptance_criteria`、`fallback_variant`、`review_cycle` 等）。**同一 harness 二选一安装，勿与父包同装**；本目录即唯一源，无构建脚本、无派生目录。详见各包 README 的「★ NB-skills」节。
  - `bundle.json`（装哪些 skill + Codex 策略表）、`agents.json`（12 个 agent 的安装路径与应取文件夹）、`scripts/`（生成 / 安装 / 校验工具）。装到本机：`pwsh -File <包>/scripts/install-skills.ps1 -Agent claude,dsh,codex`（默认 junction 链接，仓库即唯一源）。
  - 已核实的 harness 机制与硬规则（frontmatter 字段、描述长度上限、目录约定）见各包 README 的「安装」与「多端兼容硬规则」两节。
- **MCP Server**：`FastGraph-MCP/`、`Dhole-MCP/`、`DeepEye-MCP/` 为 Python 包源码，本仓库为其镜像收录，开发与发布以各自独立仓库为准。安装方式：`pip install fastgraph-mcp` / `pip install "dhole-mcp[all]"` / `pip install deepeye-mcp`（均已在 PyPI 发布）。其中 **`Dhole-MCP/` 是 [dondai1234/master-fetch](https://github.com/dondai1234/master-fetch) 的二创**、**`DeepEye-MCP/` 是 [Favio8/deepeye](https://github.com/Favio8/deepeye) 的二创**（上游均为 MIT，原始版权归各自原作者；完整声明见各子目录 `README.md` 的「致谢」段与 `LICENSE`）。
- **Agent Skill**：`chaoxing-tasker/` 为单个 `SKILL.md`，放入对应客户端的 skills 目录即可使用；`find-extensions/` 为 `SKILL.md` + `references/`（含 `search.mjs`，需 Node 运行），整体放入 skills 目录即可使用。
- 各子目录保留其原有的 README、依赖声明、忽略规则与第三方许可说明（如 `Dhole-MCP/LICENSE`、`Dhole-MCP/NOTICE.ddgs.txt`），使用前请一并阅读。
- 本仓库其余内容 MIT License，作者 Ouli；`Dhole-MCP/`、`DeepEye-MCP/` 及其派生代码的版权归属见各子目录的 `LICENSE` 与 `README.md`「致谢」段。
