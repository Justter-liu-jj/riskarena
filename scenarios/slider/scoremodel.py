# vendored from slider-captcha-lab (原型仓库)@2026-10;除本行与 import 调整外未改动 —— 原理说明见原型 README
"""连续打分模型 —— 风控行为层的"现代形态"。

v2 的规则是二值的(过/不过);商业风控输出的是**连续拟人置信分**
(DMTG 实测 GeeTest 类系统按 1~6 分返回轨迹置信度,见 references.md)。
本模块用纯标准库实现最小可用版:

  特征(13 维):行为 10 维(来自 detector.metrics)+ 环境 3 维(指纹)
  模型:逻辑回归(梯度下降,full-batch,标准化)
  输出:p(human) ∈ [0,1] → 1~6 分;≥4 分视为通过(即 p ≥ 0.5)

⚠️ 循环论证警告(比 v2 的更强):这个模型的训练集**就是我们自己写的生成器**
—— 它"抓得住 sneaky"是因为 sneaky 就在负样本里。它演示的是机制
(连续分、多特征融合、环境信号参与打分),不是可部署的风控模型。
真实部署需要真实人机语料(Herley, USENIX '22 的批评在这里加倍成立)。
"""
import math
import random

from . import detector
from . import fingerprint
from . import generator

# ---------------------------------------------------------------- 特征工程

FEATURE_NAMES = [
    "dur_ratio", "peak_speed_ratio", "straightness", "jitter_rms", "dir_changes",
    "dt_std_ms", "direction_entropy", "log_accel_var", "speed_cv", "log_n_samples",
    "env_webdriver", "env_plugins_zero", "env_ua_inconsistent",
]


def _min_dur(displacement):
    return 0.15 + 0.0003 * displacement


def features(metrics, fp):
    """(detector.metrics, 指纹dict) -> 13 维特征列表。

    环境位的分工:env 层负责"字段缺失/矛盾"的硬拦截;模型只消费 3 个二进制位 ——
    webdriver 非 False(True 或缺失,无法自证非自动化)、plugins==0(桌面 Chrome
    无插件,headless 常态)、UA 与平台矛盾,都记可疑。指纹整体缺失时前两位
    按可疑计 —— "没上报"在模型眼里不等于"清白"。
    """
    fp = fp if isinstance(fp, dict) else {}
    dur_ratio = metrics["duration_s"] / max(_min_dur(metrics["displacement_px"]), 1e-6)

    ua = str(fp.get("ua", ""))
    platform = str(fp.get("platform", ""))
    # 与 fingerprint.check 同一套映射:真实 ChromeOS(UA 含 CrOS)和 iPad
    # (platform=MacIntel + iPad UA)是合法组合,不能当 UA 矛盾误伤
    tokens = {"Win32": ("Windows NT",), "MacIntel": ("Macintosh", "iPad"),
              "Linux x86_64": ("Linux", "CrOS"), "Linux armv8l": ("Android", "Linux")}
    expected = tokens.get(platform)
    ua_bad = 1 if (expected is not None and not any(tok in ua for tok in expected)) else 0

    plugins = fp.get("plugins")
    plugins_zero = 1 if (isinstance(plugins, (int, float)) and not isinstance(plugins, bool)
                         and plugins == 0) else 0

    return [
        min(dur_ratio, 10.0),
        metrics["peak_speed_ratio"],
        metrics["straightness"],
        metrics["jitter_rms_px"],
        float(metrics["dir_changes"]),
        metrics["dt_std_ms"],
        metrics["direction_entropy"],
        math.log1p(max(metrics["accel_var"], 0.0)),
        metrics["speed_cv"],
        math.log1p(metrics["n_samples"]),
        0.0 if fp.get("webdriver") is False else 1.0,   # True 或缺失都记可疑
        float(plugins_zero),
        float(ua_bad),
    ]


# ---------------------------------------------------------------- 逻辑回归

def _sigmoid(z):
    return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, z))))


def _fit(X, y, epochs=250, lr=0.5):
    n, d = len(X), len(X[0])
    mu = [sum(row[j] for row in X) / n for j in range(d)]
    sd = [math.sqrt(sum((row[j] - mu[j]) ** 2 for row in X) / n) or 1.0 for j in range(d)]
    Z = [[(row[j] - mu[j]) / sd[j] for j in range(d)] for row in X]
    w, b = [0.0] * d, 0.0
    for _ in range(epochs):
        gw, gb = [0.0] * d, 0.0
        for row, label in zip(Z, y):
            p = _sigmoid(sum(wj * xj for wj, xj in zip(w, row)) + b)
            g = p - label
            for j in range(d):
                gw[j] += g * row[j]
            gb += g
        w = [wj - lr * gj / n for wj, gj in zip(w, gw)]
        b -= lr * gb / n
    return {"w": w, "b": b, "mu": mu, "sd": sd}


