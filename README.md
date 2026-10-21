# RiskArena —— 开放的风控攻防竞技场

**An open, adversarial benchmark for bot-detection / risk-control defenses.**

> 你的防线的误伤率,不该由你自己写的机器人来打分。

---

## 为什么要有这个仓库

风控(验证码、反自动化)研究有个老毛病:**防线和测试它的机器人是同一批人**。
自己训的模型,拿自己写的生成器一测,捕获率 99%——然后真实世界一来,
要么咬伤一半真人,要么被一段 0.15px 的亚像素噪声整个绕过
(我们在姊妹项目 [slider-captcha-lab](../slider-captcha-lab) 里把这条循环论证
亲手踩了一遍:同一个人写的防线和标本,pro 型标本通过率 100%,utility 满分,
自我感觉良好)。

C. Herley 在 USENIX Security '22 把这个问题定名:没有独立对抗的防御评估,
是 *the plight of the targeted defender*。

RiskArena 的结构性解法:**让攻防双方成为不同的人。**

```
防线作者 ──提交──> Defense(分层判定:协议/规则/模型/环境)
                        │
                        ▼ 只通过 Challenge / Submission 见面
标本作者 ──提交──> Specimen(行为生成器,bot 或 human 意图)
                        │
                        ▼
              裁判 referee(全知视角)
              跑锦标赛 + 协议探针 + 统一计分 → leaderboard.json
```

- 标本只见 challenge 明文,看不到防线内部;
- 防线只见 submission,不知道出自哪个标本;
- 误伤率用**冻结的公开真人语料**回放(见 `data/corpus/PROVENANCE.md`),
  不用防线作者自己的"人类模拟器"。

## 快速开始(1 分钟,纯标准库,零依赖)

```bash
python -m riskarena tournament --trials 200
python -m riskarena leaderboard
python -m riskarena specimens
```

当前基线(2026-10,seed=2026,trials=200,含真实语料回放):

```
defense: slider-v3@3.1.0
  specimen                           intent    n  blocked  solved
  rookie                             bot     200   100.0%  100.0%   ← 什么都不装的脚本
  pro                                bot     200     0.0%  100.0%   ← 拟人生成器,全过
  sneaky                             bot     200   100.0%  100.0%   ← 只偷指纹质量
  human-sim                          human   200     0.0%  100.0%
  sloppy-sim                         human   200    33.0%   69.0%   ← 手抖真人(未对准=重试)
  corpus-human(1053 条真人拖拽)      human   200     0.0%  100.0%   ← 冻结语料

  catch_rate 66.7% · fp_rate 0.7% · utility +0.647 (λ=3.0)
  protocol: challenge 一次性 ✓ · 伪造票据全拒 ✓ · 票据单次性 ✓
```

读法:pro 全过 = 这条防线的**已知上限**(它就是我们实验室的"满级标本",
在黑盒联赛里新防线见不到它);corpus-human 0% 被拦 = 行为层没咬真人。

## 上线第一天,竞技场抓到了三个 bug(包括它自己的)

把真实语料接进来的第一场锦标赛,utility 从 +0.647 掉到 **-0.143**。
逐层验尸(`tools/debug_verdicts.py`)后修了三件事,每一件都是这个设计要抓的:

1. **指标混淆**:把"没对准滑块"计成了"误伤真人"。前者是重试,
   后者才是 `solved=True 仍被拦`。→ 误伤率改用 accused 率
   (`metrics.py`),另设 `HUMAN_SOLVE_FLOOR=0.5`:
   把挑战做得连真人都完不成的防线直接取消评分资格。
2. **机器速度伪影**:锦标赛以机器速度连发试次,human-sim 和语料回放共用
   静态指纹,把防线的 60s 频控(240 次)打爆 → 80% 的"误伤"其实是
   "同一个指纹每秒上千次验证"被忠实拦截。→ 锦标赛语义定为
   **每试次重置时间域状态**(i.i.d. 独立访客),频控这类时间域层
   明确移出榜单计分(见 `docs/league-rules.md`),要评它得等会话模式。
3. **真人验证**:修完上面两条,1053 条真人拖拽在规则层/模型层 0% 误伤,
   模型层给真人打 6/6 满分 —— 说明 v3 的 60Hz 事件合并增强
   (传输层陷阱)是真功夫,不是在自家生成器上的过拟合。

这条链就是本仓库的存在理由:**换一批人来打分,结论才会动。**

## 指标

```
utility = catch_rate − λ · fp_rate        (λ = 3:咬伤一个真人 ≈ 放过 3 次机器)
catch_rate = 机器人标本的宏观平均拦截率
fp_rate    = 真人标本 "完成了任务仍被拦"(accused)的宏观平均率
deep_catch_rate = 机器人完成拼图之后仍被拦的比例(防线在拼图之外的真实甄别力)
human_solved_rate < 0.5 → disqualified(挑战不可用)
协议探针   = challenge 一次性 / 伪造票据 / 票据单次性,任一 HOLE 写进榜单
```

## 联赛

- **白盒联赛**:标本可 import 防线代码,榜单单独标注 —— 用于定向压测。
- **黑盒联赛**:标本只见 challenge;防线上榜时发布的是可跑实例,
  权重不公开的版本由维护者持私有副本跑同一裁判(防"看榜调参到语料上")。

## 语料纪律(防循环论证的第二根支柱)

- 只接**许可明确的公开数据集**,无许可证默认拒绝(哪怕代码开源)。
- 当前语料:[NingNing0111/slider-track-model](https://github.com/NingNing0111/slider-track-model)
  (MIT)1053 条真人滑块拖拽,60Hz 采样 —— 转换脚本 `tools/convert_corpus.py`,
  来源与告诫见 `data/corpus/PROVENANCE.md`。
- 核查过并**拒绝**的:BeCAPTCHA-Mouse(需邮件签署 EMA)、
  geetest_track(无许可证)、SapiMouse(无数据许可证,且是自由鼠标不是验证码)。
- 回放手术:位移差 ≤5% 纯平移;超差则 x 等比缩放(保时长/保 y 抖动),
  如实声明,不做其他任何变换。

## 目录

```
riskarena/            接口契约、裁判、指标、语料(框架核心)
scenarios/slider/     滑块场景:v3 四层防线 + 内置标本(原型仓库直系移植)
tools/                语料转换、验尸调试
data/corpus/          冻结真人语料 + PROVENANCE.md
docs/                 架构、联赛规则、防线/标本贡献指南
CHARTER.md            红线:只打自家实例、合成标本、许可语料、黑盒纪律
```

## 参与贡献

两条赛道,见 [CONTRIBUTING.md](CONTRIBUTING.md):
**提交防线**(接受标本矩阵的审判)或**提交标本**(给现有防线出难题)。
冷启动承诺:只按文档走,30 分钟内应能跑通你的第一次锦标赛 ——
跑不通算文档 bug,请开 issue。

## 已知局限(诚实清单)

- 行为模型是 13 特征逻辑回归、语料来自单一采集组件(拖距 120~270px,
  y 近零)—— 结论只在滑块场景内成立,换场景请重测;
- 频控/信誉等时间域层在锦标赛语义下**不计分**(等会话模式);
- pro 型标本 100% 通过是**设计内的事实**:它定义了这条防线的已知上界,
  竞技场的任务是让"下一条防线"把这个上界打下来。

## 许可

代码 Apache-2.0(`LICENSE`);语料沿各自许可(`data/corpus/PROVENANCE.md`)。
红线见 [CHARTER.md](CHARTER.md):**只打本仓库内置的防线实例,永不指向真实站点。**
