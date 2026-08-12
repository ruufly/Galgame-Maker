"""Galgame Maker 编辑器 — .gal 序列化器 (模型 -> 文本)。

设计:
- 与 framework.engine.parser 共享 Statement / Script 结构,
  保证"编辑器模型 = 解析结果" (单一事实来源)。
- serialize() 是纯函数: Script -> .gal 文本。
- 往返保证: parse(serialize(parse(t))) 与 parse(t) 结构等价
  (注释 / 行号 / 空白排版不保留, 属预期; 见 KNOWN_LIMITS)。

已知保真限制 (parser 上游丢弃, 序列化器无法找回):
- 注释与空行 (parser 预处理阶段剥离)
- 普通语句参数的"是否带引号"信息 (按安全规则重引号, 语义不变)
- choice 行内参数 (choice ui_click ...) 被 parser 丢弃
"""

from framework.engine.parser import Script, Statement

# 属性块: 渲染为 "op [id]" + 键值属性行
CREATE_OPS = frozenset({
    "weight", "sprite", "object", "char", "character", "scene", "scenery",
    "window", "config", "title", "style", "selection_style", "menu_bar",
    "plugins", "ui", "sound", "gallery", "language",
})

# 特殊结构块
BLOCK_OPS = frozenset({"choice", "if", "menu", "settings"})

INDENT = "    "  # 4 空格, 与 engine_demo 一致

# 会破坏 tokenize 的字符 (对应 parser._SYMBOLS + 空白 + 引号)
_UNSAFE_CHARS = frozenset(' \t"\'->==!=<=>=<>=:+*/')


def _safe_bare(value: str) -> bool:
    """该值裸写后重新 tokenize 是否得到同一个字符串。

    额外规则: 以 '#' 开头的值 (十六进制颜色) 必须加引号 ——
    framework parser 把键值行中的 " #" (空格+井号) 当行内注释,
    裸写 '#ffffff' 会被吞成空串。
    """
    return (bool(value) and not value.startswith("#")
            and not any(ch in _UNSAFE_CHARS for ch in value))


def _quote(value: str) -> str:
    """双引号字符串 (转义反斜杠与引号)。"""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _fmt_value(value: str) -> str:
    """属性值 / 普通参数: 安全裸 token 原样, 否则加引号。"""
    return value if _safe_bare(value) else _quote(value)


# ----------------------------------------------------------------------
# 各类语句渲染
# ----------------------------------------------------------------------
def _render_kv(key: str, value: str, indent: str) -> str:
    return indent + key + ": " + _fmt_value(value)


def _render_create(stmt: Statement, indent: str) -> list:
    lines = [indent + stmt.op + (" " + stmt.args[0] if stmt.args else "")]
    for k, v in stmt.kwargs.items():
        lines.append(_render_kv(k, v, indent + INDENT))
    return lines


def _render_choice(stmt: Statement, indent: str) -> list:
    lines = [indent + "choice:"]
    for text, target in stmt.kwargs.get("options", []):
        lines.append(indent + INDENT + _quote(text) + " -> " + str(target))
    return lines


def _render_if(stmt: Statement, indent: str) -> list:
    lines = []
    branches = stmt.kwargs.get("branches", [])
    else_body = stmt.kwargs.get("else")
    for idx, (cond, body) in enumerate(branches):
        kw = "if" if idx == 0 else "elif"
        lines.append(indent + kw + " " + str(cond) + ":")
        lines.extend(_render_body(body, indent + INDENT))
    if else_body is not None:
        lines.append(indent + "else:")
        lines.extend(_render_body(else_body, indent + INDENT))
    lines.append(indent + "endif")
    return lines


def _render_menu(stmt: Statement, indent: str) -> list:
    lines = [indent + "menu" + (" " + stmt.args[0] if stmt.args else "")]
    for k, v in stmt.kwargs.items():
        lines.append(_render_kv(k, v, indent + INDENT))
    for btn in stmt.block:
        lines.append(indent + INDENT + btn.op)
        for k, v in btn.kwargs.items():
            lines.append(_render_kv(k, v, indent + INDENT * 2))
    return lines


def _render_settings(stmt: Statement, indent: str) -> list:
    lines = [indent + "settings"]
    for k, v in stmt.kwargs.items():
        lines.append(_render_kv(k, v, indent + INDENT))
    for item in stmt.block:
        key = item.args[0] if item.args else ""
        lines.append(indent + INDENT + "setting " + key)
        for k, v in item.kwargs.items():
            lines.append(_render_kv(k, v, indent + INDENT * 2))
    return lines


def _render_raw(stmt: Statement, indent: str) -> list:
    """raw 代码块 (python:: 等): 代码原样保留, 按块位置重排缩进。"""
    lines = [indent + stmt.op + "::"]
    code = stmt.kwargs.get("code", "")
    raw_lines = code.split("\n")
    # 求代码最小缩进 (排除空行), 用于剥离后再按新位置重排
    inds = []
    for ln in raw_lines:
        stripped = ln.lstrip(" \t")
        if stripped:
            inds.append(len(ln) - len(stripped))
    base = min(inds) if inds else 0
    for ln in raw_lines:
        if ln.strip():
            lines.append(indent + INDENT + ln[base:])
        else:
            lines.append("")          # 空行原样保留
    return lines


def _render_statement(stmt: Statement, indent: str) -> list:
    if stmt.op == "choice":
        return _render_choice(stmt, indent)
    if stmt.op == "if":
        return _render_if(stmt, indent)
    if stmt.op == "menu":
        return _render_menu(stmt, indent)
    if stmt.op == "settings":
        return _render_settings(stmt, indent)
    if stmt.op in CREATE_OPS:
        return _render_create(stmt, indent)
    # raw 代码块: kwargs 含 code 且非属性块
    if "code" in stmt.kwargs:
        return _render_raw(stmt, indent)
    # set: "set name = expr" (expr 已由 parser 用 repr 重构)
    if stmt.op == "set" and len(stmt.args) == 2:
        return [indent + "set " + stmt.args[0] + " = " + stmt.args[1]]
    if stmt.op == "->":
        return [indent + "-> " + " ".join(stmt.args)]
    # 未知属性块 (插件自定义): 兜底按 create 渲染, 不丢数据
    if stmt.kwargs:
        return _render_create(stmt, indent)
    # 普通语句
    parts = [stmt.op] + [_fmt_value(a) for a in stmt.args]
    return [indent + " ".join(parts)]


def _render_body(body: list, indent: str) -> list:
    lines = []
    for stmt in body:
        lines.extend(_render_statement(stmt, indent))
    return lines


# ----------------------------------------------------------------------
# 入口
# ----------------------------------------------------------------------
def serialize(script: Script) -> str:
    """Script -> .gal 文本。"""
    lines: list = []
    # 元信息
    for key in ("name", "author", "copyright"):
        if key in script.meta:
            lines.append(key + ": " + _fmt_value(str(script.meta[key])))
    # widgets/functions 目录声明
    if script.widgets_dir:
        lines.append("widgets @ " + _quote(script.widgets_dir))
    if script.functions_dir:
        lines.append("functions @ " + _quote(script.functions_dir))
    # 顶层语句
    for stmt in script.statements:
        lines.extend(_render_statement(stmt, ""))
    # 标签 (语义: 标签按名跳转, 顺序不影响执行, 按解析顺序输出)
    for label, body in script.labels.items():
        if lines and lines[-1] != "":
            lines.append("")
        lines.append(label + ":")
        lines.extend(_render_body(body, INDENT))
    return "\n".join(lines) + "\n"
