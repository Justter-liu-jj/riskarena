# vendored from slider-captcha-lab (原型仓库)@2026-10;除本行与 import 调整外未改动 —— 原理说明见原型 README
"""环境指纹层 —— 风控第三层:不只看"做了什么",还看"用什么做的"。

真实系统的这一层采 Canvas/WebGL 指纹、插件列表、UA 一致性、自动化痕迹
(navigator.webdriver、headless 特征),并按设备 ID 累积跨请求信誉
(见 references.md 的厂商采集字段清单)。本靶场实现一个教学版:

  1. webdriver / 自动化标记检查
  2. UA vs platform 一致性
  3. 无插件桌面 Chrome(headless 常态)、指纹字段缺失/伪造
  4. 频控:同一指纹 60 秒窗口内高频验证(信誉层的最简形态)

前端在 static/captcha.js 的 collectFingerprint() 采集,/api/bot 的各模式
由 fingerprint.profile_for() 伪造对应质量的指纹 —— rookie 连伪装都不做。
"""
import time
from collections import defaultdict, deque

REQUIRED_FIELDS = {"webdriver", "plugins", "languages", "platform", "ua",
                   "screen", "timezone", "canvas_hash"}

# 信誉(频控)参数:同一指纹 60s 内超过 REP_LIMIT 次验证 → 命中
REP_WINDOW_S = 60.0
REP_LIMIT = 240
_REP = defaultdict(deque)          # fp_id -> deque[timestamps]
_rep_calls = 0


def reset_rep():
    """清空频控窗口(riskarena 附加:锦标赛每试次重置时间域状态,见 spec.reset_session)。"""
    _REP.clear()


def fp_id(fp):
    """指纹的稳定 ID:canvas_hash 优先(它跨会话稳定),退化到字段拼接。"""
    if not isinstance(fp, dict):
        return "?"
    ch = fp.get("canvas_hash")
    if ch not in (None, "", 0):
        return f"c:{ch}"
    return "raw:" + "|".join(f"{k}={fp.get(k)}" for k in sorted(fp))


def rep_touch_and_check(fpid, now=None):
    """记录一次验证,并判断是否超频。返回 (超频?, 窗口内次数)。

    已知教学点(2026-10 审计确认):fp_id 由客户端可控的 canvas_hash 派生,
    每次请求随机化它即可完全绕开本频控 —— 这正是"没有跨设备关联图"的真实含义,
    见 README 教学简化清单。"""
    global _rep_calls
    now = time.time() if now is None else now
    q = _REP[fpid]
    q.append(now)
    _rep_calls += 1
    if _rep_calls % 512 == 0:      # 顺手清坟:窗口已完全过期的时间桶直接删,防内存无界
        dead = [k for k, dq in _REP.items() if not dq or dq[-1] < now - REP_WINDOW_S]
        for k in dead:
            _REP.pop(k, None)
    cutoff = now - REP_WINDOW_S
    while q and q[0] < cutoff:
        q.popleft()
    return len(q) > REP_LIMIT, len(q)


