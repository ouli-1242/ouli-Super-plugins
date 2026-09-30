<div align="center">

# FastGraph-MCP

**轻量级代码智能 MCP：AST + 增量索引 + 调用图。无 embedding、无图数据库、无 LSP，低内存、低 context。**

<a href="https://pypi.org/project/fastgraph-mcp/"><img src="https://img.shields.io/pypi/v/fastgraph-mcp.svg" alt="PyPI version"></a>
<img src="https://img.shields.io/pypi/pyversions/fastgraph-mcp.svg" alt="Python 3.11+">
<a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-green.svg" alt="MIT License"></a>
<img src="https://img.shields.io/badge/transport-stdio-blueviolet.svg" alt="MCP stdio transport">

</div>

定位是**代码导航层**：代码在哪、谁调用谁、改了影响谁、刚改了什么——补 grep（分不清定义与调用点）和 LSP（无全局调用图/影响分析）的短板。读改代码、重构、diagnostics 交给编辑器/LSP 工具。

## 特性

- **快**：实测冷索引 preact 242 文件 2.6s / vue core 538 文件 6.6s / element-plus 1,979 文件（含 829 个 `.vue`）20.7s；查询本身 0.1~2ms。每次调用另付一次目录扫描（538 文件 ~19ms，2k 文件 ~99ms，17.7k 文件 ~0.8s），改动一个文件后的刷新 140~380ms，取决于该文件自身的调用边密度
- **规模上限**：冷索引的主要成本在调用边解析，因此随**边数**而非文件数增长——kubernetes 的 `staging/src/k8s.io/api`（496 个生成代码密集的 Go 文件、11.8 万条调用边）要 23s，而文件数更多的普通仓库快得多。sentry（17,703 个可索引文件 = 8.1k Python + 8.6k TSX，66 万条调用边）首次索引是几十分钟量级，规划者请把它当"单包/单服务"工具用。**大仓库首次调用不再阻塞**：单次调用最多索引 20 秒就先用已建好的部分回答，并在 `refresh.pending_files` + `hint` 里明说结果不完整（此时"查不到"= 还不知道，不是不存在）；后续调用自动续建，想一次建完就调 `reindex()`（预算可用环境变量 `FASTGRAPH_INDEX_BUDGET_S` 调大或调小）。实测 4,788 文件的包：7 次调用、最长一次 41s 建完，与一次阻塞 157s 建出来的索引**逐条指纹完全相同**；收尾那次唯一没被预算切的阶段是全量依赖边重建，它在 17,700 文件 / 14.7 万 import 上实测 9.7s。写盘按 128 文件一批提交，中断、超时或 IDE 重启都不丢已完成的部分
- **检索排序与中文**：`code_search` 的文档/签名命中按 **BM25 加权**排（`name` 4.0、`qualified_name` 3.0、`signature` 1.5、`doc` 1.0、`kind` 0.1、`file_path` 1.0），同分时才回到"源码目录优先"的位置启发式——此前命中只按路径与行号排，等于让"碰巧先被索引的文件"代替"真正在讲这件事的文档"。中文/日文这类连续文本由第二张 **FTS5 trigram 索引**负责：`unicode61` 不切 CJK 语流，所以整条中文 docstring 是一个 token，词面前缀匹配结构上就命中不了。规则是**按字符数分工**——一个 trigram 至少 3 字符，≥3 字符的词走索引（多词 AND，比原先只取第一个词的 LIKE 精确），更短的词与不含 trigram 支持的 SQLite 构建自动退回 LIKE 全表扫。实测（合成语料，每符号一条中文 docstring）：查询耗时 trigram 恒定 ~1.6ms，LIKE 随规模线性走（1.2k 符号 0.5ms → 9.6k 符号 4.0ms），小仓库仍是 LIKE 更快，收益在千级符号之后。**英文仓库不付这份钱**：只有含非 ASCII 文本的行才进第二张表，1200 文件全中文 docstring 的库索引体积 1.99MB → 2.04MB。零新依赖，`pyproject` 仍然只有 `mcp` + tree-sitter
- **顺带修掉一个老缺陷**：单行 `"""docstring"""` 会被"三引号采集"和"单行字符串字面量采集"两条路径各存一次，去引号后完全相同，于是内容检索的同一条正文能占掉两个结果位（实测五结果里两个是重复行）。现在采集侧去重，查询侧也对**已存在的重复行**去重——为了这个瑕疵去重解析所有仓库上的索引，代价明显不对
- **轻**：无 embedding 模型、无图数据库、无 LSP；索引一个中型仓库额外占用约 10MB（进程基础占用 ~56MB，其中绝大部分是 MCP SDK 与 pydantic 的导入开销，非本项目可控），万级文件仓库约 ~80MB / 索引文件 ~316MB
- **省 context**：所有工具只返回 `file / symbol / line / relation`，不返回文件正文（仅 `read_code` 例外，且有硬上限）
- **诚实**：调用图是名字解析的近似而非类型推断；解析不了的边显式报 `unresolved_incoming`/`unresolved_outgoing`，绝不猜、绝不把"空列表"伪装成"没人用"

