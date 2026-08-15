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
from editor.i18n import t

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
    "commands": "plugins.cap_commands", "actions": "plugins.cap_actions",
    "transitions": "plugins.cap_transitions",
    "sprite_effects": "plugins.cap_sprite_effects",
    "text_modes": "plugins.cap_text_modes",
    "settings": "plugins.cap_settings", "keybinds": "plugins.cap_keybinds",
    "menu_buttons": "plugins.cap_menu_buttons",
    "events": "plugins.cap_events",
    "blocks": "plugins.cap_blocks",
}


def _add_kv(parent, key, values):
    if not values:
        return
    item = QTreeWidgetItem([t(_CAP_LABELS.get(key, key)), ""])
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

        info = QLabel(t("plugins.info"))
        info.setStyleSheet("color:#888;")
        layout.addWidget(info)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels([t("plugins.cap"), t("plugins.content")])
        self.tree.header().setStretchLastSection(True)
        self.tree.setColumnWidth(0, 220)
        layout.addWidget(self.tree, 1)

        # plugins 块配置
        form = QFormLayout()
        self.ed_only = QLineEdit()
        self.ed_only.setPlaceholderText(t("plugins.only_hint"))
        self.ed_except = QLineEdit()
        self.ed_except.setPlaceholderText(t("plugins.except_hint"))
        form.addRow(t("plugins.only"), self.ed_only)
        form.addRow(t("plugins.except"), self.ed_except)
        btn_save = QPushButton(t("plugins.save"))
        btn_save.clicked.connect(self._save_plugins_block)
        layout.addLayout(form)
        row = QHBoxLayout()
        btn_gen = QPushButton(t("plugins.gen_settings"))
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
        kernel = QTreeWidgetItem([t("plugins.kernel"), ""])
        kernel.setForeground(0, Qt.darkBlue)
        _add_kv(kernel, "commands", KERNEL_COMMANDS)
        _add_kv(kernel, "blocks", KERNEL_BLOCKS)
        _add_kv(kernel, "events", KERNEL_EVENTS)
        _add_kv(kernel, "actions", KERNEL_ACTIONS)
        self.tree.addTopLevelItem(kernel)
        kernel.setExpanded(True)

        # 2. 插件 (editor/plugins 注册中心, 插件主动注册)
        plug_root = QTreeWidgetItem([t("plugins.plugins_root"), ""])
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
            QTreeWidgetItem(plug_root, [t("plugins.none"), ""])
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
            self.log.emit(t("plugins.no_project"))
            return
        caps = {name: {
            "settings": [(k, d.get("label", k))
                         for k, d in reg.settings.items()],
            "settings_detail": dict(reg.settings),
        } for name, reg in registry.plugins().items()}
        total = sum(len(c.get("settings", [])) for c in caps.values())
        if total == 0:
            self.log.emit(t("plugins.no_registered_settings"))
            return
        script = self.project.scripts.get("setting.gal")
        if script is None:
            self.log.emit(t("plugins.no_setting_gal"))
            return
        added = add_plugin_settings(script, caps)
        if added:
            save_script(script, os.path.join(self.project.root, "setting.gal"))
            self.log.emit(t("plugins.settings_generated",
                            n=len(added),
                            names=", ".join("%s.%s" % (p, k)
                                            for p, k in added)))
        else:
            self.log.emit(t("plugins.settings_exist"))

    def _save_plugins_block(self):
        got = self._plugins_script()
        if got is None:
            self.log.emit(t("plugins.no_project"))
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
        self.log.emit(t("plugins.saved"))
