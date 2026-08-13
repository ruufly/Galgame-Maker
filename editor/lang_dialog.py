"""多语言文本编辑对话框 (流程画布/定义面板共用)。

开发者看到的是当前语言下的**显示效果**; 点击"编辑多语言…"
进入本对话框, 按语言并列编辑 ``lang/<code>.json`` 中的条目。

两种形态:
- 文本已含 {@key} 占位符: 矩阵编辑 (key × 语言), 底部实时预览
- 文本无占位符: 提示"转换为多语言文本", 自动生成 key 并预填
  当前语言, 其它语言留空 (运行时缺失回退默认语言)

用法::

    dlg = LangEditDialog(gl, "你好 {@welcome}", parent)
    if dlg.exec() == QDialog.Accepted:
        new_text = dlg.result_text()   # 可能从原文转为 {@key}
        gl.save()  # 已自动保存
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QHeaderView, QLabel,
                               QLineEdit, QPushButton, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from editor.i18n import t
from editor.lang_utils import PLACEHOLDER_RE

_LANG_NAMES = {"zh-CN": "简体中文", "en": "English", "ja": "日本語",
               "ko": "한국어", "fr": "Français", "de": "Deutsch",
               "es": "Español", "ru": "Русский", "it": "Italiano"}


def lang_label(code: str) -> str:
    return _LANG_NAMES.get(code, code)


def make_lang_edit_widget(gl, text: str, parent=None, on_commit=None):
    """多语言编辑控件工厂: 返回 (widget, getter)。

    - 项目有语言表: "当前语言显示效果 + 编辑多语言…" 按钮 (只读预览)
    - 无语言表: 回退普通 QLineEdit (直接编辑, on_commit 实时回调)
    getter() 返回最新文本 (含 {@key}); on_commit(new_text) 在
    多语言对话框保存后 (或 QLineEdit 编辑时) 回调。
    """
    if gl is None or not gl.langs:
        ed = QLineEdit(text)
        if on_commit:
            ed.textChanged.connect(on_commit)
        return ed, ed.text
    state = {"text": text}
    row = QWidget(parent)
    lay = QHBoxLayout(row)
    lay.setContentsMargins(0, 0, 0, 0)
    lbl = QLabel(gl.resolve(text) or " ")
    lbl.setWordWrap(True)
    lbl.setStyleSheet("color:#d8d8e0; background:#14141c; padding:4px;"
                      " border-radius:3px;")
    btn = QPushButton(t("flow.edit_lang"))
    btn.clicked.connect(
        lambda: _open_lang_editor(gl, state, lbl, row, on_commit))
    lay.addWidget(lbl, 1)
    lay.addWidget(btn)
    return row, (lambda: state["text"])


def _open_lang_editor(gl, state: dict, lbl: QLabel, parent=None,
                      on_commit=None) -> None:
    dlg = LangEditDialog(gl, state["text"], parent)
    if dlg.exec() == QDialog.Accepted:
        state["text"] = dlg.result_text()
        lbl.setText(gl.resolve(state["text"]) or " ")
        if on_commit is not None:
            on_commit(state["text"])


class LangEditDialog(QDialog):
    """编辑一段文本的多语言条目。"""

    locate_requested = Signal(str)   # 请求在多语言面板定位某 key

    def __init__(self, gl, text: str, parent=None):
        super().__init__(parent)
        self.gl = gl
        self._text = text
        self._keys = PLACEHOLDER_RE.findall(text)
        self.setWindowTitle(t("langedit.title"))
        self.setMinimumWidth(560)

        layout = QVBoxLayout(self)
        # 当前语言效果预览 (只读)
        self.lbl_preview = QLabel()
        self.lbl_preview.setWordWrap(True)
        self.lbl_preview.setStyleSheet(
            "background:#1c1c28; color:#eaeaea; padding:8px;"
            " border-radius:4px;")
        # 右键: 框架核心富文本渲染预览
        self.lbl_preview.setContextMenuPolicy(Qt.CustomContextMenu)
        self.lbl_preview.customContextMenuRequested.connect(
            self._preview_menu)
        self._refresh_preview()
        layout.addWidget(self.lbl_preview)

        if self._keys:
            self._build_matrix(layout)
        else:
            self._build_convert(layout)

        btns = QHBoxLayout()
        if self._keys:
            b_locate = QPushButton(t("langedit.open_panel"))
            b_locate.clicked.connect(self._open_panel)
            btns.addWidget(b_locate)
            btns.addStretch(1)
        ok = QPushButton(t("langedit.save"))
        ok.clicked.connect(self._save)
        cc = QPushButton(t("langedit.cancel"))
        cc.clicked.connect(self.reject)
        btns.addWidget(ok)
        btns.addWidget(cc)
        layout.addLayout(btns)

    def _preview_menu(self, _pos) -> None:
        from PySide6.QtGui import QAction
        from PySide6.QtWidgets import QMenu
        from editor.rich_preview import RichPreviewDialog
        menu = QMenu(self)
        a = QAction(t("local.preview"), self)
        a.triggered.connect(
            lambda: RichPreviewDialog(
                self.gl.resolve(self._text), self).exec())
        menu.addAction(a)
        menu.exec(self.lbl_preview.mapToGlobal(_pos))

    def _open_panel(self) -> None:
        """关闭本对话框, 请求多语言面板定位第一个 key。"""
        if self._keys:
            self.locate_requested.emit(self._keys[0])
        self.reject()

    # ---- 形态: 含占位符 -> 矩阵编辑 -----------------------------------
    def _build_matrix(self, layout) -> None:
        langs = self.gl.langs
        self.table = QTableWidget(len(self._keys), len(langs) + 1)
        self.table.setHorizontalHeaderLabels(
            [t("langedit.key")] + [lang_label(c) for c in langs])
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.Stretch)
        for r, key in enumerate(self._keys):
            self.table.setItem(r, 0, QTableWidgetItem(key))
            self.table.item(r, 0).setFlags(Qt.ItemIsEnabled)
            for c, code in enumerate(langs):
                item = QTableWidgetItem(self.gl.text(key, code))
                self.table.setItem(r, c + 1, item)
        layout.addWidget(self.table, 1)

    # ---- 形态: 无占位符 -> 转换建议 -----------------------------------
    def _build_convert(self, layout) -> None:
        hint = QLabel(t("langedit.convert_hint"))
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#d6a23c; padding:6px;")
        layout.addWidget(hint)
        langs = self.gl.langs
        self.table = QTableWidget(1, len(langs))
        self.table.setHorizontalHeaderLabels([lang_label(c) for c in langs])
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch)
        for c, code in enumerate(langs):
            default = self._text if code == self.gl.current else ""
            self.table.setItem(0, c, QTableWidgetItem(default))
        layout.addWidget(self.table, 1)

    # ---- 预览 ---------------------------------------------------------
    def _refresh_preview(self) -> None:
        resolved = self.gl.resolve(self._text)
        self.lbl_preview.setText("%s: %s" % (
            t("langedit.preview", lang=lang_label(self.gl.current)),
            resolved))

    # ---- 保存 ---------------------------------------------------------
    def _save(self) -> None:
        if self._keys:
            for r, key in enumerate(self._keys):
                for c, code in enumerate(self.gl.langs):
                    item = self.table.item(r, c + 1)
                    self.gl.set_text(key, code,
                                     item.text() if item else "")
        else:
            # 转换: 生成 key, 各语言写回; 当前语言用原文
            new_key = self.gl.ensure_key(self._text)
            for c, code in enumerate(self.gl.langs):
                item = self.table.item(0, c)
                if item and item.text().strip():
                    self.gl.set_text(new_key, code, item.text())
            self._text = "{@%s}" % new_key
        self.gl.save()
        self.accept()

    def result_text(self) -> str:
        return self._text
