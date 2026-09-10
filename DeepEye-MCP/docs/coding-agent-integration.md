# DeepEye 接入 Coding Agent 指南

本文档详细说明如何将 DeepEye 接入各类主流 coding agent / MCP 客户端。

## 简介

DeepEye 是一个 **stdio 类型的 MCP Server**，为纯文本模型（如 DeepSeek V4 Flash）提供视觉能力。它通过标准输入输出以 JSON-RPC 协议与 MCP 客户端通信，将图像理解、视觉推理等能力以 MCP 工具的形式暴露给宿主应用。DeepEye 提供四个核心工具：`describe_image`（图像描述）、`extract_text`（OCR 文字提取）、`ask_about_image`（视觉问答）、`analyze_layout`（UI 布局结构化分析，返回包含布局类型与元素树的 JSON，适合前端复刻）。

启动命令：`deepeye`（`pip install -e .` 后注册的 console script 入口），等价于 `python -m deepeye_mcp.server`。配置通过环境变量传递（pydantic-settings 读取，环境变量优先于 `.env` 文件）。

**为什么要接入 coding agent**：当前主流的 coding agent / AI 编辑器（Claude Code、Cursor、Cline、Windsurf 等）均已原生支持 MCP。把 DeepEye 接入这些工具后，原本只能处理文本的 coding agent 就能在编码流程中调用视觉能力——例如分析 UI 截图、读取图表、理解设计稿、识别报错截图等，从而显著扩展纯文本模型在开发场景下的适用边界。由于 DeepEye 是 stdio 类型 server，各客户端的接入方式高度相似但配置文件位置、字段命名、JSON 结构存在差异，本文档对这些差异逐一梳理。

### DeepEye 关键信息速查

| 项 | 值 |
|---|---|
| 启动命令 | `deepeye`（等价 `python -m deepeye_mcp.server`） |
| 传输方式 | stdio（标准输入输出 JSON-RPC） |
| 配置方式 | 环境变量（优先于 `.env` 文件） |
| Windows 启动命令 | `D:/Program Files/Python314/python.exe -m deepeye_mcp.server`（`python` 不在 PATH 时用完整路径） |
| macOS/Linux 启动命令 | `python -m deepeye_mcp.server` |

DeepEye 支持的环境变量：

| 环境变量 | 说明 | 默认值 |
|---|---|---|
| `VISION_PROVIDER` | 视觉后端：`openai` / `gemini` / `gemini-interactions` / `anthropic` / `responses` | `openai` |
| `OPENAI_API_KEY` | OpenAI 视觉模型 API Key | - |
| `OPENAI_MODEL` | OpenAI 视觉模型名（须支持图片输入） | `gpt-5.6-luna` |
| `OPENAI_BASE_URL` | OpenAI 兼容端点。**任意兼容厂商都能用**，如阿里通义 `https://dashscope.aliyuncs.com/compatible-mode/v1`、智谱 GLM `https://open.bigmodel.cn/api/paas/v4`、阶跃星辰 `https://api.stepfun.com/step_plan/v1`；留空用官方 | - |
| `GEMINI_API_KEY` / `GEMINI_MODEL` | Gemini 后端（`gemini` generateContent / `gemini-interactions` 新版 API，复用同一组变量） | - |
| `ANTHROPIC_API_KEY` / `ANTHROPIC_MODEL` / `ANTHROPIC_BASE_URL` | Anthropic Claude 原生 Messages API（默认 `claude-sonnet-5`） | - |
| `RESPONSES_API_KEY` / `RESPONSES_MODEL` / `RESPONSES_BASE_URL` | OpenAI 官方 Responses API（默认 `gpt-5.6`） | - |
| `IMAGE_MAX_DIM` | 图片预处理最大边长（像素），超过则等比缩放转 JPEG。`0` 禁用预处理 | `2048` |
| `CACHE_ENABLED` | 是否开启视觉结果缓存（LRU + TTL） | `true` |
| `CACHE_MAX_SIZE` | 缓存最大条目数 | `128` |
| `CACHE_TTL` | 缓存存活秒数 | `3600` |
| `REQUEST_TIMEOUT` | 视觉后端 HTTP 请求超时（秒） | `120` |
| `MAX_RETRIES` | 失败重试次数（仅对网络/超时错误重试） | `3` |
| `MAX_TOKENS` | 视觉模型返回的最大 token 数 | `4096` |

> 本文示例统一以 OpenAI 后端为例。启动命令统一用 `deepeye`（`pip install` 后自动注册到 PATH）；若不在 PATH，可用 `python -m deepeye_mcp.server` 或完整路径。

