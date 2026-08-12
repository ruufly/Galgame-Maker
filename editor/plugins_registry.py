"""插件能力注册表 (P3): 静态扫描插件源码, 自动发现其能力。

设计目标:
- 编辑器区分 内核提供 与 插件提供 的功能
- 插件开发者写好插件放入 plugins/ 后, 编辑器自动识别其:
  指令 (@command / add_command) / 事件监听 (@event_listener / listen)
  动作 (register_action) / 过渡 (display.register_transition)
  立绘效果 (display.register_sprite_effect) / 文字模式
  (display.register_text_mode) / 设置项 (settings.register)
  快捷键 (keybinds.register) / 菜单按钮 (register_menu_button)

实现: 用 ast 遍历插件源码, 提取注册调用 (不执行插件代码, 无副作用)。
"""

import ast
import os
import re


def _call_name(node):
    """调用目标名: ast.Name / ast.Attribute (display.register_transition)。"""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _call_name(node.value)
        return ("%s.%s" % (base, node.attr)) if base else node.attr
    return ""


def _str_literal_args(node):
    """位置参数中的字符串字面量。"""
    out = []
    for a in node.args:
        if isinstance(a, ast.Constant) and isinstance(a.value, str):
            out.append(a.value)
    return out


def _kw_str(node, key):
    for kw in node.keywords:
        if kw.arg == key and isinstance(kw.value, ast.Constant) \
                and isinstance(kw.value.value, str):
            return kw.value.value
    return None


