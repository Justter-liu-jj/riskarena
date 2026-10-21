# 联赛规则

## 比赛定义

一场锦标赛 = 一条防线 × 一组标本 × trials 次(默认 200)× 固定 seed(默认 2026)。
裁判:`python -m riskarena tournament`。
可复现性:防线实现 `seed(s)` 后,挑战抽样与标本随机流都由 `--seed` 决定
—— 未实现 seed 的防线,报告里的 seed 字段按"假可复现"对待。
标本每试次拿到的 rng 是独立实例、challenge 是深拷贝(见 spec.py)。

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
  榜单**沉底并标注** —— 把挑战做得连真人都完不成,不配拿 catch 分。
  这是强制执行(写入与排序),不是建议。
- **rankable**:报告中必须同时存在 bot 与 human 意图标本且各有 ≥1 条有效
  试次,否则 rankable=False、不参与排名 —— 没有误伤率,utility 无意义
  ("零真人阵容 utility=1.0"是审查抓到的刷分洞)。
- **verified_solved / solved_mismatches**:防线实现了 `check_solved` 时,
  裁判逐试次独立复核 solved 并计分只认复核值;自报与几何事实的矛盾次数
  写进榜单。未实现的防线标 `verified_solved=False`,评审会追问原因。
- **意图标签**:必须是精确的 `"bot"`/`"human"`(metrics 宏平均只认这两串);
  语料里标签不合法的行跳过并告警,绝不静默归桶。标本意图造假 = 逐出
  (CHARTER 红线 4), intents 与实际行为不符由评审代码检查把守。
- λ=3 的量级依据:放过一个机器人 ≈ 一次廉价重试;咬伤一个真人 ≈ 一次流失。
  商用风控普遍把两者估为 3~10 倍价差。改 λ = 改规则,需 maintainer 提案。

## 语料证据分级

fp_rate 的证据强度取决于人类语料的可核实性:

| 等级 | 定义 | 当前状态 |
|---|---|---|
| synthetic | 合成生成器(防线作者可自造,自证循环) | human-sim / sloppy-sim |
| **purported-human** | 自称真人、不可核实、无伦理记录 | corpus-human·1050(ningning,MIT) |
| verified-human | 有采集方法、人数、设备构成与知情同意记录 | **暂缺 —— 求贡献** |

榜单条目的 `corpus` 字段必须写明等级。**只有 verified-human 语料上的
fp_rate 才能作为防线可用性的最终结论**;purported-human 的数字是体检
信号,不是判决书。

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
