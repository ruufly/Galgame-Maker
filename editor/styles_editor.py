"""样式可视化编辑器 (P4 重构): 多样式源 + 插件可注册编辑项。

样式源 (左侧列表, 从项目脚本扫描):
- style (对话框/选择支配色)   - selection_style (标题/ESC 菜单按钮)
- menu_bar (常驻菜单栏)        - ui (九宫格主题切片)
- menu (命名菜单: title/system 块级字段)
- gallery (鉴赏, 字段由 gallery 插件注册) - settings (设置界面)

每个源的字段 = 内核清单 (KERNEL_SOURCE_FIELDS) + 插件注册
(plugins_api.add_style_fields)。编辑写回对应 Statement kwargs。

纯逻辑 (可测试, 保持 P3 兼容):
- get_style_block / ensure_style_block / apply_style_values
- STYLE_FIELDS / _DEFAULTS (style 块, 与测试断言一致)
"""

import os

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QCheckBox, QColorDialog, QComboBox,
                               QFileDialog, QFormLayout, QHBoxLayout, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem,
                               QPushButton, QScrollArea, QSpinBox,
                               QVBoxLayout, QWidget)

from framework.engine.parser import Statement
from editor.project_settings import save_script
from editor.i18n import t
from editor.plugins_api import registry

_TRUE = ("true", "1", "yes", "on")


# ----------------------------------------------------------------------
# style 块字段 (P3 兼容: 三元组, _DEFAULTS 全覆盖)
# ----------------------------------------------------------------------
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


def _style_fields_with_defaults() -> list:
    """style 块字段 (4 元组: key/标签/类型/默认)。"""
    return [(k, l, ty, _DEFAULTS.get(k, "")) for k, l, ty in STYLE_FIELDS]


# ----------------------------------------------------------------------
# 其它样式源的内核字段 (4 元组: key/标签/类型/默认)
# ----------------------------------------------------------------------
KERNEL_SOURCE_FIELDS = {
    "selection_style": [
        ("width_ratio", "宽度比例 (0-1)", "text", "0.32"),
        ("width", "按钮宽度 (像素)", "int", "400"),
        ("height", "按钮高度", "int", "56"),
        ("gap", "按钮间距", "int", "14"),
        ("anchor_x", "水平对齐", "combo", "center"),
        ("anchor_y", "垂直对齐", "combo", "center"),
        ("button_bg", "按钮背景", "color", "#2a2a44"),
        ("button_bg_hover", "按钮悬停背景", "color", "#3a3a5c"),
        ("button_border", "按钮边框", "color", "#5a5a7a"),
        ("button_border_hover", "按钮悬停边框", "color", "#e94560"),
        ("button_radius", "按钮圆角", "int", "8"),
        ("text_size", "按钮字号", "int", "24"),
        ("text_color", "按钮文字色", "color", "#eaeaea"),
        ("text_color_hover", "按钮悬停文字色", "color", "#ffffff"),
        ("dim_alpha", "背景遮罩不透明度", "int", "150"),
        ("dialog_image", "面板背景图", "image", ""),
        ("button_image", "按钮图 (默认, 焦点)", "text", ""),
    ],
    "menu_bar": [
        ("bg", "条背景色", "color", "#1a1a2e"),
        ("border", "边框色", "color", "#5a5a7a"),
        ("align", "按钮对齐", "combo", "center"),
        ("gap", "按钮间距", "int", "12"),
        ("padding", "按钮左右内边距", "int", "18"),
        ("height", "条高度", "int", "56"),
        ("btn_h", "按钮高度", "int", "38"),
        ("y_offset", "纵向微调", "int", "0"),
        ("button_bg", "按钮背景", "color", "#2a2a44"),
        ("button_bg_hover", "按钮悬停背景", "color", "#e94560"),
        ("button_border", "按钮边框", "color", "#44446a"),
        ("button_border_hover", "按钮悬停边框", "color", "#ffd282"),
        ("button_radius", "按钮圆角", "int", "8"),
        ("text_color", "按钮文字色", "color", "#eaeaea"),
        ("text_color_hover", "按钮悬停文字色", "color", "#ffffff"),
        ("text_size", "按钮字号", "int", "22"),
        ("bg_image", "条背景图", "image", ""),
        ("button_image", "按钮图", "image", ""),
        ("button_image_hover", "按钮悬停图", "image", ""),
        ("button_image_active", "按钮激活图", "image", ""),
        ("button_image_disabled", "按钮禁用图", "image", ""),
    ],
    "ui": [
        ("textbox", "文本框背景", "image", ""),
        ("choice_button", "选择按钮图 (默认, 焦点)", "text", ""),
        ("title_buttons", "标题按钮图 (默认, 焦点; 多组用; 分隔)", "text", ""),
        ("menu_button", "菜单按钮图", "text", ""),
        ("confirm_panel", "确认框面板", "image", ""),
        ("confirm_button", "确认框按钮", "text", ""),
        ("slot_frame", "存档框", "image", ""),
        ("slot_panel", "存档面板", "image", ""),
        ("error_panel", "错误面板", "image", ""),
        ("error_button", "错误按钮", "text", ""),
        ("notice_panel", "通知面板", "image", ""),
    ],
    "menu": [
        ("button_columns", "按钮列数", "int", "1"),
        ("ui_hover_sound", "悬停音效", "text", ""),
        ("ui_click_sound", "点击音效", "text", ""),
    ],
    "gallery": [],
    "settings": [
        ("title", "界面标题", "text", "设置"),
        ("columns", "条目列数", "int", "2"),
        ("bg", "面板背景图", "image", ""),
        ("item_image", "条目背景图", "image", ""),
        ("item_image_hover", "条目悬停图", "image", ""),
        ("tab_image", "分栏图", "image", ""),
        ("tab_image_hover", "分栏激活图", "image", ""),
        ("back_image", "返回按钮图", "image", ""),
        ("slider_track_image", "滑条轨道图", "image", ""),
    ],
}

