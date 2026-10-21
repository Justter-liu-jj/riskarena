"""把公开真人滑块轨迹数据集转成 riskarena 语料格式(JSONL)。

当前支持:
  ningning  NingNing0111/slider-track-model(MIT 许可,1053 条真人滑块拖拽)
            格式: {"targetDistance": px, "points": [{"x","y","t"},...]}
            x = 起点为 0 的累计位移, t = 按下起的相对毫秒, ~60Hz 采样
            来源: https://github.com/NingNing0111/slider-track-model

用法:
  python tools/convert_corpus.py --src <ningning目录> --out data/corpus/converted.jsonl

纪律(见 CHARTER.md):
  * 只接入许可明确的公开数据集。无许可证的数据(如 Aruelius/geetest_track)
    默认拒绝接入 —— 想本地实验请自行下载并自担合规责任,本仓库不随附。
  * 转换是纯格式搬运,不改任何数值(不重采样、不平滑、不筛异常)。
    只丢弃无法使用的坏行(点数 < 5 或总位移 < 20px 的死轨迹)并计数。
"""
import argparse
import glob
import json
import os
import sys

SOURCES = {
    "ningning": {
        "glob": "trajectory_dataset-*.json",
        "tool": "ningning-slider-track-model",
        "source_url": "https://github.com/NingNing0111/slider-track-model",
        "license": "MIT",
        "extract": lambda rec: (rec.get("targetDistance"),
                                [[p["t"], p["x"], p["y"]] for p in rec["points"]]),
    },
}


def convert(source, src_dir):
    cfg = SOURCES[source]
    files = sorted(glob.glob(os.path.join(src_dir, cfg["glob"])))
    if not files:
        print(f"[convert] {src_dir} 下没有匹配 {cfg['glob']} 的文件", file=sys.stderr)
        return 2
    out, dropped = [], 0
    for path in files:
        with open(path, "r", encoding="utf-8") as f:
            records = json.load(f)
        for rec in records:
            try:
                dist, pts = cfg["extract"](rec)
                assert isinstance(pts, list) and len(pts) >= 5
                dx = pts[-1][1] - pts[0][1]
                assert dx >= 20                     # 死轨迹回放无意义
                assert all(isinstance(v, (int, float)) for p in pts for v in p)
            except Exception:
                dropped += 1
                continue
            out.append({"label": "human", "tool": cfg["tool"],
                        "source": cfg["source_url"], "license": cfg["license"],
                        "target_distance": dist, "pts": pts})
    return out, dropped, len(files)


def main():
    ap = argparse.ArgumentParser(description="公开轨迹数据集 → riskarena 语料")
    ap.add_argument("--source", choices=sorted(SOURCES), default="ningning")
    ap.add_argument("--src", required=True, help="数据集目录")
    ap.add_argument("--out", default="data/corpus/converted.jsonl")
    args = ap.parse_args()

    result = convert(args.source, args.src)
    if isinstance(result, int):
        return result
    records, dropped, n_files = result
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    prov = os.path.join(os.path.dirname(args.out) or ".", "PROVENANCE.md")
    with open(prov, "w", encoding="utf-8") as f:
        f.write(f"""# 语料来源与处理记录

- 来源: {SOURCES[args.source]["source_url"]}
- 许可: {SOURCES[args.source]["license"]}(随数据集分发,本目录不重复其全文)
- 转换: tools/convert_corpus.py --source {args.source}
- 输入: {n_files} 个文件
- 保留: {len(records)} 条 human 轨迹;丢弃 {dropped} 条(点数<5 或位移<20px 的坏/死轨迹)
- 处理: 纯格式搬运(t,x,y 直拷),不重采样、不平滑、不筛异常值
- 已知告诫: 采集方标注为真人录制但无法逐一核实;y 值近零(采集组件特性),
  与合成生成器的 y 分布不同 —— 这正是防线要面对的真实分布,不做修正。
""")

    print(f"[convert] 写入 {len(records)} 条 -> {args.out}(丢弃 {dropped},来源 {n_files} 文件)")
    print(f"[convert] 溯源记录 -> {prov}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
