# evals/ — 基线证据

writing-skills 的铁律：**没有失败测试，就不写 skill**。本目录就是证据的存放地——没有它，"这些 skill 有效"就是一个未经验证的断言，恰好是这个包最反对的事。

## 就绪的实况夹具

`fixtures/pricing-lab/` —— 一个零依赖的 Node 项目，内含一个现有测试套件看不见的边界 bug。协议、分组与评分表在其 README 里。`_template/` 存放逐次运行的记录模板。

## 一条记录是什么

每个 skill（或每个生命周期场景）一个文件夹，以 skill 命名：

```
evals/
├── README.md            # 本文件
├── INDEX.md             # 每次 recorded run 一行（台账）
├── superwork/
│   └── 2026-09-20-execute-done-routing/
│       ├── scenario.md  # 交给 agent 的任务原文，逐字
│       ├── red.md       # 无 skill 基线：agent 做错了什么
│       └── green.md     # 载入 skill 后：什么变了
└── tdd/
    └── ...
```

- **scenario.md** — 交给 agent 的确切任务，附模型名称/档位与日期。不可复现的场景不叫证据。
- **red.md** — 无 skill 基线。写明失败在哪（跳过了规则、形状不对、缺了要素）。没有失败的 RED = 无物可教 = 不配写 skill。
- **green.md** — 同一场景载入 skill 后的表现。写明是哪条约束产生了合规行为。

永远先 RED 后 GREEN。只有 green 的记录是证言，不是测试。

## 值得记录的东西

- 用户**纠正了路由器选的路线** → 在 `superwork/` 记一条，INDEX.md 加一行（`misroute` 类型）。
- 某条约束**在新压力下失效** → 在该 skill 的文件夹里加新场景（这就是 writing-skills 说的 REFACTOR 输入）。
- 一个**新借口**攻破了一条纪律 → 该 skill `rationalizations.md` 的候选行（链到场景）。

## 诚实的边界声明

- 这些是**单模型、单操作者的观察**，不是基准测试。它们证明的是"这个失败存在，且 skill 改变了它"——不是统计命中率。
- 子代理基线没法从本仓库内部跑；转写文本从真实会话粘贴进来，密钥已脱敏（diagnosing-bugs 的脱敏纪律在这里同样适用）。
- 被证伪的记录（"失败"其实是正确行为）追加更正说明，绝不静默删除。
