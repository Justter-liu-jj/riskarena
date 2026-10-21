# 联赛规则

## 比赛定义

一场锦标赛 = 一条防线 × 一组标本 × trials 次(默认 200)× 固定 seed(默认 2026)。
裁判:`python -m riskarena tournament`。

## 指标定义(唯一口径,来自 riskarena/metrics.py)

| 指标 | 定义 | 备注 |
|---|---|---|
| blocked_rate | 标本被拦比例 | 含"没对准"的重试 |
| solved_rate | 完成场景任务(滑块=对准缺口)的比例 | 与 blocked 独立 |
| **accused_rate** | **solved 且仍被拦** 的比例 | 真人误伤的真定义;机器人=深捕获 |
| catch_rate | bot 标本 blocked_rate 的宏观平均 | 实用拦截率 |
| deep_catch_rate | bot 标本 solved 后仍被拦的比例的宏观平均 | 拼图之外的甄别力 |
| **fp_rate** | human 标本 accused_rate 的宏观平均 | "没对准"不算误伤 |
| human_solved_rate | human 标本 solved_rate 宏观平均 | 可用性体检 |
| utility | catch_rate − 3.0 × fp_rate | λ=3:咬真人 ≈ 放过 3 次机器 |

- **HUMAN_SOLVE_FLOOR = 0.5**:human_solved_rate < 0.5 的防线 disqualified,
  沉底并标注 —— 把挑战做得连真人都完不成,不配拿 catch 分。
- λ=3 的量级依据:放过一个机器人 ≈ 一次廉价重试;咬伤一个真人 ≈ 一次流失。
  商用风控普遍把两者估为 3~10 倍价差。改 λ = 改规则,需 maintainer 提案。

## 时间域层

锦标赛每试次调用 `defense.reset_session()`(i.i.d. 访客语义)。
频控、信誉窗口、会话内速率等**依赖真实时间流的层因此不计榜单分**;
防线应在 reset_session 的 docstring 里声明哪些层被移出。
会话模式(带 inter-arrival 的访问序列)在路线图里,落地前
任何"频控捕获率"宣传口径都不被榜单承认。

## 协议探针

独立于锦标赛,测跨请求状态,不重置:
`replay_challenge`(challenge 一次性)、`forged_ticket`(6 种伪造全拒)、
`ticket_replay`(真票单次性)。任一 HOLE 原文写进榜单条目 ——
协议层是风控的"最后一公里",HOLE 不扣 utility 分但必须可见。

## 联赛分级

- **白盒**:标本可 import 防线代码。榜单单独标注 `whitebox: true`。
  用途:定向压测一条防线的已知实现。
- **黑盒**:标本只见 challenge 明文。防线上榜 = 可跑实例;
  权重私有的版本由维护者用私有副本跑同一裁判、同一 seed,只发布结果。
  目的:防"看榜调参到语料上"(榜单过拟合)。

## 榜单与发布

- 本地跑的结果进 `results/history.jsonl`(追加)+ `leaderboard.json`(覆盖同名防线),
  都在 .gitignore,按克隆各自生成。
- 维护者发布版流程:PR 合并 → 检索历史榜单与 scenarios/ 做**名字冲突检查**
  (冲突则后到者改名)→ 用固定 seed 复跑 → 更新公开 leaderboard 与 README 数字。
- 复核清单见 CONTRIBUTING.md;红线见 CHARTER.md。

## 争议处理

对某条结果的异议:开 issue 附你的完整 tournament 输出(含 seed 与 trials)。
裁决顺序:先查是否复现 → 再查语义(时间域层?探针例外?)→ 最后查指标口径。
**指标口径争议不私下解决**,改口径 = 改规则 = maintainer 提案 + 榜单注明断层。
