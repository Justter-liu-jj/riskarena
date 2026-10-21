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

场景约定:轨迹从 **x=0** 起拖到 gap_x(场景不承诺滑块起始坐标,裁判按
位移计;内置生成器的 X0=10 是历史口径差,与从 0 出发等价)。

## intent 标注(最重要的一个字)

- `"bot"` —— 你的标本**想通过验证**。榜单用它算防线的 catch_rate;
- `"human"` —— 你的标本模拟**真人**(生成器或冻结语料回放)。
  榜单用它算 fp_rate:human 标本 `solved ∧ blocked` = 误伤。

标注造假 = 逐出(CHARTER 红线 4)。两个自检:
bot 标本不该"故意输"来刷防线误伤;human 标本不该带 bot 逻辑。

## 指纹

- 交 `fingerprint` dict —— 想测行为层就给合格档。字段集合(黑盒标本请
  硬编码,不要 import 场景模块):`webdriver, plugins, languages, platform,
  ua, screen, timezone, canvas_hash`;
- 交 `None` —— 合法,但环境层会拦你(缺失即信号),别把这下毒计成"误伤"。
- 黑盒纪律的边界:`import scenarios.slider.fingerprint` 这类取"指纹档"
  的捷径**不算**白盒(它不是判定逻辑),但推荐硬编码 —— 完全自足的
  标本对评审最友好;`import scenarios.slider.detector/scoremodel/ticket/scenario`
  则是白盒,`tools/lint_redlines.py` 对 specimens/ 目录机械拦截。

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
python tools/lint_redlines.py                          # 红线(CI 同款)
python -m riskarena specimens                          # 你的标本应被自动发现
python -m riskarena tournament --trials 200            # 看它的表现
python tools/debug_verdicts.py slow-drag-fp            # 卡在哪层(按名查)
```

本地标本放仓库根 `specimens/` 目录即被 CLI 自动发现(不入库);或
`--specimen 文件.py:类名`。PR 描述里给:名字 / intent / 作者 / 白盒与否 /
一句话策略 / 完整 tournament 输出。

## 内置标本一览

`python -m riskarena specimens`

| 标本 | intent | 策略 | 教学点 |
|---|---|---|---|
| rookie | bot | 匀速直线,不装指纹 | 什么都不会的下限 |
| pro | bot | 拟人节奏+合格指纹 | 实验室防线的已知上界 |
| sneaky | bot | 只偷指纹质量,行为拉胯 | 指纹好≠行为好 |
| slow-drag-fp | bot | 极慢匀速+终点修正+合格指纹 | 首位贡献者的通过配方:模型把"极慢"判满分真人 |
| human-sim | human | 拟人生成器 | 合成基线(有循环论证嫌疑,故需语料) |
| sloppy-sim | human | 手抖、拖过头 | "没对准"是重试,不是误伤 |
| corpus-human·1050 | human | 冻结语料回放(purported-human) | 防循环论证的标尺 |
