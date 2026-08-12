"""多语言面板: 全项目占位符条目的集中管理 (key × 语言 大列表)。

- 行 = 一个 {@key}, 列 = 各语言文本 + 引用位置
- 双击单元格就地编辑, 自动写回 lang/<code>.json (防抖保存)
- locate(key): 外部跳转定位 (流程画布/定义面板等"涉及多语言处"双击直达)
"""

import os

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (QComboBox, QHBoxLayout, QHeaderView, QLabel,
                               QPushButton, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)

from editor.i18n import t
from editor.lang_utils import PLACEHOLDER_RE
from editor.lang_dialog import lang_label


def scan_refs(project) -> dict:
    """扫描全部脚本中的 {@key} 引用: key -> [(脚本, 标签), ...]。"""
    refs: dict = {}

    def _scan_text(text: str, where: tuple):
        # 属性值可能是非字符串 (数字/布尔), 跳过
        if not isinstance(text, str):
            return
        for m in PLACEHOLDER_RE.finditer(text):
            refs.setdefault(m.group(1), []).append(where)

    if project is None:
        return refs
    for rel, script in project.scripts.items():
        for stmt in script.statements:
            for a in stmt.args:
                _scan_text(a, (rel, ""))
            for v in stmt.kwargs.values():
                _scan_text(v, (rel, ""))
        for label, body in script.labels.items():
            for stmt in body:
                for a in stmt.args:
                    _scan_text(a, (rel, label))
                for v in stmt.kwargs.values():
                    _scan_text(v, (rel, label))
    return refs


class LocalizationPanel(QWidget):
    """多语言大列表 (中央 Tab)。"""

    locate_requested = Signal(str)   # 反查: 从面板跳到引用处 (预留)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.project = None
        self.lang = None          # GameLang
        self._refs: dict = {}
        self._saving = False
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._save_now)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        bar = QHBoxLayout()
        self.cb_lang = QComboBox()
        self.cb_lang.currentIndexChanged.connect(self._on_lang_switch)
        bar.addWidget(QLabel(t("local.edit_lang")))
        bar.addWidget(self.cb_lang)
        self.btn_add = QPushButton(t("local.add_key"))
        self.btn_add.clicked.connect(self._add_key)
        self.btn_refresh = QPushButton(t("local.refresh"))
        self.btn_refresh.clicked.connect(self.refresh)
        bar.addWidget(self.btn_add)
        bar.addWidget(self.btn_refresh)
        bar.addStretch(1)
        self.lbl_info = QLabel("")
        self.lbl_info.setStyleSheet("color:#888;")
        bar.addWidget(self.lbl_info)
        layout.addLayout(bar)

        self.table = QTableWidget(0, 0)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.DoubleClicked
                                   | QTableWidget.EditKeyPressed
                                   | QTableWidget.SelectedClicked)
        self.table.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self.table, 1)

    # ---- 数据 ---------------------------------------------------------
    def set_project(self, project) -> None:
        self.project = project
        from editor.lang_utils import GameLang
        self.lang = GameLang(project.root, project.main_script()) \
            if project is not None else None
        self.refresh()

    def refresh(self) -> None:
        if self.lang is None:
            self.table.clear()
            self.table.setRowCount(0)
            return
        langs = self.lang.langs
        self.cb_lang.blockSignals(True)
        self.cb_lang.clear()
        for c in langs:
            self.cb_lang.addItem(lang_label(c), c)
        idx = langs.index(self.lang.current) if self.lang.current in langs \
            else 0
        self.cb_lang.setCurrentIndex(idx)
        self.cb_lang.blockSignals(False)

        self._refs = scan_refs(self.project)
        keys = self.lang.keys()
        self.table.blockSignals(True)
        self.table.clear()
        self.table.setColumnCount(len(langs) + 2)
        self.table.setHorizontalHeaderLabels(
            [t("local.key")] + [lang_label(c) for c in langs]
            + [t("local.refs")])
        self.table.setRowCount(len(keys))
        for r, key in enumerate(keys):
            self.table.setItem(r, 0, QTableWidgetItem(key))
            self.table.item(r, 0).setFlags(Qt.ItemIsEnabled
                                           | Qt.ItemIsSelectable)
            for c, code in enumerate(langs):
                self.table.setItem(r, c + 1,
                                   QTableWidgetItem(self.lang.text(key, code)))
            refs = self._refs.get(key, [])
            ref_label = ", ".join("%s%s" % (rel, ":%s" % lb if lb else "")
                                  for rel, lb in refs[:3])
            if len(refs) > 3:
                ref_label += " …"
            self.table.setItem(r, len(langs) + 1, QTableWidgetItem(ref_label))
            self.table.item(r, len(langs) + 1).setFlags(
                Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(
            len(langs), QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(
            len(langs) + 1, QHeaderView.ResizeToContents)
        self.table.blockSignals(False)
        self.lbl_info.setText(t("local.info", n=len(keys)))

    # ---- 编辑 ---------------------------------------------------------
    def _on_lang_switch(self, _idx: int) -> None:
        if self.lang is None:
            return
        self.lang.current = self.cb_lang.currentData() or self.lang.current
        self.refresh()

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if self.lang is None or self._saving:
            return
        col = item.column()
        if col == 0 or col >= len(self.lang.langs) + 1:
            return
        key_item = self.table.item(item.row(), 0)
        if key_item is None:
            return
        code = self.lang.langs[col - 1]
        self.lang.set_text(key_item.text(), code, item.text())
        self._save_timer.start(600)   # 防抖落盘

    def _save_now(self) -> None:
        if self.lang is not None:
            self.lang.save()

    def _add_key(self) -> None:
        if self.lang is None:
            return
        key = self.lang._next_key()
        self.lang.set_text(key, self.lang.current, "")
        self.refresh()
        self.locate(key)

    # ---- 定位 ---------------------------------------------------------
    def locate(self, key: str) -> None:
        """滚动到指定 key 所在行并选中 (供其它面板双击跳转)。"""
        if self.lang is None:
            return
        for r in range(self.table.rowCount()):
            it = self.table.item(r, 0)
            if it is not None and it.text() == key:
                self.table.selectRow(r)
                self.table.scrollToItem(it)
                self.table.setFocus()
                return
