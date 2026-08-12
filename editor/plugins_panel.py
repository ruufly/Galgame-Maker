"""插件面板 (P3): 区分 内核提供 / 插件提供 的能力 + 项目插件配置。

- 能力总览树:
  引擎内核 (framework 内置 DSL/属性块/事件/动作)
  插件 (framework/plugins/*.py, AST 自动发现能力)
  项目插件 (项目 plugins/ 目录)
- 项目 plugins 块配置 (only/except) + 保存
"""

import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QComboBox, QFormLayout, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QTreeWidget,
                               QTreeWidgetItem, QVBoxLayout, QWidget)

from editor.plugins_api import registry
from editor.project_settings import save_script
from editor.plugin_settings import add_plugin_settings

# ----------------------------------------------------------------------
# 内核能力清单 (framework/engine, 随框架版本)
# ----------------------------------------------------------------------
KERNEL_COMMANDS = [
    "text", "nar", "say", "bg", "show", "hide", "move", "rotate", "flip",
    "clear", "choice", "confirm", "set", "if", "jump", "call", "return",
    "sleep", "typing", "music", "sfx", "volume", "pause", "resume", "stop",
    "save", "load", "fade", "fadeout", "ending", "using", "plugin",
    "fullscreen", "import", "read_settings",
]
KERNEL_BLOCKS = [
    "window", "language", "plugins", "title", "menu", "menu_bar", "style",
    "selection_style", "ui", "char", "scene", "sound", "settings",
    "window config",
]
KERNEL_EVENTS = [
    "engine_start", "script_load", "script_block", "label_enter",
    "statement", "text_show", "choice_show", "choice_prepare", "bg_change",
    "scene_change", "sprite_show", "var_set", "music_play", "save", "load",
    "confirm_show", "action", "draw_overlay", "error",
]
KERNEL_ACTIONS = ["start", "quit", "title", "continue", "slot_menu",
                  "save", "load", "close"]

_CAP_LABELS = {
    "commands": "DSL 指令", "actions": "动作", "transitions": "背景过渡",
    "sprite_effects": "立绘效果", "text_modes": "文字模式",
    "settings": "设置项", "keybinds": "快捷键", "menu_buttons": "菜单按钮",
    "events": "事件监听",
}


def _add_kv(parent, key, values):
    if not values:
        return
    item = QTreeWidgetItem([_CAP_LABELS.get(key, key), ""])
    if isinstance(values, list):
        if values and isinstance(values[0], (list, tuple)):
            text = ", ".join("%s (%s)" % (k, l) for k, l in values)
        else:
            text = ", ".join(str(v) for v in values)
    else:
        text = str(values)
    child = QTreeWidgetItem(["", text])
    child.setForeground(1, Qt.gray)
    item.addChild(child)
    parent.addChild(item)


