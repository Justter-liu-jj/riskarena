# vendored from slider-captcha-lab (原型仓库)@2026-10;除本行与 import 调整外未改动 —— 原理说明见原型 README
"""一次性票据 —— 风控协议层的"最后一公里"。

真实系统的流程:验证通过 ≠ 放行,而是下发一张短时效、单次使用的签名票据,
真正的业务接口(登录/下单)凭票放行。顶象的同类设计:票据 2 分钟有效、
只能校验一次(见 references.md)。这样即使轨迹伪造全套通过,攻击者
也拿不到可复用的通行证 —— 重放直接被识别。

本靶场实现(HMAC-SHA256,纯标准库):
  issue(challenge_id)  -> token "exp-nonce-sig",120s 有效、单次使用
  consume(token)       -> ("ok"|"replay"|"expired"|"invalid", msg)

实现说明:票据以完整字符串为键存入 _ISSUED(精确匹配 allowlist),
能查到即等于验签通过 —— 因此没有独立的"验签失败"分支,伪造=查无此票
(签名仍写在 token 里:密钥只有服务器知道,客户端构造不出能命中
allowlist 的串)。consume 用 dict.pop 一步原子取出:并发吃同一张票,
只有一个线程能看到 entry —— 不会双花,也不会把并发重放打成 KeyError 断连。
"""
import hashlib
import hmac
import os
import time
import uuid

TTL_S = 120
RETAIN_S = TTL_S * 10              # _USED 里保留重放记录的时长(过后重放读"invalid")
_SECRET = os.urandom(32)           # 进程级密钥:重启即作废全部票据
_ISSUED = {}                       # token -> (issue_time, challenge_id)
_USED = {}                         # token -> (consume_time, final_status)
_last_sweep = 0.0


def _sig(cid, exp, nonce):
    return hmac.new(_SECRET, f"{cid}|{exp}|{nonce}".encode(),
                    hashlib.sha256).hexdigest()[:32]


def issue(challenge_id):
    exp = int(time.time()) + TTL_S
    nonce = uuid.uuid4().hex[:8]
    cid = str(challenge_id)
    token = f"{exp}-{nonce}-{_sig(cid, exp, nonce)}"
    _ISSUED[token] = (time.time(), cid)
    return token, TTL_S


def consume(token):
    """状态机:未签发→invalid;已签发→验期→焚毁;已焚毁→replay(大声说出来,
    连"原状态是什么"一起说 —— 重放一张已过期的票也会被点名)。"""
    if not isinstance(token, str) or token.count("-") < 2:
        return "invalid", "票据格式错误"
    try:
        exp_s, nonce, sig = token.split("-", 2)
        exp = int(exp_s)
    except ValueError:
        return "invalid", "票据无法解析"

    entry = _ISSUED.pop(token, None)          # 原子取出:并发重放只有一个能拿到
    now = time.time()
    if entry is None:
        prior = _USED.get(token)
        if prior:
            return "replay", (f"重放被拒绝:该票据已消费过(原状态:{prior[1]})"
                              " —— 这就是单次票据存在的意义")
        return "invalid", "票据不存在(未签发、已过期被清理,或服务器密钥已轮换)"

    cid = entry[1]
    if not hmac.compare_digest(sig, _sig(cid, exp, nonce)):
        # 纵深防御,正常不可达:整串 token 是 allowlist 键,能查到说明没被篡改
        _USED[token] = (now, "invalid")
        return "invalid", "签名校验失败 —— 票据被伪造或篡改"
    if exp < now:
        _USED[token] = (now, "expired")
        return "expired", f"票据已过期(有效期 {TTL_S}s)—— 它的重放也会被记录"

    _USED[token] = (now, "ok")
    return "ok", f"受保护动作执行成功(绑定 challenge {cid[:8]}…,票据已焚毁)"


def sweep_if_due(interval=30.0):
    """server 在发挑战时顺手调用:清过期票据与过旧的重放记录,防内存无界。"""
    global _last_sweep
    now = time.time()
    if now - _last_sweep < interval:
        return
    _last_sweep = now
    for t in [t for t, (ts, _) in _ISSUED.items() if ts + TTL_S < now]:
        _ISSUED.pop(t, None)
    for t in [t for t, (ts, _) in _USED.items() if ts + RETAIN_S < now]:
        _USED.pop(t, None)
