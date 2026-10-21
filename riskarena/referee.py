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
import json
import random
import time
import uuid

from .metrics import SpecimenReport, TournamentReport

RESULTS_FILE_DEFAULT = "results/history.jsonl"
LEADERBOARD_FILE_DEFAULT = "leaderboard.json"


# ---------------------------------------------------------------- 锦标赛

def run_tournament(defense, specimens, trials=200, seed=2026):
    """跑一遍 防 × 标本 矩阵,返回 TournamentReport。"""
    rng = random.Random(seed)
    rep = TournamentReport(defense=defense.name, defense_version=defense.version,
                           trials_per_specimen=trials, seed=seed)
    for spec in specimens:
        sr = SpecimenReport(name=spec.name, intent=spec.intent, author=spec.author,
                            whitebox=getattr(spec, "whitebox", False))
        layer_ok = {}
        scores = []
        for _ in range(trials):
            defense.reset_session()            # 每试次 = 独立访客(见 spec.reset_session)
            challenge = defense.new_challenge()
            submission = spec.build(challenge, rng)
            verdict = defense.evaluate(challenge, submission)
            sr.n += 1
            if verdict.blocked:
                sr.blocked += 1
            if verdict.solved:
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
    for name, fn in PROBES:
        try:
            out[name] = fn(defense)
        except Exception as e:                     # 探针自身故障不掩盖防线问题
            out[name] = (f"probe-error: {type(e).__name__}: {e}", "")
    return {k: v if isinstance(v, str) else f"{v[0]} | {v[1]}" if v[1] else v[0]
            for k, v in out.items()}


# ---------------------------------------------------------------- 榜单持久化

def save_report(rep, results_file=RESULTS_FILE_DEFAULT, leaderboard_file=LEADERBOARD_FILE_DEFAULT):
    """把一场锦标赛写进 results/history.jsonl,并刷新 leaderboard.json。"""
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
        entries = [e for e in board.get("entries", [])
                   if e.get("defense") != entry["defense"]]
        entries.append({"defense": entry["defense"],
                        "utility": entry["utility"],
                        "catch_rate": entry["catch_rate"],
                        "fp_rate": entry["fp_rate"],
                        "protocol": entry["protocol"],
                        "recorded_at": entry["recorded_at"]})
        entries.sort(key=lambda e: -e["utility"])
        board["entries"] = entries
        with open(leaderboard_file, "w", encoding="utf-8") as f:
            json.dump(board, f, ensure_ascii=False, indent=2)
    return entry


def new_challenge_id():
    return uuid.uuid4().hex
