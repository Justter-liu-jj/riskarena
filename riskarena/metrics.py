"""指标 —— 裁判的计分规则,一处定义,榜单共用。

核心立场(与 slider-captcha-lab v2/v3 的课程一脉相承):
  捕获率不是唯一指标。固定阈值时代的教训是"抓得越狠,误伤越狠",
  所以效用函数对误伤的惩罚必须显著高于放过。

  utility = catch_rate − λ · fp_rate      (λ 默认 3.0)

  λ 的量级依据:放过一个机器人通常意味着一次廉价重试;
  咬伤一个真人意味着一次流失。商用风控普遍把两者估为 3~10 倍价差
  (本靶场实测:v1 固定阈值抓 pro 全力以赴时误伤 sloppy ~50% ——
  那样的防线 utility 必须是负的,榜单要让它现形)。
"""
from dataclasses import dataclass, field

LAMBDA_DEFAULT = 3.0


@dataclass
class SpecimenReport:
    name: str
    intent: str                      # bot | human
    author: str = "anonymous"
    whitebox: bool = False
    n: int = 0
    blocked: int = 0
    solved: int = 0
    accused: int = 0                 # solved 且仍被拦 —— "完成了任务还被当贼"(真人误伤的真定义)
    errors: int = 0                  # 标本侧异常(build 抛错)—— 不计入 n
    def_errors: int = 0              # 防线侧异常(evaluate 抛错)—— 记一次未拦截
    solved_mismatch: int = 0         # 裁判独立复核与防线自报 solved 的矛盾次数
    avg_score: float = 0.0
    layer_pass: dict = field(default_factory=dict)   # 每层通过率,给防守方定位用

    @property
    def blocked_rate(self):
        return self.blocked / self.n if self.n else 0.0

    @property
    def solved_rate(self):
        return self.solved / self.n if self.n else 0.0

    @property
    def accused_rate(self):
        return self.accused / self.n if self.n else 0.0


# 人类完成率的地板:防线把挑战做得太难(真人完成率低于此)直接取消评分资格 ——
# 否则"谁都过不了"的防线 utility 满分
HUMAN_SOLVE_FLOOR = 0.5


@dataclass
class TournamentReport:
    defense: str
    defense_version: str
    trials_per_specimen: int
    seed: int
    specimens: list = field(default_factory=list)     # [SpecimenReport]
    protocol: dict = field(default_factory=dict)      # 协议探针结果
    lambda_: float = LAMBDA_DEFAULT
    verified_solved: bool = False    # 裁判是否用 check_solved 独立复核了 solved

    @property
    def has_human(self):
        return any(s.intent == "human" and s.n for s in self.specimens)

    @property
    def has_bot(self):
        return any(s.intent == "bot" and s.n for s in self.specimens)

    @property
    def rankable(self):
        """没有人类标本就没有误伤率,utility 无意义 —— 不予排名。"""
        return self.has_human and self.has_bot

    @property
    def catch_rate(self):
        bots = [s for s in self.specimens if s.intent == "bot" and s.n]
        return sum(s.blocked_rate for s in bots) / len(bots) if bots else 0.0

    @property
    def deep_catch_rate(self):
        """solved 之后仍被拦的比例 —— 防线在拼图之外的真实甄别力。"""
        bots = [s for s in self.specimens if s.intent == "bot" and s.solved]
        per = [s.accused / s.solved for s in bots]
        return sum(per) / len(per) if per else 0.0

    @property
    def fp_rate(self):
        """误伤率 = 真人完成了任务仍被拦(solved=False 只算重试,不算被当贼)。"""
        humans = [s for s in self.specimens if s.intent == "human" and s.n]
        return sum(s.accused_rate for s in humans) / len(humans) if humans else 0.0

    @property
    def human_solved_rate(self):
        humans = [s for s in self.specimens if s.intent == "human" and s.n]
        return sum(s.solved_rate for s in humans) / len(humans) if humans else 0.0

    @property
    def disqualified(self):
        return self.human_solved_rate < HUMAN_SOLVE_FLOOR

    @property
    def utility(self):
        return self.catch_rate - self.lambda_ * self.fp_rate

    def _has_corpus(self):
        return any(s.author == "public-corpus" for s in self.specimens)

    def summary(self):
        mismatches = sum(s.solved_mismatch for s in self.specimens)
        return {
            "defense": f"{self.defense}@{self.defense_version}",
            "trial_semantics": "reset-per-trial (i.i.d. visitors; 时间域层不计分,见 league-rules)",
            "corpus": "purported-human (ningning-slider-track-model, MIT, n=1050)" if self._has_corpus() else "synthetic-only",
            "verified_solved": self.verified_solved,
            "solved_mismatches": mismatches,
            "rankable": self.rankable,
            "catch_rate": round(self.catch_rate, 4),
            "deep_catch_rate": round(self.deep_catch_rate, 4),
            "fp_rate": round(self.fp_rate, 4),
            "human_solved_rate": round(self.human_solved_rate, 4),
            "disqualified": self.disqualified,
            "utility": round(self.utility, 4),
            "lambda": self.lambda_,
            "trials_per_specimen": self.trials_per_specimen,
            "seed": self.seed,
            "protocol": self.protocol,
            "specimens": [
                {"name": s.name, "intent": s.intent, "author": s.author,
                 "whitebox": s.whitebox, "n": s.n,
                 "blocked_rate": round(s.blocked_rate, 4),
                 "solved_rate": round(s.solved_rate, 4),
                 "accused_rate": round(s.accused_rate, 4),
                 "errors": s.errors, "def_errors": s.def_errors,
                 "solved_mismatch": s.solved_mismatch,
                 "avg_score": round(s.avg_score, 3),
                 "layer_pass": {k: round(v, 4) for k, v in s.layer_pass.items()}}
                for s in self.specimens
            ],
        }
