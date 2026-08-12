"""结构比较工具: 丢弃 line/raw 的归一化 + 相等比较。

主窗口"校验项目"与测试共用; 归一化后比较等价于
"解析 -> 序列化 -> 再解析" 的结构一致性。
"""

from framework.engine.parser import Script, Statement


def norm_value(v):
    if isinstance(v, Statement):
        return norm_stmt(v)
    if isinstance(v, list):
        return [norm_value(x) for x in v]
    if isinstance(v, tuple):
        return tuple(norm_value(x) for x in v)
    if isinstance(v, dict):
        return {k: norm_value(x) for k, x in v.items()}
    return v


def norm_stmt(stmt: Statement) -> dict:
    return {
        "op": stmt.op,
        "args": list(stmt.args),
        "kwargs": {k: norm_value(v) for k, v in stmt.kwargs.items()},
        "block": [norm_stmt(s) for s in stmt.block],
    }


def norm_script(script: Script) -> dict:
    return {
        "name": script.name,
        "meta": dict(script.meta),
        "widgets_dir": script.widgets_dir,
        "functions_dir": script.functions_dir,
        "statements": [norm_stmt(s) for s in script.statements],
        "labels": {k: [norm_stmt(s) for s in body]
                   for k, body in script.labels.items()},
    }


def roundtrip_ok(script: Script) -> bool:
    """该 Script 序列化后重新解析是否结构等价。"""
    from editor.serializer import serialize
    from framework.engine.parser import parse
    text = serialize(script)
    return norm_script(script) == norm_script(parse(text))
