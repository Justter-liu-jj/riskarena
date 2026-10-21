"""滑块场景包 —— RiskArena 的第一个场景,也是原型(slider-captcha-lab v3)的直系移植。

场景定义:
  challenge.kind = "slider",payload = {gap_x, width, height, piece, tolerance}
  submission.samples = [[t_ms, x, y], ...]  拖动轨迹
  solved = 轨迹终点落在缺口 ±tolerance 内

内置防线 SliderDefense = 原型 v3 的四层:
  协议层(challenge 一次性 + HMAC 一次性票据)
  规则层(v2 尺度化行为阈值)
  模型层(13 维特征逻辑回归,1~6 拟人分,≥4 放行)
  环境层(webdriver / UA 一致性 / 插件 / Canvas + 同指纹频控)

内置标本 = 原型五种生成器 + 可选真实语料回放(见 corpora.py)。
"""
import random
import uuid

from riskarena.spec import Challenge, Defense, Specimen, Submission, Verdict

from . import detector, fingerprint, scoremodel, ticket

WIDTH, HEIGHT, PIECE, TOLERANCE = 640, 360, 44, 6
GAP_MIN, GAP_MAX = 200, WIDTH - PIECE - 20


# ---------------------------------------------------------------- 防线

class SliderDefense(Defense):
    name = "slider-v3"
    version = "3.2.0"

    def __init__(self):
        self._open = {}                     # challenge_id -> gap_x(一次性)
        self._rng = random.Random(0)        # seed() 会重播种(见下)
        scoremodel.get_model()              # 启动时训练(固定种子,权重稳定)

    def seed(self, s):
        """裁判在锦标赛开始时调用 —— 否则 --seed 管不住挑战抽样(假可复现)。"""
        self._rng = random.Random(s)

    # -- 场景面
    def new_challenge(self):
        cid = uuid.uuid4().hex
        gap = self._rng.randint(GAP_MIN, GAP_MAX)
        self._open[cid] = gap
        return Challenge(kind="slider", challenge_id=cid,
                         payload={"gap_x": gap, "width": WIDTH, "height": HEIGHT,
                                  "piece": PIECE, "tolerance": TOLERANCE})

    def check_solved(self, challenge, submission):
        """几何复核:终点落在缺口容差内即 solved。只凭明文,不经防线内部 ——
        裁判靠它独立复核 Verdict.solved(防自报刷指标)。"""
        samples = submission.samples if isinstance(submission.samples, list) else None
        gap = challenge.payload.get("gap_x")
        tol = challenge.payload.get("tolerance", TOLERANCE)
        if not samples or gap is None:
            return False
        try:
            return abs(float(samples[-1][1]) - float(gap)) <= float(tol)
        except (TypeError, ValueError, IndexError):
            return False

    def evaluate(self, challenge, submission):
        gap = self._open.pop(challenge.challenge_id, None)   # 协议层:challenge 一次性
        if gap is None:
            return Verdict(blocked=True, solved=False,
                           layers={"protocol": {"ok": False}},
                           note="challenge 不存在或已使用")
        samples = submission.samples if isinstance(submission.samples, list) else []
        try:
            res = detector.analyze(samples, gap_x=gap, tolerance=TOLERANCE, profile="v2")
            env = fingerprint.check(submission.fingerprint)
            model = (scoremodel.judge(res["metrics"], submission.fingerprint)
                     if res["metrics"] else
                     {"p": 0.0, "score": 1, "is_model": False})
        except Exception:
            return Verdict(blocked=True, solved=False,
                           layers={"protocol": {"ok": True}},
                           note="轨迹数据无法解析")

        blocked = not (res["solved"] is True and res["is_human"]
                       and model["is_model"] and env["ok"])
        verdict = Verdict(blocked=blocked, solved=res["solved"],
                          score=model["score"],
                          layers={"protocol": {"ok": True},
                                  "rules": {"ok": res["is_human"]},
                                  "model": {"ok": model["is_model"], "score": model["score"]},
                                  "env": {"ok": env["ok"]}},
                          reasons=[r for r in res["reasons"] if not r.get("ok")]
                                  + [r for r in env["reasons"] if not r.get("ok")])
        if not blocked and self.supports_protocol():
            token, _ttl = ticket.issue(challenge.challenge_id)
            verdict.ticket = token
        return verdict

    # -- 协议面(探针套件用)
    def supports_protocol(self):
        return True

    def use_ticket(self, token):
        return ticket.consume(token)

    def reset_session(self):
        """锦标赛语义:试次 = 独立访客。频控(时间域层)不在榜单计分,
        见本方法在 spec.Defense 的契约说明与 docs/league-rules.md。"""
        fingerprint.reset_rep()

    def make_human_submission(self, challenge):
        """协议探针用:造一条大概率全过的真人提交。"""
        from . import generator
        return Submission(
            samples=generator.gen_human(challenge.payload["gap_x"],
                                        self._rng.randrange(1 << 30)),
            fingerprint=fingerprint.profile_for("human"))