# 样式源 -> 块 op 与新建默认名
SOURCE_DEFS = [
    ("style", "style", "custom"),
    ("selection_style", "selection_style", ""),
    ("menu_bar", "menu_bar", ""),
    ("ui", "ui", ""),
    ("menu", "menu", "title"),
    ("gallery", "gallery", ""),
    ("settings", "settings", ""),
]


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


def collect_plugin_style_fields() -> dict:
    """插件注册的样式字段: block_op -> [(key, 标签, 类型, 默认)]。"""
    out: dict = {}
    for p in registry.plugins().values():
        for op, fields in p.style_fields.items():
            out.setdefault(op, []).extend(list(fields))
    return out


def fields_for(op: str) -> list:
    """某样式源字段 = 内核 + 插件注册 (去重)。"""
    fields = list(KERNEL_SOURCE_FIELDS.get(op, []))
    if op == "style":
        fields = _style_fields_with_defaults()
    seen = set()
    out = []
    for f in fields:
        if f[0] not in seen:
            seen.add(f[0])
            out.append(f)
    for f in collect_plugin_style_fields().get(op, []):
        if f[0] not in seen:
            seen.add(f[0])
            out.append(f)
    return out


def find_blocks(project) -> dict:
    """扫描项目全部脚本中的样式源块: op -> [(Statement, rel)]。"""
    out: dict = {}
    if project is None:
        return out
    for rel, script in project.scripts.items():
        for stmt in script.statements:
            if stmt.op in KERNEL_SOURCE_FIELDS or stmt.op == "style":
                out.setdefault(stmt.op, []).append((stmt, rel))
            elif stmt.op == "menu" and stmt.args:
                out.setdefault("menu", []).append((stmt, rel))
    return out


# ----------------------------------------------------------------------
# 颜色按钮 / 字段控件
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


def _make_field_editor(field, current: str | None, parent=None,
                       root_dir: str | None = None):
    """按字段类型创建编辑控件, 返回 (widget, getter)。

    root_dir: 项目根目录 (image 字段浏览时转相对路径, 保证项目可移植)。
    """
    key, label, ftype, default = field
    val = current if current is not None else default
    if ftype == "color":
        btn = ColorButton(str(val or "#000000"), parent)
        return btn, btn.color
    if ftype == "int":
        sp = QSpinBox(parent)
        sp.setRange(-10000, 100000)
        try:
            sp.setValue(int(val))
        except (TypeError, ValueError):
            sp.setValue(0)
        return sp, (lambda: str(sp.value()))
    if ftype == "bool":
        chk = QCheckBox(parent)
        chk.setChecked(str(val).lower() in _TRUE)
        return chk, (lambda: "true" if chk.isChecked() else "false")
    if ftype == "combo":
        cb = QComboBox(parent)
        if label.find("对齐") >= 0 or key in ("anchor_x", "anchor_y",
                                              "align"):
            cb.addItems(["left", "center", "right"])
        if str(val) in [cb.itemText(i) for i in range(cb.count())]:
            cb.setCurrentText(str(val))
        cb.setEditable(True)
        return cb, cb.currentText
    if ftype == "image":
        row = QWidget(parent)
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        ed = QLineEdit(str(val), row)
        btn = QPushButton("…", row)
        btn.setFixedWidth(30)
        btn.clicked.connect(lambda: _browse_image(ed, parent, root_dir))
        lay.addWidget(ed, 1)
        lay.addWidget(btn)
        return row, ed.text
    ed = QLineEdit(str(val), parent)
    return ed, ed.text


