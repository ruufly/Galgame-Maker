"""插件设置项 -> setting.gal (P3): 把插件 settings.register 的
设置项生成到项目设置界面, 实现"插件配置在编辑器完成"闭环。

纯逻辑 (可测试):
- settings_block_of(script): 取 settings 块 (op=='settings')
- ensure_settings_block(script): 无则新建 (插入 import 前)
- ensure_setting_item(block, key, label, detail): 无则添加 setting 子块
- add_plugin_settings(script, caps): 批量添加, 返回新增 key 列表
"""

from framework.engine.parser import Statement

# DSL setting 子块: kwargs 键映射 (值统一字符串)
_KIND_MAP = {"slider": "slider", "checkbox": "checkbox", "cycle": "cycle",
             "input": "input", "keybind": "keybind", "button": "button"}


def settings_block_of(script):
    for stmt in script.statements:
        if stmt.op == "settings":
            return stmt
    return None


def ensure_settings_block(script):
    """无 settings 块则新建 (插入到第一个 import 之前)。"""
    block = settings_block_of(script)
    if block is None:
        block = Statement(op="settings", args=[], kwargs={})
        insert_at = 0
        for i, s in enumerate(script.statements):
            if s.op == "import":
                insert_at = i
                break
        script.statements.insert(insert_at, block)
    return block


def _fmt_value(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (list, tuple)):
        return ", ".join(str(x) for x in v)
    return str(v)


def ensure_setting_item(block, key: str, label: str, detail: dict) -> bool:
    """无该 setting 子块则添加, 返回是否新增。"""
    for item in block.block:
        if item.op == "setting" and item.args and item.args[0] == key:
            return False
    props = {"label": label}
    kind = detail.get("kind", "checkbox")
    props["type"] = _KIND_MAP.get(str(kind), str(kind))
    for dk, dk_key in (("var", "var"), ("default", "default"),
                       ("section", "section"), ("min", "min"),
                       ("max", "max"), ("step", "step"),
                       ("options", "options")):
        if dk in detail:
            props[dk_key] = _fmt_value(detail[dk])
    block.block.append(Statement(op="setting", args=[key], kwargs=props))
    return True


def add_plugin_settings(script, caps: dict) -> list:
    """caps: {插件名: 能力 dict}; 返回新增的 (插件名, key) 列表。"""
    block = ensure_settings_block(script)
    added = []
    for pname, cap in caps.items():
        for key, label in cap.get("settings", []):
            detail = cap.get("settings_detail", {}).get(key, {"label": label})
            if ensure_setting_item(block, key, label, detail):
                added.append((pname, key))
    return added