# ---------------------------------------------------------------- 标本

def _gen_of(mode):
    from . import generator
    names = {"sloppy": "gen_human_sloppy", "sneaky": "gen_sneaky"}
    return getattr(generator, names.get(mode, f"gen_{mode}"))


class GeneratorSpecimen(Specimen):
    """把原型的生成器包装成标本。变体噪声/参数写在自己的 build 里,别改生成器。"""

    def __init__(self, mode, intent="bot", name=None, author="slider-lab"):
        self.mode = mode
        self.intent = intent
        self.name = name or mode
        self.author = author

    def build(self, challenge, rng):
        gen = _gen_of(self.mode)
        pts = gen(challenge.payload["gap_x"], rng.randrange(1 << 30))
        return Submission(samples=pts,
                          fingerprint=fingerprint.profile_for("sneaky"
                                                              if self.mode == "sneaky"
                                                              else self.mode))


class SlowDragFpBot(Specimen):
    """慢速匀速拖拽 + 完整指纹(bot)—— 首位贡献者标本(2026-10 冷启动测试产出)。

    策略:35~60px/s 极慢匀速主体 + 终点瞄准修正 + 字段完整一致的指纹。
    对 slider-v3 的实测:全过(0% 拦截,模型平均 6.00)。机制:
      1. 匀速主体本应被规则层 peak_speed_ratio≥1.4 拦下,但终点瞄准修正的
         一步 ~3px/16.7ms(≈170px/s)"松手拽动"把峰均比抬进钟形曲线;
      2. 模型层把"极慢"(≈Fitts 下限 30 倍)判成满分真人 —— 训练集里
         慢=人类。规则层要的钟形速度曲线,被一次 3px 的松手动作满足。
    黑盒:只消费 challenge.payload 明文;指纹硬编码,不 import 任何场景模块。
    """
    name = "slow-drag-fp"
    intent = "bot"
    author = "first-contributor"
    whitebox = False

    FINGERPRINT = {
        "webdriver": False, "plugins": 5, "languages": "zh-CN,zh",
        "platform": "Win32",
        "ua": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
               "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
        "screen": "1920x1080", "timezone": "Asia/Shanghai",
        "canvas_hash": -27182818,
    }

    def build(self, challenge, rng):
        gap = float(challenge.payload["gap_x"])
        tol = float(challenge.payload.get("tolerance", 6))
        speed = rng.uniform(35.0, 60.0)            # px/s,人类速度分布的慢尾
        step_ms = 16.7                             # rAF 节奏;匀速 = 每步等距
        pts = [[0.0, 0.0, 0.0]]
        t = x = 0.0
        while x < gap - 0.5:
            t += step_ms
            x = min(x + speed * step_ms / 1000.0, gap)
            pts.append([t, x, rng.gauss(0, 0.6)])
        err = max(-tol + 1.0, min(tol - 1.0, rng.gauss(0, 1.0)))
        pts.append([t + step_ms, gap + err, pts[-1][2] + rng.gauss(0, 0.3)])
        return Submission(samples=pts, fingerprint=dict(self.FINGERPRINT))


BUILTIN_SPECIMENS = [
    GeneratorSpecimen("rookie", intent="bot", name="rookie"),
    GeneratorSpecimen("pro", intent="bot", name="pro"),
    GeneratorSpecimen("sneaky", intent="bot", name="sneaky"),
    SlowDragFpBot(),
    GeneratorSpecimen("human", intent="human", name="human-sim"),
    GeneratorSpecimen("sloppy", intent="human", name="sloppy-sim"),
]

BUILTIN_DEFENSES = {"slider-v3": SliderDefense}
