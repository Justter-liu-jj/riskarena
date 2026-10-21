"""RiskArena CLI。

  python -m riskarena tournament [--trials 200] [--seed 2026] [--corpus PATH]
  python -m riskarena leaderboard
  python -m riskarena specimens

tournament:内置防线 × 内置标本(+ 可选真实语料回放标本)跑矩阵,
            输出每层通过率与效用分,并把结果写入 results/history.jsonl
            和 leaderboard.json。
"""
import argparse
import json
import os
import sys

from . import referee
from .corpora import load_corpus
from .spec import ReplaySpecimen

# 真实语料的默认寻找路径(找到就自动加进误伤组;见 corpora.KNOWN_CORPORA)
CORPUS_SEARCH = [
    os.environ.get("RISKARENA_CORPUS", ""),
    "data/corpus/converted.jsonl",            # in-repo:ningning (MIT),见 PROVENANCE.md
]


def _load_corpus_specimens():
    from scenarios.slider import fingerprint
    for path in CORPUS_SEARCH:
        if path and os.path.exists(path):
            human, bots = load_corpus(path)
            out = []
            if human:
                out.append(ReplaySpecimen(
                    name=f"corpus-human({os.path.basename(path)}, n={len(human)})",
                    traces=human, author="public-corpus",
                    fingerprint=fingerprint.profile_for("human")))
                # 指纹给真人档:语料考察的是行为层,别让"没填指纹"替它挨枪
            if bots:
                out.append(ReplaySpecimen(
                    name=f"corpus-bot({os.path.basename(path)}, n={len(bots)})",
                    traces=bots))
                # 语料里的 bot 也是"别人写的生成器" —— 对防循环论证有独立价值,
                # 但意图标注按语料自己的 label 来
                out[-1].intent = "bot"
            if out:
                print(f"  [corpus] {path}: human={len(human)} bot={len(bots)}")
            return out
    print("  [corpus] 未找到真实语料,只用合成标本(榜单将标注 corpus=synthetic)")
    return []


def cmd_tournament(args):
    from scenarios.slider import BUILTIN_SPECIMENS, SliderDefense

    defense = SliderDefense()
    print(f"defense: {defense.name}@{defense.version}")
    specimens = list(BUILTIN_SPECIMENS) + _load_corpus_specimens()

    print(f"tournament: {len(specimens)} specimens × {args.trials} trials "
          f"(seed={args.seed})\n")
    rep = referee.run_tournament(defense, specimens, trials=args.trials, seed=args.seed)
    rep.protocol = referee.run_protocol_suite(defense)

    s = rep.summary()
    print(f"  {'specimen':34s} {'intent':6s} {'n':>4s} {'blocked':>8s} {'solved':>7s}")
    for sp in s["specimens"]:
        print(f"  {sp['name'][:34]:34s} {sp['intent']:6s} {sp['n']:4d} "
              f"{sp['blocked_rate']:8.1%} {sp['solved_rate']:7.1%}")
    print(f"\n  catch_rate {s['catch_rate']:.1%} · fp_rate {s['fp_rate']:.1%}"
          f" · utility {s['utility']:+.3f} (λ={s['lambda']})")
    print(f"  protocol: {s['protocol']}")

    entry = referee.save_report(rep)
    print(f"\n  recorded -> results/history.jsonl, leaderboard.json "
          f"(utility {entry['utility']:+.3f})")
    return 0


def cmd_leaderboard(args):
    if not os.path.exists("leaderboard.json"):
        print("leaderboard.json 不存在 —— 先跑一次 tournament")
        return 1
    with open("leaderboard.json", "r", encoding="utf-8") as f:
        board = json.load(f)
    print(f"updated: {board.get('updated_at')}\n")
    for i, e in enumerate(board.get("entries", []), 1):
        print(f"  {i}. {e['defense']:24s} utility {e['utility']:+.3f} "
              f"catch {e['catch_rate']:.1%} fp {e['fp_rate']:.1%}  ({e['recorded_at']})")
    return 0


def cmd_specimens(args):
    from scenarios.slider import BUILTIN_SPECIMENS
    print("内置标本(scenarios/slider):")
    for s in BUILTIN_SPECIMENS:
        print(f"  {s.name:12s} intent={s.intent:5s} author={s.author}")
    print("\n贡献你自己的标本见 CONTRIBUTING.md —— 黑盒联赛里权重不公开。")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="riskarena",
                                description="开放的风控攻防竞技场")
    sub = p.add_subparsers(dest="cmd", required=True)

    t = sub.add_parser("tournament", help="跑防 × 标本矩阵")
    t.add_argument("--trials", type=int, default=200)
    t.add_argument("--seed", type=int, default=2026)
    t.set_defaults(fn=cmd_tournament)

    sub.add_parser("leaderboard", help="看当前榜单").set_defaults(fn=cmd_leaderboard)
    sub.add_parser("specimens", help="列出内置标本").set_defaults(fn=cmd_specimens)

    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
