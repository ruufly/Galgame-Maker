"""项目设置 (P2): window 块表单化编辑。

核心逻辑 (可测试, 不依赖 Qt):
- get_window_block(script): 找主 window 块语句
- apply_window_values(stmt, values): 把表单值写回 kwargs
- save_script(script, path): 序列化写盘

ProjectSettingsDialog: 分组表单 (常规 / 确认框 / 按键 / 菜单文案),
OK 后写回模型并落盘。
"""

import os

from PySide6.QtWidgets import (QCheckBox, QDialog, QDoubleSpinBox, QFileDialog,
                               QFormLayout, QGroupBox, QHBoxLayout, QLabel,
                               QLineEdit, QMessageBox, QPushButton, QSpinBox,
                               QTabWidget, QVBoxLayout, QWidget)

from editor.serializer import serialize

_TRUE = ("true", "1", "yes", "on")


# ----------------------------------------------------------------------
# 纯逻辑 (可测试)
# ----------------------------------------------------------------------
def get_window_block(script):
    """主 window 块 (op=='window' 且无 args, 即非 window config)。"""
    for stmt in script.statements:
        if stmt.op == "window" and not stmt.args:
            return stmt
    return None


def bool_to_gal(v: bool) -> str:
    return "true" if v else "false"


def gal_to_bool(v) -> bool:
    return str(v).lower() in _TRUE


def apply_window_values(stmt, values: dict) -> None:
    """把表单值 dict 写回 window 块 kwargs (值统一为字符串)。"""
    for key, value in values.items():
        stmt.kwargs[key] = value