def check(fp, fpid=None):
    """校验一个指纹 dict → {ok, reasons[]}。reasons 的 kind 统一为 env。"""
    reasons = []

    def add(detector, ok, note):
        reasons.append({"detector": detector, "ok": ok, "kind": "env", "note": note})

    if not isinstance(fp, dict) or not fp:
        add("fingerprint", False, "未上报环境指纹 —— 正常浏览器都会带,缺失本身即信号")
        return {"ok": False, "reasons": reasons}

    missing = REQUIRED_FIELDS - set(fp)
    # 空串字段 = 没给:真浏览器的 UA/platform/screen 不会是 ""
    missing |= {k for k, v in fp.items() if isinstance(v, str) and not v.strip()}
    if missing:
        add("fingerprint", False, f"指纹字段缺失/为空:{','.join(sorted(missing))}(伪造/自动化常见)")
    else:
        add("fingerprint", True, f"指纹字段完整({len(REQUIRED_FIELDS)} 项)")

    wd = fp.get("webdriver")
    if wd is True:
        add("webdriver", False, "navigator.webdriver=true —— Selenium/Playwright/CDP 自动化标记")
    elif wd is False:
        add("webdriver", True, "无自动化标记")
    else:
        add("webdriver", False, "webdriver 字段异常(非布尔)")

    ua = str(fp.get("ua", ""))
    platform = str(fp.get("platform", ""))
    # 2026-10 审计修正:真实 ChromeOS 的 platform 是 Linux x86_64 而 UA 含 CrOS;
    # 真实 iPad(请求移动版)的 platform 是 MacIntel 而 UA 含 iPad —— 都是合法组合
    ua_tokens = {"Win32": ("Windows NT",), "MacIntel": ("Macintosh", "iPad"),
                 "Linux x86_64": ("Linux", "CrOS"), "Linux armv8l": ("Android", "Linux")}
    # 只有 UA 明说"别的系统"才算矛盾;映射外的未知组合只记录,不定罪
    contradictions = {"Win32": ("Macintosh", "CrOS", "iPad", "Android"),
                      "MacIntel": ("Windows NT", "CrOS", "Android"),
                      "Linux x86_64": ("Windows NT", "Macintosh", "iPad", "Android"),
                      "Linux armv8l": ("Windows NT", "Macintosh", "CrOS", "iPad")}
    expected = ua_tokens.get(platform)
    if expected:
        if any(tok in ua for tok in expected):
            add("ua_consistency", True, f"platform={platform} 与 UA 一致")
        elif any(tok in ua for tok in contradictions.get(platform, ())):
            add("ua_consistency", False,
                f"platform={platform} 但 UA 明说别的系统 —— 伪造指纹的典型裂缝")
        else:
            add("ua_consistency", True,
                f"platform={platform},UA 组合在映射外(仅记录,不定罪)")
    else:
        add("ua_consistency", True, f"platform={platform}(未知映射,仅记录)")

    plugins = fp.get("plugins")
    if isinstance(plugins, (int, float)) and not isinstance(plugins, bool):
        desktop_chrome = ("Chrome" in ua) and ("Mobile" not in ua) and ("Headless" not in ua)
        if plugins == 0 and desktop_chrome:
            add("plugins", False, "桌面 Chrome 但插件数为 0 —— headless 常态,真人罕见")
        elif plugins >= 0:
            add("plugins", True, f"插件数 {int(plugins)}")
        else:
            add("plugins", True, "插件数未知(移动端常态)")
    else:
        add("plugins", False, "plugins 字段类型异常")

    if not fp.get("canvas_hash"):
        add("canvas", False, "缺少 Canvas 指纹 —— 无法建立跨会话设备 ID")
    else:
        add("canvas", True, f"Canvas 指纹 {fp.get('canvas_hash')}")

    fpid = fpid or fp_id(fp)
    over, count = rep_touch_and_check(fpid)
    if over:
        add("rep_rate", False, f"同一指纹 {REP_WINDOW_S:.0f}s 内验证 {count} 次(>{REP_LIMIT})—— 信誉层命中")
    else:
        add("rep_rate", True, f"频控正常({count}/{REP_LIMIT} 次/分钟)")

    return {"ok": all(r["ok"] for r in reasons), "reasons": reasons}


def profile_for(mode):
    """/api/bot 各模式伪造的指纹:质量随"知情程度"递增。
    rookie 不伪装;sneaky 带一套完整一致的假指纹(所以环境层抓不到它,
    必须靠行为模型 —— 这正是 v3 的教学分工)。"""
    if mode == "rookie":
        return {"webdriver": True, "plugins": 0, "languages": "", "platform": "",
                "ua": "python-requests/2.31", "screen": "", "timezone": "",
                "canvas_hash": ""}
    if mode == "sneaky":
        return {"webdriver": False, "plugins": 5, "languages": "zh-CN,zh",
                "platform": "Win32", "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
                "screen": "1920x1080", "timezone": "Asia/Shanghai",
                "canvas_hash": -31415926}
    # human / sloppy / pro:完整、一致的正常指纹(只是没有真实硬件熵)
    return {"webdriver": False, "plugins": 5, "languages": "zh-CN,zh",
            "platform": "Win32", "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "screen": "2560x1440", "timezone": "Asia/Shanghai",
            "canvas_hash": hash(mode) % 100000}
