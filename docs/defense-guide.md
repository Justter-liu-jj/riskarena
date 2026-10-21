# 防线编写指南

## 最小骨架

```python
from riskarena.spec import Challenge, Defense, Submission, Verdict

class MyDefense(Defense):
    name = "my-defense"
    version = "0.1.0"

    def new_challenge(self) -> Challenge:
        # challenge_id 必须一次性(协议探针会重放它)
        return Challenge(kind="my-scenario", challenge_id=make_id(), payload={...})

    def evaluate(self, challenge, submission) -> Verdict:
        # 返回 Verdict(blocked, solved, score, layers, reasons)
        ...

    def reset_session(self):
        # 锦标赛每试次前调用:清空频控/信誉等时间域状态
        ...
```

## evaluate 的四件事

1. **消耗 challenge**:弹出 challenge_id(重复提交直接拦 —— 探针在测这个)。
2. **场景判定**:任务完成了吗?填 `solved`(与 blocked 独立!
   裁判靠 solved∧blocked 识别"真人被咬")。
3. **分层判定**:每层给 `layers[name] = {"ok": bool, ...}`。
   `blocked` 的语义是"任何一层报警即拦"。层名建议:protocol / rules / model / env。
4. **给连续分**:有模型就给 `score`(1~6 或原始 p),裁判算平均分分布。

## 可选协议面

实现 `supports_protocol() → True` 和 `use_ticket(token) → ("ok"|"replay"|"expired"|"invalid", msg)`
即可参加协议探针套件:

- `_probe_replay_challenge`:同一 challenge 提交两次,第二次必须拦;
- `_probe_forged_ticket`:None/12345/空串/假签名等 6 种伪造必须全拒;
- `_probe_ticket_replay`:真票消费两次,第二次必须非 ok。

探针 HOLE 会原文写进榜单条目。参考实现:`scenarios/slider/ticket.py`
(一次性票据:原子 dict.pop + 已用票据带原状态回显)。

## reset_session / seed / check_solved 的纪律

- **reset_session()**:时间域状态(频控窗口、信誉分、会话内计数)在
  锦标赛语义下每试次重置,这些层不计榜单分。别试图"偷偷保留"——
  裁判机器速度会让它变成"同一指纹每秒千次验证"的伪影(我们实测过:
  误伤率虚增 80%)。如实重置,docstring 声明,等会话模式再回来计分。
- **seed(s)**:裁判在锦标赛开始时调用。把 `new_challenge` 的抽样挂到这个
  种子上 —— 不实现的话,报告里的 `--seed` 是假的可复现性(两次同 seed
  运行数字对不上,评审直接打回)。
- **check_solved(challenge, submission)**:只凭明文独立判定任务完成。
  裁判计分只认它的结果,你自报的 solved 与它的矛盾会计入榜单
  `solved_mismatches` —— 这是防"凡拦截一律报没完成"把误伤率刷成 0 的
  机制。不实现也能跑,但榜单会标 `verified_solved=False`,评审会追问。

## 上榜自查

```bash
python -m riskarena tournament --trials 200
```

- `corpus-human` 的 accused 率 = 你的真人误伤体检(真实拖拽,不是合成);
- 协议探针无 HOLE;
- `human_solved_rate ≥ 0.5`(否则 disqualified);
- 把完整输出贴进 PR。

## 参考实现

`scenarios/slider/scenario.py::SliderDefense` —— 协议/规则/模型/环境四层,
vendored 自 slider-captcha-lab v3.1(各模块首行注明出处)。
读它的 evaluate:注意 solved 与 blocked 的分离、layers 的组装、
票据只在全过时签发。
