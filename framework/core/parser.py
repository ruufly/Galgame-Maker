""".gal 脚本解析器。

语法规则:
- 注释: 以 # 开头的整行
- 标签: 形如 `name:` 的行 (可任意缩进), 例如 `start:`
- 命令: `命令名 参数...`, 参数可用双引号/单引号包裹以包含空格
- 块命令: `choice:` / `if 表达式:` 等以冒号结尾的命令, 其缩进的子行构成子块
- 文件头声明: `widgets @ "widgets/"` 形式的行, 收集到 Script.headers 中

兼容性说明 (对齐编辑器 test/main.gal 的旧语法):
- `weight` 块: 定义组件的多行属性 (image/mode/effect/x/y), 由 `-> name` 命名
- `-> name`: 给最近一个 weight 块命名
- 二者在解析阶段保留为普通命令, 由引擎在运行时解释
"""

import re
import shlex
from typing import List, Optional

from .ast import Command, Header, Label, Script

LABEL_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*):\s*$")
BLOCK_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*):\s*$")   # choice: / if ...: 由调用方预判
HEADER_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s+@\s+(.+)$")


class ParseError(Exception):
    def __init__(self, line, msg):
        super().__init__("第 %d 行: %s" % (line, msg))
        self.line = line
        self.msg = msg


def _strip_comment(line: str) -> str:
    """去掉整行注释。行内 # 不处理 (避免误伤字符串/URL)。"""
    stripped = line.strip()
    if stripped.startswith("#"):
        return ""
    return line


def split_args(text: str) -> List[str]:
    """按 shell 规则切分参数, 支持引号包裹。"""
    try:
        return shlex.split(text, posix=True)
    except ValueError as e:
        raise ValueError("参数解析失败: %s (%s)" % (text, e))


def parse(text: str) -> Script:
    lines = text.splitlines()
    script = Script()
    current_label: Optional[Label] = None
    stack: List[List[Command]] = []      # 缩进块栈
    stack_indent: List[int] = []

    def indent_of(line: str) -> int:
        return len(line) - len(line.lstrip(" \t"))

    def active_block() -> List[Command]:
        return stack[-1] if stack else (current_label.commands if current_label else None)

    for lineno, raw in enumerate(lines, start=1):
        line = _strip_comment(raw)
        if not line.strip():
            continue
        stripped = line.strip()
        indent = indent_of(line)

        # 回退缩进栈: 处理块结束
        while stack_indent and indent <= stack_indent[-1]:
            stack.pop()
            stack_indent.pop()

        if stack:
            # 块内不允许出现标签
            if LABEL_RE.match(stripped):
                raise ParseError(lineno, "块内不允许定义标签: %s" % stripped)
        else:
            # 顶层: 标签定义
            m = LABEL_RE.match(stripped)
            if m:
                name = m.group(1)
                if name in script.labels:
                    raise ParseError(lineno, "重复的标签: %s" % name)
                current_label = Label(name=name, line=lineno)
                script.labels[name] = current_label
                script.order.append(name)
                continue

        # 文件头声明 (仅顶层且尚未出现任何命令时)
        if not stack and current_label is None:
            m = HEADER_RE.match(stripped)
            if m:
                script.headers.append(Header(key=m.group(1), value=m.group(2), raw=stripped))
                continue

        # 普通命令
        if current_label is None:
            raise ParseError(lineno, "命令出现在任何标签之前: %s" % stripped)

        is_block = stripped.endswith(":") and not LABEL_RE.match(stripped)
        if is_block:
            head = stripped[:-1]
            name = head.split()[0] if head.split() else head
            rest = head[len(name):].strip()
            args = split_args(rest) if rest else []
            cmd = Command(name=name, args=args, body=[], line=lineno)
        else:
            parts = split_args(stripped)
            cmd = Command(name=parts[0], args=parts[1:], line=lineno)

        target = active_block()
        if target is None:
            raise ParseError(lineno, "命令出现在任何标签之前: %s" % stripped)
        target.append(cmd)

        if is_block:
            stack.append(cmd.body)
            stack_indent.append(indent)

    if stack:
        raise ParseError(0, "存在未闭合的命令块 (缩进不完整)")

    return script


def parse_file(path: str) -> Script:
    with open(path, "r", encoding="utf-8") as f:
        return parse(f.read())
