# 贡献指南 —— 两条赛道

先读 [CHARTER.md](CHARTER.md) 的红线。提交任何 PR 即表示你已读过并接受。

环境要求:Python ≥ 3.8,**零第三方依赖**(纯标准库 —— 这是仓库纪律,
防线/标本也不例外)。Windows 终端建议设 UTF-8:
cmd: `set PYTHONIOENCODING=utf-8` · PowerShell: `$env:PYTHONIOENCODING="utf-8"` ·
Git Bash: `PYTHONIOENCODING=utf-8 python ...`。

```bash
python tools/lint_redlines.py                 # 红线机械检查(CI 同款)
python -m riskarena tournament --trials 200   # 基线应复现 README 的数字
python tools/debug_verdicts.py                # 想看每层为什么拦
```

---

## 赛道 A:提交防线

1. 建目录 `scenarios/<你的场景名>/`(或复用 `scenarios/slider/`)。
2. 实现 `Defense` 子类(`riskarena/spec.py` 是唯一契约):
   - `new_challenge()` → `Challenge`(必须带一次性 `challenge_id`);
   - `evaluate(challenge, submission)` → `Verdict`:
     - `blocked` 是最终裁决,**任何一层报警都足以拦截**;
     - `solved` 是场景语义的"任务完成"(滑块=对准缺口),与 blocked 独立 ——
       裁判靠这两个字的组合区分"重试"和"误伤";
     - `layers` 给每层一个 `{"ok": bool, ...}`,裁判按层算通过率;
     - `score` 给连续风险分(1~6 或原始 p)。
   - 可选 `supports_protocol()` + `use_ticket(token)`:实现了就自动参加
     协议探针(challenge 重放 / 伪造票据 / 票据单次性),探针 HOLE 会写进榜单。
   - **强烈建议**实现 `check_solved(challenge, submission)`:只凭明文
     独立判定任务完成 —— 裁判用它复核你自报的 solved,矛盾计入榜单
     `solved_mismatches`;不实现则裁判按自报计分并标注 `verified_solved=False`
     (评审会追问为什么不敢被复核)。
   - **必须**实现 `reset_session()`:清空所有时间域状态(频控、信誉窗口)。
     锦标赛每试次前调用;时间域层不计榜单分(见 docs/league-rules.md)。
   - **必须**实现 `seed(s)`:让 `new_challenge` 的抽样进可复现轨道,
     否则报告里的 `--seed` 是假的可复现性。
3. 跑 `python -m riskarena tournament`,确认:
   - `corpus-human` 的 accused 率有数字(它就是你防线的误伤体检,证据等级
     为 purported-human,见 PROVENANCE.md);
   - 协议探针没有 HOLE;`solved_mismatches` 为 0;
   - `human_solved_rate ≥ 0.5`,否则榜单直接沉底(disqualified)。
4. PR 里附一次 `tournament` 的完整输出。评审按 CHARTER 红线 +
   `docs/league-rules.md` 的复核清单。

参考实现:`scenarios/slider/scenario.py::SliderDefense`(四层:协议/规则/模型/环境)。

## 赛道 B:提交标本

1. 写一个 `Specimen` 子类,单独放一个文件。**本地试验:放进仓库根的
   `specimens/` 目录,CLI 自动发现加载**(该目录不入库);也可以
   `python -m riskarena tournament --specimen 我的标本.py:类名` 显式指定。
   合并入库时由维护者移入对应场景包并登记进内置清单。
   - `intent` 必须如实标:`"bot"`(想通过验证的机器)或
     `"human"`(真人行为模拟/回放)。**标注造假 = 逐出**;
   - `build(challenge, rng)` → `Submission(samples=[[t_ms,x,y],...], fingerprint=...)`。
     只消费 challenge 的明文 payload(裁判传给你的是深拷贝,随便读;
     篡改不会影响评分,但会被记录),不许 import 防线模块(那是白盒联赛,
     `tools/lint_redlines.py` 会拦);
   - 场景约定:轨迹从 x=0 起拖到 gap_x(场景不承诺滑块起始坐标,
     裁判按位移计);黑盒标本请**硬编码自己的 fingerprint dict**
     (字段集合见 specimen-guide),不要 import 场景模块取指纹档;
   - 用了任何变换(缩放/重采样/插值)在 docstring 里如实声明。
2. PR 描述里给出:名字、intent、作者、白盒与否、一句话策略
   (这里说的"注册"就是在 PR 文字里申报,合并后由维护者登记)。
3. 本地跑锦标赛看它的表现(`python -m riskarena specimens` 应能看到它),
   把输出贴进 PR。

参考:`scenarios/slider/scenario.py::GeneratorSpecimen`、
`scenarios/slider/scenario.py::SlowDragFpBot`(首位贡献者的标本)、
`riskarena/spec.py::ReplaySpecimen`(语料回放)。

## 榜单规则(概要,全文见 docs/league-rules.md)

- 结果写进 `results/history.jsonl` + `leaderboard.json`(两者都在 .gitignore,
  按克隆各自生成;维护者发布版用固定 seed + 公开 trials 复核)。
- 排序只按 `utility = catch − λ·fp`(λ=3); disqualified 的防线沉底并标注。
- 同名防线按版本覆盖旧条目;**名字冲突**由维护者在合并前检索历史榜单
  与 scenarios/ 目录,冲突时后到者改名。

## 评审复核清单(维护者用,也是你的自查表)

- [ ] `python tools/lint_redlines.py` 通过(网络模块/黑盒导入/语料字段)
- [ ] 无对外网络请求;只作用于本仓库内的 Challenge/Submission
- [ ] 标本不 import 防线(黑盒);白盒已标注
- [ ] intent 标注与代码行为一致(bot 标本别"故意输"刷误伤,human 别带 bot 逻辑)
- [ ] 语料引用过许可关:LICENSE 全文随附、PROVENANCE 已更新(含上游项目
      性质与证据等级)
- [ ] 变换/手术已声明;指标用 `riskarena/metrics.py` 的定义
- [ ] 新防线带 reset_session + seed + check_solved;探针无 HOLE;
      solved_mismatches 为 0
- [ ] 点名真实厂商仅限已发表文献引用,无产品参数情报(CHARTER 红线 6)

## 冷启动承诺

只按本文档走,30 分钟内应能跑通你的第一次锦标赛。
跑不通算文档 bug —— 开 issue,贴报错,我们修文档而不是让你猜。