---

## 总览表格

| # | Coding Agent | 配置文件（全局） | 配置文件（项目级） | 格式 | 顶层字段 | 传输类型 |
|---|---|---|---|---|---|---|
| 1 | opencode | `~/.config/opencode/opencode.json` | `.opencode/opencode.json` 或项目根 `opencode.json` | JSON | `mcp` | stdio（`type: "local"`） |
| 2 | OpenAI Codex CLI | `~/.codex/config.toml` | `.codex/config.toml`（受信任项目） | TOML | `mcp_servers` | stdio（`command`） |
| 3 | Claude Code | `~/.claude.json` | `.mcp.json` | JSON | `mcpServers` | stdio（`command`） |
| 4 | Cline | VS Code 扩展存储下的 `cline_mcp_settings.json`；CLI 为 `~/.cline/mcp.json` | 无（全局为主） | JSON | `mcpServers` | stdio（`command`+`args`） |
| 5 | Cursor | `~/.cursor/mcp.json` | `.cursor/mcp.json` | JSON | `mcpServers` | stdio（`command`+`args`） |
| 6 | Windsurf | `~/.codeium/windsurf/mcp_config.json` | 无（仅全局） | JSON | `mcpServers` | stdio（`command`+`args`） |
| 7 | Continue | `~/.continue/config.json`（或 `config.yaml`） | 无（全局为主） | JSON/YAML | `mcpServers`（数组） | stdio（`transport.type: "stdio"`） |
| 8 | Zed | `~/.config/zed/settings.json`（Windows: `%APPDATA%\Zed\settings.json`） | 无（settings.json 内） | JSON | `context_servers` | stdio（`command`+`args`） |
| 9 | Roo Code | VS Code 扩展存储下的 `mcp_settings.json` | `.roo/mcp.json` | JSON | `mcpServers` | stdio（`command`+`args`） |

> 注意字段命名差异：opencode 用 `mcp`、Codex CLI 用 `mcp_servers`（snake_case）、Claude Code/Cursor/Windsurf/Cline/Roo Code 用 `mcpServers`（camelCase）、Zed 用 `context_servers`、Continue 用 `mcpServers` 但是是**数组**而非对象。

---

## 1. opencode（sst/opencode）

### 简介

opencode 是一个开源的终端 AI coding agent，支持通过 MCP 扩展工具能力。

### 配置文件位置

- 全局：`~/.config/opencode/opencode.json`
- 项目级：`.opencode/opencode.json`（优先级最高）或项目根目录的 `opencode.json`

### 配置格式

JSON。MCP server 配置在 `mcp` 字段下，每个 server 一个对象。本地 stdio server 使用 `type: "local"`，`command` 为数组形式，`environment` 为对象，`enabled` 可选。