## 安装

```bash
pip install fastgraph-mcp           # 日常使用
pip install "fastgraph-mcp[dev]"    # 开发者
```

从源码安装：

```bash
git clone https://github.com/ouli-1242/FastGraph-mcp.git
cd FastGraph-mcp
python -m pip install .              # 日常使用（装完源码目录可删）
python -m pip install -e ".[dev]"    # 开发者（改动即时生效）
```

要求 Python ≥ 3.11。

## 快速开始

**1. 配置 MCP**（零配置：不写 `--root`、不写 `cwd`，打开哪个项目就索引哪个项目）

> `-P` 不是可省的（Python ≥ 3.11）：`python -m x` 会把进程 cwd 排到 `sys.path` 最前面，而桌面客户端就是以你的项目目录为 cwd 启动 MCP 进程的。项目里只要有与标准库同名的顶层包/模块（`types/`、`json/`、`logging/`……），解释器在加载 `runpy` 阶段就崩了，服务器在 MCP 握手之前退出（sentry 的 `src/sentry/types/` 就会触发）。`-P` 只关掉「不把 cwd/脚本目录加进 sys.path」这一件事。`python -I -m fastgraph` 或直接调用装好的 `fastgraph` 命令同样有效，但 `-I` 是隔离模式，还会忽略 `PYTHONPATH` 与用户 site-packages——用 `pip install --user`／靠 PYTHONPATH 跑源码开发版的人会因此找不到包。

Claude Code（`~/.claude.json` 或项目 `.mcp.json`）：

```json
{
  "mcpServers": {
    "fastgraph": {
      "command": "python",
      "args": ["-P", "-m", "fastgraph"]
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
      "command": ["python", "-P", "-m", "fastgraph"]
    }
  }
}
```

**2. 使用**：打开任意项目，调用任意工具（推荐先 `project_overview`）即自动建索引，之后增量更新。

桌面客户端（Claude Desktop、Qoder 等，以固定 cwd 启动 MCP 进程——Qoder 实测以用户主目录为 cwd）先调一次 `activate_project(root="/abs/path")` 激活项目；换项目再调一次。要固定分析某个目录，启动参数加 `--root D:/work/my-project`（或环境变量 `FASTGRAPH_ROOT`）。

> Windows 注意：`python` 不要用微软商店别名（用 `where python` 确认）；JSON 路径推荐写正斜杠 `D:/work/project`。

**3. 索引存在哪**：`<项目>/.fastgraph/index.sqlite`（SQLite WAL，纯本地，删掉即重建）。实测规模：17,703 文件的仓库索引 316MB。该目录自带 `.gitignore`（内容为 `*`），不会出现在你项目的 `git status` 里，也不需要改你自己的 `.gitignore`。要额外排除目录/文件，编辑 `.fastgraph/.fastgraphignore`（首次索引自动生成带注释的模板，默认已排除 `.venv`/`node_modules`/`dist`/密钥文件等）；被排除的文件会从索引里删除。首次索引分批落盘（每 256 个文件提交一次），中断或 IDE 重启后续建而不从头开始。

## 让模型主动使用

MCP 工具对模型是可选的——不引导，模型默认用自己顺手的 grep/read。最有效的一步：把下面这段粘贴进项目的 `CLAUDE.md` / `AGENTS.md`（服务端 instructions 与工具描述已内置同样的决策表）：

