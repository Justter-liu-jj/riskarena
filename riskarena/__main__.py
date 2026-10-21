"""RiskArena CLI。

  python -m riskarena tournament [--trials 200] [--seed 2026] [--corpus PATH]
                                 [--specimen 路径或模块:类]...
  python -m riskarena leaderboard
  python -m riskarena specimens

tournament:内置防线 × 标本跑矩阵,输出每层通过率与效用分,并写入
            results/history.jsonl 和 leaderboard.json。

标本注册(2026-10 冷启动修复:按文档走必须能跑通):
  * 仓库根的 specimens/*.py 自动发现加载(本地试验放这里即可);
  * 或 --specimen 显式指定:文件路径、模块路径、"模块:类名" 均可,
    可重复传多个;
  * RISKARENA_CORPUS 环境变量可覆盖语料 JSONL 的寻找路径。
"""
import argparse
import glob
import importlib.util
import json
import os
import sys

from . import referee
from .corpora import load_corpus
from .spec import ReplaySpecimen, Specimen

# 真实语料的默认寻找路径(找到就自动加进误伤组;见 corpora.KNOWN_CORPORA)
CORPUS_SEARCH = [
    os.environ.get("RISKARENA_CORPUS", ""),
    "data/corpus/converted.jsonl",            # in-repo:ningning (MIT),见 PROVENANCE.md
]

SPECIMENS_DIR = "specimens"


def _load_class(path_or_target):
    """'文件.py' / 'pkg.mod' / 'pkg.mod:Class' → Specimen 实例。"""
    target = path_or_target
    cls_name = None
    if ":" in target:
        target, cls_name = target.rsplit(":", 1)
    if target.endswith(".py") and os.path.exists(target):
        name = os.path.splitext(os.path.basename(target))[0]
        spec = importlib.util.spec_from_file_location(f"user_specimen_{name}", target)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    else:
        mod = importlib.import_module(target)
    obj = getattr(mod, cls_name) if cls_name else None
    if obj is None:
        classes = [v for v in vars(mod).values()
                   if isinstance(v, type) and issubclass(v, Specimen)
                   and v is not Specimen and v is not ReplaySpecimen]
        if len(classes) != 1:
            raise SystemExit(f"[specimen] {target} 里没有(或有多于一个)Specimen 类,"
                             f"请用 '路径:类名' 消歧")
        obj = classes[0]
    inst = obj()
    if not isinstance(inst, Specimen):
        raise SystemExit(f"[specimen] {target}:{cls_name} 不是 Specimen 子类")
    return inst


def _load_extra_specimens(flags):
    """--specimen 显式项 + specimens/*.py 自动发现(仓库不存在该目录则跳过)。"""
    out = []
    for t in flags or []:
        s = _load_class(t)
        print(f"  [specimen] 显式加载: {s.name} (intent={s.intent})")
        out.append(s)
    if os.path.isdir(SPECIMENS_DIR):
        for path in sorted(glob.glob(os.path.join(SPECIMENS_DIR, "*.py"))):
            try:
                s = _load_class(path)
            except SystemExit as e:
                print(f"  [specimen] {path}: {e}")
                continue
            if any(s.name == getattr(x, "name", None) for x in out):
                continue
            print(f"  [specimen] 自动发现: {path} -> {s.name} (intent={s.intent})")
            out.append(s)
    return out


def _load_corpus_specimens(path_override=None):
    from scenarios.slider import fingerprint
    paths = ([path_override] if path_override else CORPUS_SEARCH)
    for path in paths:
        if path and os.path.exists(path):
            records = load_corpus(path)
            human = [r for r in records if r["label"] == "human"]
            bots = [r for r in records if r["label"] == "bot"]
            out = []
            if human:
                out.append(ReplaySpecimen(
                    name=f"corpus-human·{len(human)}",
                    traces=human, author="public-corpus",
                    fingerprint=fingerprint.profile_for("human")))
                # 指纹给真人档:语料考察的是行为层,别让"没填指纹"替它挨枪
            if bots:
                out.append(ReplaySpecimen(
                    name=f"corpus-bot·{len(bots)}", traces=bots))
                out[-1].intent = "bot"
            if out:
                print(f"  [corpus] {path}: human={len(human)} bot={len(bots)}")
            return out
    print("  [corpus] 未找到真实语料,只用合成标本(榜单将标注 corpus=synthetic-only)")
    return []