### DeepEye 示例配置

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "deepeye": {
      "type": "local",
      "command": ["deepeye"],
      "enabled": true,
      "environment": {
        "VISION_PROVIDER": "openai",
        "OPENAI_API_KEY": "sk-xxx",
        "OPENAI_MODEL": "gpt-5.6-luna"
      }
    }
  }
}
```

Windows 示例（注意反斜杠转义）：

```json
{
  "mcp": {
    "deepeye": {
      "type": "local",
      "command": ["deepeye"],
      "enabled": true,
      "environment": {
        "VISION_PROVIDER": "openai",
        "OPENAI_API_KEY": "sk-xxx",
        "OPENAI_MODEL": "gpt-5.6-luna"
      }
    }
  }
}
```

### 验证方法

执行 `opencode mcp list`，DeepEye 状态应为 `connected`。

### 进阶：粘贴图片自动调用 DeepEye（opencode-easy-vision 插件）

默认情况下，在 opencode 中粘贴图片后，纯文本模型（如 DeepSeek V4 Flash）无法直接看到图片，需要手动提供文件路径。安装 [opencode-easy-vision](https://github.com/devadathanmb/opencode-easy-vision) 插件后，粘贴的图片会自动保存为临时文件并注入路径，模型即可自动调用 DeepEye 工具分析图片——实现"粘贴图片 → 问问题 → 出结果"的无缝体验。

**安装插件**：

```bash
opencode plugin opencode-easy-vision --global
```

**配置插件指向 DeepEye**：

在 `~/.config/opencode/opencode.json` 中添加 `plugin` 字段：

```json
{
  "$schema": "https://opencode.ai/config.json",
  "plugin": ["opencode-easy-vision"],
  "mcp": {
    "deepeye": { ... }
  }
}
```

然后创建 `~/.config/opencode/opencode-easy-vision.json`，指定 DeepEye 工具：

```json
{
  "models": ["*"],
  "imageAnalysisTool": "deepeye_describe_image"
}
```

- `"models": ["*"]`：对所有模型生效（不限于 MiniMax）
- `"imageAnalysisTool": "deepeye_describe_image"`：粘贴图片时自动调用 DeepEye 的 `describe_image` 工具

配置完成后重启 opencode，直接在对话中粘贴图片即可。

### 注意事项

- opencode 的 `command` 是数组形式（与其他多数客户端的 `command` 字符串 + `args` 数组不同）。
- Windows 路径反斜杠在 JSON 中需转义为 `\\`。
- 配置文件优先级：项目级 `.opencode/opencode.json` > 项目根 `opencode.json` > 全局。
- `opencode-easy-vision` 插件的 `imageAnalysisTool` 值为 `<mcp-server-key>_<tool-name>` 格式，即 `deepeye_describe_image`。

---

## 2. OpenAI Codex CLI（openai/codex）

### 简介

OpenAI 官方的命令行 coding agent，支持通过 MCP 接入外部工具。

### 配置文件位置

- 全局：`~/.codex/config.toml`
- 项目级：`.codex/config.toml`（仅受信任项目生效）

### 配置格式

TOML。使用 `[mcp_servers.<name>]` 表（注意是 snake_case `mcp_servers`，不是 `mcpServers`）。stdio server 字段：`command`（必填，字符串）、`args`（数组）、`env`（inline table 或独立子表）、`enabled`、`startup_timeout_sec`、`tool_timeout_sec`。

也可用 CLI 添加：`codex mcp add <name> --env KEY=val -- <command> <args>`。

### DeepEye 示例配置

```toml
[mcp_servers.deepeye]
command = "deepeye"
startup_timeout_sec = 20
tool_timeout_sec = 60

[mcp_servers.deepeye.env]
VISION_PROVIDER = "openai"
OPENAI_API_KEY = "sk-xxx"
OPENAI_MODEL = "gpt-5.6-luna"
```

Windows 示例（TOML 中字符串反斜杠无需双写，但建议用正斜杠或原始字符串）：

```toml
[mcp_servers.deepeye]
command = "deepeye"
startup_timeout_sec = 20
tool_timeout_sec = 60

[mcp_servers.deepeye.env]
VISION_PROVIDER = "openai"
OPENAI_API_KEY = "sk-xxx"
OPENAI_MODEL = "gpt-5.6-luna"
```

### 验证方法

- `codex mcp list`：列出所有已配置的 MCP server。
- `codex mcp get deepeye`：查看 DeepEye 详细配置与连接状态。

### 注意事项

- 字段名是 snake_case `mcp_servers`，与 Claude Code 的 camelCase `mcpServers` 不同，容易混淆。
- 一个 server 只能选一种传输方式：`command`（stdio）或 `url`（HTTP），二者不能混用。
- 项目级配置只在受信任项目（trusted project）中生效。

---

## 3. Claude Code（Anthropic 官方 CLI）

### 简介

Anthropic 官方的终端 coding agent，对 MCP 有一等支持，是 MCP 生态的参考实现。

### 配置文件位置

- 用户级（全局）：`~/.claude.json`
- 项目级（团队共享）：`.mcp.json`（项目根目录，可提交到版本控制）
- 也可通过 CLI `claude mcp add` 管理

### 配置格式

JSON，顶层字段为 `mcpServers`（camelCase）。stdio server 使用 `command`（字符串）+ `env`（对象）。

### DeepEye 示例配置

CLI 方式（推荐，stdio）：

```bash
claude mcp add --scope user \
  -e VISION_PROVIDER=openai \
  -e OPENAI_API_KEY=sk-xxx \
  -e OPENAI_MODEL=gpt-5.6-luna \
  deepeye -- deepeye
