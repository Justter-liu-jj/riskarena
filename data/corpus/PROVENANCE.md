# 语料来源与处理记录

## 来源(如实披露,含不利信息)

- 上游仓库: <https://github.com/NingNing0111/slider-track-model>
- 许可: MIT(全文见本目录 [LICENSE-ningning.txt](LICENSE-ningning.txt),版权
  "Copyright (c) 2026 PG Thinker" —— MIT 再分发条款要求随副本附带,故全文随附)
- **上游项目性质(2026-10 伦理审查后补充,必须知情)**: 上游是一个
  **条件 WGAN-GP 滑块轨迹生成器**项目 —— 其自述目标是"生成在几何形状、
  速度曲线、加速度特征、抖动分布等方面都尽量接近真人操作的轨迹",
  用途标注为"防刷/风控",并在文档中把**京东滑块**列为行为检测的测试对象。
  本仓库摄入的**不是**其生成器输出,而是它用来训练生成器的真人采集
  训练集(`trajectory_dataset-*.json`,共 7 个文件,上游 README 称
  "前端 web/index.html 采集真实滑块轨迹,导出为 JSON";上游 AUDIT.md
  将 `dataset/train` 称为人工轨迹)。
- **证据等级: purported-human(自称真人,不可核实)**:
  1. "真人"标注出自上游自述,采集环节无任何知情同意/伦理记录可查;
  2. 采集组件、采集人数、设备构成均不可考(上游 AUDIT 自己提示
     "若采集环境单一,生成轨迹可能只在'鼠标风格'上过关");
  3. y 值近零、60Hz 采样、拖距 120~270px —— 单一采集组件的窄分布。
- 因此本仓库**不**将其表述为"冻结真人语料";榜单/指标中的 fp 证据等级
  见 `docs/league-rules.md`(purported-human < verified-human)。

## 处理记录

- 转换: `python tools/convert_corpus.py --source ningning --src <上游目录>`
- 输入: 7 个文件;保留 **1050** 条(label=human),丢弃 2 条
  (点数<5 或位移<20px 的坏/死轨迹)
- 处理: 纯格式搬运(t,x,y 直拷 + 保留 target_distance),不重采样、
  不平滑、不筛异常值
- 回放手术(评估时发生,不改本文件): 见 `riskarena/corpora.py::
  align_translation` —— 小差纯平移;大差时空等比缩放(靶点锚定,
  保速度剖面与松手误差)
- 已知告诫: 与合成生成器的 y 分布不同,这正是防线要面对的真实(窄)分布,
  不做修正
