"""验尸工具:语料回放被拦时,看看到底是哪层在拦、理由分布如何。

  python tools/debug_verdicts.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from riskarena import corpora
from riskarena.spec import ReplaySpecimen
from scenarios.slider import BUILTIN_SPECIMENS, SliderDefense, fingerprint

CORPUS = os.path.join(os.path.dirname(__file__), "..", "data", "corpus", "converted.jsonl")


def main():
    import random
    human, _ = corpora.load_corpus(CORPUS)
    d = SliderDefense()
    spec = ReplaySpecimen(name="corpus-human", traces=human,
                          fingerprint=fingerprint.profile_for("human"))
    rng = random.Random(2026)

    layer_fail = {}
    reason_count = {}
    scores = []
    n = 300
    blocked = 0
    for _ in range(n):
        ch = d.new_challenge()
        sub = spec.build(ch, rng)
        v = d.evaluate(ch, sub)
        if v.blocked:
            blocked += 1
            for lname, st in (v.layers or {}).items():
                if st.get("ok") is False:
                    layer_fail[lname] = layer_fail.get(lname, 0) + 1
            for r in v.reasons:
                key = f"{r.get('kind', '?')}:{r.get('detector', '?')}|{r.get('note', '?')}"
                key = key[:90]
                reason_count[key] = reason_count.get(key, 0) + 1
        if v.score is not None:
            scores.append(v.score)

    print(f"corpus-human n={n} blocked={blocked} ({blocked/n:.1%})")
    print(f"layer fail counts: {layer_fail}")
    if scores:
        from collections import Counter
        c = Counter(scores)
        print(f"score distribution: {dict(sorted(c.items()))}")
    print("\ntop reasons:")
    for k, cnt in sorted(reason_count.items(), key=lambda kv: -kv[1])[:12]:
        print(f"  {cnt:4d}  {k}")

    # 对照:同样 300 次的合成 human,看分数分布差在哪
    hs = next(s for s in BUILTIN_SPECIMENS if s.name == "human-sim")
    d2 = SliderDefense()
    scores2 = []
    for _ in range(n):
        ch = d2.new_challenge()
        v = d2.evaluate(ch, hs.build(ch, rng))
        if v.score is not None:
            scores2.append(v.score)
    if scores2:
        from collections import Counter
        c2 = Counter(scores2)
        print(f"\nhuman-sim (对照) score distribution: {dict(sorted(c2.items()))}")


if __name__ == "__main__":
    main()
