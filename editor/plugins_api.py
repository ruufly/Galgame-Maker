"""编辑器插件 API（责任反转）。

设计原则:
- 编辑器只提供**注册点** (PluginRegistry), 不分析插件源码
- 插件在 editor/plugins/<名>.py 中主动调用 API, 声明自己的
  指令参数表单 / 动作候选 / 文字模式 / 设置项 / 元信息等
- 编辑器 UI (action 参数提示 / 插件面板 / 设置项生成) 只查询注册中心
- framework/plugins 的每个插件在 editor/plugins 有对应文件 (内置);
  自定义插件通过 文件->导入插件 安装 (.galpkg)

内置插件对应的 editor/plugins/<名>.py 写法::

    from editor.plugins_api import registry

    def setup(reg):
        p = reg.register_plugin("fx", meta={"name": "fx",
                                            "description": "屏幕特效"})
        p.add_command("shake", params=[("时长 (秒)", "number", "0.3"),
                                       ("幅度 (像素)", "int", "8")])
        p.add_action("my_action")
"""

import importlib.util
import os
from dataclasses import dataclass, field


@dataclass
class PluginRegistration:
    """一个插件在编辑器侧的注册信息。"""

    name: str
    meta: dict = field(default_factory=dict)          # main.yml / 内置元信息
    commands: dict = field(default_factory=dict)      # 指令名 -> 参数表单
    actions: list = field(default_factory=list)       # do_action 候选
    transitions: list = field(default_factory=list)   # 背景过渡
    sprite_effects: list = field(default_factory=list)  # 立绘效果
    text_modes: list = field(default_factory=list)    # 文字模式
    settings: dict = field(default_factory=dict)      # 设置项 key -> detail
    keybinds: list = field(default_factory=list)      # (name, label)
    menu_buttons: list = field(default_factory=list)
    events: list = field(default_factory=list)        # 事件监听

    # ---- 链式注册 API ------------------------------------------------
    def add_command(self, cmd: str, params: list | None = None):
        self.commands[cmd] = list(params or [])
        return self

    def add_commands(self, *cmds: str):
        for c in cmds:
            self.commands[c] = []
        return self

    def add_action(self, *names: str):
        self.actions.extend(names)
        return self

    def add_transition(self, *names: str):
        self.transitions.extend(names)
        return self

    def add_sprite_effect(self, *names: str):
        self.sprite_effects.extend(names)
        return self

    def add_text_mode(self, *names: str):
        self.text_modes.extend(names)
        return self

    def add_setting(self, key: str, label: str, **detail):
        d = {"label": label}
        d.update(detail)
        self.settings[key] = d
        return self

    def add_keybind(self, name: str, label: str):
        self.keybinds.append((name, label))
        return self

    def add_menu_button(self, mid: str):
        self.menu_buttons.append(mid)
        return self

    def add_event(self, *events: str):
        self.events.extend(events)
        return self


class PluginRegistry:
    """编辑器插件注册中心。"""

    def __init__(self):
        self._plugins: dict[str, PluginRegistration] = {}

    # ---- 注册 ---------------------------------------------------------
    def register_plugin(self, name: str, meta: dict | None = None
                        ) -> PluginRegistration:
        if name not in self._plugins:
            self._plugins[name] = PluginRegistration(name=name,
                                                     meta=dict(meta or {}))
        else:
            self._plugins[name].meta.update(meta or {})
        return self._plugins[name]

    def unregister_plugin(self, name: str):
        self._plugins.pop(name, None)

    # ---- 查询 (UI 只读) ----------------------------------------------
    def plugins(self) -> dict:
        return dict(self._plugins)

    def get(self, name: str) -> PluginRegistration | None:
        return self._plugins.get(name)

    def command_params(self, op: str) -> list | None:
        """指令参数表单; 未注册返回 None。"""
        for p in self._plugins.values():
            if op in p.commands:
                return p.commands[op]
        return None

    def has_command(self, op: str) -> bool:
        return self.command_params(op) is not None

    def actions(self) -> list:
        out = []
        for p in self._plugins.values():
            out.extend(p.actions)
        return _dedup(out)

    def text_modes(self) -> list:
        out = []
        for p in self._plugins.values():
            out.extend(p.text_modes)
        return _dedup(out)

    def transitions(self) -> list:
        out = []
        for p in self._plugins.values():
            out.extend(p.transitions)
        return _dedup(out)

    def namespaces(self) -> list:
        """有指令注册的插件命名空间 (using 候选)。"""
        return sorted(n for n, p in self._plugins.items() if p.commands)

    def settings_meta(self) -> dict:
        out = {}
        for p in self._plugins.values():
            out.update(p.settings)
        return out

    def all_settings(self) -> list:
        return [(key, d.get("label", key)) for key, d
                in self.settings_meta().items()]


def _dedup(items):
    seen, out = set(), []
    for it in items:
        if it not in seen:
            seen.add(it)
            out.append(it)
    return out


# 全局注册中心 (编辑器单例)
registry = PluginRegistry()


# ----------------------------------------------------------------------
# 加载器: 加载 editor/plugins/<名>.py 并调用其 setup(registry)
# ----------------------------------------------------------------------
def load_editor_plugins(directory: str) -> list:
    """加载目录下全部插件接口文件, 返回已加载插件名列表。"""
    loaded = []
    if not os.path.isdir(directory):
        return loaded
    for f in sorted(os.listdir(directory)):
        if f.startswith("_") or not f.endswith(".py"):
            continue
        name = f[:-3]
        path = os.path.join(directory, f)
        try:
            spec = importlib.util.spec_from_file_location(
                "editor.plugins.%s" % name, path)
            if spec is None or spec.loader is None:
                continue
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            setup = getattr(mod, "setup", None)
            if callable(setup):
                setup(registry)
            loaded.append(name)
        except Exception as exc:  # 插件接口异常不应拖垮编辑器
            print("[editor-plugin] 加载失败 %s: %s" % (name, exc))
    return loaded
