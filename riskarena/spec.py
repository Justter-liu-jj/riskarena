"""RiskArena 接口契约 —— 攻防双方的唯一合法见面方式。

设计原则:
  1. 防线(Defense)与标本(Specimen)互相只见对方的最小面:
     标本拿得到 challenge(明文协议),看不到防线内部;
     防线拿得到 submission,不知道它出自哪个标本。
  2. 裁判(Referee)拥有全知视角,负责计分。
  3. 一切皆纯标准库 —— 与 slider-captcha-lab 同一哲学。

术语:
  challenge   一次待验证挑战(场景定义,如滑块的 gap_x)
  submission  标本对挑战的应答(轨迹 + 环境指纹 + 场景附加物)
  verdict     防线对 submission 的分层判定
  specimen    攻击/行为样本的产生器,分两类意图:
              intent="bot"   想通过验证的机器 → 测防线捕获率
              intent="human" 真人行为的模拟/回放 → 测防线误伤率
"""
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------- 数据结构

@dataclass
class Challenge:
    """场景下发的挑战。场景包负责具体字段,这里只约定公共面。"""
    kind: str                    # 场景名,如 "slider"
    challenge_id: str            # 一次性 ID(协议层测试点)
    payload: dict = field(default_factory=dict)   # 场景字段,如 {"gap_x": 358}


@dataclass
class Submission:
    """标本对挑战的应答。"""
    samples: Optional[list] = None        # 轨迹 [[t_ms, x, y], ...](场景定义语义)
    fingerprint: Optional[dict] = None    # 环境指纹(可缺失 —— 这本身就是信号)
    extra: dict = field(default_factory=dict)


@dataclass
class Verdict:
    """防线的判定。blocked 是最终裁决:True = 拦截。"""
    blocked: bool
    solved: Optional[bool] = None         # 场景语义的"完成任务"(如拼图对准)
    score: Optional[float] = None         # 连续风险分(若有,1~6 或原始 p)
    layers: dict = field(default_factory=dict)   # {"rules": {...}, "model": {...}, ...}
    reasons: list = field(default_factory=list)
    ticket: Optional[str] = None          # 全过时下发的协议票据(可选能力)
    note: str = ""


# ---------------------------------------------------------------- 防线接口

class Defense:
    """防线基类:实现者组合若干层,对 submission 给出最终裁决。

    攻防不对称由 evaluate 的契约体现:任何一层报警都足以拦截。
    """
    name: str = "unnamed-defense"
    version: str = "0.0.1"

    def new_challenge(self) -> Challenge:
        raise NotImplementedError

    def evaluate(self, challenge: Challenge, submission: Submission) -> Verdict:
        raise NotImplementedError

    # ---- 可选协议能力:实现了才参加协议探针套件
    def supports_protocol(self) -> bool:
        return False

    def use_ticket(self, token: str) -> tuple:
        """("ok"|"replay"|"expired"|"invalid", msg)。不实现则探针跳过。"""
        raise NotImplementedError

    # ---- 锦标赛语义:裁判在每个试次前调用
    def reset_session(self) -> None:
        """清空时间域状态(频控窗口、会话信誉等)。

        锦标赛的试次是 i.i.d. 的独立访客样本,以机器速度连发 —— 防线若带着
        跨试次的时间域状态跑,会把"模拟器跑得快"误读成"同一个客户端每秒
        上千次验证"(2026-10 实测:语料回放误伤率因此虚高到 80%)。

        频控/信誉这类**依赖真实时间流**的层因此无法在锦标赛语义下计分:
        请在本方法里如实重置,并在 docstring 里声明该层不计入榜单 ——
        它需要在带时间语义的会话模式里评(见 docs/league-rules.md)。
        裁判在**每个试次前**调用本方法(基类默认 no-op)。
        """
        return None


# ---------------------------------------------------------------- 标本接口

class Specimen:
    """标本基类。build 收到 challenge,返回 submission。

    黑盒纪律:实现者只允许消费 Challenge 的明文内容与(白盒联赛才有)自己在
    历史试探里积累的记忆 —— 不允许 import 防线模块读内部状态。
    """
    name: str = "unnamed-specimen"
    intent: str = "bot"          # "bot" | "human"
    author: str = "anonymous"
    whitebox: bool = False       # 白盒标本在榜单上单独标注

    def build(self, challenge: Challenge, rng) -> Submission:
        raise NotImplementedError


class ReplaySpecimen(Specimen):
    """语料回放标本:把冻结的人类轨迹语料平移对齐到挑战缺口后提交。

    平移(不改速度/时长/抖动)是对真实语料最少的手术;场景包可提供更聪明的
    适配器,但任何变换都必须在 specimen 的 docstring 里如实声明。
    """
    def __init__(self, name, traces, fingerprint=None, author="corpus"):
        self.name = name
        self.intent = "human"
        self.author = author
        self._traces = traces
        self._fp = fingerprint

    def build(self, challenge, rng):
        from .corpora import align_translation
        pts = rng.choice(self._traces)
        gap = challenge.payload.get("gap_x")
        return Submission(samples=align_translation(pts, gap), fingerprint=self._fp)