```md
## 代码导航：用 FastGraph MCP，不要先用 grep
- 找代码在哪 / 找用法：先 code_search
- 打开不熟悉的文件前：先 read_code(path, structure=true) 看结构
- 回答"谁调用了 X"：用 call_graph(X, direction="in")（结果为空但带 unresolved_incoming>0 表示有调用者未解析；若两者都没有而带 imported_by，说明它是被读取的枚举/常量，都不能当无人使用）
- 改函数/类之前：先 impact_analysis(symbol) 看影响面
- 改 import 前：file_deps(path)；查架构：module_cycles()
- 只读一个符号：read_code(name)；读整文件用 read_code(path)
- 改完代码：changes() 复查波及范围
- 进陌生仓库：先 project_overview()
```

## 工具（默认 15 个：11 只读 + 4 记忆）

| 任务 | 工具 |
| --- | --- |
| 桌面端激活项目 | `activate_project(root)` |
| 大仓库不想等（`full=true` 则清掉重建） | `reindex(full?)` |
| 陌生仓库看全局 | `project_overview()` |
| 按关键词/自然语言定位代码 | `code_search(query, kind?, limit?)` |
| 一个符号是什么 | `symbol_info(symbol)` |
| 读代码：整文件 / 行区间 / 单个符号 / 只要结构 | `read_code(target, start_line?, end_line?, structure?, limit?)` |
| 谁调用它、它调用谁（`depth≥2` 传递） | `call_graph(symbol, direction?, depth?, limit?)` |
| 改动前看影响面 | `impact_analysis(symbol)` |
| import 了什么 / 被谁 import | `file_deps(path)` |
| 文件间 import 环（架构健康） | `module_cycles()` |
| 改完看变更波及（git 工作树/分支，或对比某个基线） | `changes(base?, since?, to?)` |

推荐节奏：`project_overview` → `code_search` 定位 → `read_code` 读 → `impact_analysis` 改前 → `changes` 改后。

所有工具都接受可选 `root=` 参数做单次跨项目查询（按 LRU 缓存 8 个项目）。符号名可写 `top`、`Class.method`、`Class/method`，Rust/C++ 的 `Class::method` 与带泛型的 `Controller<'_>::print_file` 也接受（按去泛型后的名字回退匹配）。输出行号全部 1-based。另有 resource `fastgraph://overview` 与 prompt `fastgraph-workflow` 可选配。

## 工具面：`FASTGRAPH_PROFILE=full|lean`

只有 7 个工具时它们的答案是一样的，只是问法不同（读文件还是读符号、查上游还是查下游、跟 git 比还是跟基线比）——而这些区分要调用方在**还不知道自己要什么**的时候先选对。所以合并成 3 个，并把"选错了很便宜"设计进去：响应里的 `mode`（`lines|structure|symbol_body`）与 `in`/`out` 嵌套会说明这次走的是哪条分支。

| profile | 注册的工具 | 什么时候用 |
| --- | --- | --- |
| `full`（默认） | 11 只读 + 4 记忆 = 15 | 单独使用：读、定位、图谱、变更、记忆全都在 |
| `lean` | 8 只读 + 4 记忆 = 12 | 与客户端自带 Read/Grep 或另一个 LSP 代码服务器并存：不再重复 advertise 读文件、找定义、定位代码 |

`lean` 少的恰好是别处已经答得了的三件：`code_search`、`symbol_info`、`read_code`；留下的是图谱聚合（`call_graph` 出边、`impact_analysis`、`file_deps`、`module_cycles`）、变更感知（`changes`）与记忆。**lean 不减能力，只减 advertise**——三个工具都还在 Python 侧，测试也还在跑。

保证这条的是 `tests/test_symbol_name_paths.py`：四种 profile 组合下，instructions / prompt / 每个工具描述与参数描述里都不会出现**未注册**的工具名（工具引用一律写成 `name(` 或 `` `name` ``，所以能精确判定）。给模型指一条它走不通的路，比不指更糟。

与另一个代码服务器分工的说明请写在**客户端**（AGENTS.md 或 MCP 配置的 instructions 里），不要写进这里：FastGraph 展示给模型的任何文字都不提别的服务器，这样"开不开那个服务器"都不影响本仓库的正确性。可直接粘的一段：

