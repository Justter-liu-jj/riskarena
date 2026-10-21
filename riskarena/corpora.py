"""语料 —— 防循环论证的第一根支柱。

问题:防线作者与生成器作者若是同一批人,指标就是自嗨(slider-captcha-lab
README 的循环论证警告)。解法分两半:
  1. 人类行为语料 **冻结 + 分版**:来自公开研究数据集(BeCAPTCHA-Mouse 等,
     见 docs/architecture.md 的语料清单),防线只能训练、不能改;
     误伤率(fp_rate)必须在冻结语料 + 合成人类标本两处同时报告。
  2. 回放手术最小化:真实鼠标轨迹不是滑块轨迹,回放时只做**平移**
     (终点对齐缺口),不改时长、速度、抖动 —— 变换越少,自证越少。

语料文件格式(JSONL,一行一条):
  {"label": "human"|"bot", "tool": "<产生器/来源名>", "pts": [[t_ms,x,y],...]}
"""
import json
import os

# 已知公开语料盘点(2026-10 实地核查;接入前必须过 CHARTER 的许可关)
KNOWN_CORPORA = {
    "ningning-slider-track-model": {
        "url": "https://github.com/NingNing0111/slider-track-model",
        "license": "MIT(仓库含 LICENSE 文件)",
        "size": "1053 条真人滑块拖拽,60Hz,拖距 120~270px",
        "caveats": "采集方自述真人,无法逐条核实;y 近零(采集组件特性)",
        "convert": "python tools/convert_corpus.py --source ningning --src <目录>",
    },
    "geetest_track (Aruelius)": {
        "url": "https://github.com/Aruelius/geetest_track",
        "license": "无 —— 默认拒绝接入(见 CHARTER.md 语料纪律)",
        "size": "100 条真人 GeeTest 轨迹,采样较粗",
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
    """读 JSONL 语料 → (human_traces, bot_traces)。坏行跳过并计数。"""
    human, bots, bad = [], [], 0
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                pts = rec["pts"]
                assert isinstance(pts, list) and len(pts) >= 5
            except Exception:
                bad += 1
                continue
            (human if rec.get("label") == "human" else bots).append(pts)
    if bad:
        print(f"  [corpora] {path}: 跳过 {bad} 条坏行")
    return human, bots


def align_translation(pts, gap_x, scale_threshold=0.05):
    """回放手术:让语料轨迹对准挑战缺口,同时尽量少动行为特征。

    规则:
      |dx - gap| <= gap*5%   → 纯平移(不动任何时间/速度/抖动特征)
      否则                   → x 等比缩放到 gap + 平移对齐
                               (时长、y 抖动、节奏原样保留;x 向速度按比例
                               放缩 —— 拖更远本来就该更快,是文献里标准的
                               replay surgery 取舍,如实声明而非藏起来)

    语料拖距域(如 120~270px)与场景缺口域(如 200~576px)不重合时,
    缩放是让真实节奏得以被评估的最小改动的办法;纯平移会让长缺口必失配,
    那是数据域伪影,不是防线性质。
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
    ratio = gap_x / dx
    return [[t, (x - x0) * ratio, y] for t, x, y in pts]


def corpus_available(path):
    return os.path.exists(path) and os.path.getsize(path) > 0
