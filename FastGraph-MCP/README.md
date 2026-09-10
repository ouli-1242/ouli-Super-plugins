# FastGraph-MCP

> Lightweight code intelligence MCP for coding agents.
> AST + Incremental Index + Code Graph, zero embeddings, low memory, low context.

FastGraph-MCP 是一个轻量级代码智能 MCP 服务器，专注**项目级检索、调用图、影响分析与变更感知**，定位是"高速代码导航层"——可以单独使用，也可以与编辑器 / LSP 类工具配合：

- **快**：首次索引中型项目数秒~十几秒（实测 525 文件 17.8s）；典型查询 <100ms；**增量更新只重解析改动文件**，编辑保存后无需全量重建
- **轻**：无 embedding 模型、无图数据库、无 LSP；常驻内存 <50MB（实测 525 文件峰值 43MB）
- **省 Context**：所有工具只返回 `file / symbol / line / relation`，绝不返回文件正文
- **补 LSP 所短**：全局符号搜索、call graph、impact_analysis、git diff 变更意识、项目架构概览

## 目录

- [快速开始（5 分钟）](#快速开始5-分钟)
- [MCP 配置](#mcp-配置)
- [工具速查](#工具速查)
- [边界（做什么 / 不做什么）](#边界做什么--不做什么)
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
| 桌面客户端（Claude Desktop 等） | 先调 `activate_project(root="D:/my/project")` | 会话内激活项目，之后所有工具自动指向它；换项目再调一次 |
| 单次跨项目查询 | 工具传 `root="D:/my/project"` 可选参数 | 不传用激活的/默认 root；各 root 的索引按 **LRU 最多缓存 8 个**，超出即关闭最久未用者（否则会长期占用外部项目的 `.fastgraph/` 句柄） |
| 固定分析 + 不改参数（桌面客户端） | 配置 `env`：`FASTGRAPH_ROOT: "D:/tools"` | 环境变量等效 `--root`，优先级低于 `--root`、高于自动探测 |
| 同时分析多个项目 | 复制整段配置，每个用不同名字 + `--root`；或单实例用 `root=` 参数切 | 一次只能挂一个实例 |

> 命令行放入客户端配置的写法随客户端而异：Claude Code 拆成 `command` + `args` 数组（见上方快速开始）；OpenCode 把整条命令行放进 `command` 数组（如 `["python", "-m", "fastgraph", "--root", "D:/work/my-project"]`）、`type` 用 `"local"`、并需 `enabled: true`。

> ⚠️ 两个路径**完全不同**：`--root` 是要被索引的**目标项目**；`cwd` 是 **FastGraph 仓库自身**（未安装时兜底 import）。最容易犯的错：把两者填成同一个目录，结果把 FastGraph 源码当成了索引对象——已安装时 `cwd` 可省略。

> 💡 **桌面客户端（Claude Desktop 等）**：它们以固定工作目录（如 `C:\Windows\System32`）启动 MCP 进程，零配置探测永远拿不到项目。解法是先调 **`activate_project(root="C:/my/project")`** 会话内激活项目，之后所有工具自动指向它；换文件夹时再调一次即可。每个工具也支持可选 `root` 参数做单次跨项目查询（不传用激活的/默认 root）。路径不可写时默认 root 自动回退用户主目录并打印 notice。

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

## 工具速查

固定 **13 个工具**，单独使用与配合其他代码工具时都是同一套表面——不做环境探测、不需要切换、也没有隐藏档位：

| 任务 | 工具 | 说明 |
| --- | --- | --- |
| 先激活当前项目（桌面端必调） | `activate_project(root)` | 之后所有工具指向该文件夹；每个工具也可传 `root=` 做单次跨项目查询 |
| 陌生代码库，先看全局 | `project_overview()` | 语言/文件符号数/索引版本/入口点/顶层布局/跨模块依赖方向/解析失败文件 |
| 不知道某段代码在哪 | `code_search(query, kind?, limit?)` | 按关键词/符号名/自然语言定位代码；多词查询要求**每个词都命中符号名**，否则回落到注释/字符串内容检索 |
| 想知道一个符号是什么 | `symbol_info(symbol)` | 文件、行号、签名、doc、它调用了谁（支持 `Class.method`） |
| 准备读某个文件 | `file_symbols(path)` | 文件内符号清单（kind/签名/行号），先看结构再决定读不读全文；被 `limit` 截断时返回 `truncated: true` |
| 读文件 | `read_file(path, start_line?, end_line?)` | 读项目内**任意文本文件**（源码/文档/配置皆可）或其行区间；行号 1-based；不给 `end_line` 时默认返回前 400 行（`total_lines`/`truncated` 说明是否还有更多）；根目录外、dot 段、`.fastgraphignore` 命中的路径**不可读**（与索引可见性一致，密钥类文件读不到）；源码文件另带 `indexed: true` |
| 只读一个符号 | `symbol_body(symbol, max_lines?)` | 只返回该符号的源码，比读整文件更省更准 |
| 谁在调用 / 它调用谁 | `find_callers(symbol, depth?)` / `find_callees(symbol, depth?)` | `depth>=2` 返回多级**传递**调用者 / 完整下游调用树（每条带 `depth`/`via`） |
| 改代码前：影响面 | `impact_analysis(symbol, max_depth?)` | 直接调用者(HIGH)/间接(MEDIUM)/测试单列 |
| 改 import 前 | `file_deps(path)` | import 了什么（内部 `imports` / 外部 `external_imports` 分开）、被谁 import |
| 架构健康 | `module_cycles(max_cycles?)` | 文件间 import 环（强连通分量），最大的排前面 |
| 刚改完代码 | `changed_context()` | git diff → 变更文件/符号 → 受影响的调用者；**非 git 项目**自动退化为"自上次调用以来被重解析的文件"（返回 `source: "mtime"`） |

> **为什么只有 13 个**：每个工具定义都会随**每次请求**重新发送，所以一个工具必须能回答"LSP 类工具答不出、或答起来很贵"的事才值得占位。`trace_path` / `rename_impact` / `type_hierarchy` / `unused_symbols` / `hot_symbols` / `file_metrics` / `get_status` **仍然完整实现、测试覆盖，但不对外暴露**（保留为内部 Python API，随时可一行加回）。逐条理由写在 `fastgraph/server.py` 的 `UNEXPOSED` 注释里。

输出统一为 `symbol / file / line / relation`；只有 `read_file` / `symbol_body` 返回正文（强制字符上限 + `truncated` 标记）。稳态调用不返回 `refresh`/`ms` 遥测（省 context）；只有索引真正重解析/报错时才带 `refresh` 统计。

符号参数同时接受 `Class.method` 与斜杠 name path（`Class/method`，可带前导 `/` 与尾部 `[i]`）；嵌套符号的结果会附带 `name_path` 字段，便于把标识符直接复用。

**行号基准**：FastGraph 全部输出为 **1-based**（与编辑器一致）。注意有些按 0 计数的读取接口（例如 LSP 风格的 `start_line`）需要自行 **减 1**。

## 边界（做什么 / 不做什么）

```
AI Agent
   |
FastGraph        ── 定位与关系：代码在哪、谁调用谁、影响范围、依赖方向、最近改了什么
编辑器 / LSP 工具 ── 操作与精确性：读改代码、重构、rename、diagnostics
```

| 阶段 | 先调 FastGraph | 再交给编辑器 / LSP 工具 |
| --- | --- | --- |
| 定位代码 | `code_search` / `symbol_info` / `file_symbols` | 读/改正文 |
| 理解文件 | `file_symbols(path)` 不读正文先看结构 | 读/改正文 |
| 改动前 | `impact_analysis(symbol)` 影响面 | 实施修改 |
| 改 import | `file_deps(path)` 看是 API 还是内部实现 | 修改 |
| 改完复查 | `changed_context()` git diff 波及范围 | — |

FastGraph **不做** edit / rename / refactor / diagnostics——那是 LSP 类工具的职责，而且它们做得更准。对应地，**全局检索、call graph、影响分析、依赖图、git 变更感知**是 FastGraph 补上的那部分。定位不是 RAG：

- 无 embedding、无 vector store（对比 CocoIndex/Vera：不跑模型）
- 无图数据库、无 docker 服务（对比 CodeGraphContext 的 docker-compose）
- 仅 13 个工具、输出极小（对比 CodeGraph 45 个工具 + 大输出）
- 增量秒级，无全量重索引（对比常见 RAG 的更新成本）

## 索引机制

- **懒 + 增量（无后台任务）**：每次工具调用前检查一次，mtime+size 比对，只重解析变化的文件；文件删除自动移出索引。没有定时器——不调工具索引就不动，任何保存（即使不提交 git）下次查询即反映
- **模块级调用**：每个文件都有一个 `module` 符号，**导入期执行的调用**（`register_adapter(...)`、`app.include_router(...)`、`if __name__ == "__main__": main()`）挂在它名下，所以调用图与死代码检测不会被"装配层"代码骗过（当前覆盖 Python 与 TS/JS/Vue/Svelte；Go/Rust/Java/C++ 尚未接入）
- **首次**：调用任意工具时自动全量扫描（>2MB 文件跳过，Node 黑名单目录排除）
- **位置**：项目 `.fastgraph/index.sqlite`（自动忽略，不污染 git）
- **忽略规则**：`.fastgraph/.fastgraphignore`（gitignore 风格，仅本地生效，首次索引自动生成）——模板自带热门语言默认忽略项（`node_modules/`、`dist/`、`__pycache__/`、`*.min.js`、`.venv/` 等，删行即恢复索引），新增规则后下次调用自动把已索引的文件移出

## 支持语言

Python、TypeScript/TSX、JavaScript、**Vue (`.vue`)、Svelte (`.svelte`)**、Go、Rust、Java、C/C++（`.c/.h/.cpp/.cc/.hpp`）

Vue/Svelte 通过提取 `<script>` 块解析（支持 `lang="ts"`），符号行号对齐原始 `.vue/.svelte` 文件；JSX/TSX 直接支持。

**依赖图（`file_deps` / `module_cycles` / `project_overview.layering`）按语言的 import 写法解析**：

| 语言 | import 写法 | 内部依赖解析 |
| --- | --- | --- |
| Python / TS-JS / Vue / Svelte | `from x import y`、`import … from`、`require()` | ✓ |
| Java | `import com.a.B;` | ✓ |
| Go | `import (...)` 块 / `import "x"` | ✓（按 go.mod 的 module 前缀映射到包目录，见下） |
| Rust | `use crate::a::b::Item;` | ✓（剥 `crate/self/super`，去掉末段 item） |
| C/C++ | `#include "x.h"` / `#include <x>` | ✓（按 basename 匹配；`<>` 系统头自然落空） |

解析顺序：**别名**（tsconfig `paths` / `baseUrl`、vite `alias`、uni-app `@`）→ **导入文件所在目录**（相对路径按路径解析，否则同目录及父目录按文件名匹配）→ **目录入口**（`import './server'` → `server/index.ts`；`from . import x`、`import pkg.sub` → `x.py` / `sub/__init__.py`，仅 Python 与 JS 家族，显式写了扩展名时不回退到目录）→ **全库后缀匹配**。每一步都要求：

- **扩展名一致**：`#include "jv.h"` 不会配到 `jv.c`（`.js` 允许落到 `.ts`，Node 的 TS 解析约定）
- **目标类型属于导入语言的文件族**：`.py` 里的 `import os` 不会配到 C++ 的 `os.h`
- JS/TS 的**裸标识符按 Node 语义视为 npm 包**（项目里的同名文件不再被误连），除非项目配了 `baseUrl`

实测效果（6 个真实仓库：axios / cobra / fmt / gson / jq / ripgrep）：多候选（歧义）的 import 行 **324 → 0**，同时唯一命中的边从 1357 增至 1634。

目录入口的实测：vite 的 76 条目录型相对导入（`import './x'`，`x` 是目录）从"未解析"变为命中 `x/index.js`；requests 的 11 条 `from . import X` 全部命中（`_types.py`、`sub/__init__.py`，以及包入口 re-export 的 `tests/__init__.py`），相对导入未解析行 **11 → 0**。

### 调用图的边界（重要）

**调用图（`find_callers` / `find_callees` / `impact_analysis`）是名字解析的近似结果，不是类型推断的结论**，使用时必须知道三件事：

| 事实 | 说明 |
| --- | --- |
| 解析率 | 真实仓库上 **21%~40%** 的调用边能连到唯一确定的符号（6 个仓库实测）。其余要么指向外部库（`len()`、`assert.Equal`），要么接收者类型无法静态确定（`svc.run()` 而项目里有多个 `run`）—— 后者一律**不连边**，不猜 |
| `via` 字段 | 每条调用者带 `via`：`"resolved"` = 已解析的调用边；`"text"` = 未解析、仅因调用文本同名而折叠上来的**猜测**（如 `thing.do_x()` 撞上一个叫 `thing` 的类） |
| `unresolved_incoming` / `unresolved_outgoing` | 名字指向该符号、但无法唯一确定的边数。**空列表 ≠ 没有调用者**：出现这个字段就按"未知"处理，绝不能据此判定"没人调用/可以删" |

不做的：类型推断。`self.x()` 的接收者归属、接口实现、回调注册、动态派发（`getattr`、依赖注入容器）都不会连边 —— 宁可漏，不可错。

索引的其它盲区由 `project_overview` 报出：`skipped_large_files`（超过 2MB 未索引，也不进 `parse_errors`）与 `scan_truncated`（扫描条目超过 20 万，索引是部分结果）。

**Go 与 Rust 走模块根解析**，不再靠文件名猜：

- **Go**：读最近的 `go.mod` 的 `module` 行，`"<module>/internal/x"` 精确映射到 `internal/x/` 目录（一个 Go import = 一个包 = 该目录下的文件）；不匹配该前缀的一律判为 stdlib/第三方
- **Rust**：按 crate root（`…/src`、`…/tests` 等，集成测试自带 crate）解析 `crate::a::b` → `a/b.rs` 或 `a/b/mod.rs`；`self::`/`super::` 按模块相对逐级向上

仍未做的：C++ 的 `-I` 搜索路径拿不到（依赖构建系统），`<...>` 系统头也未与项目头区分；C# 尚无解析器。另外 Rust 的父子模块（`mod.rs` ↔ 同目录子模块）互指是模块树的结构性事实，`module_cycles` 会把它报成 2 环。

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