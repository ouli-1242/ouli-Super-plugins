# FastGraph-MCP

> Lightweight code intelligence MCP for coding agents.
> AST + Incremental Index + Code Graph, zero embeddings, low memory, low context.

FastGraph-MCP 是一个轻量级代码智能 MCP 服务器，补充 Serena 等编辑型 MCP 所缺的**项目级检索、调用图、影响分析与变更感知**，定位是"高速代码导航层"：

- **快**：首次索引中型项目数秒~十几秒（实测 525 文件 17.8s）；典型查询 <100ms；**增量更新只重解析改动文件**，编辑保存后无需全量重建
- **轻**：无 embedding 模型、无图数据库、无 LSP；常驻内存 <50MB（实测 525 文件峰值 43MB）
- **省 Context**：所有工具只返回 `file / symbol / line / relation`，绝不返回文件正文
- **补 Serena**：全局符号搜索、call graph、impact_analysis、git diff 变更意识、项目架构概览

## 目录

- [快速开始（5 分钟）](#快速开始5-分钟)
- [MCP 配置](#mcp-配置)
- [工具速查（17 个）](#工具速查17-个)
- [与 Serena 分工](#与-serena-分工)
- [支持语言](#支持语言)
- [开发](#开发)
- [路线图](#路线图)

## 快速开始（5 分钟）

**1. 安装（只需一次，二选一）**

### 方式一：正式安装（日常使用）

```bash
cd /path/to/FastGraph-mcp
python -m pip install .
```

- 代码复制进 `site-packages`，之后可以删除/移动源码文件夹
- 更新时重新 `pip install .` 即可
- MCP 配置不依赖源码路径

### 方式二：开发者安装（要改 FastGraph 源码）

```bash
cd /path/to/FastGraph-mcp
python -m pip install -e .
```

- editable 安装，改动即时生效，无需重装
- 依赖源码文件夹保留（不能删）

安装方式切换：从 editable 切回正式版，先卸掉 editable 记录再装：

```bash
python -m pip uninstall fastgraph-mcp   # 先卸掉 editable 记录
python -m pip install .                 # 再装正式版
```

**2. 配置 MCP（只需一次，全局即可）**

零配置模式：**不写 `--root`、不写 `cwd`**。你打开哪个项目，FastGraph 就索引哪个项目。

Claude Code（`~/.claude.json` 或项目 `.mcp.json`）：

```json
{
  "mcpServers": {
    "fastgraph": {
      "command": "python",
      "args": ["-m", "fastgraph"]
    }
  }
}
```

OpenCode（`opencode.json`）：

```json
{
  "mcp": {
    "fastgraph": {
      "type": "local",
      "enabled": true,
      "command": ["python", "-m", "fastgraph"]
    }
  }
}
```

**3. 使用**

打开任何项目即可调用工具（如 `project_overview` 看全貌）。首次调用自动建索引，之后增量更新。

桌面客户端（Claude Desktop 等）见下方 [MCP 配置](#mcp-配置)：先调 `activate_project(root="项目路径")` 会话内激活当前文件夹。

## MCP 配置

### 零配置（推荐，默认模式）

`--root` 缺省时自动探测项目根：从启动目录向上找最近的 git 根（有 `.git` 即视为仓库边界）；非 git 目录用启动目录本身。

| 需求 | 命令行 | 说明 |
| --- | --- | --- |
| 打开哪个项目就用哪个（推荐） | `python -m fastgraph` | 客户端从当前项目目录启动 server |
| 固定分析某个目录 | `python -m fastgraph --root D:/work/my-project` | `--root` 显式指定后不做自动探测 |
| 桌面客户端（Claude Desktop 等） | 先调 `activate_project(root="D:/my/project")` | Serena 同款：会话内激活项目，之后所有工具自动指向它；换项目再调一次 |
| 单次跨项目查询 | 工具传 `root="D:/my/project"` 可选参数 | 不传用激活的/默认 root |
| 固定分析 + 不改参数（桌面客户端） | 配置 `env`：`FASTGRAPH_ROOT: "D:/tools"` | 环境变量等效 `--root`，优先级低于 `--root`、高于自动探测 |
| 同时分析多个项目 | 复制整段配置，每个用不同名字 + `--root`；或单实例用 `root=` 参数切 | 一次只能挂一个实例 |

> 命令行放入客户端配置的写法随客户端而异：Claude Code 拆成 `command` + `args` 数组（见上方快速开始）；OpenCode 把整条命令行放进 `command` 数组（如 `["python", "-m", "fastgraph", "--root", "D:/work/my-project"]`）、`type` 用 `"local"`、并需 `enabled: true`。

> ⚠️ 两个路径**完全不同**：`--root` 是要被索引的**目标项目**；`cwd` 是 **FastGraph 仓库自身**（未安装时兜底 import）。最容易犯的错：把两者填成同一个目录，结果把 FastGraph 源码当成了索引对象——已安装时 `cwd` 可省略。

> 💡 **桌面客户端（Claude Desktop 等）**：它们以固定工作目录（如 `C:\Windows\System32`）启动 MCP 进程，零配置探测永远拿不到项目。解法与 Serena 相同——先调 **`activate_project(root="C:/my/project")`** 会话内激活项目，之后所有工具自动指向它；换文件夹时再调一次即可。每个工具也支持可选 `root` 参数做单次跨项目查询（不传用激活的/默认 root）。路径不可写时默认 root 自动回退用户主目录并打印 notice。

### 注意事项

- **venv**：用虚拟环境时把 `command` 换成 venv 的 python 绝对路径（如 `D:/tools/FastGraph-mcp/.venv/Scripts/python.exe`）
- **Windows `python` 别名**：不要用微软商店安装的 `python` 别名（py 启动器）；用 `where python` 确认真实解释器
- **Windows 路径**：JSON 里反斜杠要转义（`"D:\\work\\my-project"`），推荐写正斜杠 `"D:/work/my-project"`，完全兼容
- **非 Claude Code / OpenCode**（Cursor、Zed、VS Code MCP 插件等）：同是 stdio MCP，但字段命名按各自 schema（有的拆 `command`+`args`，有的用整条命令数组），套用上表命令行即可
- 配置后建议跑一次任意工具（如 `project_overview`），确认 stdout 是 MCP 协议而非报错

#### 性能诊断（可选）：`FASTGRAPH_DEBUG`

默认工具响应很短，`refresh` 统计只在索引真正重解析/报错时出现。排查查询/索引性能时，可在 MCP 配置的 `env` 里加：

```json
{
  "mcpServers": {
    "fastgraph": {
      "command": "python",
      "args": ["-m", "fastgraph"],
      "env": { "FASTGRAPH_DEBUG": "1" }
    }
  }
}
```

打开后**每次工具响应都带 `refresh` 统计**（`scanned` / `parsed` / `deleted` / `errors` / `refresh_ms`），其中 `refresh_ms` 是每次调用前的索引增量检查耗时（查询的主要开销来源）。平时不用开，定位慢查询时再开。

## 工具速查（17 个）

按任务选工具：

| 任务 | 工具 | 说明 |
| --- | --- | --- |
| 先激活当前项目（桌面端必调） | `activate_project(root)` | 之后所有工具指向该文件夹；每个工具也可传 `root=` 做单次跨项目查询 |
| 陌生代码库，先看全局 | `project_overview()` | 语言/文件符号数/入口点/顶层布局/跨模块依赖方向/解析失败文件 |
| 不知道某段代码在哪 | `code_search(query, kind?, limit?)` | 按关键词/符号名/自然语言定位代码 |
| 想知道一个符号是什么 | `symbol_info(symbol)` | 文件、行号、签名、doc、它调用了谁（支持 `Class.method`） |
| 准备读某个文件 | `file_symbols(path)` | 文件内符号清单（kind/签名/行号），先看结构再决定读不读全文 |
| 谁在调用 / 它调用谁 | `find_callers(symbol)` / `find_callees(symbol)` | `depth>=2` 返回多级调用者/完整下游调用树 |
| 两个符号之间有无调用链 | `trace_path(from, to?)` | 不给 `to` 返回 `from` 的调用者链 |
| 继承关系 | `type_hierarchy(symbol)` | 祖先类 + 子类，改基类前查 |
| 改代码前：影响面 | `impact_analysis(symbol, max_depth?)` | 直接调用者(HIGH)/间接(MEDIUM)/测试单列 |
| 改名之前：风险评估 | `rename_impact(symbol)` | 全部定义 + 引用点，HIGH/MEDIUM/LOW 分级 |
| 改 import 前 | `file_deps(path)` | import 了什么（内部 `imports` / 外部 `external_imports` 分开）、被谁 import |
| 找死代码 | `unused_symbols(limit?)` | 无入边的方法/函数（排除测试、入口、接口成员、Vue 模板绑定、uni-app/Vue 生命周期回调；候选需 `find_callers` 复核） |
| 找核心代码 | `hot_symbols(limit?)` | 入边最多的符号 + 测试调用数拆分，回答"这个仓库的核心是什么" |
| 找复杂文件 | `file_metrics(limit?)` | 每文件符号数/出入调用边，快速定位大而复杂的文件 |
| 架构健康 | `module_cycles(max_cycles?)` | 文件间 import 环（强连通分量），最大的排前面 |
| 刚改完代码 | `changed_context()` | git diff → 变更文件/符号 → 受影响的调用者 |

输出统一为 `symbol / file / line / relation`，绝不含文件正文。稳态调用不返回 `refresh`/`ms` 遥测（省 context）；只有索引真正重解析/报错时才带 `refresh` 统计。

## 与 Serena 分工

```
AI Agent
   |
FastGraph ── 项目理解：代码在哪、什么关系、影响范围
Serena    ── 代码操作：读代码、改代码、重构、diagnostics
```

| 阶段 | 先调 FastGraph | 再交给 Serena |
| --- | --- | --- |
| 改名前 | `rename_impact(symbol)` 风险分级 | `rename_symbol` |
| 理解文件 | `file_symbols(path)` 不读正文先看结构 | 读/改正文 |
| 改动前 | `impact_analysis(symbol)` 影响面 | 实施修改 |
| 改 import | `file_deps(path)` 看是 API 还是内部实现 | 修改 |
| 改基类前 | `type_hierarchy(symbol)` 族谱风险 | 修改 |
| 改完复查 | `changed_context()` git diff 波及范围 | — |

FastGraph 不做 LSP / rename / edit / refactor（那是 Serena 的职责）；Serena 没有的**全局检索、call graph、影响分析、git 变更感知**由 FastGraph 补充。定位不是 RAG：

- 无 embedding、无 vector store（对比 CocoIndex/Vera：不跑模型）
- 无图数据库、无 docker 服务（对比 CodeGraphContext 的 docker-compose）
- 仅 17 个工具、输出极小（对比 CodeGraph 45 个工具 + 大输出）
- 增量秒级，无全量重索引（对比常见 RAG 的更新成本）

## 索引机制

- **懒 + 增量（无后台任务）**：每次工具调用前检查一次，mtime+size 比对，只重解析变化的文件；文件删除自动移出索引。没有定时器——不调工具索引就不动，任何保存（即使不提交 git）下次查询即反映
- **首次**：调用任意工具时自动全量扫描（>2MB 文件跳过，Node 黑名单目录排除）
- **位置**：项目 `.fastgraph/index.sqlite`（自动忽略，不污染 git）
- **忽略规则**：`.fastgraph/.fastgraphignore`（gitignore 风格，仅本地生效，首次索引自动生成）——模板自带热门语言默认忽略项（`node_modules/`、`dist/`、`__pycache__/`、`*.min.js`、`.venv/` 等，删行即恢复索引），新增规则后下次调用自动把已索引的文件移出

## 支持语言

Python、TypeScript/TSX、JavaScript、**Vue (`.vue`)、Svelte (`.svelte`)**、Go、Rust、Java、C/C++（`.c/.h/.cpp/.cc/.hpp`）

Vue/Svelte 通过提取 `<script>` 块解析（支持 `lang="ts"`），符号行号对齐原始 `.vue/.svelte` 文件；JSX/TSX 直接支持。

## 开发

```bash
pip install -e ".[dev]"   # pytest
python -m pytest tests/
```

测试覆盖：索引、搜索、callers/callees、trace、impact、增量更新、git 变更感知、Vue/Svelte 前端组件。

## 路线图

- [x] Phase 1：MCP Server + tree-sitter + SQLite + `code_search`/`project_overview`
- [x] Phase 2：call graph（calls/imports/inherits）+ `find_callers/find_callees/trace_path`
- [x] Phase 3：`impact_analysis` + `changed_context`（git diff 集成）
- [x] Phase 3.5：分析工具（`unused_symbols` / `hot_symbols` / `file_metrics` / `module_cycles`）+ Vue 模板引用、别名导入、内容搜索、`@` 别名 file_deps、类级 call graph
- [ ] Phase 4：可选 BM25/embedding 语义搜索（--no-embed 模式默认关闭）
- [ ] Phase 5：多项目 workspace 支持

## 常见问题（FAQ）

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 工具不可见 / 启动失败 | 未安装，或 `python` 是微软商店别名 | 仓库目录跑 `python -m fastgraph` 验证；用 `where python` 确认真实解释器 |
| 索引了错误目录（如 FastGraph 仓库自己） | `--root` / `cwd` 填成了同一个路径 | 显式指定 `--root 目标项目`；或检查客户端启动目录 |
| 改了代码但查询结果旧 | 增量刷新未触发（如文件被 git 操作替换） | 删除目标项目 `.fastgraph/index.sqlite`，下次调用自动重建 |
| 首工具调用慢（数秒~十几秒） | 首次全量索引 | 正常；之后增量 <100ms |