def save_script(script, path: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(serialize(script))


# ----------------------------------------------------------------------
# 对话框
# ----------------------------------------------------------------------
class ProjectSettingsDialog(QDialog):
    """项目设置: 编辑主脚本 window 块 (标题/窗口/确认框/按键/菜单文案)。"""

    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.project = project
        self.setWindowTitle("项目设置 — %s" % os.path.basename(project.root))
        self.setMinimumWidth(520)

        self.script = project.main_script()
        self.block = get_window_block(self.script) if self.script else None
        if self.block is None:
            # 主脚本没有 window 块: 允许新建 (保存时插入到顶层)
            self.block = None

        from editor.lang_dialog import make_lang_edit_widget
        from editor.lang_utils import GameLang
        self._gl = GameLang(project.root, project.main_script()) \
            if project is not None else None

        k = self.block.kwargs if self.block else {}

        tabs = QTabWidget(self)
        tabs.addTab(self._tab_general(k), "常规")
        tabs.addTab(self._tab_confirm(k), "确认框")
        tabs.addTab(self._tab_keys(k), "按键")
        tabs.addTab(self._tab_menu(k), "菜单文案")

        btns = QHBoxLayout()
        btn_ok = QPushButton("保存")
        btn_cancel = QPushButton("取消")
        btn_ok.clicked.connect(self._save)
        btn_cancel.clicked.connect(self.reject)
        btns.addStretch(1)
        btns.addWidget(btn_ok)
        btns.addWidget(btn_cancel)

        layout = QVBoxLayout(self)
        layout.addWidget(tabs, 1)
        layout.addLayout(btns)

    # ---- 表单构建 -----------------------------------------------------
    def _tab_general(self, k):
        box = QGroupBox("窗口与常规")
        form = QFormLayout(box)

        self.ed_title, self._title_getter = make_lang_edit_widget(
            self._gl, str(k.get("title", "")))
        form.addRow("窗口标题", self.ed_title)

        self.sp_w = QSpinBox(); self.sp_w.setRange(320, 7680)
        self.sp_w.setValue(_int(k.get("width", 1280)))
        self.sp_h = QSpinBox(); self.sp_h.setRange(240, 4320)
        self.sp_h.setValue(_int(k.get("height", 720)))
        row = QHBoxLayout(); row.addWidget(self.sp_w); row.addWidget(QLabel("×")); row.addWidget(self.sp_h)
        form.addRow("逻辑分辨率 (宽×高)", row)

        self.sp_fps = QSpinBox(); self.sp_fps.setRange(15, 240)
        self.sp_fps.setValue(_int(k.get("fps", 60)))
        form.addRow("帧率", self.sp_fps)

        icon_row = QHBoxLayout()
        self.ed_icon = QLineEdit(str(k.get("icon", "")))
        btn_icon = QPushButton("浏览…")
        btn_icon.clicked.connect(self._browse_icon)
        icon_row.addWidget(self.ed_icon, 1)
        icon_row.addWidget(btn_icon)
        form.addRow("窗口图标", icon_row)

        self.chk_fullscreen = QCheckBox("全屏启动")
        self.chk_fullscreen.setChecked(gal_to_bool(k.get("fullscreen", "false")))
        self.chk_resizable = QCheckBox("允许拖拽缩放窗口 (内容等比)")
        self.chk_resizable.setChecked(gal_to_bool(k.get("resizable", "true")))
        form.addRow("", self.chk_fullscreen)
        form.addRow("", self.chk_resizable)

        self.sp_slots = QSpinBox(); self.sp_slots.setRange(1, 99)
        self.sp_slots.setValue(_int(k.get("save_slots", 6)))
        form.addRow("存档槽位数", self.sp_slots)

        self.sp_fade = QDoubleSpinBox(); self.sp_fade.setRange(0, 10)
        self.sp_fade.setSingleStep(0.1)
        self.sp_fade.setValue(float(k.get("music_fade", 1.0)))
        form.addRow("BGM 淡入淡出 (秒)", self.sp_fade)

        self.ed_click = QLineEdit(str(k.get("ui_click_sound", "")))
        self.ed_click.setPlaceholderText("如: sfx_click")
        form.addRow("全局 UI 点击音", self.ed_click)

        wrap = QVBoxLayout()
        wrap.addWidget(box)
        wrap.addStretch(1)
        w = QWidget(); w.setLayout(wrap)
        return w

    def _tab_confirm(self, k):
        box = QGroupBox("确认框 (退出/读档/返回标题)")
        form = QFormLayout(box)
        self.conf = {}
        for key, label in (("confirm_quit", "退出游戏"), ("confirm_load", "读取存档"),
                           ("confirm_title", "返回标题")):
            chk = QCheckBox("启用「%s」确认框" % label)
            # 引擎默认不启用确认框 (False); 未配置时保持关闭,
            # 避免"不改动直接保存"意外开启弹窗
            chk.setChecked(gal_to_bool(k.get(key, "false")))
            text_w, text_g = make_lang_edit_widget(
                self._gl, str(k.get(key + "_text", "")))
            yes_w, yes_g = make_lang_edit_widget(
                self._gl, str(k.get(key + "_yes", "")))
            no_w, no_g = make_lang_edit_widget(
                self._gl, str(k.get(key + "_no", "")))
            form.addRow(chk, text_w)
            form.addRow("    确定按钮", yes_w)
            form.addRow("    取消按钮", no_w)
            self.conf[key] = (chk, (text_w, text_g), (yes_w, yes_g),
                              (no_w, no_g))
        wrap = QVBoxLayout()
        wrap.addWidget(box)
        wrap.addStretch(1)
        w = QWidget(); w.setLayout(wrap)
        return w

    def _tab_keys(self, k):
        box = QGroupBox("键盘导航 (逗号分隔多键, 如 up, w)")
        form = QFormLayout(box)
        self.keys = {}
        for key, label in (("key_up", "上移"), ("key_down", "下移"),
                           ("key_left", "左移"), ("key_right", "右移"),
                           ("key_confirm", "确认")):
            ed = QLineEdit(str(k.get(key, "")))
            form.addRow(label, ed)
            self.keys[key] = ed
        wrap = QVBoxLayout()
        wrap.addWidget(box)
        wrap.addStretch(1)
        w = QWidget(); w.setLayout(wrap)
        return w

    def _tab_menu(self, k):
        box = QGroupBox("ESC 菜单 / 标题按钮文案")
        form = QFormLayout(box)
        self.menu_texts = {}
        for key, label in (("menu_continue", "继续游戏"), ("menu_save", "存档"),
                           ("menu_load", "读取存档"), ("menu_title", "返回标题"),
                           ("menu_quit", "退出游戏")):
            w, getter = make_lang_edit_widget(self._gl, str(k.get(key, "")))
            form.addRow(label, w)
            self.menu_texts[key] = (w, getter)
        wrap = QVBoxLayout()
        wrap.addWidget(box)
        wrap.addStretch(1)
        w = QWidget(); w.setLayout(wrap)
        return w

    # ---- 保存 ---------------------------------------------------------
    def _browse_icon(self):
        if self.project is None:
            return
        start = os.path.join(self.project.root, "materials")
        f, _ = QFileDialog.getOpenFileName(self, "选择窗口图标", start,
                                           "图片 (*.png *.jpg *.jpeg *.ico)")
        if f:
            rel = os.path.relpath(f, self.project.root).replace("\\", "/")
            self.ed_icon.setText(rel)

    def _collect_values(self) -> dict:
        v = {
            "title": self._title_getter().strip(),
            "width": str(self.sp_w.value()),
            "height": str(self.sp_h.value()),
            "fps": str(self.sp_fps.value()),
            "icon": self.ed_icon.text().strip(),
            "fullscreen": bool_to_gal(self.chk_fullscreen.isChecked()),
            "resizable": bool_to_gal(self.chk_resizable.isChecked()),
            "save_slots": str(self.sp_slots.value()),
            "music_fade": str(round(self.sp_fade.value(), 2)),
            "ui_click_sound": self.ed_click.text().strip(),
        }
        for key, (chk, text_pair, yes_pair, no_pair) in self.conf.items():
            v[key] = bool_to_gal(chk.isChecked())
            v[key + "_text"] = text_pair[1]().strip()
            v[key + "_yes"] = yes_pair[1]().strip()
            v[key + "_no"] = no_pair[1]().strip()
        for key, ed in self.keys.items():
            v[key] = ed.text().strip()
        for key, (w, getter) in self.menu_texts.items():
            v[key] = getter().strip()
        return v

    def _save(self):
        try:
            values = self._collect_values()
            if self.block is None:
                # 主脚本无 window 块: 插入新的 (import 语句前)
                from framework.engine.parser import Statement
                self.block = Statement(op="window", args=[], kwargs={})
                insert_at = 0
                for i, s in enumerate(self.script.statements):
                    if s.op == "import":
                        insert_at = i
                        break
                self.script.statements.insert(insert_at, self.block)
            apply_window_values(self.block, values)
            save_script(self.script,
                        os.path.join(self.project.root, self.project.main))
            self.accept()
        except Exception as exc:
            QMessageBox.critical(self, "保存失败", str(exc))


def _int(v, default=0):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default
