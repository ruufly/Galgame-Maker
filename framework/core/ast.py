"""脚本语法树定义。

一个 .gal 脚本由三部分组成：
- headers: 文件头声明（如 `widgets @ "widgets/"` / `functions @ "functions/"`）
- labels:  标签定义（`start:` 后跟若干命令）
- order:   标签出现顺序（决定默认入口，第一个标签为游戏入口）
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict


@dataclass
class Header:
    """文件头声明行, 例如 `widgets @ "widgets/"`。"""
    key: str          # 声明名, 如 widgets / functions
    value: str        # 参数原文, 如 "widgets/"
    raw: str          # 原始行


@dataclass
class Command:
    """一条脚本命令。

    name: 命令名, 例如 show / say / jump / choice
    args: 已解析的参数列表 (字符串均去掉引号)
    body: 缩进子块 (choice / if 等块命令使用), 否则为 None
    line: 源文件行号 (用于报错)
    """
    name: str
    args: List[str] = field(default_factory=list)
    body: Optional[List["Command"]] = None
    line: int = 0

    def __repr__(self):
        return "Command(%s %r)" % (self.name, self.args)


@dataclass
class Label:
    """一个标签 (流程节点)。"""
    name: str
    commands: List[Command] = field(default_factory=list)
    line: int = 0


@dataclass
class Script:
    """解析后的完整脚本。"""
    headers: List[Header] = field(default_factory=list)
    labels: Dict[str, Label] = field(default_factory=dict)
    order: List[str] = field(default_factory=list)   # 标签出现顺序

    @property
    def entry(self) -> Optional[Label]:
        return self.labels[self.order[0]] if self.order else None
