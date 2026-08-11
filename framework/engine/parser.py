"""DSL 解析器: 把 .gal 脚本文本解析成语句列表与标签表。

语法概览 (与 Galgame-Maker 编辑器语法风格兼容)::

    # 声明 (顶层)
    widgets @ "widgets/"
    functions @ "functions/"

    name: demo          # 元信息 (可选, 也支持 author/copyright)

    start:              # 标签块
        weight          # 创建背景对象 (属性块)
            image: "bg.png"
            mode: full
            effect: fade
        -> bg1          # 绑定 id
        show bg1

        sprite girl     # 创建立绘 (属性块)
            image: "girl.png"
            pos: center
        show girl
        text "你好世界"
        say 主角 "这是对话"
        choice:
            "选项一" -> label_a
            "选项二" -> label_b
        set love = 0
        if love > 0:
            text "好感度高"
        else:
            text "好感度低"
        endif
        jump label_a
        call label_b
        return
        music "bgm.mp3"
        save
        fadeout
        ending

支持的指令由运行时执行 (见 runtime.py), 解析器只负责结构。
"""

import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from framework.engine import log


class ParserError(Exception):
    pass


@dataclass
class Statement:
    """一条解析后的语句。

    op     : 指令名 ('text'/'say'/'jump'/... 或 '->' 绑定, 'weight'/'sprite' 创建)
    args   : 位置参数 (字符串已去引号, 数字/表达式保持原样)
    kwargs : 关键字参数 (来自属性块或块结构数据, 如 choice 的 options)
    block  : 子语句列表 (if 分支体等)
    line   : 源文件行号
    raw    : 原始行文本
    """

    op: str
    args: List[str] = field(default_factory=list)
    kwargs: dict = field(default_factory=dict)
    block: List["Statement"] = field(default_factory=list)
    line: int = 0
    raw: str = ""

    def __repr__(self):
        return f"<Stmt {self.op} {self.args} {self.kwargs} @{self.line}>"


@dataclass
class Script:
    """一次解析的结果。"""

    path: str = ""
    name: str = ""
    meta: dict = field(default_factory=dict)
    statements: List[Statement] = field(default_factory=list)  # 顶层语句
    labels: dict = field(default_factory=dict)                 # label -> [Statement]
    widgets_dir: Optional[str] = None
    functions_dir: Optional[str] = None


# ----------------------------------------------------------------------
# 词法: 把一行拆成 token, 支持字符串/符号/单词
# ----------------------------------------------------------------------
_SYMBOLS = ["->", "==", "!=", "<=", ">=", "<", ">", "=", ":", "+", "-", "*", "/"]


def _tokenize(text: str) -> List[Tuple[str, str]]:
    """返回 [(kind, value)], kind 为 'str' / 'sym' / 'word'。"""
    tokens: List[Tuple[str, str]] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c.isspace():
            i += 1
            continue
        if c in ('"', "'"):
            quote = c
            j = i + 1
            buf = []
            while j < n and text[j] != quote:
                if text[j] == "\\" and j + 1 < n:
                    buf.append(text[j + 1])
                    j += 2
                else:
                    buf.append(text[j])
                    j += 1
            tokens.append(("str", "".join(buf)))
            i = j + 1
            continue
        matched = None
        for sym in _SYMBOLS:
            if text.startswith(sym, i):
                matched = sym
                break
        if matched:
            tokens.append(("sym", matched))
            i += len(matched)
            continue
        j = i
        while j < n and not text[j].isspace():
            # 单词在符号处截断 (如 "choice:" -> choice + ':')
            if any(text.startswith(s, j) for s in _SYMBOLS):
                break
            j += 1
        tokens.append(("word", text[i:j]))
        i = j
    return tokens