class PluginsPanel(QWidget):
    """插件能力总览 + 项目插件装载配置。"""

    log = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.project = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)

        info = QLabel("能力来源区分: 引擎内核 (framework/engine) 与插件 "
                      "(framework/plugins + 项目 plugins/)")
        info.setStyleSheet("color:#888;")
        layout.addWidget(info)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["能力", "内容"])
        self.tree.header().setStretchLastSection(True)
        self.tree.setColumnWidth(0, 220)
        layout.addWidget(self.tree, 1)

        # plugins 块配置
        form = QFormLayout()
        self.ed_only = QLineEdit()
        self.ed_only.setPlaceholderText("只装载, 逗号分隔 (留空 = 全部)")
        self.ed_except = QLineEdit()
        self.ed_except.setPlaceholderText("排除, 逗号分隔 (留空 = 不排除)")
        form.addRow("只装载 (only)", self.ed_only)
        form.addRow("排除 (except)", self.ed_except)
        btn_save = QPushButton("保存 plugins 配置")
        btn_save.clicked.connect(self._save_plugins_block)
        layout.addLayout(form)
        row = QHBoxLayout()
        btn_gen = QPushButton("生成插件设置项 → setting.gal")
        btn_gen.clicked.connect(self._gen_settings)
        row.addWidget(btn_gen)
        row.addStretch(1)
        layout.addLayout(row)
        layout.addWidget(btn_save)

    # ---- 数据 ---------------------------------------------------------
    def set_project(self, project) -> None:
        self.project = project
        self.refresh()
        self._load_plugins_block()

    def refresh(self) -> None:
        self.tree.clear()

        # 1. 引擎内核
        kernel = QTreeWidgetItem(["引擎内核 (framework/engine)", ""])
        kernel.setForeground(0, Qt.darkBlue)
        _add_kv(kernel, "commands", KERNEL_COMMANDS)
        _add_kv(kernel, "blocks", KERNEL_BLOCKS)
        _add_kv(kernel, "events", KERNEL_EVENTS)
        _add_kv(kernel, "actions", KERNEL_ACTIONS)
        self.tree.addTopLevelItem(kernel)
        kernel.setExpanded(True)

        # 2. 插件 (editor/plugins 注册中心, 插件主动注册)
        plug_root = QTreeWidgetItem(["插件 (editor/plugins 注册)", ""])
        plug_root.setForeground(0, Qt.darkGreen)
        for name, reg in registry.plugins().items():
            cap = {
                "commands": list(reg.commands),
                "actions": reg.actions,
                "transitions": reg.transitions,
                "sprite_effects": reg.sprite_effects,
                "text_modes": reg.text_modes,
                "settings": [(k, d.get("label", k))
                             for k, d in reg.settings.items()],
                "keybinds": reg.keybinds,
                "menu_buttons": reg.menu_buttons,
                "events": reg.events,
            }
            self._add_plugin(plug_root, name, cap)
        if not registry.plugins():
            QTreeWidgetItem(plug_root, ["(无)", ""])
        self.tree.addTopLevelItem(plug_root)
        plug_root.setExpanded(True)

    def _add_plugin(self, parent, name, cap):
        p = QTreeWidgetItem(["%s" % name, ""])
        p.setForeground(0, Qt.darkGreen)
        for key in ("commands", "actions", "transitions", "sprite_effects",
                    "text_modes", "settings", "keybinds", "menu_buttons",
                    "events"):
            _add_kv(p, key, cap.get(key, []))
        parent.addChild(p)
        p.setExpanded(False)

    # ---- plugins 块配置 ----------------------------------------------
    def _plugins_script(self):
        if self.project is None:
            return None
        script = self.project.main_script()
        if script is None:
            return None
        for stmt in script.statements:
            if stmt.op == "plugins":
                return script, stmt
        from framework.engine.parser import Statement
        stmt = Statement(op="plugins", args=[], kwargs={})
        script.statements.append(stmt)
        return script, stmt

    def _load_plugins_block(self):
        got = self._plugins_script()
        if got is None:
            return
        _s, stmt = got
        self.ed_only.setText(str(stmt.kwargs.get("only", "")))
        self.ed_except.setText(str(stmt.kwargs.get("except", "")))

    def _gen_settings(self):
        """把全部插件注册的设置项写入 setting.gal 的 settings 块。"""
        if self.project is None:
            self.log.emit("请先打开项目")
            return
        caps = {name: {
            "settings": [(k, d.get("label", k))
                         for k, d in reg.settings.items()],
            "settings_detail": dict(reg.settings),
        } for name, reg in registry.plugins().items()}
        total = sum(len(c.get("settings", [])) for c in caps.values())
        if total == 0:
            self.log.emit("当前插件未注册设置项 (插件可在编辑器接口用 "
                          "add_setting 注册)")
            return
        script = self.project.scripts.get("setting.gal")
        if script is None:
            self.log.emit("项目缺少 setting.gal, 跳过")
            return
        added = add_plugin_settings(script, caps)
        if added:
            save_script(script, os.path.join(self.project.root, "setting.gal"))
            self.log.emit("已生成 %d 个插件设置项: %s"
                          % (len(added),
                             ", ".join("%s.%s" % (p, k) for p, k in added)))
        else:
            self.log.emit("插件设置项均已存在, 无新增")

    def _save_plugins_block(self):
        got = self._plugins_script()
        if got is None:
            self.log.emit("请先打开项目")
            return
        script, stmt = got
        only = self.ed_only.text().strip()
        except_ = self.ed_except.text().strip()
        stmt.kwargs.pop("only", None)
        stmt.kwargs.pop("except", None)
        if only:
            stmt.kwargs["only"] = only
        if except_:
            stmt.kwargs["except"] = except_
        save_script(script, os.path.join(self.project.root, self.project.main))
        self.log.emit("plugins 配置已保存")
