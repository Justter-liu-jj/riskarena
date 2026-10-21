"""验尸工具:某个标本被拦时,看看到底是哪层在拦、理由分布如何。

  python tools/debug_verdicts.py [标本名]      # 默认 corpus-human·1050
                                               # 内置/自动发现标本均可按名查

注意:本工具模拟锦标赛语义 —— 每试次 reset_session(不重置的话,
频控会把机器速度连打当成攻击,给出与榜单矛盾的伪影数字)。
"""
import os
import random
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from riskarena import corpora
from riskarena.__main__ import _load_extra_specimens
from riskarena.spec import ReplaySpecimen
from scenarios.slider import BUILTIN_SPECIMENS, SliderDefense, fingerprint

CORPUS = os.path.join(os.path.dirname(__file__), "..", "data", "corpus", "converted.jsonl")


def _find_specimen(name):
    for s in BUILTIN_SPECIMENS:
        if s.name == name:
            return s
    for s in _load_extra_specimens([]):
        if s.name == name:
            return s
    if name.startswith("corpus"):
        records = [r for r in corpora.load_corpus(CORPUS) if r["label"] == "human"]
        return ReplaySpecimen(name="corpus-human", traces=records,
                              fingerprint=fingerprint.profile_for("human"))
    raise SystemExit(f"没找到标本 {name!r} —— python -m riskarena specimens 看列表")


def autopsy(spec, n=300, seed=2026):
    d = SliderDefense()
    d.seed(seed)
    rng = random.Random(seed)
    layer_fail, reason_count, scores = {}, {}, []
    blocked = 0
    for _ in range(n):
        d.reset_session()                       # 锦标赛语义:每试次独立访客
        ch = d.new_challenge()
        sub = spec.build(ch, rng)
        v = d.evaluate(ch, sub)
        if v.blocked:
            blocked += 1
            for lname, st in (v.layers or {}).items():
                if st.get("ok") is False:
                    layer_fail[lname] = layer_fail.get(lname, 0) + 1
            for r in v.reasons:
                key = f"{r.get('kind', '?')}:{r.get('detector', '?')}|{r.get('note', '?')}"[:90]
                reason_count[key] = reason_count.get(key, 0) + 1
        if v.score is not None:
            scores.append(v.score)

    print(f"{spec.name} (intent={spec.intent}) n={n} blocked={blocked} ({blocked/n:.1%})")
    print(f"layer fail counts: {layer_fail}")
    if scores:
        print(f"score distribution: {dict(sorted(Counter(scores).items()))}")
    if reason_count:
        print("top reasons:")
        for k, cnt in sorted(reason_count.items(), key=lambda kv: -kv[1])[:10]:
            print(f"  {cnt:4d}  {k}")


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else "corpus-human"
    autopsy(_find_specimen(name))


if __name__ == "__main__":
    main()
