"""裁判 —— 全知视角的锦标赛执行者。

  标本只见 challenge,防线只见 submission,裁判见全部。

锦标赛(白盒/黑盒同流程,区别在纪律):
  for trial in K:
      challenge = defense.new_challenge()
      submission = specimen.build(challenge, rng)
      verdict = defense.evaluate(challenge, submission)
      计入 per-specimen blocked/solved/layer 通过率

协议探针套件(独立于锦标赛,测协议层的"最后一公里"):
  对实现了 use_ticket 的防线,自动跑:重放已用票据 / 伪造签名 / 格式攻击,
  任何一条本应被拒却放行的探针记为 HOLE。
"""
import copy
import json
import random
import time
import uuid

from .metrics import SpecimenReport, TournamentReport
from .spec import Defense

RESULTS_FILE_DEFAULT = "results/history.jsonl"
LEADERBOARD_FILE_DEFAULT = "leaderboard.json"


# ---------------------------------------------------------------- 锦标赛

def run_tournament(defense, specimens, trials=200, seed=2026):
    """跑一遍 防 × 标本 矩阵,返回 TournamentReport。

    裁判纪律(2026-10 设计审查后定型):
      * solved 由 defense.check_solved 独立复核(实现了才启用);裁判计分
        只认复核值,与 Verdict.solved 的矛盾计入 integrity —— 否则
        "凡 blocked 一律报 solved=False"一句话就能把误伤率刷成 0。
      * 标本拿到的是 challenge 的深拷贝 + 每试次独立的 rng 实例 ——
        篡改靶点、污染全场随机流都到不了 evaluate。
      * 逐试次异常隔离:标本异常跳过该试次(不计 n),防线异常记
        def_error(等价于没拦住)—— 一个必抛异常的第三方模块炸不掉整场。
    """
    rng = random.Random(seed)
    defense.seed(seed)                       # 挑战生成进入可复现轨道
    rep = TournamentReport(defense=defense.name, defense_version=defense.version,
                           trials_per_specimen=trials, seed=seed)
    rep.verified_solved = type(defense).check_solved is not Defense.check_solved
    for spec in specimens:
        sr = SpecimenReport(name=spec.name, intent=spec.intent, author=spec.author,
                            whitebox=getattr(spec, "whitebox", False))
        layer_ok = {}
        scores = []
        for _ in range(trials):
            trial_rng = random.Random(rng.getrandbits(64))   # 每试次独立随机流
            defense.reset_session()          # 每试次 = 独立访客(见 spec.reset_session)
            challenge = defense.new_challenge()
            try:
                submission = spec.build(copy.deepcopy(challenge), trial_rng)
            except Exception:
                sr.errors += 1               # 标本自己的锅,不计入 n
                continue
            sr.n += 1
            try:
                verdict = defense.evaluate(challenge, submission)
            except Exception:
                sr.def_errors += 1           # 防线判不动 = 没拦住,计入 n 拉低 catch
                continue

            solved_eff = verdict.solved
            if rep.verified_solved:
                try:
                    gt = defense.check_solved(challenge, submission)
                except Exception:
                    gt = None
                if gt is not None:
                    solved_eff = bool(gt)
                    if verdict.solved is not None and bool(verdict.solved) != solved_eff:
                        sr.solved_mismatch += 1     # 防线自报与几何事实矛盾
            if verdict.blocked:
                sr.blocked += 1
            if solved_eff:
                sr.solved += 1
                if verdict.blocked:
                    sr.accused += 1        # 完成了任务还被拦:真人=误伤,机器人=深捕获
            if verdict.score is not None:
                scores.append(verdict.score)
            for lname, lstate in (verdict.layers or {}).items():
                ok = lstate.get("ok")
                if ok is not None:
                    a = layer_ok.setdefault(lname, [0, 0])
                    a[1] += 1
                    a[0] += 1 if ok else 0
        sr.avg_score = sum(scores) / len(scores) if scores else 0.0
        sr.layer_pass = {k: v[0] / v[1] for k, v in layer_ok.items() if v[1]}
        rep.specimens.append(sr)
    return rep


# ---------------------------------------------------------------- 协议探针

def _probe_replay_challenge(defense):
    """同一 challenge 提交两次:第二次必须被拦(challenge 一次性)。"""
    ch = defense.new_challenge()
    sub = _any_submission(defense, ch)
    defense.evaluate(ch, sub)
    v2 = defense.evaluate(ch, sub)
    return ("passed" if v2.blocked else "HOLE: challenge 可重复使用",
            "challenge 一次性")


def _probe_forged_ticket(defense):
    """伪造票据必须被拒,且不许给出 ok。"""
    fakes = [
        "9999999999-deadbeef-" + "0" * 32,
        "abc-def-ghi",
        "",
        "1-2-3",
        None,
        12345,
    ]
    for tok in fakes:
        try:
            status, _msg = defense.use_ticket(tok)
        except Exception:
            continue                       # 异常也算拒绝(客户端拿到的是失败)
        if status == "ok":
            return (f"HOLE: 伪造票据 {tok!r} 被放行", "伪造票据必须拒绝")
    return ("passed", "伪造票据全部拒绝")


