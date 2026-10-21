# vendored from slider-captcha-lab (原型仓库)@2026-10;除本行与 import 调整外未改动 —— 原理说明见原型 README
"""滑块轨迹检测器 v2 —— 双 profile 对照实验。

  profile="v1" : 网上教程式 7 项固定阈值。设计初衷是"机器太完美、人有误差",
                 但按本靶场人类模型的仿真(见 selftest)它把大量【真人】判成
                 机器人 —— 因为它把"熟练/精准/干净"全当成了机器特征,方向反了。
  profile="v2" : 尺度化最小规则集:
                 - duration_scaled : 时长下限随距离缩放(Fitts 定律的线性替身)
                 - peak_speed_ratio: 峰值/均速 ≥1.4 —— 人手是钟形速度曲线,
                     匀速直线插值不是(这是 v1 accel_var 想抓而没抓到的)
                 其余指标全部降级为 info 仅记录:它们要么测的是设备/传输层
                 (dt_std、量化),要么惩罚精准(jitter、直线度、方向熵),
                 固定阈值必然切进真人分布(设计 agent 对本靶场模型的仿真
                 误伤 50-95%)。
                 注意:v2 也会切进自家 flick 原型(甩得快的人)—— 没有真实
                 语料之前,任何阈值都是在猜。这不是可部署的风控,是最小教学集。

一条轨迹 = [[t, x, y], ...] 采样点,t 为毫秒时间戳,x/y 为指针坐标。
solved(完成拼图)与 is_human(行为判定)分开:真人失手=重试,≠机器人。
"""
import math
import statistics

TH_V1 = {
    "min_duration_s": 0.35,
    "straightness_max": 0.995,
    "jitter_rms_min": 0.25,
    "min_dir_changes": 3,
    "accel_var_min": 0.05,
    "dt_std_min_ms": 0.6,
    "direction_entropy_min": 0.15,
}


def _dist(a, b):
    return math.hypot(b[0] - a[0], b[1] - a[1])