def cmd_tournament(args):
    from scenarios.slider import BUILTIN_SPECIMENS, SliderDefense

    defense = SliderDefense()
    print(f"defense: {defense.name}@{defense.version}")
    specimens = (list(BUILTIN_SPECIMENS) + _load_extra_specimens(args.specimen)
                 + _load_corpus_specimens(args.corpus))

    print(f"tournament: {len(specimens)} specimens × {args.trials} trials "
          f"(seed={args.seed})\n")
    rep = referee.run_tournament(defense, specimens, trials=args.trials, seed=args.seed)
    rep.protocol = referee.run_protocol_suite(defense)

    s = rep.summary()
    print(f"  {'specimen':36s} {'intent':6s} {'n':>4s} {'blocked':>8s} {'solved':>7s}"
          f"  layers(通过率)")
    for sp in s["specimens"]:
        layers = " · ".join(f"{k} {v:.0%}" for k, v in sp["layer_pass"].items())
        print(f"  {sp['name'][:36]:36s} {sp['intent']:6s} {sp['n']:4d} "
              f"{sp['blocked_rate']:8.1%} {sp['solved_rate']:7.1%}  {layers}")
    print(f"\n  verified_solved {s['verified_solved']}"
          f"(solved_mismatches {s['solved_mismatches']})"
          f" · rankable {s['rankable']} · disqualified {s['disqualified']}")
    print(f"  catch {s['catch_rate']:.1%} · deep_catch {s['deep_catch_rate']:.1%}"
          f" · fp {s['fp_rate']:.1%} · utility {s['utility']:+.3f} (λ={s['lambda']})")
    print(f"  protocol: {s['protocol']}")

    entry = referee.save_report(rep)
    flag = "" if entry["rankable"] and not entry["disqualified"] else \
        "  [unranked: " + ("无人类标本" if not entry["rankable"] else "human_solved_rate < 0.5") + "]"
    print(f"\n  recorded -> results/history.jsonl, leaderboard.json "
          f"(utility {entry['utility']:+.3f}){flag}")
    return 0


def cmd_leaderboard(args):
    if not os.path.exists("leaderboard.json"):
        print("leaderboard.json 不存在 —— 先跑一次 tournament")
        return 1
    with open("leaderboard.json", "r", encoding="utf-8") as f:
        board = json.load(f)
    print(f"updated: {board.get('updated_at')}\n")
    for i, e in enumerate(board.get("entries", []), 1):
        flag = ""
        if not e.get("rankable", True):
            flag = "  [unranked: 无人类标本]"
        elif e.get("disqualified"):
            flag = "  [DISQUALIFIED: human_solved_rate < 0.5]"
        print(f"  {i}. {e['defense']:24s} utility {e['utility']:+.3f} "
              f"catch {e['catch_rate']:.1%} deep {e['deep_catch_rate']:.1%} "
              f"fp {e['fp_rate']:.1%}  ({e['recorded_at']}){flag}")
    return 0


def cmd_specimens(args):
    from scenarios.slider import BUILTIN_SPECIMENS
    print("内置标本(scenarios/slider):")
    for s in BUILTIN_SPECIMENS:
        wb = " whitebox" if getattr(s, "whitebox", False) else ""
        print(f"  {s.name:16s} intent={s.intent:5s} author={s.author}{wb}")
    if os.path.isdir(SPECIMENS_DIR):
        extra = _load_extra_specimens([])
        if extra:
            print("\n本地 specimens/ 自动发现(进入 tournament,不入榜单发布):")
            for s in extra:
                print(f"  {s.name:16s} intent={s.intent:5s} author={s.author}")
    print("\n贡献你自己的标本见 CONTRIBUTING.md —— 黑盒联赛里权重不公开。")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="riskarena",
                                description="开放的风控攻防竞技场")
    sub = p.add_subparsers(dest="cmd", required=True)

    t = sub.add_parser("tournament", help="跑防 × 标本矩阵")
    t.add_argument("--trials", type=int, default=200)
    t.add_argument("--seed", type=int, default=2026)
    t.add_argument("--corpus", default=None,
                   help="语料 JSONL 路径(覆盖默认寻找顺序)")
    t.add_argument("--specimen", action="append", default=[],
                   metavar="路径或模块:类",
                   help="加载自定义标本,可重复")
    t.set_defaults(fn=cmd_tournament)

    sub.add_parser("leaderboard", help="看当前榜单").set_defaults(fn=cmd_leaderboard)
    sub.add_parser("specimens", help="列出内置标本").set_defaults(fn=cmd_specimens)

    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