def _tokens_to_text(tokens: List[Tuple[str, str]]) -> str:
    """把 token 重构为可求值的表达式文本 (字符串重新加引号)。"""
    parts = []
    for kind, value in tokens:
        if kind == "str":
            parts.append(repr(value))
        else:
            parts.append(value)
    return " ".join(parts)


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] in ('"', "'") and value[-1] == value[0]:
        return value[1:-1]
    return value


# ----------------------------------------------------------------------
# 解析器
# ----------------------------------------------------------------------
class Parser:
    def __init__(self) -> None:
        self.lines: List[Tuple[int, int, str]] = []  # (indent, lineno, content)

    # -- 入口 ----------------------------------------------------------
    def parse(self, text: str, path: str = "") -> Script:
        script = Script(path=path)
        self._preprocess(text)
        i = 0
        n = len(self.lines)
        current_label: Optional[str] = None

        while i < n:
            indent, lineno, content = self.lines[i]

            # 标签块内的语句 (有缩进)
            if indent > 0:
                if current_label is None:
                    raise ParserError(
                        f"{path}:{lineno} 顶层语句不允许缩进: {content!r}"
                    )
                # raw 代码块: xxx:: (双冒号) —— 块内行原样捕获
                m_raw = re.match(
                    r"^([A-Za-z_\u4e00-\u9fff][\w\u4e00-\u9fff]*):{2,}$",
                    content)
                if m_raw:
                    stmt, i = self._parse_raw_block(
                        i, indent, m_raw.group(1), content)
                    script.labels[current_label].append(stmt)
                    continue
                stmt, i = self._parse_statement(i, indent)
                if stmt is not None:
                    script.labels[current_label].append(stmt)
                continue

            # 声明: widgets @ "..." / functions @ "..."
            m = re.match(r"^(widgets|functions)\s*@\s*(.+)$", content)
            if m:
                key, value = m.group(1), _unquote(m.group(2))
                if key == "widgets":
                    script.widgets_dir = value
                else:
                    script.functions_dir = value
                i += 1
                continue
            # 元信息: name: xxx
            m = re.match(r"^(name|author|copyright):\s*(.+)$", content)
            if m:
                script.meta[m.group(1)] = _unquote(m.group(2))
                if m.group(1) == "name":
                    script.name = _unquote(m.group(2))
                i += 1
                continue
            # raw 代码块: xxx:: (双冒号) —— 块内行原样捕获 (不解析)
            m_raw = re.match(
                r"^([A-Za-z_\u4e00-\u9fff][\w\u4e00-\u9fff]*):{2,}$",
                content)
            if m_raw:
                stmt, i = self._parse_raw_block(
                    i, indent, m_raw.group(1), content)
                if current_label is not None:
                    script.labels[current_label].append(stmt)
                else:
                    script.statements.append(stmt)
                continue
            # 标签: 行尾冒号且无内容
            if content.endswith(":") and not content.startswith("->"):
                label = content[:-1].strip()
                if not re.match(r"^[A-Za-z_\u4e00-\u9fff][\w\u4e00-\u9fff]*$", label):
                    raise ParserError(f"{path}:{lineno} 非法标签名: {label!r}")
                if label in script.labels:
                    raise ParserError(f"{path}:{lineno} 重复标签: {label!r}")
                script.labels[label] = []
                current_label = label
                i += 1
                continue
            # 普通语句 (顶层, 无标签时)
            stmt, i = self._parse_statement(i, indent)
            if stmt is None:
                continue
            if current_label is not None:
                script.labels[current_label].append(stmt)
            else:
                script.statements.append(stmt)
        return script

    # -- 预处理 ---------------------------------------------------------
    def _preprocess(self, text: str) -> None:
        text = text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
        self._source_lines = text.split("\n")   # raw 代码块取原样行用
        self.lines = []
        for lineno, raw in enumerate(text.split("\n"), start=1):
            content = raw.strip()
            if not content or content.startswith("#"):
                continue
            indent = 0
            for ch in raw:
                if ch == " ":
                    indent += 1
                elif ch == "\t":
                    indent += 4
                else:
                    break
            self.lines.append((indent, lineno, content))

    # -- raw 代码块 -----------------------------------------------------
    def _parse_raw_block(self, i: int, indent: int, op: str,
                         content: str):
        """捕获 raw 代码块 (如 ``python::``): 块内行**原样保留**
        (含空行与 # 注释), 不按 DSL 解析; 生成 Statement(op=op,
        kwargs={"code": 原样文本}) 交给运行时/插件处理。"""
        _, lineno, _ = self.lines[i]
        src = self._source_lines
        code_lines = []
        for k in range(lineno, len(src)):     # src[lineno] 即下一行
            raw_line = src[k]
            if not raw_line.strip():
                code_lines.append("")          # 空行保留 (缩进块需要)
                continue
            ind2 = 0
            for ch in raw_line:
                if ch == " ":
                    ind2 += 1
                elif ch == "\t":
                    ind2 += 4
                else:
                    break
            if ind2 > indent:
                code_lines.append(raw_line)
            else:
                break
        stmt = Statement(op=op, args=[],
                         kwargs={"code": "\n".join(code_lines)},
                         line=lineno, raw=content)
        # 跳过 self.lines 中属于块内的行
        j = i + 1
        while j < len(self.lines) and self.lines[j][0] > indent:
            j += 1
        return stmt, j

    # -- 语句 -----------------------------------------------------------
    def _parse_statement(self, i: int, indent: int):
        """解析 lines[i] 处的一条语句 (可能含子块), 返回 (stmt, next_index)。"""
        ind, lineno, content = self.lines[i]
        tokens = _tokenize(content)
        if not tokens:
            return None, i + 1
        kind, first = tokens[0]

        # `-> id` 绑定行 (weight 块收尾)
        if first == "->":
            return Statement(op="->", args=[_unquote(v) for k, v in tokens[1:]],
                             line=lineno, raw=content), i + 1
        if kind != "word":
            raise ParserError(f"第{lineno}行无法识别: {content!r}")
        op = first
        rest = tokens[1:]

        # ---- 子块类: choice / if --------------------------------
        if op == "choice" and rest and rest[-1] == ("sym", ":"):
            return self._parse_choice(i, indent, lineno, content)
        if op == "if" and rest and rest[-1] == ("sym", ":"):
            return self._parse_if(i, indent, lineno, content)

        # ---- menu 嵌套块: menu <id> + 按键名子块 + 属性 ----
        if op == "menu":
            return self._parse_menu(i, indent, lineno, content, rest)

        # ---- settings 嵌套块: 布局属性 + setting <key> 子块 ----
        if op == "settings":
            return self._parse_settings(i, indent, lineno, content)

        # ---- 对象创建: ... / plugins / ui + 属性块
        # gallery 等插件自定义块也在语法层识别为属性块 (引擎通过
        # script_block 事件广播给插件处理, 未装载对应插件时安全忽略)
        if op in ("weight", "sprite", "object", "char", "character",
                  "scene", "scenery", "window", "config", "title", "style",
                  "selection_style", "menu_bar", "plugins", "ui", "sound",
                  "gallery", "language"):
            return self._parse_create(i, indent, lineno, content, op, rest)

        # ---- set: 保留字符串引号, 表达式部分重构 ----------------
        if op == "set":
            name = rest[0][1] if rest and rest[0][0] == "word" else None
            if name:
                eq_idx = None
                for idx, (k, v) in enumerate(rest):
                    if k == "sym" and v == "=":
                        eq_idx = idx
                        break
                if eq_idx is not None:
                    expr = _tokens_to_text(rest[eq_idx + 1:])
                else:
                    expr = _tokens_to_text(rest[1:])
                return Statement(op="set", args=[name, expr],
                                 line=lineno, raw=content), i + 1

        # ---- 普通语句: token 重组 --------------------------------
        args = []
        kwargs = {}
        # 普通行中的 `->` 只出现在 choice 选项里 (已处理), set 的 `=` 在 args 里保留
        for kind2, value in rest:
            args.append(value)
        return Statement(op=op, args=args, kwargs=kwargs, line=lineno, raw=content), i + 1

    # -- choice 块 ------------------------------------------------------
    def _parse_choice(self, i, indent, lineno, content):
        i += 1
        options = []
        n = len(self.lines)
        while i < n:
            ind, ln, cnt = self.lines[i]
            if ind <= indent:
                break
            if "->" in cnt:
                left, right = cnt.split("->", 1)
                options.append((_unquote(left), _unquote(right)))
            else:
                log.w("log.parser.choice_invalid", line=ln, text=cnt)
            i += 1
        if not options:
            raise ParserError(f"第{lineno}行: choice 块没有选项")
        return Statement(op="choice", kwargs={"options": options}, line=lineno, raw=content), i

    # -- menu 嵌套块 ----------------------------------------------------
    def _parse_menu(self, i, indent, lineno, content, rest):
        """menu <id> + 按键子块 (每个按键一层缩进, 属性再一层)。

        menu title
            start_button
                text: "开始游戏"
                image: "a.png, b.png"
                action: start game_start
        """
        ident = rest[0][1] if rest and rest[0][0] == "word" else None
        i += 1
        n = len(self.lines)
        items = []
        kwargs = {}
        while i < n:
            ind, ln, cnt = self.lines[i]
            if ind <= indent:
                break
            # 菜单级属性行 (含冒号): ui_click_sound 等
            if ":" in cnt and not cnt.strip().endswith(":"):
                kv = cnt.split(":", 1)
                val = kv[1]
                comment = val.find(" #")
                if comment != -1:
                    val = val[:comment]
                kwargs[kv[0].strip()] = _unquote(val)
                i += 1
                continue
            name = cnt.strip()
            if name.endswith(":"):
                name = name[:-1].strip()
            i += 1
            props = {}
            while i < n:
                ind2, ln2, cnt2 = self.lines[i]
                if ind2 <= ind:
                    break
                kv = cnt2.split(":", 1)
                if len(kv) == 2:
                    val = kv[1]
                    comment = val.find(" #")
                    if comment != -1:
                        val = val[:comment]
                    props[kv[0].strip()] = _unquote(val)
                else:
                    log.w("log.parser.attr_invalid", line=ln2)
                i += 1
            items.append(Statement(op=name, args=[], kwargs=props,
                                   line=ln, raw=cnt))
        return Statement(op="menu", args=[ident] if ident else [],
                         kwargs=kwargs, block=items, line=lineno,
                         raw=content), i

    def _parse_settings(self, i, indent, lineno, content):
        """settings 块: 布局属性 + 嵌套 ``setting <key>`` 子块。

        settings
            title: "设置"
            columns: 2
            bg: "panel.png"            # 面板背景 (九宫格)
            setting bgm_volume
                label: "音乐音量"
                type: slider
            setting player_name
                label: "主角名字"
                type: cycle
                options: "小明, 小红"
        """
        i += 1
        n = len(self.lines)
        kwargs = {}
        items = []
        while i < n:
            ind, ln, cnt = self.lines[i]
            if ind <= indent:
                break
            name = cnt.strip()
            # 子块: "setting <key>" 前缀优先 (键名可能含冒号, 如 voice:xx)
            if name.startswith("setting "):
                key = name[len("setting "):].strip()
            elif ":" in cnt and not name.endswith(":"):
                # settings 级属性行 (含冒号)
                kv = cnt.split(":", 1)
                val = kv[1]
                comment = val.find(" #")
                if comment != -1:
                    val = val[:comment]
                kwargs[kv[0].strip()] = _unquote(val)
                i += 1
                continue
            elif name.endswith(":"):
                key = name[:-1].strip()
            else:
                key = name
            i += 1
            props = {}
            while i < n:
                ind2, ln2, cnt2 = self.lines[i]
                if ind2 <= ind:
                    break
                kv = cnt2.split(":", 1)
                if len(kv) == 2:
                    val = kv[1]
                    comment = val.find(" #")
                    if comment != -1:
                        val = val[:comment]
                    props[kv[0].strip()] = _unquote(val)
                else:
                    log.w("log.parser.attr_invalid", line=ln2)
                i += 1
            items.append(Statement(op="setting", args=[key],
                                   kwargs=props, line=ln, raw=cnt))
        return Statement(op="settings", args=[], kwargs=kwargs,
                         block=items, line=lineno, raw=content), i
    def _parse_if(self, i, indent, lineno, content):
        # 条件表达式: "if X:" 中的 X
        cond_tokens = _tokenize(content)[1:-1]
        branches = []
        cond, i = self._parse_cond_and_body(i, indent, cond_tokens)
        branches.append(cond)
        else_body = None
        n = len(self.lines)
        while i < n:
            ind, ln, cnt = self.lines[i]
            if ind != indent:
                break
            if cnt.startswith("elif"):
                cond_tokens = _tokenize(cnt)[1:-1]
                c2, i = self._parse_cond_and_body(i, indent, cond_tokens)
                branches.append(c2)
            elif cnt == "else:":
                body, i = self._parse_body(i + 1, indent)
                else_body = body
            elif cnt == "endif":
                i += 1
                break
            else:
                break
        return Statement(
            op="if",
            kwargs={"branches": branches, "else": else_body},
            line=lineno,
            raw=content,
        ), i

    def _parse_cond_and_body(self, i, indent, cond_tokens):
        cond_expr = _tokens_to_text(cond_tokens)
        body, i = self._parse_body(i + 1, indent)
        return (cond_expr, body), i

    def _parse_body(self, i, indent):
        """收集缩进 > indent 的语句, 返回 (body, next_index)。"""
        body = []
        n = len(self.lines)
        while i < n:
            ind, ln, cnt = self.lines[i]
            if ind <= indent:
                break
            stmt, i = self._parse_statement(i, ind)
            if stmt is not None:
                body.append(stmt)
        return body, i

    # -- 对象创建块 (weight/sprite + 属性) -----------------------------
    def _parse_create(self, i, indent, lineno, content, op, rest):
        kwargs = {}
        # 第一个 word 参数是 id (如 "sprite girl")
        ident = None
        if rest and rest[0][0] == "word":
            ident = rest[0][1]
        n = len(self.lines)
        i += 1
        while i < n:
            ind, ln, cnt = self.lines[i]
            if ind <= indent:
                break
            kv = cnt.split(":", 1)
            if len(kv) == 2:
                val = kv[1]
                # 支持行内注释: 值后跟 " #..." (空白+#)
                comment = val.find(" #")
                if comment != -1:
                    val = val[:comment]
                kwargs[kv[0].strip()] = _unquote(val)
            else:
                log.w("log.parser.attr_invalid_value", line=ln, text=cnt)
            i += 1
        return Statement(
            op=op, args=[ident] if ident else [], kwargs=kwargs,
            line=lineno, raw=content,
        ), i


# ----------------------------------------------------------------------
def parse(text: str, path: str = "") -> Script:
    return Parser().parse(text, path)


# 脚本文件解码器 (文件编解码钩子 "script" scope; 引擎构造时绑定,
# 无插件注册时为 None 原样读取)
_SCRIPT_DECODER = None


def set_script_decoder(fn) -> None:
    """插件/引擎 API: 设置 .gal 脚本文件解码器 fn(bytes)->bytes。"""
    global _SCRIPT_DECODER
    _SCRIPT_DECODER = fn


def parse_file(path: str) -> Script:
    with open(path, "rb") as f:
        raw = f.read()
    if _SCRIPT_DECODER is not None:
        raw = _SCRIPT_DECODER(raw)
    text = raw.decode("utf-8-sig")
    return parse(text, path)
