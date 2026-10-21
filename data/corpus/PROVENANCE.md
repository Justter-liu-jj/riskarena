# 语料来源与处理记录

- 来源: https://github.com/NingNing0111/slider-track-model
- 许可: MIT(随数据集分发,本目录不重复其全文)
- 转换: tools/convert_corpus.py --source ningning
- 输入: 7 个文件
- 保留: 1050 条 human 轨迹;丢弃 2 条(点数<5 或位移<20px 的坏/死轨迹)
- 处理: 纯格式搬运(t,x,y 直拷),不重采样、不平滑、不筛异常值
- 已知告诫: 采集方标注为真人录制但无法逐一核实;y 值近零(采集组件特性),
  与合成生成器的 y 分布不同 —— 这正是防线要面对的真实分布,不做修正。