def scan_plugin_source(source: str) -> dict:
    """扫描插件源码, 返回能力 dict。

    含轻量常量传播: 收集 简单赋值 / for 循环字面量 / 类 name 属性,
    以解析 `register_sprite_effect(name, ...)` 与 `cls.name` 形式。
    """
    cap = {
        "commands": [],       # DSL 指令名
        "actions": [],        # 选择列表动作
        "transitions": [],    # 背景过渡
        "sprite_effects": [], # 立绘登场/退场效果
        "text_modes": [],     # 文字显示模式
        "settings": [],       # (key, label) 设置项
        "keybinds": [],       # (name, label) 快捷键
        "menu_buttons": [],   # 菜单按钮 mid
        "events": [],         # 监听的事件名
        "settings_detail": {},  # key -> {kind/min/max/step/options/section/var/default}
        "command_params": {},   # 指令名 -> docstring 参数名列表 (<名称> 约定)
    }
    tree = ast.parse(source)

    # ---- 轻量常量传播 ----
    var_map = {}        # 变量名 -> [字符串 或 ("class", 类名)]
    class_names = {}    # 类名 -> {属性: 值}

    def _record(name, value):
        var_map.setdefault(name, []).append(value)

    def _collect_module_assigns(node):
        """递归收集 模块级 (非类/函数内) 的字符串赋值, 避免
        类属性 name="custom_actions" 污染循环变量收集。"""
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.ClassDef, ast.FunctionDef,
                                  ast.AsyncFunctionDef, ast.Lambda)):
                continue
            if isinstance(child, ast.Assign):
                for t in child.targets:
                    if (isinstance(t, ast.Name)
                            and isinstance(child.value, ast.Constant)
                            and isinstance(child.value.value, str)):
                        _record(t.id, child.value.value)
            _collect_module_assigns(child)

    _collect_module_assigns(tree)

    for node in ast.walk(tree):
        if isinstance(node, ast.For) and isinstance(node.iter, ast.Tuple):
            # 目标: 单变量或元组解包 (for name, fn, dur in ...)
            target_names = []
            if isinstance(node.target, ast.Name):
                target_names = [node.target.id]
            elif isinstance(node.target, ast.Tuple):
                target_names = [t.id for t in node.target.elts
                                if isinstance(t, ast.Name)]
            for elt in node.iter.elts:
                if isinstance(elt, ast.Tuple) and elt.elts:
                    first = elt.elts[0]
                    if isinstance(first, ast.Constant) \
                            and isinstance(first.value, str):
                        for tn in target_names:
                            _record(tn, first.value)
                    elif isinstance(first, ast.Name):
                        for tn in target_names:
                            _record(tn, ("class", first.id))
                elif isinstance(elt, ast.Name):
                    for tn in target_names:
                        _record(tn, ("class", elt.id))
        elif isinstance(node, ast.ClassDef):
            info = {}
            for stmt in node.body:
                if isinstance(stmt, ast.Assign):
                    for t in stmt.targets:
                        if isinstance(t, ast.Name) \
                                and isinstance(stmt.value, ast.Constant):
                            info[t.id] = stmt.value.value
            if info:
                class_names[node.name] = info

    def _arg_values(arg):
        """参数 -> 可能的字符串值列表。"""
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            return [arg.value]
        if isinstance(arg, ast.Name):
            out = []
            for v in var_map.get(arg.id, []):
                if isinstance(v, str):
                    out.append(v)
                elif isinstance(v, tuple) and v[0] == "class":
                    cn = class_names.get(v[1], {})
                    if "name" in cn:
                        out.append(cn["name"])
            return out
        if isinstance(arg, ast.Attribute) and arg.attr == "name" \
                and isinstance(arg.value, ast.Name):
            out = []
            refs = var_map.get(arg.value.id, [])
            for v in refs:
                if isinstance(v, tuple) and v[0] == "class":
                    cn = class_names.get(v[1], {})
                    if "name" in cn:
                        out.append(cn["name"])
            return out
        return []

    def _kw_value(node, key):
        """关键字参数中的常量值 (数字/字符串/列表/负数字面量)。"""
        for kw in node.keywords:
            if kw.arg != key:
                continue
            v = kw.value
            if isinstance(v, ast.Constant):
                return v.value
            if isinstance(v, (ast.List, ast.Tuple)):
                return [e.value for e in v.elts
                        if isinstance(e, ast.Constant)]
            if isinstance(v, ast.UnaryOp) and isinstance(v.op, ast.USub) \
                    and isinstance(v.operand, ast.Constant):
                return -v.operand.value
        return None

    # ---- 注册调用识别 ----
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            doc = ast.get_docstring(node) or ""
            doc_params = re.findall(r"<([^<>]+)>", doc)
            for dec in node.decorator_list:
                name = (_call_name(dec.func)
                        if isinstance(dec, ast.Call) else _call_name(dec))
                if name == "command":
                    for a in dec.args:
                        for v in _arg_values(a):
                            cap["commands"].append(v)
                            if doc_params:
                                cap["command_params"][v] = doc_params
                elif name == "event_listener":
                    for a in dec.args:
                        cap["events"] += _arg_values(a)
        if isinstance(node, ast.Call):
            fname = _call_name(node.func)
            if fname.startswith("self."):
                fname = fname[len("self."):]
            if not node.args:
                continue
            first_vals = _arg_values(node.args[0])
            if fname == "command" and first_vals:
                cap["commands"] += first_vals
            elif fname in ("event_listener", "listen") and first_vals:
                cap["events"] += first_vals
            elif fname in ("register_action",
                           "engine.register_action") and first_vals:
                cap["actions"] += first_vals
            elif fname in ("register_transition",
                           "display.register_transition",
                           "engine.display.register_transition") \
                    and first_vals:
                cap["transitions"] += first_vals
            elif fname in ("register_sprite_effect",
                           "display.register_sprite_effect",
                           "engine.display.register_sprite_effect") \
                    and first_vals:
                cap["sprite_effects"] += first_vals
            elif fname in ("register_text_mode",
                           "display.register_text_mode",
                           "engine.display.register_text_mode") \
                    and first_vals:
                cap["text_modes"] += first_vals
            elif fname in ("settings.register",
                           "engine.settings.register"):
                if first_vals:
                    key0 = first_vals[0]
                    label = _kw_str(node, "label") or (
                        _arg_values(node.args[1])[0]
                        if len(node.args) > 1 else key0)
                    cap["settings"].append((key0, label))
                    detail = {"label": label}
                    for k in ("kind", "var", "default", "section",
                              "min", "max", "step"):
                        v = _kw_value(node, k)
                        if v is not None:
                            detail[k] = v
                    opts = _kw_value(node, "options")
                    if opts:
                        detail["options"] = opts
                    cap["settings_detail"][key0] = detail
            elif fname in ("keybinds.register",
                           "engine.keybinds.register"):
                if first_vals:
                    label = _kw_str(node, "label") or (
                        _arg_values(node.args[1])[0]
                        if len(node.args) > 1 else first_vals[0])
                    cap["keybinds"].append((first_vals[0], label))
            elif fname in ("register_menu_button",
                           "engine.register_menu_button") and first_vals:
                cap["menu_buttons"] += first_vals
            elif fname == "add_command" and first_vals:
                cap["commands"] += first_vals

    # 去重保序
    for key in ("settings", "keybinds"):
        seen, out = set(), []
        for item in cap[key]:
            if item[0] not in seen:
                seen.add(item[0])
                out.append(item)
        cap[key] = out
    for key in ("commands", "actions", "transitions", "sprite_effects",
                "text_modes", "menu_buttons", "events"):
        seen, out = set(), []
        for item in cap[key]:
            if item not in seen:
                seen.add(item)
                out.append(item)
        cap[key] = out
    return cap


def scan_plugin_file(path: str) -> dict | None:
    """扫描插件文件; 以下划线开头或非 .py 返回 None。"""
    name = os.path.basename(path)
    if name.startswith("_") or not name.endswith(".py"):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return scan_plugin_source(f.read())
    except (OSError, SyntaxError):
        return None


def scan_plugins_dir(directory: str) -> dict:
    """扫描插件目录: {插件名: 能力 dict}。"""
    out = {}
    if not os.path.isdir(directory):
        return out
    for f in sorted(os.listdir(directory)):
        if f.startswith("_") or not f.endswith(".py"):
            continue
        path = os.path.join(directory, f)
        cap = scan_plugin_file(path)
        if cap is not None:
            out[f[:-3]] = cap
    return out


# 内置插件目录 (framework 子模块)
def framework_plugins_dir():
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(here, "framework", "plugins")
