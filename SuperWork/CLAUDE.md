# SuperWork Skill 路由

本文件是人类参考副本。**模型侧的权威路由在 `skills/superwork/SKILL.md`**（元
skill，会被各工具索引并按需加载）；两处内容冲突时以元 skill 为准。

## 无条件纪律（不被任何豁免；skill 未加载也必须遵守）

1. **先测后码**：项目有测试套件时，实现功能/修复先写失败测试再写生产代码
   （红→绿）；修 bug 必须带回归测试。例外需先问用户：一次性原型、生成
   代码、纯配置。详见 `tdd`。
2. **证据先于完成**：声称"完成/通过/修复"之前，必须在本轮运行完整验证
   命令并读取输出；没有新鲜证据不得声称。"应该能过"不是证据。详见
   `verification-before-completion`。
3. **合并前评审**：分支合回主干前必须完成 Standards + Spec 双轴评审
   （`code-review`）。触发阈值（任一满足即"较大改动"）：触及核心模块 /
   diff ≥ 15 文件 / 新增引擎、API 或数据模型契约。

## 裁决顺序（规则冲突时）

1. 用户明确指令 > 本文件一切规则。
2. 无条件纪律 > "不用"负向规则（豁免只作用于方法论类 skill，过程纪律照常）。

## 生命周期分工（速览；完整路由表见元 skill）

需求模糊 → `brainstorming` → 设计批准拆计划 → `writing-plans` → 执行计划 →
`executing-plans`（逐任务内调 `tdd`）；无计划直接写代码 → `tdd`；硬 bug →
`diagnosing-bugs`；声称完成前 → `verification-before-completion`；合并前 →
`code-review` → 收到评审 → `receiving-code-review`；收尾集成 →
`finishing-a-development-branch`；冲突 → `resolving-merge-conflicts`。低频：
`grilling`（压力测试）、`domain-modeling`（术语/ADR）、`research`（查文档）、
`writing-skills`（新增/修改 skill）、`handoff`（仅手动触发）；`grilling` 的
With-Docs Mode（追问 + 落盘 ADR）也仅显式点名时启用。

## 用户优先

用户点名"用 X skill"或"不用 skill"时，优先于本文件全部规则（包括无条件
纪律——用户明确放弃时从之，但应提示风险）。
