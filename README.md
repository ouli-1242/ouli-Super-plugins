# Ouli Super Plugins

Ouli 的个人 Claude Code skill 插件合集。本仓库为源码托管/备份仓库，内含两个独立插件子目录（非单仓结构，不可直接 `claude plugin install` 本仓库根目录）。

## 插件列表

| 子目录 | 插件名 | 版本 | 说明 |
|---|---|---|---|
| [`SuperWork/`](SuperWork/) | `superwork` | 1.5.0 | 全量精选 skill 组合包：TDD、debugging、code review、grilling、domain-modeling、verification 等 16 个 skill |
| [`SuperLite/`](SuperLite/) | `superlite` | 1.0.0 | 轻量 skill 包：TDD、debugging、review、verification + 通用 writing、research、grilling、handoff |

## 说明

- 每个子目录是一个完整独立的 Claude Code 插件（含 `.claude-plugin/` 与 `marketplace.json`，`source: "./"`）。
- 如需可直接安装，请分别将 `SuperWork/`、`SuperLite/` 各自单独建仓后再 `claude plugin install <repo-url>`。
- MIT License，作者 Ouli。