def analyze(samples, gap_x=None, tolerance=6, profile="v2"):
    """返回 {pass, solved, is_human, score, reasons, metrics, info}。"""
    out = {"pass": False, "solved": None, "is_human": False, "profile": profile,
           "score": 0, "reasons": [], "metrics": {}, "info": {}}

    def _finite(v):
        return (isinstance(v, (int, float)) and not isinstance(v, bool)
                and math.isfinite(v))

    if not isinstance(samples, (list, tuple)):
        samples = []
    samples = [s for s in samples if isinstance(s, (list, tuple)) and len(s) >= 3
               and all(_finite(v) for v in s[:3])]
    if len(samples) < 5:
        out["reasons"].append({"detector": "samples", "ok": False, "kind": "meta",
                               "note": f"采样点太少或含非法值({len(samples)}),连轨迹都算不上"})
        return out

    ts = [float(s[0]) for s in samples]
    xs = [float(s[1]) for s in samples]
    ys = [float(s[2]) for s in samples]

    if any(ts[i + 1] < ts[i] for i in range(len(ts) - 1)):
        out["reasons"].append({"detector": "malformed", "ok": False, "kind": "meta",
                               "note": "时间戳倒退 —— 畸形轨迹,直接拒绝"})
        return out

    duration_s = (ts[-1] - ts[0]) / 1000.0
    segs = [_dist((xs[i], ys[i]), (xs[i + 1], ys[i + 1])) for i in range(len(xs) - 1)]
    path_len = sum(segs)
    displacement = _dist((xs[0], ys[0]), (xs[-1], ys[-1]))
    straightness = displacement / path_len if path_len > 1e-9 else 1.0

    dxt, dyt = xs[-1] - xs[0], ys[-1] - ys[0]
    norm = math.hypot(dxt, dyt) or 1.0
    ux, uy = dxt / norm, dyt / norm
    perps = [abs((x - xs[0]) * uy - (y - ys[0]) * ux) for x, y in zip(xs, ys)]
    jitter_rms = math.sqrt(sum(p * p for p in perps) / len(perps))

    dts = [max(ts[i + 1] - ts[i], 1.0) for i in range(len(ts) - 1)]
    speeds = [segs[i] / dts[i] * 1000.0 for i in range(len(segs))]          # px/s
    accels = [(speeds[i + 1] - speeds[i]) / dts[i + 1] * 1000.0
              for i in range(len(speeds) - 1)]                              # px/s²
    accel_var = statistics.pvariance(accels) if len(accels) > 2 else 0.0
    mean_speed = sum(speeds) / len(speeds) if speeds else 0.0
    peak_ratio = (max(speeds) / mean_speed) if mean_speed > 1e-9 else 0.0
    speed_cv = (statistics.pstdev(speeds) / mean_speed) if mean_speed > 1e-9 else 0.0

    signs = []
    for i in range(len(xs) - 1):
        d = xs[i + 1] - xs[i]
        if abs(d) > 0.05:
            signs.append(1 if d > 0 else -1)
    dir_changes = sum(1 for i in range(1, len(signs)) if signs[i] != signs[i - 1])
    dt_std_ms = statistics.pstdev(dts) if len(dts) > 1 else 0.0

    bins = [0] * 8
    for i in range(len(xs) - 1):
        if segs[i] < 0.3:
            continue
        ang = math.atan2(ys[i + 1] - ys[i], xs[i + 1] - xs[i]) % math.pi
        bins[min(int(ang / (math.pi / 8)), 7)] += 1
    total = sum(bins)
    entropy = (-sum((b / total) * math.log(b / total, 2) for b in bins if b)
               / math.log(8, 2)) if total else 0.0

    out["metrics"] = {
        "n_samples": len(samples), "duration_s": round(duration_s, 3),
        "displacement_px": round(displacement, 1),
        "straightness": round(straightness, 4), "jitter_rms_px": round(jitter_rms, 3),
        "dir_changes": dir_changes, "accel_var": round(accel_var, 1),
        "dt_std_ms": round(dt_std_ms, 2), "direction_entropy": round(entropy, 3),
        "mean_speed": round(mean_speed, 1), "max_speed": round(max(speeds), 1),
        "peak_speed_ratio": round(peak_ratio, 2), "speed_cv": round(speed_cv, 3),
    }

    endpoint_ok = True
    if gap_x is not None:
        err = abs(xs[-1] - gap_x)
        out["info"]["endpoint_error_px"] = round(err, 2)
        out["info"]["overshoot_px"] = round(max(0.0, max(xs) - gap_x - tolerance), 2)
        endpoint_ok = err <= tolerance
        out["solved"] = endpoint_ok
        out["reasons"].append({"detector": "position", "ok": endpoint_ok,
                               "kind": "position", "value": round(err, 2),
                               "note": (f"终点误差 {err:.1f}px(容差 ±{tolerance}px)"
                                        if endpoint_ok else
                                        f"终点误差 {err:.1f}px 超出 ±{tolerance}px —— 没对准,重试即可")})

    if profile == "v1":
        checks = [
            ("duration", duration_s >= TH_V1["min_duration_s"],
             f"总时长 {duration_s:.2f}s(固定下限 {TH_V1['min_duration_s']}s)",
             "太快——但你砍的是老手的一记甩动"),
            ("straightness", straightness <= TH_V1["straightness_max"],
             f"路径直线度 {straightness:.4f}(阈值 ≤{TH_V1['straightness_max']})",
             "太直——可轨迹贴着水平导轨本来就近乎直线"),
            ("jitter_rms", jitter_rms >= TH_V1["jitter_rms_min"],
             f"垂直微颤 {jitter_rms:.2f}px(阈值 ≥{TH_V1['jitter_rms_min']})",
             "没抖——触屏/笔/稳的手本来就没多少抖动"),
            ("dir_changes", dir_changes >= TH_V1["min_dir_changes"],
             f"水平微回调 {dir_changes} 次(阈值 ≥{TH_V1['min_dir_changes']})",
             "没回调——真人有意回调的众数是 0~2 次"),
            ("accel_var", accel_var >= TH_V1["accel_var_min"],
             f"加速度方差 {accel_var:.1f}(阈值 ≥{TH_V1['accel_var_min']})",
             "速度太匀——注意真人实测是 10⁶~10⁹,这阈值形同虚设"),
            ("dt_std", dt_std_ms >= TH_V1["dt_std_min_ms"],
             f"采样间隔σ {dt_std_ms:.2f}ms(阈值 ≥{TH_V1['dt_std_min_ms']}ms)",
             "采样太齐——但 rAF 合流/125Hz USB 鼠标本来就齐"),
            ("entropy", entropy >= TH_V1["direction_entropy_min"],
             f"方向熵 {entropy:.2f}(阈值 ≥{TH_V1['direction_entropy_min']})",
             "方向单一——水平导轨任务上这指标没有判别力"),
        ]
    else:
        min_dur = 0.15 + 0.0003 * displacement        # 随距离缩放(Fitts)
        checks = [
            ("duration_scaled", min_dur <= duration_s <= 20,
             f"总时长 {duration_s:.2f}s(距离缩放下限 {min_dur:.2f}s)",
             "快到超出人类反应+运动极限"),
            ("peak_speed_ratio", peak_ratio >= 1.4,
             f"峰值/均速 {peak_ratio:.2f}(阈值 ≥1.4)",
             "匀速直线插值——人手是钟形速度曲线,峰值≈均速的 1.9 倍"),
        ]

    for name, ok, value, hint in checks:
        out["reasons"].append({"detector": name, "ok": ok, "kind": "behavior",
                               "value": value,
                               "note": value if ok else f"{value} → {hint}"})

    if profile == "v2":   # 旧 7 项降级为 info:仅记录,不参与判定
        info_rows = [
            ("straightness", straightness <= TH_V1["straightness_max"],
             f"直线度 {straightness:.4f}", "惩罚精准,无判别力"),
            ("jitter_rms", jitter_rms >= TH_V1["jitter_rms_min"],
             f"微颤 {jitter_rms:.2f}px", "惩罚稳的手/触屏"),
            ("dir_changes", dir_changes >= TH_V1["min_dir_changes"],
             f"微回调 {dir_changes} 次", "真人众数 0~2 次"),
            ("dt_std", dt_std_ms >= TH_V1["dt_std_min_ms"],
             f"采样σ {dt_std_ms:.2f}ms", "传输层属性,不是行为"),
            ("direction_entropy", entropy >= TH_V1["direction_entropy_min"],
             f"方向熵 {entropy:.2f}", "导轨任务上度量的是坐标噪声"),
            ("accel_var", accel_var >= TH_V1["accel_var_min"],
             f"加速度方差 {accel_var:.1f}", "尺度失准(真人 10⁶~10⁹)"),
        ]
        for name, ok, value, comment in info_rows:
            out["reasons"].append({"detector": name, "kind": "info",
                                   "value": value, "note": f"{value}(info:{comment})"})

    scored = [r for r in out["reasons"] if r.get("ok") is not None]
    ok_count = sum(1 for r in scored if r["ok"])
    out["score"] = int(100 * ok_count / max(len(scored), 1))
    behavior = [r for r in out["reasons"] if r.get("kind") == "behavior"]
    out["is_human"] = all(r["ok"] for r in behavior)
    out["pass"] = out["solved"] is True and out["is_human"]
    return out