def _browse_image(ed: QLineEdit, parent=None, root_dir: str | None = None) -> None:
    f, _ = QFileDialog.getOpenFileName(parent, "选择图片", "",
                                       "图片 (*.png *.jpg *.jpeg *.webp)")
    if f:
        # 项目内素材存相对路径 (可移植/可打包); 项目外文件保留绝对路径
        if root_dir:
            try:
                rel = os.path.relpath(f, root_dir).replace("\\", "/")
                if not rel.startswith(".."):
                    ed.setText(rel)
                    return
            except ValueError:
                pass
        ed.setText(f)


# ----------------------------------------------------------------------
# 预览面板 (style 块)
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

        bg = QColor("#20203a")
        for i in range(h):
            tt = i / max(1, h)
            c = QColor(int(bg.red() + (40 - bg.red()) * tt),
                       int(bg.green() + (50 - bg.green()) * tt),
                       int(bg.blue() + (70 - bg.blue()) * tt))
            p.setPen(c)
            p.drawLine(0, i, w, i)
        p.setPen(QColor("#8a8ab0"))
        p.drawText(20, 50, "样式预览 (游戏画面示意)")

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
        p.setPen(Qt.NoPen)
        sp_bg = col("speaker_bg", "#1e3a5f")
        p.setBrush(sp_bg)
        p.drawRoundedRect(QRectF(48, box.top() - 34, 110, 34), 8, 8)
        p.setPen(col("speaker_color", "#ffd282"))
        p.drawText(QRectF(48, box.top() - 34, 110, 34), Qt.AlignCenter,
                   "制作人")
        # 台词
        p.setPen(col("text_color", "#eaeaea"))
        f = p.font()
        f.setPointSize(int(v.get("text_size", "28")) // 4)
        p.setFont(f)
        p.drawText(QRectF(48, box.top() + 20, w - 96, 60),
                   "欢迎来到 Galgame Maker 引擎演示！\n"
                   "这是{c=#ffcc00}彩色文字{/c}示例。")
        # 选择按钮
        y = box.top() - 140
        for i, (txt, hover) in enumerate([("选项一", False),
                                          ("选项二", True)]):
            rr = QRectF(w - 300, y + i * 52, 260, 42)
            p.setBrush(col("choice_bg_hover" if hover else "choice_bg",
                           "#3a3a5c" if hover else "#2a2a44"))
            p.setPen(QPen(col("choice_border_hover" if hover
                              else "choice_border", "#5a5a7a"), 2))
            p.drawRoundedRect(rr, 8, 8)
            p.setPen(col("choice_text_color_hover" if hover
                         else "choice_text_color", "#eaeaea"))
            p.drawText(rr, Qt.AlignCenter, txt)


# ----------------------------------------------------------------------
# 编辑器面板
# ----------------------------------------------------------------------
class StylesEditor(QWidget):
    """样式面板: 左侧样式源列表 + 右侧动态字段表单 + 实时预览。"""

    log = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.project = None
        self._current = None      # (op, stmt, rel)
        self._editors: list = []

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)

        # 左: 样式源列表
        left = QVBoxLayout()
        left.addWidget(QLabel(t("styles.sources")))
        self.list = QListWidget()
        self.list.itemClicked.connect(self._on_source_clicked)
        left.addWidget(self.list, 1)
        btn_new = QPushButton(t("styles.new_block"))
        btn_new.clicked.connect(self._new_block)
        left.addWidget(btn_new)
        layout.addLayout(left, 2)

        # 右: 字段表单 + 预览
        right = QVBoxLayout()
        self.lbl_title = QLabel("")
        self.lbl_title.setStyleSheet("font-weight:bold; color:#d8d8e0;")
        right.addWidget(self.lbl_title)
        self.form_widget = QWidget()
        self.form = QFormLayout(self.form_widget)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.form_widget)
        right.addWidget(scroll, 1)
        self.preview = StylePreview()
        self.preview.setVisible(False)
        right.addWidget(self.preview, 1)
        row = QHBoxLayout()
        self.btn_save = QPushButton(t("styles.save"))
        self.btn_save.clicked.connect(self._save)
        self.btn_save.setEnabled(False)
        self.btn_reset = QPushButton(t("styles.reset"))
        self.btn_reset.clicked.connect(self._reset)
        row.addStretch(1)
        row.addWidget(self.btn_reset)
        row.addWidget(self.btn_save)
        right.addLayout(row)
        layout.addLayout(right, 5)

    # ---- 语言/项目 ----------------------------------------------------
    def apply_lang(self) -> None:
        self.refresh()

    def set_project(self, project) -> None:
        self.project = project
        self.refresh()

    # ---- 列表 ---------------------------------------------------------
    def refresh(self) -> None:
        self.list.clear()
        blocks = find_blocks(self.project) if self.project else {}
        for op, _name, _dflt in SOURCE_DEFS:
            items = blocks.get(op, [])
            if not items:
                it = QListWidgetItem("%s (未定义)" % _label_of(op))
                it.setData(Qt.UserRole, ("__missing__", op, None, None))
                it.setForeground(QColor("#777"))
                self.list.addItem(it)
                continue
            for stmt, rel in items:
                name = stmt.args[0] if stmt.args else ""
                it = QListWidgetItem("%s%s (%s)" % (
                    _label_of(op), " " + name if name else "", rel))
                it.setData(Qt.UserRole, ("block", op, stmt, rel))
                self.list.addItem(it)
        self._current = None
        self._show_empty()

    def _on_source_clicked(self, item: QListWidgetItem) -> None:
        kind, op, stmt, rel = item.data(Qt.UserRole)
        if kind == "__missing__":
            self._current = ("missing", op, None, None)
            self._show_missing(op)
            return
        self._current = (op, stmt, rel)
        self._build_form(op, stmt, rel)

    # ---- 表单 ---------------------------------------------------------
    def _show_empty(self) -> None:
        self.lbl_title.setText(t("styles.pick_source"))
        self._clear_form()
        self.preview.setVisible(False)
        self.btn_save.setEnabled(False)

    def _show_missing(self, op: str) -> None:
        self.lbl_title.setText("%s (%s)" % (_label_of(op), t("styles.missing")))
        self._clear_form()
        self.preview.setVisible(False)
        self.btn_save.setEnabled(False)

    def _build_form(self, op: str, stmt, rel: str) -> None:
        self.lbl_title.setText("%s — %s" % (_label_of(op), rel))
        self._clear_form()
        fields = fields_for(op)
        root_dir = self.project.root if self.project is not None else None
        self._editors = []
        for key, label, ftype, default in fields:
            widget, getter = _make_field_editor(
                (key, label, ftype, default),
                stmt.kwargs.get(key), self.form_widget, root_dir)
            self.form.addRow(label + ":", widget)
            self._editors.append((key, getter))
        self.btn_save.setEnabled(True)
        self.preview.setVisible(op == "style")
        if op == "style":
            self.preview.set_values({k: g() for k, g in self._editors})

    def _clear_form(self) -> None:
        while self.form.rowCount():
            self.form.removeRow(0)
        self._editors = []

    # ---- 保存 ---------------------------------------------------------
    def _save(self) -> None:
        if self._current is None or self._current[0] == "missing":
            return
        op, stmt, rel = self._current
        # 合并写入 (保留面板未覆盖的键)
        for key, getter in self._editors:
            stmt.kwargs[key] = getter()
        script = self.project.scripts.get(rel)
        if script is not None:
            save_script(script, os.path.join(self.project.root, rel))
            self.project.load()
        self.refresh()
        self._log(t("styles.saved", target=rel))

    def _reset(self) -> None:
        if self._current is None:
            return
        op = self._current[0]
        if op == "missing":
            return
        _, stmt, rel = self._current
        for key, _l, _ty, default in fields_for(op):
            stmt.kwargs[key] = default
        self._build_form(op, stmt, rel)
        self._save()

    # ---- 新建 ---------------------------------------------------------
    def _new_block(self) -> None:
        if self.project is None:
            return
        it = self.list.currentItem()
        if it is None:
            return
        kind, op, _stmt, _rel = it.data(Qt.UserRole)
        if kind != "__missing__":
            return
        target = None
        for rel in ("ui.gal", "demo.gal"):
            if rel in self.project.scripts:
                target = rel
                break
        if target is None:
            return
        script = self.project.scripts[target]
        name = ""
        for _o, _n, dflt in SOURCE_DEFS:
            if _o == op:
                name = dflt
                break
        stmt = Statement(op=op, args=[name] if name else [], kwargs={})
        script.statements.append(stmt)
        save_script(script, os.path.join(self.project.root, target))
        self.project.load()
        self.refresh()
        self._log(t("styles.created", op=op, rel=target))

    def _log(self, msg: str) -> None:
        self.log.emit(msg)


def _label_of(op: str) -> str:
    return {"style": "对话框样式", "selection_style": "菜单按钮样式",
            "menu_bar": "常驻菜单栏", "ui": "UI 主题切片",
            "menu": "命名菜单", "gallery": "鉴赏 (插件)",
            "settings": "设置界面"}.get(op, op)
