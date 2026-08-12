"""样式可视化编辑器 (P3): 编辑 ui.gal 的 style 块 + 实时样例预览。

纯逻辑 (可测试):
- get_style_block(script): 取第一个 style 块 (op=='style')
- ensure_style_block(script, name): 无则新建
- apply_style_values(stmt, values): 整体替换 kwargs
- save_script: 复用 project_settings

StylesEditor: 左表单 (颜色/整数/文本控件) + 右实时预览
(用 Qt 自绘模拟对话框/选择支, 即时反馈配色)。
"""

import os

from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtCore import QRectF, Qt
from PySide6.QtWidgets import (QColorDialog, QFormLayout, QHBoxLayout,
                               QLabel, QLineEdit, QPushButton, QScrollArea,
                               QSpinBox, QVBoxLayout, QWidget)

from framework.engine.parser import Statement
from editor.project_settings import save_script
from editor.i18n import t

# (key, 标签, 类型)  type: color / int / text
STYLE_FIELDS = [
    ("textbox_bg", "对话框背景色", "color"),
    ("textbox_alpha", "背景不透明度 (0-255)", "int"),
    ("textbox_border", "对话框边框色", "color"),
    ("textbox_border_width", "边框宽度", "int"),
    ("textbox_radius", "圆角", "int"),
    ("text_color", "台词颜色", "color"),
    ("text_size", "台词字号", "int"),
    ("speaker_color", "名字文字色", "color"),
    ("speaker_bg", "名字背景色", "color"),
    ("font", "字体", "text"),
    ("choice_bg", "选项背景", "color"),
    ("choice_bg_hover", "选项悬停背景", "color"),
    ("choice_border", "选项边框", "color"),
    ("choice_border_hover", "选项悬停边框", "color"),
    ("choice_text_size", "选项字号", "int"),
    ("choice_text_color", "选项文字色", "color"),
    ("choice_text_color_hover", "选项悬停文字色", "color"),
]

_DEFAULTS = {
    "textbox_bg": "#1a1a2e", "textbox_alpha": "210",
    "textbox_border": "#e94560", "textbox_border_width": "3",
    "textbox_radius": "12", "text_color": "#eaeaea", "text_size": "28",
    "speaker_color": "#ffd282", "speaker_bg": "#1e3a5f",
    "font": "", "choice_bg": "#2a2a44", "choice_bg_hover": "#3a3a5c",
    "choice_border": "#5a5a7a", "choice_border_hover": "#e94560",
    "choice_text_size": "26", "choice_text_color": "#eaeaea",
    "choice_text_color_hover": "#ffffff",
}


# ----------------------------------------------------------------------
# 纯逻辑 (可测试)
# ----------------------------------------------------------------------
def get_style_block(script):
    for stmt in script.statements:
        if stmt.op == "style" and stmt.args:
            return stmt
    return None


def ensure_style_block(script, name: str = "custom"):
    stmt = get_style_block(script)
    if stmt is None:
        stmt = Statement(op="style", args=[name], kwargs={})
        script.statements.append(stmt)
    return stmt


def apply_style_values(stmt, values: dict) -> None:
    stmt.kwargs.clear()
    stmt.kwargs.update(values)


# ----------------------------------------------------------------------
# 颜色按钮
# ----------------------------------------------------------------------
class ColorButton(QPushButton):
    def __init__(self, color: str, parent=None):
        super().__init__(parent)
        self.set_color(color)
        self.setFixedSize(56, 26)
        self.clicked.connect(self._pick)

    def _pick(self):
        c = QColorDialog.getColor(QColor(self._color), self, "选择颜色")
        if c.isValid():
            self.set_color(c.name())

    def set_color(self, color: str):
        self._color = color if color.startswith("#") else "#" + color
        self.setStyleSheet(
            "background:%s; border:1px solid #888;" % self._color)

    def color(self) -> str:
        return self._color