```

JSON 方式（`.mcp.json` 或 `~/.claude.json`）：

```json
{
  "mcpServers": {
    "deepeye": {
      "command": "deepeye",
      "env": {
        "VISION_PROVIDER": "openai",
        "OPENAI_API_KEY": "sk-xxx",
        "OPENAI_MODEL": "gpt-5.6-luna"
      }
    }
  }
}
```

### 验证方法

执行 `claude mcp list`，DeepEye 状态应为 `✔ Connected`。

### 注意事项

- 作用域（scope）：`--scope local`（默认，仅当前项目）/ `--scope project`（写入 `.mcp.json`，团队共享）/ `--scope user`（全局）。
- CLI 语法中所有 flag 必须在 `<name>` 之前，`--` 之后才是启动命令及其参数。
- JSON 字段是 camelCase `mcpServers`，与 Codex CLI 的 snake_case `mcp_servers` 不同。
- `.mcp.json` 适合团队共享，但其中的 API Key 等敏感信息不要直接提交到公开仓库。

---

## 4. Cline（VS Code 插件，原 Claude Dev）

### 简介

Cline 是一款流行的 VS Code AI 编码助手扩展（原名 Claude Dev），支持通过 MCP 接入外部工具与数据源，同时提供独立的 CLI。

### 配置文件位置

- VS Code 扩展：`cline_mcp_settings.json`
  - 推荐通过 UI 打开：Cline 面板顶部 **MCP Servers** 图标 → **Configure** 标签 → **Configure MCP Servers** 按钮（该按钮会打开当前安装对应的正确文件）。
  - 磁盘路径（因版本而异，以 Configure 按钮为准）：
    - macOS：`~/Library/Application Support/Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json`
    - Linux：`~/.config/Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json`
    - Windows：`%APPDATA%\Code\User\globalStorage\saoudrizwan.claude-dev\settings\cline_mcp_settings.json`
- Cline CLI：`~/.cline/mcp.json`（或 `~/.cline/data/settings/cline_mcp_settings.json`，取决于版本）

### 配置格式

JSON，顶层字段为 `mcpServers`。stdio server 使用 `command`（字符串）+ `args`（数组）+ `env`（对象）。Cline 额外字段：`disabled`（布尔）、`autoApprove`（数组，工具名）、`timeout`。

### DeepEye 示例配置

```json
{
  "mcpServers": {
    "deepeye": {
      "command": "deepeye",
      "args": [],
      "env": {
        "VISION_PROVIDER": "openai",
        "OPENAI_API_KEY": "sk-xxx",
        "OPENAI_MODEL": "gpt-5.6-luna"
      },
      "disabled": false,
      "autoApprove": []
    }
  }
}
```

Windows 示例（反斜杠转义）：

```json
{
  "mcpServers": {
    "deepeye": {
      "command": "deepeye",
      "args": [],
      "env": {
        "VISION_PROVIDER": "openai",
        "OPENAI_API_KEY": "sk-xxx",
        "OPENAI_MODEL": "gpt-5.6-luna"
      },
      "disabled": false,
      "autoApprove": []
    }
  }
}
```

### 验证方法

- 打开 MCP Servers 面板，每个 server 显示状态行与启用/禁用开关。
- 展开 server 条目可看到已发现的工具列表。
- 在对话中让 Cline 调用 DeepEye 工具，未在 `autoApprove` 中列出的工具每次调用前会请求确认。

也可用 CLI 非交互查看：`cline config mcp` 或 `cline config mcp --json`。

### 注意事项

- 文件路径在不同版本间发生过迁移，**优先用 Configure 按钮打开**，不要手动猜测路径。
- GUI 启动的 VS Code 不一定继承 shell 的 PATH，`command` 建议使用绝对路径。
- `autoApprove` 数组用于免确认调用可信工具，留空表示每次调用都需手动确认。
- Cline 使用 `autoApprove` 字段，注意与 Roo Code 的 `alwaysAllow` 区分。

---

## 5. Cursor（AI 编辑器）

### 简介

Cursor 是一款 AI 原生代码编辑器，原生支持 MCP，可将外部工具与数据源接入其 Agent / Chat 能力。

### 配置文件位置

- 全局：`~/.cursor/mcp.json`（Windows：`%USERPROFILE%\.cursor\mcp.json`）
- 项目级：`.cursor/mcp.json`（项目根目录，可提交到版本控制团队共享）

也可通过 UI：Cursor Settings（`Ctrl+Shift+J` / `Cmd+Shift+J`）→ **Tools & Integrations**（或 **Tools & MCP**）→ **New MCP Server**，会自动创建/打开 `mcp.json`。

### 配置格式

JSON，顶层字段为 `mcpServers`（与 Claude Desktop 格式一致，可互相复制）。stdio server 使用 `command`（字符串）+ `args`（数组）+ `env`（对象）。远程 server 使用 `url` + 可选 `headers`。

### DeepEye 示例配置

```json
{
  "mcpServers": {
    "deepeye": {
      "command": "deepeye",
      "args": [],
      "env": {
        "VISION_PROVIDER": "openai",
        "OPENAI_API_KEY": "sk-xxx",
        "OPENAI_MODEL": "gpt-5.6-luna"
      }
    }
  }
}
```

Windows 示例（反斜杠转义）：

```json
{
  "mcpServers": {
    "deepeye": {
      "command": "deepeye",
      "args": [],
      "env": {
        "VISION_PROVIDER": "openai",
        "OPENAI_API_KEY": "sk-xxx",
        "OPENAI_MODEL": "gpt-5.6-luna"
      }
    }
  }
}
```

### 验证方法

- 打开 Settings → Tools & MCP 面板，查看 DeepEye 的状态指示（绿色 = 正常，红色 = 连接失败）。
- Cursor 支持配置热重载，修改 `mcp.json` 后无需重启即可生效，在面板中确认状态。
- 在 Chat / Agent 模式下让 Cursor 调用 DeepEye 工具验证。

### 注意事项

- Cursor 与 Claude Desktop 使用相同的 `mcpServers` 格式，配置可互相复用。
- 默认 Agent 调用 MCP 工具前会询问确认；可在设置中开启自动运行模式。
- 项目级 `.cursor/mcp.json` 与全局配置会合并，注意同名 server 的覆盖关系。

---

## 6. Windsurf（Codeium 的 AI IDE）

### 简介

Windsurf 是 Codeium 推出的 AI 原生 IDE，内置 AI 助手 Cascade，原生支持 MCP，可接入外部工具与数据源。

### 配置文件位置

- 全局：`~/.codeium/windsurf/mcp_config.json`（Windows：`%USERPROFILE%\.codeium\windsurf\mcp_config.json`）
- 仅全局配置，**不支持项目级**配置。

可通过 UI 打开：Settings → Tools → Windsurf Settings → **Add Server**；或 Cascade 面板的锤子图标（🔨）→ **Configure** 打开原始 `mcp_config.json`；或命令面板执行 "Windsurf: Configure MCP Servers"。

### 配置格式

JSON，顶层字段为 `mcpServers`。stdio server 使用 `command`（字符串）+ `args`（数组）+ `env`（对象）。远程 HTTP server 使用 `serverUrl` 或 `url` + 可选 `headers`。支持三种传输：`stdio`、`Streamable HTTP`、`SSE`。

Windsurf 支持配置插值：在 `command`、`args`、`env`、`serverUrl`、`url`、`headers` 字段中使用 `${env:VARIABLE_NAME}` 引用系统环境变量。

### DeepEye 示例配置

```json
{
  "mcpServers": {
    "deepeye": {
      "command": "deepeye",
      "args": [],
      "env": {
        "VISION_PROVIDER": "openai",
        "OPENAI_API_KEY": "sk-xxx",
        "OPENAI_MODEL": "gpt-5.6-luna"
      }
    }
  }
}
```

Windows 示例（反斜杠转义）：

```json
{
  "mcpServers": {
    "deepeye": {
      "command": "deepeye",
      "args": [],
      "env": {
        "VISION_PROVIDER": "openai",
        "OPENAI_API_KEY": "sk-xxx",
        "OPENAI_MODEL": "gpt-5.6-luna"
      }
    }
  }
}
```

### 验证方法

- MCP 工具栏显示 "1 available MCP server"。
- 点击锤子图标（🔨）查看可用工具，server 名称旁有绿点表示连接正常。
- 修改配置后点击刷新按钮（🔄），或完全重启 Windsurf。
- 测试：在 Cascade 中提示 "使用 DeepEye 分析这张截图"。

### 注意事项

- **仅全局配置**，没有项目级配置；所有 server 在所有项目中可用。
- 修改 `mcp_config.json` 后需重启 Windsurf（完全退出再打开，而非简单 reload）才能生效。
- Cascade 有 100 个工具的总数上限，需在 MCP 设置页合理开关工具。
- Enterprise 用户需在设置中手动开启 MCP 功能。
- 远程 HTTP server 字段是 `serverUrl`（注意与 Cursor 的 `url` 略有不同）。

---

## 7. Continue（VS Code / JetBrains 插件）

### 简介

Continue 是一款开源的 AI 编码助手，以插件形式运行于 VS Code 与 JetBrains IDE，是首个完整支持 MCP 全部特性（Resources、Prompts、Tools、Sampling）的客户端之一。

### 配置文件位置

- 全局：`~/.continue/config.json`（新版也支持 `~/.continue/config.yaml`）
- 配置在所有 IDE 间共享（VS Code 与 JetBrains 使用同一份配置）。
- 打开方式：`Cmd/Ctrl+Shift+P` → **Continue: Open config.json**，或 Continue 侧栏齿轮图标 → "Open config.json"。

### 配置格式

JSON（或 YAML）。顶层字段为 `mcpServers`，但与其他客户端不同——**Continue 的 `mcpServers` 是数组而非对象**，每个元素包含 `name` 与 `transport`。stdio server 在 `transport` 对象中指定 `type: "stdio"`、`command`、`args`、`env`。

需要 Continue v0.9.195+ 才支持 MCP。

### DeepEye 示例配置

```json
{
  "mcpServers": [
    {
      "name": "deepeye",
      "transport": {
        "type": "stdio",
        "command": "deepeye",
        "args": [],
        "env": {
          "VISION_PROVIDER": "openai",
          "OPENAI_API_KEY": "sk-xxx",
          "OPENAI_MODEL": "gpt-5.6-luna"
        }
      }
    }
  ]
}
```

Windows 示例（反斜杠转义）：

```json
{
  "mcpServers": [
    {
      "name": "deepeye",
      "transport": {
        "type": "stdio",
        "command": "deepeye",
        "args": [],
        "env": {
          "VISION_PROVIDER": "openai",
          "OPENAI_API_KEY": "sk-xxx",
          "OPENAI_MODEL": "gpt-5.6-luna"
        }
      }
    }
  ]
}
```

### 验证方法

- 保存配置后执行 `Cmd/Ctrl+Shift+P` → **Continue: Reload config** 重新加载。
- 在 Continue 面板查看 server 连接状态。
- 在对话中通过 `@deepeye` 引用并调用工具测试。

### 注意事项

- **`mcpServers` 是数组**，不是对象——这是 Continue 与其他客户端最大的结构差异，直接复制其他客户端的对象式配置会失败。
- 需要 Continue v0.9.195 及以上版本。
- 配置文件可能是 `config.json` 或 `config.yaml`，取决于版本与个人选择，二者格式相应不同。
- JetBrains 与 VS Code 共用同一份 `~/.continue/` 配置。

---

## 8. Zed（编辑器，原生 MCP 支持）

### 简介

Zed 是一款高性能代码编辑器，内置 Agent Panel，原生支持 MCP，将 MCP server 称为 "context servers"（上下文服务器）。

### 配置文件位置

- 全局：`~/.config/zed/settings.json`（Windows：`%APPDATA%\Zed\settings.json`）
- 打开方式：命令面板 `Cmd/Ctrl+Shift+P` → **zed: open settings**，或 `Cmd+,`。
- 也可通过 UI：Settings → AI → MCP Servers → **Add Server** → **Add Local Server**；或 Agent Panel（`Cmd/Ctrl+Shift+A`）→ 设置齿轮 → **Add Custom Server**。

### 配置格式

JSON，顶层字段为 **`context_servers`**（注意：不是 `mcpServers`）。stdio server 使用 `command`（字符串）+ `args`（数组）+ `env`（对象）。远程 server（新版 v0.226+）使用 `url` + 可选 `headers`。

Zed 当前仅支持 MCP 的 **Tools** 与 **Prompts** 特性，暂不支持 Resources 与 Sampling。原生仅支持 stdio 传输；旧版本接入远程 HTTP server 需借助 `mcp-remote` 桥接。

### DeepEye 示例配置

```json
{
  "context_servers": {
    "deepeye": {
      "command": "deepeye",
      "args": [],
      "env": {
        "VISION_PROVIDER": "openai",
        "OPENAI_API_KEY": "sk-xxx",
        "OPENAI_MODEL": "gpt-5.6-luna"
      }
    }
  }
}
```

Windows 示例（反斜杠转义）：

```json
{
  "context_servers": {
    "deepeye": {
      "command": "deepeye",
      "args": [],
      "env": {
        "VISION_PROVIDER": "openai",
        "OPENAI_API_KEY": "sk-xxx",
        "OPENAI_MODEL": "gpt-5.6-luna"
      }
    }
  }
}
```

### 验证方法

- 打开 Settings → AI → MCP Servers，查看 DeepEye 名称旁的指示点：绿色 = "Server is active"，其他颜色查看 tooltip 提示。
- 打开 Agent Panel（`Cmd/Ctrl+Shift+A`）对话，在提示中提及 "deepeye" 以帮助模型路由到对应工具。
- 查看日志：`Cmd/Ctrl+Shift+P` → **zed: open logs**。

### 注意事项

- 字段名是 **`context_servers`**，不是 `mcpServers`——这是 Zed 最易踩坑的点，直接复用其他客户端配置会不生效。
- Zed 用登录 shell 的 `$PATH` 解析命令，macOS 上可能与交互式 shell 不同；若 `command` 找不到，建议使用绝对路径。
- `args` 数组中每个参数必须是独立的字符串元素，不能合并成一个字符串。
- 环境变量用 `env` 块传递，不要依赖 `.bashrc` 中的 `export`（不一定能传递到 Zed 子进程）。
- 默认每次工具调用都会请求权限；如需自动放行，可在 settings.json 中设置 `"agent": { "always_allow_tool_actions": true }`（谨慎使用）。
- 修改配置后通常需重启 Zed 或重新打开 Agent Panel 才能生效。

---

## 9. Roo Code（VS Code 插件，原 Roo Cline）

### 简介

Roo Code 是 Cline 的一个分支（原名 Roo Cline），由 Roo 团队维护，支持多模式（Code / Architect / Ask / Debug 等）与 MCP，是 VS Code 上的开源 AI 编码 agent。

### 配置文件位置

- 全局：`mcp_settings.json`（位于 VS Code 扩展存储目录）
  - macOS：`~/Library/Application Support/Code/User/globalStorage/rooveterinaryinc.roo-cline/settings/mcp_settings.json`
  - Linux：`~/.config/Code/User/globalStorage/rooveterinaryinc.roo-cline/settings/mcp_settings.json`
  - Windows：`%APPDATA%\Code\User\globalStorage\rooveterinaryinc.roo-cline\settings\mcp_settings.json`
  - 新版可能使用 `roo-code` 作为 slug，建议以下方 UI 方式打开。
- 项目级：`.roo/mcp.json`（项目根目录，可提交到版本控制团队共享；**项目级优先级高于全局**）
- 打开方式：Roo Code 面板顶部 MCP 图标 → 滚动到底部 → **Edit Global MCP** / **Edit Project MCP**；或命令面板执行 "Roo Code: Open MCP Settings"。

### 配置格式

JSON，顶层字段为 `mcpServers`。stdio server 字段：`command`（必填，字符串）、`args`（数组）、`cwd`（可选，工作目录）、`env`（对象）、`alwaysAllow`（数组，工具名）、`disabled`（布尔）、`timeout`（秒，1-3600，默认 60）、`watchPaths`（数组）、`disabledTools`（数组）。

支持在 `args` 中使用 `${env:VARIABLE_NAME}` 引用系统环境变量。支持三种传输：STDIO、Streamable HTTP、SSE。

### DeepEye 示例配置

```json
{
  "mcpServers": {
    "deepeye": {
      "command": "deepeye",
      "args": [],
      "env": {
        "VISION_PROVIDER": "openai",
        "OPENAI_API_KEY": "sk-xxx",
        "OPENAI_MODEL": "gpt-5.6-luna"
      },
      "alwaysAllow": [],
      "disabled": false
    }
  }
}
```

Windows 示例（反斜杠转义）：

```json
{
  "mcpServers": {
    "deepeye": {
      "command": "deepeye",
      "args": [],
      "env": {
        "VISION_PROVIDER": "openai",
        "OPENAI_API_KEY": "sk-xxx",
        "OPENAI_MODEL": "gpt-5.6-luna"
      },
      "alwaysAllow": [],
      "disabled": false
    }
  }
}
```

### 验证方法

- 在 Roo Code MCP 设置视图查看 DeepEye 的状态与已发现工具列表。
- 在对话中让 Roo 调用 DeepEye 工具，未在 `alwaysAllow` 中的工具每次调用前会请求确认。
- 查看输出面板排查问题：View → Output → 选择 "Roo Code"。

### 注意事项

- Roo Code 使用 **`alwaysAllow`**（camelCase）字段做工具免确认，**与上游 Cline 的 `autoApprove` 不同**——从 Cline 迁移配置时需改名。
- 扩展 publisher id 历史上为 `rooveterinaryinc.roo-cline`，新版可能为 `roo-code`；优先用 UI 按钮打开正确文件，避免手敲路径出错。
- 项目级 `.roo/mcp.json` 优先级高于全局 `mcp_settings.json`，适合团队共享配置。
- `${env:VARIABLE_NAME}` 语法可避免在配置中硬编码密钥。

---

## 通用注意事项

### 1. 环境变量优先于 .env 文件

DeepEye 使用 pydantic-settings 读取配置，**环境变量优先级高于 `.env` 文件**。各 coding agent 都通过 MCP 配置中的 `env` / `environment` 字段把变量注入到 DeepEye 子进程的环境变量中，这等价于直接设置环境变量，会覆盖项目 `.env` 文件中的同名值。因此推荐在 MCP 配置的 env 字段中直接填写所需的视觉后端凭证，而不依赖 `.env`。

### 2. Windows 路径与命令形式

- 在 JSON 配置文件（Cline、Cursor、Windsurf、Continue、Zed、Roo Code、Claude Code 的 `.mcp.json` 等）中，若 `command` 用 Windows 完整路径，反斜杠 `\` 必须转义为 `\\`，例如 `"command": "D:\\Program Files\\Python314\\python.exe"`。
- 也可直接用 `"command": "python"` + `"args": ["-m", "deepeye_mcp.server"]`，此时依赖 PATH 中的 `python`。
- 在 TOML 配置文件（Codex CLI）中，字符串内反斜杠无需双写，但建议 Windows 路径直接用正斜杠 `/` 以避免歧义。

### 3. 启动命令与绝对路径

- DeepEye 是全局安装（`pip install deepeye-mcp` 或源码 `pip install -e .`），启动命令统一为 `deepeye`（等价 `python -m deepeye_mcp.server`）。
- 多数 coding agent（尤其从 GUI 启动的 VS Code 类插件）不一定继承终端的 shell PATH，**强烈建议在 `command` 中使用绝对路径**而非依赖 `deepeye` 命令的 PATH 解析，可避免 "command not found" 类问题。
- 推荐形式：`command` 为 Python 绝对路径，`args` 为 `["-m", "deepeye_mcp.server"]`。Windows 示例：`"command": "D:/Program Files/Python314/python.exe", "args": ["-m", "deepeye_mcp.server"]`。

### 4. 字段命名差异速查

不同客户端的顶层字段与字段命名存在差异，配置不可直接通用复制：

| 客户端 | 顶层字段 | command 形式 | env 字段 | 免确认字段 |
|---|---|---|---|---|
| opencode | `mcp` | 数组 | `environment` | `enabled` |
| Codex CLI | `mcp_servers`（TOML） | 字符串 + `args` | `env` | `enabled` |
| Claude Code | `mcpServers` | 字符串 + `args` | `env` | - |
| Cline | `mcpServers` | 字符串 + `args` | `env` | `autoApprove` |
| Cursor | `mcpServers` | 字符串 + `args` | `env` | - |
| Windsurf | `mcpServers` | 字符串 + `args` | `env` | - |
| Continue | `mcpServers`（数组） | `transport.command` | `transport.env` | - |
| Zed | `context_servers` | 字符串 + `args` | `env` | `agent.always_allow_tool_actions` |
| Roo Code | `mcpServers` | 字符串 + `args` | `env` | `alwaysAllow` |

### 5. API Key 安全

- **不要将包含真实 API Key 的 MCP 配置文件提交到公开版本控制**。项目级配置（如 `.mcp.json`、`.cursor/mcp.json`、`.roo/mcp.json`、`.codex/config.toml`）若要团队共享，应配合 `.gitignore` 或使用占位符 + 环境变量插值（Windsurf 与 Roo Code 支持 `${env:VAR}` 语法）。
- 部分客户端支持从系统环境变量读取：可在 shell 启动文件（`.bashrc`/`.zshrc`/PowerShell `$PROFILE`）中 `export` 凭证，配置文件中用插值引用。但需注意 GUI 启动的 IDE 不一定继承交互式 shell 的环境变量，此时仍应显式写入 `env` 字段或使用绝对路径。
- 团队共享场景下，推荐用占位符并附 README 说明每人本地填写，或使用各客户端支持的密钥管理机制。

### 6. 传输类型确认

DeepEye 是 **stdio 类型** MCP Server，配置时只需 `command`（+ `args`）与 `env`，**不要**填写 `url` / `serverUrl` / `headers` 等 HTTP 相关字段。多数客户端中，stdio 与 HTTP 传输互斥，同一 server 不能同时配置命令与 URL。

### 7. 配置生效与验证通用流程

1. 写入对应客户端的配置文件（或用 CLI/UI 添加）。
2. 按需重启客户端或重新加载配置（Cursor 支持热重载；Windsurf、Zed 等通常需要重启）。
3. 在客户端的 MCP 管理面板查看 DeepEye 连接状态（绿色 / connected / active 即正常）。
4. 在对话中显式让 agent 调用 DeepEye 的视觉工具验证端到端可用性。
5. 排查问题时优先在终端手动运行启动命令（`python -m deepeye_mcp.server`）确认进程能正常拉起、环境变量无误。
