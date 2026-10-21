# 标本编写指南

## 你在写什么

一个 `Specimen` 是**行为生成器**:吃 challenge,吐 submission。
它不是"对某站的攻击脚本"—— CHARTER 红线 2。写的是思路:
怎样把动作做得更像人/更像机器,给防线出难题或当体检标尺。

## 最小骨架

```python
import random
from riskarena.spec import Specimen, Submission

class SlowDragBot(Specimen):
    name = "slow-drag-bot"
    intent = "bot"            # "bot" = 想通过验证的机器
    author = "you"

    def build(self, challenge, rng: random.Random) -> Submission:
        gap = challenge.payload["gap_x"]
        pts = [[0.0, 0.0, 0.0]]
        t, x = 0.0, 0.0
        while x < gap - 1:
            t += rng.uniform(8, 30)                    # 慢而稳
            x = min(gap, x + rng.uniform(1, 5))
            pts.append([t, x, rng.gauss(0, 0.6)])      # 一点 y 抖动
        return Submission(samples=pts)                 # 指纹可缺 —— 缺失本身是信号
```

## intent 标注(最重要的一个字)

- `"bot"` —— 你的标本**想通过验证**。榜单用它算防线的 catch_rate;
- `"human"` —— 你的标本模拟**真人**(生成器或冻结语料回放)。
  榜单用它算 fp_rate:human 标本 `solved ∧ blocked` = 误伤。

标注造假 = 逐出(CHARTER 红线 4)。两个自检:
bot 标本不该"故意输"来刷防线误伤;human 标本不该带 bot 逻辑。

## 指纹

- 交 `fingerprint` dict(字段见场景的 REQUIRED_FIELDS)—— 想测行为层就给合格档;
- 交 `None` —— 合法,但环境层会拦你(缺失即信号),别把这下毒计成"误伤"。
- human 意图的语料回放标本请配场景的真人指纹档(见 `__main__.py` 的做法):
  语料考察的是行为,别让"没填指纹"替它挨枪。

## 白盒纪律

黑盒标本**不许 import 防线模块**。你只能消费 challenge 的明文 payload
(滑块 = gap_x/width/piece/tolerance)。想针对某条防线内部做定向压测?
那是白盒联赛:标 `whitebox = True`,榜单单独标注。

## 变换要声明

对语料/生成轨迹做任何变换(等比缩放、重采样、插值、去噪),
在 docstring 里如实写。回放手术的默认政策见 docs/architecture.md。
粉饰指标 = 拒收(CHARTER 红线 5)。

## 上传前自查

```bash
python -m riskarena tournament --trials 200
python tools/debug_verdicts.py     # 看你的标本卡在哪层(若被拦)
```

PR 描述里给:名字 / intent / 作者 / 白盒与否 / 一句话策略 / 完整 tournament 输出。

## 内置标本一览

`python -m riskarena specimens`

| 标本 | intent | 策略 | 教学点 |
|---|---|---|---|
| rookie | bot | 匀速直线,不装指纹 | 什么都不会的下限 |
| pro | bot | 拟人节奏+合格指纹 | 实验室防线的已知上界 |
| sneaky | bot | 只偷指纹质量,行为拉胯 | 指纹好≠行为好 |
| human-sim | human | 拟人生成器 | 合成基线(有循环论证嫌疑,故需语料) |
| sloppy-sim | human | 手抖、拖过头 | "没对准"是重试,不是误伤 |
| corpus-human | human | 1053 条冻结真人拖拽回放 | 防循环论证的标尺 |
