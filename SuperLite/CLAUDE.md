# SuperLite Skill 指南

轻量组合包（8 + 1 skill）。`superlite` mini 路由元 skill 在任务开始时触发
（路由表 + 无条件纪律），其余按 description 自动触发。人类参考副本，模型侧
以各 SKILL.md 为准。

## 分工速览

写代码 → `tdd`；硬 bug → `diagnosing-bugs`；合并前评审 → `code-review`；
声称完成前（任何交付物）→ `verification-before-completion`；写文档/计划/
邮件等书面交付物 → `writing`；查资料核实事实 → `research`；决策压力测试 →
`grilling`；会话交接 → `/handoff`（手动）。

## 纪律（skill 未加载也必须遵守）

1. 先测后码（项目有测试套件时）；例外先问用户。
2. 证据先于完成：没有当轮新鲜验证不得声称"完成/通过/修好"。
3. 较大改动合并前评审（核心模块 / diff ≥ 15 文件 / 新契约）。

## 用户优先

用户点名"用/不用 X skill"时优先于本文件全部规则。