def _p(model, feats):
    z = model["b"] + sum(wj * ((xj - mj) / sj)
                         for wj, xj, mj, sj in zip(model["w"], feats, model["mu"], model["sd"]))
    return _sigmoid(z)


def score_1to6(p):
    return 1 + min(5, int(p * 6))


def explain(model, feats, top=3):
    """按 |贡献| 排序给出模型最关注的特征(教学用)。"""
    contrib = [(abs(wj * (xj - mj) / sj), name, xj)
               for wj, xj, mj, sj, name in
               zip(model["w"], feats, model["mu"], model["sd"], FEATURE_NAMES)]
    contrib.sort(reverse=True)
    return [f"{name}={value:.2f}" for _, name, value in contrib[:top]]


# ---------------------------------------------------------------- 训练集

def _coalesce(pts, frame_ms=16.7):
    """按帧合并事件(浏览器 rAF 对高采样设备的真实行为):每帧只留最后一个点。

    不教这件事的后果(2026-10 审计实测):60Hz 显示器上 touch 原型真人 86%
    被模型判成机器 —— 采样点减半后 log_n_samples / log_accel_var 全部移位。
    """
    out, bucket = [], -1
    for t, x, y in pts:
        b = int(t // frame_ms)
        if b == bucket and out:
            out[-1][0], out[-1][1], out[-1][2] = t, x, y
        else:
            out.append([t, x, y])
            bucket = b
    return out


def _corrupt_fp(fp):
    """造一个'真矛盾'指纹:platform 与 UA 各说各话(伪造者的典型裂缝)。"""
    bad = dict(fp)
    bad["platform"] = "Win32"
    bad["ua"] = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                 "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")
    return bad


def _build_dataset():
    rng = random.Random(2026)                      # 固定种子:每次启动权重一致
    X, y = [], []
    for gen, label, count, mode in [
        (generator.gen_human, 1, 300, "human"),    # 顺利真人
        (generator.gen_human_sloppy, 1, 700, "human"),   # 手残真人(指纹同质量)
        (generator.gen_rookie, 0, 250, "rookie"),  # 教科书脚本(连伪装都不做)
        (generator.gen_sneaky, 0, 250, "sneaky"),  # 10 行 bot(带全套假指纹 → 靠行为抓)
    ]:
        fp = fingerprint.profile_for(mode)
        for _ in range(count):
            gap = rng.randint(200, 576)
            pts = gen(gap, rng.randrange(1 << 30))
            m = detector.analyze(pts, gap_x=gap)["metrics"]
            # 负样本掺 1/4 "平台/UA 互相矛盾"的指纹:让 ua_bad 这一维有训练信号
            # (否则训练集里从无矛盾组合,该特征权重恒为 0 —— 死特征)
            X.append(features(m, _corrupt_fp(fp) if (label == 0 and rng.random() < 0.25) else fp))
            y.append(label)
            # 正样本掺一半 "60Hz 事件合并"变体:真实浏览器对高采样设备就是每帧只给
            # 最后一个点,不教这件事,模型会把 60Hz 的真人当机器
            if label == 1 and rng.random() < 0.5:
                m2 = detector.analyze(_coalesce(pts), gap_x=gap)["metrics"]
                if m2:
                    X.append(features(m2, fp))
                    y.append(1)
    return X, y


def train():
    X, y = _build_dataset()
    model = _fit(X, y)
    acc = sum(1 for row, label in zip(X, y)
              if (_p(model, row) >= 0.5) == (label == 1)) / len(y)
    model["train_acc"] = acc
    return model


MODEL = None


def get_model():
    global MODEL
    if MODEL is None:
        MODEL = train()
    return MODEL


def judge(metrics, fp):
    """(metrics, 指纹) -> {p, score, verdict, explain, is_model}"""
    model = get_model()
    f = features(metrics, fp)
    p = _p(model, f)
    score = score_1to6(p)
    return {"p": round(p, 4), "score": score,
            "is_model": score >= 4,
            "verdict": "人" if score >= 4 else "机器",
            "explain": explain(model, f)}