# ----------------------------------------------------------------------
# 预览面板
# ----------------------------------------------------------------------
class StylePreview(QWidget):
    """模拟游戏画面: 背景 + 对话框 + 名字框 + 台词 + 选择按钮。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.values = dict(_DEFAULTS)
        self.setMinimumSize(420, 320)

    def set_values(self, values: dict):
        self.values = dict(_DEFAULTS)
        self.values.update(values)
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        v = self.values

        def col(key, default):
            return QColor(v.get(key, default))

        # 背景 (深色渐变模拟游戏画面)
        bg = QColor("#20203a")
        for i in range(h):
            t = i / max(1, h)
            c = QColor(int(bg.red() + (40 - bg.red()) * t),
                       int(bg.green() + (50 - bg.green()) * t),
                       int(bg.blue() + (70 - bg.blue()) * t))
            p.setPen(c)
            p.drawLine(0, i, w, i)
        p.setPen(QColor("#8a8ab0"))
        p.drawText(20, 50, "样式预览 (游戏画面示意)")

        # 对话框
        box = QRectF(24, h * 0.45, w - 48, h * 0.47)
        alpha = int(v.get("textbox_alpha", "210"))
        box_col = col("textbox_bg", "#1a1a2e")
        box_col.setAlpha(alpha)
        radius = int(v.get("textbox_radius", "12"))
        p.setPen(QPen(col("textbox_border", "#e94560"),
                      int(v.get("textbox_border_width", "3"))))
        p.setBrush(box_col)
        p.drawRoundedRect(box, radius, radius)

        # 名字框
        name_box = QRectF(box.x() + 14, box.y() - 22, 150, 34)
        p.setPen(Qt.NoPen)
        p.setBrush(col("speaker_bg", "#1e3a5f"))
        p.drawRoundedRect(name_box, 6, 6)
        p.setPen(col("speaker_color", "#ffd282"))
        p.drawText(name_box, Qt.AlignCenter, "制作人")

        # 台词
        p.setPen(col("text_color", "#eaeaea"))
        f = p.font()
        f.setPointSize(int(v.get("text_size", "28")) // 2)
        f.setBold(True)
        p.setFont(f)
        p.drawText(QRectF(box.x() + 18, box.y() + 16, box.width() - 36, 60),
                   Qt.AlignLeft | Qt.AlignVCenter,
                   "这是一段样式预览台词…")

        # 选择按钮 ×2
        btn_y = box.y() + 84
        for i, (label, hover) in enumerate((("选项一", False), ("选项二", True))):
            b = QRectF(box.x() + 18 + i * (w * 0.36), btn_y,
                       w * 0.32, 44)
            p.setPen(QPen(col("choice_border_hover" if hover else "choice_border",
                              "#5a5a7a"), 2))
            p.setBrush(col("choice_bg_hover" if hover else "choice_bg",
                           "#2a2a44"))
            p.drawRoundedRect(b, 8, 8)
            p.setPen(col("choice_text_color_hover" if hover
                         else "choice_text_color", "#eaeaea"))
            p.drawText(b, Qt.AlignCenter, label)
        p.end()


# ----------------------------------------------------------------------
# 编辑器面板
# ----------------------------------------------------------------------
class StylesEditor(QWidget):
    """样式编辑器: 左表单 + 右实时预览。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.project = None
        self._ctrls = {}

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)

        # 左: 表单 (滚动)
        form_widget = QWidget()
        form = QFormLayout(form_widget)
        form.setContentsMargins(4, 4, 12, 4)
        for key, label, typ in STYLE_FIELDS:
            if typ == "color":
                ctrl = ColorButton(_DEFAULTS[key])
            elif typ == "int":
                ctrl = QSpinBox()
                ctrl.setRange(0, 255)
                ctrl.setValue(int(_DEFAULTS[key]))
                if key in ("text_size", "choice_text_size"):
                    ctrl.setRange(8, 96)
                if key == "textbox_alpha":
                    ctrl.setRange(0, 255)
            else:
                ctrl = QLineEdit()
            if isinstance(ctrl, (QSpinBox, QLineEdit)):
                ctrl.valueChanged.connect(self._changed) \
                    if isinstance(ctrl, QSpinBox) else \
                    ctrl.textChanged.connect(self._changed)
            self._ctrls[key] = ctrl
            form.addRow(label, ctrl)
        self.btn_save = QPushButton(t("styles.save"))
        self.btn_save.clicked.connect(self.save)
        form.addRow("", self.btn_save)

        scroll = QScrollArea()
        scroll.setWidget(form_widget)
        scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(300)
        layout.addWidget(scroll, 1)

        # 右: 预览
        self.preview = StylePreview()
        layout.addWidget(self.preview, 2)

    # ---- 语言刷新 -----------------------------------------------------
    def apply_lang(self) -> None:
        self.btn_save.setText(t("styles.save"))

    # ---- 数据 ---------------------------------------------------------
    def set_project(self, project) -> None:
        self.project = project
        self.load()

    def load(self) -> None:
        if self.project is None:
            return
        script = self.project.scripts.get("ui.gal")
        if script is None:
            return
        stmt = get_style_block(script)
        k = stmt.kwargs if stmt else {}
        for key, ctrl in self._ctrls.items():
            val = k.get(key, _DEFAULTS[key])
            if isinstance(ctrl, ColorButton):
                ctrl.set_color(str(val))
            elif isinstance(ctrl, QSpinBox):
                try:
                    ctrl.setValue(int(val))
                except (TypeError, ValueError):
                    ctrl.setValue(int(_DEFAULTS[key]))
            else:
                ctrl.setText(str(val))
        self._changed()

    def _changed(self, *_a):
        self.preview.set_values(self._values())

    def _values(self) -> dict:
        v = {}
        for key, ctrl in self._ctrls.items():
            if isinstance(ctrl, ColorButton):
                v[key] = ctrl.color()
            elif isinstance(ctrl, QSpinBox):
                v[key] = str(ctrl.value())
            else:
                v[key] = ctrl.text().strip()
        return v

    # ---- 保存 ---------------------------------------------------------
    def save(self) -> None:
        if self.project is None:
            return
        script = self.project.scripts.get("ui.gal")
        if script is None:
            return
        stmt = ensure_style_block(script, "custom")
        apply_style_values(stmt, self._values())
        save_script(script, os.path.join(self.project.root, "ui.gal"))