```
读文件/找定义/改代码 → 用 serena 的工具。
整个仓库的调用图与影响面、import 依赖与环、改动波及、锚定在代码上的跨会话记忆 → 用 fastgraph。
不要用 fastgraph 读整文件（它在 lean profile 下也不提供）。
```

旧工具名 `read_file` / `symbol_body` / `file_symbols` / `find_callers` / `find_callees` / `changed_context` / `what_changed` 不再是 MCP 工具，但仍是 `Toolbox` 上的方法（内部 API，测试直接调）；`read_code` / `call_graph` / `changes` 只是它们的分流层。

## 项目记忆层（默认开，`FASTGRAPH_MEMORY=0` 关）

FastGraph 已经知道调用图长什么样，记忆层就把它变成跨会话的记忆：**笔记锚定在符号/文件/模块上，变更按调用图拓扑对比**——这是通用文本记忆方案做不到的两件事。

| 任务 | 工具 |
| --- | --- |
| 记住一个决定/警告/待办，锚定到代码 | `remember(anchor, body, kind?, source?)` |
| 读回它（改代码前先看有没有笔记） | `recall(anchor?, kind?, include_orphans?)` |
| 删掉一条已被推翻的笔记 | `forget(id)` |
| 存一个调用图基线，供日后对比 | `checkpoint(label, ref?)` |
| 自上次基线以来拓扑怎么变了 | `changes(since, to?)` —— 它是只读工具，与 git 视图共用一个入口，`since` 才走基线 |

```bash
python -P -m fastgraph                 # stdio，记忆层默认在
FASTGRAPH_MEMORY=0 python -P -m fastgraph   # 只要 11 个只读工具
```

默认开是因为这层价值只在跨会话时才出现，而要配置它的动作本身就在跨会话的那一端。**开不等于写**：`.fastgraph/memory.sqlite` 只在你真的调用 `remember` / `checkpoint` 时才出现，只读工具（`symbol_info` / `call_graph` / `impact_analysis`）不会替你在项目里落文件，`forget` 也不会（库里没有笔记时它直接拒答）；关掉时注册面回到与不含这份代码的构建逐字段一致的 11 个工具。

- **笔记可以删**：`forget(id)` 收 `recall` 返回的 id，删除时把整条笔记回显在 `removed` 里——这就是撤销路径（拿回显的 body 再 `remember` 一次）。它存在的理由不是清理：`recall` 是改代码前那一步，所以**一条错笔记比没有笔记更坏**，而只增不减的库会让 top-N 召回随时间变成过期 TODO 的堆；`include_orphans` 与 `changes` 报出的孤儿也因此才有处置动作。`notes.id` 用 `AUTOINCREMENT` 正是为了这个工具——`forget` 按这一列寻址，普通 `INTEGER PRIMARY KEY` 会把被删掉的最大 id 发给下一条插入，于是旧 id 可能删掉不相干的笔记。基线（`checkpoint`）不在此工具范围内。

