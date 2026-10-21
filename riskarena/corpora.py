"""语料 —— 防循环论证的第一根支柱。

问题:防线作者与生成器作者若是同一批人,指标就是自嗨(slider-captcha-lab
README 的循环论证警告)。解法分两半:
  1. 人类行为语料 **冻结 + 分版 + 证据分级**:只收许可明确的公开数据集
     (盘点与许可关见本模块 KNOWN_CORPORA;证据分级与披露纪律见
     CHARTER.md 红线 3 与 data/corpus/PROVENANCE.md),防线只能训练、
     不能改;误伤率(fp_rate)必须在冻结语料 + 合成人类标本两处同时报告。
  2. 回放手术最小化(见 align_translation):位移差小 → 纯平移;
     大 → 靶点锚定的时空等比缩放,保速度剖面与松手误差。

语料文件格式(JSONL,一行一条):
  {"label": "human"|"bot", "tool": "...", "source": "...", "license": "...",
   "target_distance": px, "pts": [[t_ms,x,y],...]}
  label 必须精确是 "human"/"bot",不合法的行跳过并告警(load_corpus)。
"""
import json
import os

# 已知公开语料盘点(2026-10 实地核查;接入前必须过 CHARTER 的许可关)
KNOWN_CORPORA = {
    "ningning-slider-track-model": {
        "url": "https://github.com/NingNing0111/slider-track-model",
        "license": "MIT(全文随附于 data/corpus/LICENSE-ningning.txt)",
        "size": "1050 条滑块拖拽(purported-human),60Hz,拖距 120~270px",
        "caveats": "证据等级 purported-human:上游是 WGAN-GP 轨迹生成器项目"
                   "(自述含通过滑块行为检测的目标),本语料是其真人采集"
                   "训练集;'真人'标注不可核实,采集无知情同意记录;"
                   "y 近零(采集组件特性)。完整披露见 data/corpus/PROVENANCE.md",
        "convert": "python tools/convert_corpus.py --source ningning --src <目录>",
    },
    "geetest_track (Aruelius)": {
        "url": "https://github.com/Aruelius/geetest_track",
        "license": "无 —— 默认拒绝接入(见 CHARTER.md 语料纪律)",
        "size": "100 条 GeeTest 轨迹,采样较粗",
    },
    "Searles USENIX Sec'23 (captcha-study)": {
        "url": "https://github.com/sprout-uci/captcha-study",
        "license": "无 LICENSE 文件(论文脚注:匿名化发布以利复现)",
        "size": "1000 名参与者的解题时长/人口学 —— 无轨迹,仅作时长参照",
    },
    "BeCAPTCHA-Mouse": {
        "url": "https://github.com/BiDAlab/BeCAPTCHA-Mouse",
        "license": "需邮件签署 EMA 才能取基准数据,且其公开部分为合成数据",
        "size": "未接入",
    },
}


def load_corpus(path):
    """读 JSONL 语料 → 记录列表 [{"label","pts","target_distance",...}]。

    标签必须精确是 "human" 或 "bot" —— 缺失/大小写不符的行**跳过并告警**,
    绝不静默归入某个桶(2026-10 设计审查:静默归类会让真人轨迹无声变成
    corpus-bot,评测对象被换掉且无告警)。
    """
    records, bad = [], 0
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                pts = rec["pts"]
                assert isinstance(pts, list) and len(pts) >= 5
                assert rec.get("label") in ("human", "bot"), f"bad label {rec.get('label')!r}"
            except Exception:
                bad += 1
                continue
            records.append(rec)
    if bad:
        print(f"  [corpora] {path}: 跳过 {bad} 条坏行/标签不合法行")
    return records


def align_translation(pts, gap_x, target_distance=None, scale_threshold=0.05):
    """回放手术:让语料轨迹对准挑战缺口,同时尽量少动行为特征。

    两级手术(诚实优先级从高到低):
      1. |dx - gap| <= gap*5% → 纯平移,什么都不改。
      2. 否则 → **时空等比缩放**:x 与 t 同乘 r = gap/(target_distance 或 dx)。
         同时缩放空间与时间轴,保住速度剖面/节奏比值/y 抖动 —— 只拉长
         绝对时长。2026-10 审查推翻了此前的"只缩 x"方案:等时长放大
         距离会把速度 ×r、加速度 ×r²,快拖轨迹会掉进训练分布的机器侧,
         制造假误伤。
         锚点用 target_distance(原挑战靶点)而非终点:终点误差(松手
         没对准)按比例保留,solved 不再被手术钉成 True —— 语料真实的
         失手率才参与了"重试 vs 误伤"的区分。

    变换在 ReplaySpecimen 的 docstring 与榜单 corpus 字段里如实声明。
    """
    if not pts or gap_x is None:
        return pts
    x0 = pts[0][1]
    dx = pts[-1][1] - x0
    if dx <= 0:
        return pts                              # 无法对齐的死轨迹,原样交防线处理
    if abs(dx - gap_x) <= gap_x * scale_threshold:
        shift = gap_x - pts[-1][1]
        return [[t, x + shift, y] for t, x, y in pts]
    anchor = target_distance if (target_distance and 0 < target_distance <= dx + gap_x) else dx
    if anchor <= 0:
        return pts
    r = gap_x / anchor
    return [[t * r, (x - x0) * r, y] for t, x, y in pts]


def corpus_available(path):
    return os.path.exists(path) and os.path.getsize(path) > 0
