"""Galgame Maker 编辑器 (主仓库侧, 与 framework 子模块对接)。

P0 状态: 项目模型 + .gal 序列化器 + 往返测试 + 无头渲染验证。

核心原则:
- 单一事实来源: 编辑器模型 = framework.engine.parser 的 Script/Statement 树
- Editor-first: 所有 .gal 文本均由模型序列化生成, 零基础用户不写脚本
- 往返保证: parse(serialize(parse(t))) 与 parse(t) 结构等价
"""

__version__ = "0.1.0"
