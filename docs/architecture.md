# 架构

## 一张图

```
                 ┌───────────────────────────────────────────┐
                 │                referee(全知)              │
                 │  run_tournament / run_protocol_suite      │
                 │  save_report → history.jsonl + 榜单        │
                 └──────┬────────────────────────┬───────────┘
       new_challenge()  │                        │  build(challenge, rng)
       evaluate(ch,sub) ▼                        ▼
              ┌──────────────┐          ┌──────────────────┐
              │   Defense    │          │    Specimen      │
              │ (防线实例)    │          │ (标本:生成器)     │
              └──────┬───────┘          └──────────────────┘
                     │ Verdict{blocked, solved, score, layers, reasons, ticket}
                     ▼
              ┌──────────────┐
              │   metrics    │  utility = catch − λ·fp
              └──────────────┘
```

双盲见面:防线与标本只交换 `Challenge` / `Submission`(`riskarena/spec.py`)。
裁判看得见全部,负责计分;它自己不参与攻防。

## 防循环论证的三根支柱

1. **贡献者分离**(结构性):攻与防是不同的人,这是本仓库存在的理由。
2. **冻结语料**:`data/corpus/converted.jsonl` 一经发布不再修改;
   误伤率必须在语料回放 + 合成人类标本两处同时报告。语料更新 =
   新版本文件 + PROVENANCE 更新,旧榜单数字不追溯。语料按证据分级
   (synthetic / purported-human / verified-human,见 league-rules.md);
   当前语料为 purported-human,完整披露见 data/corpus/PROVENANCE.md。
3. **黑盒联赛**:防线上榜时可发布不可读的实例,权重私有;
   同一裁判、同一探针套件、同一效用函数。

## 裁判诚信(2026-10 设计审查后定型)

- **solved 独立复核**:防线的 `Verdict.solved` 是自报值;实现了
  `check_solved` 的防线,裁判逐试次用纯几何/语义复核并**只认复核值**,
  矛盾计入 `solved_mismatches`。否则"凡拦截一律报没完成"可把误伤率
  刷成 0 —— 该洞在审查中被证实可一句话刷穿 utility。
- **异常隔离**:标本异常跳过试次(不计 n),防线异常记 def_error
  (等价没拦住)。第三方代码炸不掉整场矩阵。
- **黑盒的结构保证**:标本拿到 challenge 深拷贝与每试次独立的 rng 实例
  —— 篡改靶点、污染全场随机流都到不了 evaluate。
- **可复现**:防线实现 `seed(s)` 接管挑战抽样;标本随机流由主 seed 派生。
- **强制执行**:rankable(须同时有 bot/human 标本)与 disqualified
  (human_solved_rate < 0.5)在榜单写入与排序处强制,不是摆设;
  CHARTER 红线由 `tools/lint_redlines.py` 机械检查,CI 强制。

## 锦标赛语义(2026-10 定版)

- **试次 = i.i.d. 独立访客**。裁判每个试次前调用 `defense.reset_session()`,
  防线必须清空时间域状态(频控窗口、会话信誉)。
  依据:实测语料回放误伤率因静态指纹 + 机器速度被频控虚增至 80% ——
  那不是防线的性质,是模拟语义的伪影。
- 因此**频控/信誉等时间域层不计榜单分**。要评它们,需要带时间流的
  会话模式(specimen 产出带 inter-arrival 的访问序列)—— 路线图。
- 协议探针独立于锦标赛跑,探针之间互不继承时间域状态(它们测的恰是
  跨请求状态:challenge 一次性、票据单次性)。

## 回放手术政策

真实语料与挑战的几何域可能不重合(语料拖距 120~270px,滑块缺口 200~576px):

- |dx − gap| ≤ 5% → 纯平移;
- 否则 → **时空等比缩放**:x 与 t 同乘 r(锚点用语料的 target_distance,
  即原挑战靶点),保住速度剖面、节奏比值与松手误差。

历史注记:第一版"只缩 x 不缩 t"被设计审查推翻 —— 等时长放大距离会把
速度 ×r、加速度 ×r²,快拖轨迹掉进训练分布的机器侧制造假误伤;终点钉死
在 gap_x 则把语料真实的失手率抹掉,让"重试 vs 误伤"的区分失真。
任何额外变换(重采样/插值/去噪)都必须在标本 docstring 声明,
评审按 CHARTER 红线 5 拒绝粉饰。

## 纯标准库纪律

框架与场景零第三方依赖(教材可跑性 + 审计面最小化)。逻辑回归是
全批梯度下降手写实现;JSONL 手写解析。代价是"模型 primitive 落后",
换来的是:**任何人都能在 5 分钟内读完裁判的全部代码** ——
裁判本身必须经得起读,否则"独立计分"只是口号。

## 场景包

`scenarios/` 下每个目录 = 一个场景:payload 语义 + 内置防线 + 内置标本。
滑块场景是原型(slider-captcha-lab v3)的直系移植,vendored 模块首行
注明出处;新场景欢迎 PR,但必须自带 reset_session 语义与语料适配说明。