def _probe_ticket_replay(defense):
    """真票用两次:第二次必须被拒(ok 不可能同一张票出现两次)。"""
    for _ in range(50):
        ch = defense.new_challenge()
        sub = _humanish_submission(defense, ch)
        v = defense.evaluate(ch, sub)
        tok = getattr(v, "ticket", None)
        if not tok:
            continue
        st1, _ = defense.use_ticket(tok)
        st2, _ = defense.use_ticket(tok)
        if st2 == "ok":
            return ("HOLE: 同一张票据被消费两次都成功", "票据单次性")
        if st1 != "ok":
            return ("unsupported", f"票据首次消费即 {st1}(可能秒过期),跳过")
        return ("passed", "票据单次性")
    return ("unsupported", "50 次尝试没拿到过票据,跳过")


def _any_submission(defense, ch):
    from .spec import Submission
    return Submission(samples=[[0.0, 0.0, 0.0], [100.0, 0.0, 0.0]])


def _humanish_submission(defense, ch):
    """借场景自己的生成器造一条"像人"的提交,尽量让防线全过拿票。"""
    from .spec import Submission
    build = getattr(defense, "make_human_submission", None)
    if build:
        return build(ch)
    return Submission(samples=[[0.0, 0.0, 0.0], [100.0, 0.0, 0.0]])


PROBES = [
    ("replay_challenge", _probe_replay_challenge),
    ("forged_ticket", _probe_forged_ticket),
    ("ticket_replay", _probe_ticket_replay),
]


def run_protocol_suite(defense):
    """返回 {探针名: 状态}。状态: passed | HOLE:... | unsupported。"""
    out = {}
    if not defense.supports_protocol():
        return {"protocol": "unsupported —— 防线未实现 use_ticket,协议层不计分"}
    defense.reset_session()                        # 探针不继承锦标赛残留的时间域状态
    for name, fn in PROBES:
        defense.reset_session()                    # 探针之间同样互不继承
        try:
            out[name] = fn(defense)
        except Exception as e:                     # 探针自身故障不掩盖防线问题
            out[name] = (f"probe-error: {type(e).__name__}: {e}", "")
    return {k: v if isinstance(v, str) else f"{v[0]} | {v[1]}" if v[1] else v[0]
            for k, v in out.items()}


# ---------------------------------------------------------------- 榜单持久化

def save_report(rep, results_file=RESULTS_FILE_DEFAULT, leaderboard_file=LEADERBOARD_FILE_DEFAULT):
    """把一场锦标赛写进 results/history.jsonl,并刷新 leaderboard.json。

    榜单纪律(2026-10 审查后生效,不再是死代码):
      disqualified(human_solved_rate < 0.5)的防线沉底;
      无人类标本的报告 rankable=False,同样沉底 —— 没有误伤率,
      utility 就没有意义。
    """
    import os
    entry = rep.summary()
    entry["recorded_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    if results_file:
        os.makedirs(os.path.dirname(results_file) or ".", exist_ok=True)
        with open(results_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    if leaderboard_file:
        board = {"updated_at": entry["recorded_at"], "entries": []}
        if os.path.exists(leaderboard_file):
            try:
                with open(leaderboard_file, "r", encoding="utf-8") as f:
                    board = json.load(f)
            except Exception:
                pass
        board["updated_at"] = entry["recorded_at"]
        # 同名防线按名字(不带版本)替代旧条目 —— 版本升级是覆盖,不是并存
        my_name = entry["defense"].split("@")[0]
        entries = [e for e in board.get("entries", [])
                   if e.get("defense", "").split("@")[0] != my_name]
        entries.append({"defense": entry["defense"],
                        "utility": entry["utility"],
                        "catch_rate": entry["catch_rate"],
                        "deep_catch_rate": entry["deep_catch_rate"],
                        "fp_rate": entry["fp_rate"],
                        "human_solved_rate": entry["human_solved_rate"],
                        "rankable": entry["rankable"],
                        "disqualified": entry["disqualified"],
                        "verified_solved": entry["verified_solved"],
                        "solved_mismatches": entry["solved_mismatches"],
                        "corpus": entry["corpus"],
                        "protocol": entry["protocol"],
                        "recorded_at": entry["recorded_at"]})

        def _rank_key(e):
            if not e.get("rankable", True):
                return (2, 0, 0.0)
            if e.get("disqualified"):
                return (1, 0, 0.0)
            return (0, 0, -e["utility"])

        entries.sort(key=_rank_key)
        board["entries"] = entries
        with open(leaderboard_file, "w", encoding="utf-8") as f:
            json.dump(board, f, ensure_ascii=False, indent=2)
    return entry


def new_challenge_id():
    return uuid.uuid4().hex