- **anchor 规范形式**：`symbol:<rel_path>#<qualified_name>`、`file:<rel_path>`、`module:<dir>`、`project:`。裸名（`AuthService.login`）会先解析：唯一命中才写，多命中返回候选并拒绝（同一个名字在真实仓库里能命中好几个文件），零命中拒绝。
- **锚定的是"这个名字"，不是"这一次声明"**：键里没有行号（行号每次编辑都会动），所以同一文件内同名的多个声明共享一条笔记。写入时若命中多于一个，响应里带 `anchor_matches: N` 与说明——不是静默合并。
- **`recall` 的锚点按"位置"展开，不按字符串相等**：`file:` 会带出这个文件本身**以及**钉在它内部符号上的笔记，`module:` 带出整个子树（文件 + 符号 + 子模块）。问"这个文件我们知道什么"却返回 0 条，读起来就跟记忆丢了没错——所以粗粒度锚点必须向下覆盖。两个例外：`symbol:` 里面没有东西，保持精确；`project:` 是"仓库级"这一**桶**而不是全库，否则那几条会话级笔记会被几百条代码笔记挤出去（要全库用 `anchor=""`）。
- **`changes(since=…)` 的边差异是"resolver 视角"**：name-based 解析本来就只连得上 9%~40% 的边，所以它报的是"解析结果变了"，不等于"调用真的断了"——结论仍要回 `call_graph(direction="in")` 验。两侧快照都必须来自**建完的索引**（`pending_files`/`pending_edges` 为 0），否则工具直接拒答，不会拿建图进度冒充拓扑变化。
- **`checkpoint` 同理**：索引还在建就拒绝写入，并提示 `reindex()`。
- **存储**：`.fastgraph/memory.sqlite`（与 `index.sqlite` 分文件）。索引文件"删掉即重建"，记忆不该被牵连；符号被改名/删除后笔记不会静默消失，`recall(include_orphans=true)` 与 `changes(since=…)` 的 `stale_notes`（带 git rename 的 `moved_to`）都还能取到。
- **不自动写**：只有显式调用 `remember` / `checkpoint` 才会落库；开启后 `symbol_info` / `call_graph` / `impact_analysis` 会在顶层命中附带一个 `notes` 字段（最多 8 条、正文截 400 字）。
- 记忆只写 `.fastgraph/`，**从不往项目源码里注入注释或文件**——只读导航层的定位不变。

## 支持语言

Python、TypeScript/TSX、JavaScript、Vue、Svelte、Go、Rust、Java、C/C++（`.wxml` 模板引用亦支持）。

依赖图按各语言 import 写法解析，含 tsconfig paths / vite alias / uni-app `@` 别名、Go `go.mod` 模块根、Rust crate 根、目录入口（`index.*` / `__init__.*`）。

## 调用图的边界（重要）

真实仓库上约 9%~40% 的调用边能唯一连到符号（10 个公开仓库实测：C++/TS 38%、Rust/Python 28~29%、JS 23~31%、Go 18~24%、Java 9%——继承与框架派发最多）；仓库越大、内部依赖越多，这个比例越高（sentry 17,703 文件的混合 Python/TSX 仓库：66 万条调用边中 25 万条连上 = 37.6%）。其余要么指向外部库，要么接收者类型无法静态确定——后者**不连边、不猜**，而是计数报出：

- `call_graph(direction="in")` 每条结果带 `via`：`resolved`（确证的调用边）或 `text`（同名文本折叠的猜测）
- `call_graph(direction="out")` 每条结果带 `evidence`：`same_file` / `imported`（有文件级证据）或 `name_only`（仅同名匹配，当猜测看）
- 出现 `unresolved_incoming` / `unresolved_outgoing` 字段时，**空列表 ≠ 没有调用者**，按"未知"处理，不能据此判定可删；若某个符号既无调用边也无未解析边，`call_graph(direction="in")` 会改报 `imported_by`（它可能是被读取的枚举/常量/类型，而非无人使用）
- `self.x()`、接口实现、回调注册、动态派发不会连边——宁可漏，不可错

## 开发

```bash
python -m pytest tests/                 # 325 项全绿
python bench/bench.py <项目路径>           # 性能基准（冷索引/增量/查询时延）
```

三种注册面组合（默认全开、`FASTGRAPH_MEMORY=0`、`FASTGRAPH_PROFILE=lean`）由测试**内部显式设置环境变量**来覆盖，不读你 shell 里的值——`tests/conftest.py` 会把 `FASTGRAPH_PROFILE`/`FASTGRAPH_MEMORY` 钉回出厂默认，所以上面这一条命令已经包含全部三种面，不用再加环境前缀手跑三遍。

## 路线图

- [x] Phase 1-3.5：MCP Server、调用图、影响分析、git 变更感知、多语言依赖解析
- [x] Phase 4.5：项目记忆层（默认开，`FASTGRAPH_MEMORY=0` 关）——锚定符号的笔记 + 调用图快照 diff
- [x] Phase 4a：检索相关性——BM25 加权排序 + CJK trigram 索引（零新依赖，`tests/test_search_ranking.py`）
- [ ] Phase 4b：embedding 语义检索（要动依赖策略；先要有评测集才能证明比词面检索好，暂缓）
- [ ] Phase 5：多项目 workspace

## License

[MIT](LICENSE)
