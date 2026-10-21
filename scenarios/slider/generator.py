# vendored from slider-captcha-lab (原型仓库)@2026-10;除本行与 import 调整外未改动 —— 原理说明见原型 README
"""轨迹生成器:v2 —— 按运动控制与真实事件流特性重写。

关键修正(相对 v1 的理想化建模):
  1. 速度曲线用 min-jerk(10u³-15u⁴+6u⁵ 钟形),不是 smoothstep —— 这是指向运动
     的实证标准形态;真人"一次顺利拖动"就是 1 个主 submovement + 终点微调
  2. 真人轨迹噪声很小(σ 0.1~0.4px,鼠标上报的多是量化后的真实位置),
     常被整数像素量化;弓形弧 ≤14px
  3. 停顿 = 时间空洞(浏览器在鼠标静止时不发任何事件),不是插入点
  4. 事件流有掉帧/突发伪影(rAF 合流 + OS 调度),不是节拍器;相邻事件
     间隔不会低于 ~4ms —— 没有浏览器会上报亚毫秒级 pointermove
  5. 真人水平方向的有意回调众数是 0~2 次 —— "微回调多"不是人性特征
  6. 终点误差是混合分布:仔细修正主体 σ≈2px + 快速松手尾部 ±7~20px

  rookie : 匀速直线 + 固定 16ms 采样 —— 教程第一版脚本
  human  : 典型用户的一次顺利拖动(会被 v2 阈值放过)
  pro    : 对抗校准 —— v1/v2 两套规则都过(教学:规则挡不住知情的对抗)
  sloppy : 真人误差全景(7 类原型混合,暴露固定阈值的误伤率)
  sneaky : 10 行零噪声 min-jerk bot —— 过 v2 规则,留给 v3 模型层抓
"""
import math
import random

X0 = 10.0  # 滑块起始位置


def gen_rookie(gap_x, seed=None):
    """匀速直线脚本:教科书式反例。"""
    pts = [[0.0, X0, 0.0]]
    t, x = 0.0, X0
    while x < gap_x:
        t += 16.0
        x = min(x + 12.0, float(gap_x))
        pts.append([t, x, 0.0])
    return pts


def _minjerk(u):
    """min-jerk 位置曲线:速度钟形,加速度在两端为零(指向运动实证形态)。"""
    return 10 * u ** 3 - 15 * u ** 4 + 6 * u ** 5


def _stream(rng, duration_ms):
    """模拟浏览器 pointer 事件流:三种体制随机抽取(每条拖动一种)。

    50% rAF 合流(16.7ms,σ 0.3~1.5)/ 35% USB 125Hz(8ms)/ 15% 加卡顿间隙。
    事件流的时间结构由外设与浏览器决定,不由"努力像人"决定。
    """
    regime = rng.random()
    if regime < 0.50:
        base, sd = 16.7, rng.uniform(0.3, 1.5)     # rAF 合流
    else:
        base, sd = 8.0, rng.uniform(0.4, 1.5)      # USB 125Hz 轮询
    stutter = regime >= 0.85
    ts = [0.0]
    while ts[-1] < duration_ms:
        r = rng.random()
        if stutter and r < 0.06:
            dt = rng.uniform(25, 60)               # 系统卡顿间隙
        elif r < 0.08:
            dt = rng.uniform(4, 12)                # 事件突发(背靠背合流帧)
        else:
            dt = rng.gauss(base, sd)
        ts.append(ts[-1] + max(4.0, dt))           # 事件间隔物理下限 ~4ms(250Hz 外设)
    if ts[-1] > duration_ms:
        ts[-1] = duration_ms
    return ts


def _tremor(rng):
    """8~12Hz 生理性震颤参数:返回 (幅度px, 角频率rad/ms, 相位)。时间相关,非 iid。"""
    amp = rng.uniform(0.2, 1.0)
    omega = 2 * math.pi * rng.uniform(8, 12) / 1000.0
    phase = rng.uniform(0, 2 * math.pi)
    return amp, omega, phase


def _wander(rng, n, sigma, clip):
    """垂直整体漂移:积分随机游走(手腕/手肘轴心滑动)。"""
    ys, y = [], 0.0
    for _ in range(n):
        y = max(-clip, min(clip, y + rng.gauss(0, sigma)))
        ys.append(y)
    return ys


def _quantize(pts, rng, p=0.45):
    """整数像素量化:多数桌面浏览器 mousemove 上报整数坐标。"""
    if rng.random() < p:
        for pt in pts:
            pt[1] = float(round(pt[1]))
            pt[2] = float(round(pt[2]))
    return pts


