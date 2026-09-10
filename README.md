# Ouli Super Plugins

Ouli 的个人插件合集（源码托管 / 备份仓库），包含 Claude Code skill 插件、MCP Server 与 Agent Skill。

## 插件列表

### Skill 插件（Claude Code Plugin）

| 子目录 | 插件名 | 版本 | 说明 |
|---|---|---|---|
| [`SuperWork/`](SuperWork/) | `superwork` | 1.5.0 | 全量精选 skill 组合包：TDD、debugging、code review、grilling、domain-modeling、verification 等 16 个 skill |
| [`SuperLite/`](SuperLite/) | `superlite` | 1.0.0 | 轻量 skill 包：TDD、debugging、review、verification + 通用 writing、research、grilling、handoff |

### MCP Server（Python 包，同步自各自独立仓库）

| 子目录 | 包名 | 版本 | 独立仓库 | 说明 |
|---|---|---|---|---|
| [`FastGraph-MCP/`](FastGraph-MCP/) | `fastgraph-mcp` | 0.1.0 | [ouli-1242/FastGraph-mcp](https://github.com/ouli-1242/FastGraph-mcp) | 轻量实时代码智能 MCP：AST + 增量索引 + 代码图，无 embedding、低内存、低 context；提供项目级检索、调用图与影响分析 |
| [`Hound-MCP/`](Hound-MCP/) | `hound-mcp` | 13.14 | [ouli-1242/hound-mcp](https://github.com/ouli-1242/hound-mcp) | 让 AI 代理访问互联网：抓取、爬取、反爬绕过、PDF（含扫描件）解析、无密钥网页搜索，共 8 个工具（二创自 [dondai1234/master-fetch](https://github.com/dondai1234/master-fetch)） |
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
| [`提示词/opencode-AGENTS.md`](提示词/opencode-AGENTS.md) | OpenCode | 全局 AGENTS.md 配置 |
| [`提示词/hermesSOUL.md`](提示词/hermesSOUL.md) | Hermes | 身份与判断准则（SOUL） |
| [`提示词/hermes笔记.md`](提示词/hermes笔记.md) | Hermes | 默认操作流程（WORK） |
| [`提示词/RULE.md`](提示词/RULE.md) | 通用 | 编码与 Agent 行为规则 |
| [`提示词/Rule.mdc`](提示词/Rule.mdc) | Cursor | 规则文件（`.mdc`，`alwaysApply: true`） |
| [`提示词/1bs.md`](提示词/1bs.md) | 通用 | 第一性原理 + 对抗性审阅提示词 |
| [`提示词/2unc.md`](提示词/2unc.md) | 通用 | 不确定性枚举与验证方式提示词 |

## 说明

- **提示词配置**：`提示词/` 为各客户端全局规则 / 提示词源文件，按需复制到对应客户端的配置路径（如 `~/.claude/CLAUDE.md`、`~/.codex/AGENTS.md`）。
- **Skill 插件**：`SuperWork/`、`SuperLite/` 各是完整独立的 Claude Code 插件（含 `.claude-plugin/` 与 `marketplace.json`，`source: "./"`）。如需直接安装，请分别单独建仓后再执行 `claude plugin install <repo-url>`。
- **MCP Server**：`FastGraph-MCP/`、`Hound-MCP/`、`DeepEye-MCP/` 为 Python 包源码，本仓库为其镜像收录，开发与发布以各自独立仓库为准。安装方式见各子目录 README（`pip install .` 或 `pip install -e .`）。其中 **`Hound-MCP/` 是 [dondai1234/master-fetch](https://github.com/dondai1234/master-fetch) 的二创**、**`DeepEye-MCP/` 是 [Favio8/deepeye](https://github.com/Favio8/deepeye) 的二创**（上游均为 MIT，原始版权归各自原作者；完整声明见各子目录 `README.md` 的「致谢」段与 `LICENSE`）。
- **Agent Skill**：`chaoxing-tasker/` 为单个 `SKILL.md`，放入对应客户端的 skills 目录即可使用；`find-extensions/` 为 `SKILL.md` + `references/`（含 `search.mjs`，需 Node 运行），整体放入 skills 目录即可使用。
- 各子目录保留其原有的 README、依赖声明、忽略规则与第三方许可说明（如 `Hound-MCP/LICENSE`、`Hound-MCP/NOTICE.ddgs.txt`），使用前请一并阅读。
- 本仓库其余内容 MIT License，作者 Ouli；`Hound-MCP/`、`DeepEye-MCP/` 及其派生代码的版权归属见各子目录的 `LICENSE` 与 `README.md`「致谢」段。