def _monotonic(pts, min_dt=0.5):
    for j in range(1, len(pts)):
        if pts[j][0] <= pts[j - 1][0]:
            pts[j][0] = pts[j - 1][0] + min_dt
    return pts


def _time_hole(pts, rng, lo, hi, p):
    """在时间轴上挖一个洞:静止时不发事件,这才是真实停顿的形状。"""
    if rng.random() < p and len(pts) > 10:
        k = rng.randint(len(pts) // 4, 3 * len(pts) // 4)
        hole = rng.uniform(lo, hi)
        for j in range(k, len(pts)):
            pts[j][0] += hole
    return pts


def gen_human(gap_x, seed=None):
    """典型用户的一次顺利拖动:min-jerk + 弓形 + 终点微调,误差很小。"""
    rng = random.Random(seed)
    D = float(gap_x) - X0
    start_delay = rng.uniform(80, 300)                       # 按下→首动的反应时
    duration = (250 + 1.1 * D) * rng.uniform(0.7, 1.5)       # 个体速度人格 0.7~1.5
    ts = _stream(rng, duration)

    arc = rng.uniform(-14, 14)                               # 弓形弧(70% 向上)
    sigma = rng.uniform(0.1, 0.4)                            # 手颤很小(量化前的传感器噪声)
    trem_amp, trem_w, trem_p = _tremor(rng)
    drift = _wander(rng, len(ts), 0.15, 4)
    overshoot = rng.random() < 0.3
    over = rng.uniform(3, 12) if overshoot else 0.0

    pts = []
    for i, t in enumerate(ts):
        u = min(t / duration, 1.0)
        pts.append([t + start_delay,
                    X0 + (D + over) * _minjerk(u) + rng.gauss(0, sigma)
                        + 0.3 * trem_amp * math.sin(trem_w * t + trem_p),
                    arc * math.sin(u * math.pi) + drift[i] + rng.gauss(0, sigma)
                        + trem_amp * math.sin(trem_w * t + trem_p * 1.3)])

    if overshoot:                                            # 小超调 + 1~2 步修正
        for s in range(rng.randint(1, 2), 0, -1):
            f = (s - 1) / 2
            pts.append([pts[-1][0] + rng.uniform(40, 150),
                        X0 + D + over * f + rng.gauss(0, 0.5),
                        pts[-1][2] + rng.gauss(0, sigma)])

    # 终点微调:到位后 ±1~3px dither 数步,等视觉确认再松手
    dither = rng.randint(2, 6)
    for k in range(dither):
        f = (k + 1) / dither
        pts.append([pts[-1][0] + rng.uniform(25, 90),
                    gap_x + rng.gauss(0, 1.5) * (1 - f),
                    pts[-1][2] + rng.gauss(0, sigma)])
    pts[-1][1] = gap_x + rng.gauss(0, 1.8)                   # 仔细修正主体 σ≈2px

    _time_hole(pts, rng, 100, 400, 0.2)                      # 中途小停顿
    return _quantize(_monotonic(pts), rng)


def gen_pro(gap_x, seed=None):
    """对抗校准版:知道两套规则,逐项达标 —— 演示"规则挡不住知情的对抗"。"""
    rng = random.Random(seed)
    pts = gen_human(gap_x, rng.randrange(1 << 30))

    # v1 duration ≥0.35s:短缺口时放慢
    total = pts[-1][0] - pts[0][0]
    if total < 450:
        f = rng.uniform(1.3, 1.8)
        for p in pts:
            p[0] *= f

    # v1 方向变化 ≥3:注入 3 次真正的反向(真人没有,但规则要)。
    # 时间必须落在相邻两点之间,否则会造出时间戳倒退 → 0.5ms 微簇 → 假速度尖峰
    for _ in range(3):
        i = rng.randint(5, len(pts) - 6)
        t_mid = (pts[i - 1][0] + pts[i][0]) / 2.0
        pts.insert(i, [t_mid,
                       pts[i - 1][1] - rng.uniform(1.0, 2.5),
                       pts[i][2] + rng.gauss(0, 0.4)])

    # v1 抖动/直线度:叠加噪声直到 RMS 达标
    dxt, dyt = pts[-1][1] - pts[0][1], pts[-1][2] - pts[0][2]
    norm = math.hypot(dxt, dyt) or 1.0
    ux, uy = dxt / norm, dyt / norm
    perps = [abs((x - pts[0][1]) * uy - (y - pts[0][2]) * ux) for _, x, y in pts]
    rms = math.sqrt(sum(p * p for p in perps) / len(perps))
    while rms < 0.6:
        for p in pts:
            p[2] += rng.gauss(0, 0.3)
        perps = [abs((x - pts[0][1]) * uy - (y - pts[0][2]) * ux) for _, x, y in pts]
        rms = math.sqrt(sum(p * p for p in perps) / len(perps))

    pts[-1][1] = float(gap_x) + rng.gauss(0, 1.0)            # 终点校准进容差
    return _monotonic(pts)


def gen_sneaky(gap_x, seed=None):
    """10 行零噪声 min-jerk bot:v3 新对手。

    它精确踩着 v2 的两条规则走 —— min-jerk 速度曲线(peak_ratio≈1.875>1.4)、
    Fitts 节奏的时长(过 duration_scaled)—— 所以 v2 规则层放它过去。
    抓它的是 v3 的连续模型层:零抖动、零回调、完美直线这些统计特征,
    在 13 维特征空间里离真人聚类十万八千里。这就是"规则→模型"升级的理由。
    """
    D = float(gap_x) - X0
    duration = 250.0 + 1.1 * D                       # 学人类的时长节奏
    pts = []
    for i in range(37):
        t = duration * i / 36
        pts.append([t, X0 + D * _minjerk(i / 36), 0.0])
    pts[-1][1] = float(gap_x)
    return pts


# ---------------------------------------------------------------- 真人误差原型
# gen_human_sloppy:7 类真人原型混合(占比为教学假设,非真实人群统计)。在本靶场
# 模型上的仿真:v1 固定阈值误伤约 45~55%,v2 尺度化阈值误伤降到个位数百分比
# (残余误伤集中在 _flick 撞 duration_scaled)—— 这组对比就是本靶场的核心教学点。

def _flick(gap_x, rng):
    """老用户肌肉记忆:一记甩动,又快又直又干净 —— v1 阈值的重灾区。"""
    D = float(gap_x) - X0
    duration = rng.uniform(180, 330) + 0.15 * D
    ts = _stream(rng, duration)
    start_delay = rng.uniform(80, 250)
    arc = rng.uniform(-2, 2)
    sigma = rng.uniform(0.1, 0.3)
    trem_amp, trem_w, trem_p = _tremor(rng)
    pts = []
    for t in ts:
        u = min(t / duration, 1.0)
        pts.append([t + start_delay,
                    X0 + D * _minjerk(u) + rng.gauss(0, sigma),
                    arc * math.sin(u * math.pi) + rng.gauss(0, sigma)
                        + 0.5 * trem_amp * math.sin(trem_w * t + trem_p)])
    pts[-1][1] = gap_x + rng.gauss(0, 3.5)                   # 甩手释放
    if rng.random() < 0.2:
        pts[-1][1] = gap_x + rng.choice([-1, 1]) * rng.uniform(7, 16)
    return _quantize(pts, rng, p=0.6)


def _careful(gap_x, rng):
    """谨慎慢拖:慢而稳,轨迹反而更直更干净 —— "不够乱"的检测器全踩。"""
    D = float(gap_x) - X0
    duration = rng.uniform(2200, 4500)
    ts = _stream(rng, duration)
    drift = rng.uniform(-1.5, 1.5)
    pts = []
    for t in ts:
        u = min(t / duration, 1.0)
        pts.append([t,
                    X0 + D * _minjerk(u) + rng.gauss(0, 0.12),
                    drift * u + rng.gauss(0, 0.1)])
    pts[-1][1] = gap_x + rng.gauss(0, 1.8)
    return _quantize(pts, rng)


def _touch(gap_x, rng):
    """触屏/数字笔:指尖贴玻璃是机械低通,震颤被衰减;固定频率上报。"""
    D = float(gap_x) - X0
    duration = rng.uniform(450, 1100)
    ts, t = [], 0.0
    while t < duration:
        ts.append(t)
        t += max(4.0, rng.gauss(8.33, 0.35))                 # 120Hz 近等间隔
    ts.append(duration)
    y0 = rng.choice([0.0, 1.0])
    pts = []
    for t in ts:
        u = min(t / duration, 1.0)
        pts.append([t,
                    X0 + D * _minjerk(u) + rng.gauss(0, 0.1),
                    y0 + (rng.choice([0.0, 1.0]) if rng.random() < 0.02 else 0.0)])
    pts[-1][1] = gap_x + rng.gauss(0, 1.8)
    if rng.random() < 0.1:
        pts[-1][1] = gap_x + rng.uniform(7, 12)
    return _quantize(pts, rng, p=0.9)


def _messy(gap_x, rng):
    """普通手残党:起手犹豫、中途愣神(时间空洞)、漂移、超调拉回/欠冲爬行。"""
    D = float(gap_x) - X0
    duration = rng.uniform(900, 2600)
    ts = _stream(rng, duration)
    start_delay = rng.uniform(120, 450) if rng.random() < 0.6 else 0.0
    mode = rng.random()          # 0.35 超调拉回 / 0.30 欠冲爬行 / 0.35 直接到位
    over = rng.uniform(8, 40) if mode < 0.35 else 0.0
    under = rng.uniform(8, 25) if 0.35 <= mode < 0.65 else 0.0
    end_err = rng.gauss(0, 4)
    if rng.random() < 0.03:
        end_err += rng.choice([-1, 1]) * rng.uniform(6, 20)
    arc = rng.uniform(-14, 14)                               # 弧度和漂移共享 ≤20px 预算
    sigma = rng.uniform(0.2, 0.5)
    trem_amp, trem_w, trem_p = _tremor(rng)
    drift = _wander(rng, len(ts), 0.4, 8)

    pts = []
    for i, t in enumerate(ts):
        u = min(t / duration, 1.0)
        pts.append([t + start_delay,
                    X0 + (D + over - under) * _minjerk(u) + rng.gauss(0, sigma)
                        + 0.3 * trem_amp * math.sin(trem_w * t + trem_p),
                    arc * math.sin(u * math.pi) + drift[i] + rng.gauss(0, sigma)
                        + trem_amp * math.sin(trem_w * t + trem_p * 1.3)])
    if mode < 0.35:                                          # 大步拉回(1~2 步)
        for s in range(rng.randint(1, 2), 0, -1):
            f = (s - 1) / 2
            pts.append([pts[-1][0] + rng.uniform(120, 300),
                        X0 + D + over * f + end_err * (1 - f),
                        pts[-1][2] + rng.gauss(0, sigma)])
    elif mode < 0.65:                                        # 停驻→慢速爬行补完
        t0 = pts[-1][0] + rng.uniform(150, 500)              # 第二次注视缺口
        speed = rng.uniform(20, 150)                         # px/s,无方向反转
        n = max(3, int(under / (speed * 0.03)))
        for k in range(1, n + 1):
            f = k / n
            pts.append([t0 + under / speed * 1000 * f,
                        X0 + D - under + under * f + rng.gauss(0, 0.2),
                        pts[-1][2] + rng.gauss(0, sigma)])
    pts[-1][1] = gap_x + end_err

    _time_hole(pts, rng, 150, 1200, 0.6)                     # 发呆是最强人类信号
    if rng.random() < 0.12:                                  # 抬手重握
        k = rng.randint(len(pts) // 3, 2 * len(pts) // 3)
        for j in range(k, len(pts)):
            pts[j][0] += rng.uniform(150, 600)
    return _quantize(_monotonic(pts), rng, p=0.3)


def _release_error(gap_x, rng, err_range):
    """松手时机失误:滑过头不修 / 怕过头提前松手 —— 真人松手就是终点。"""
    pts = gen_human(gap_x, rng.randrange(1 << 30))
    pts[-1][1] = gap_x + rng.uniform(*err_range)
    return pts


def _hold_tremor(gap_x, rng):
    """到位后按住等确认:8~12Hz 震颤继续,释放时刻落在震颤随机相位上。"""
    pts = gen_human(gap_x, rng.randrange(1 << 30))
    hold, t_last = rng.uniform(250, 700), pts[-1][0]
    trem_amp, trem_w, trem_p = _tremor(rng)
    trem_amp = max(trem_amp, rng.uniform(0.8, 1.6))          # 按住不松时颤得更明显
    n = rng.randint(4, 10)
    for k in range(1, n + 1):
        t_k = t_last + hold * k / n
        pts.append([t_k,
                    gap_x + trem_amp * math.sin(trem_w * t_k + trem_p) + rng.gauss(0, 0.3),
                    pts[-1][2] + rng.gauss(0, 0.3)])
    pts[-1][1] = gap_x + rng.gauss(0, 4.5)
    return _monotonic(pts)


def gen_human_sloppy(gap_x, seed=None):
    """真人误差全景:7 类原型混合。"""
    rng = random.Random(seed)
    pop = rng.random()
    if pop < 0.20:
        return _flick(gap_x, rng)              # 老手甩动 —— v1 误伤主力
    if pop < 0.35:
        return _careful(gap_x, rng)            # 谨慎慢拖
    if pop < 0.50:
        return _touch(gap_x, rng)              # 触屏/笔 —— v1 几乎全灭
    if pop < 0.78:
        return _messy(gap_x, rng)              # 手残党(占大头)
    if pop < 0.88:
        return _release_error(gap_x, rng, (7, 20))    # 滑过头不修
    if pop < 0.95:
        return _release_error(gap_x, rng, (-15, -7))  # 提前松手
    return _hold_tremor(gap_x, rng)            # 到位后按住犹豫
