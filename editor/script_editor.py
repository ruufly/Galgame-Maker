"""脚本编辑器: 直接编辑 .gal 文本 (保留注释/排版)。

设计 (Editor-first 不变式):
- 打开: 读取**原始文本** (注释/空行完整保留, 比模型序列化更友好)
- 保存: parse 重新解析 -> 往返校验 -> 写盘 -> 更新 Project 模型 ->
  通知主窗口刷新全部面板 (定义/流程/样式等立即同步)

语法高亮: 注释 / 字符串 / 关键字 / 标签 / 属性键 / {@key} 占位符。
"""

import os

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import (QColor, QFont, QFontMetrics, QPainter, QSyntaxHighlighter,
                           QTextCharFormat)
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QMessageBox,
                               QPlainTextEdit, QPushButton, QVBoxLayout,
                               QWidget)

from editor.i18n import t

# .gal 关键字 (指令级)
_KEYWORDS = frozenset("""
say nar text bg scene char show hide clear move rotate flip
music sfx volume pause resume stop set if elif else endif
jump call return choice ending save load fade fadeout typing
use style title window import using plugin confirm read_settings
sleep fullscreen do_action menu settings gallery language plugins
window config stop all
""".split())

_COMMENT = QColor("#5a6a5a")
_STRING = QColor("#d8c47a")
_KEYWORD = QColor("#6fb3e0")
_LABEL = QColor("#e88a5a")
_KEY = QColor("#9ecb8a")
_PLACEHOLDER = QColor("#e88ad0")


def _fmt(color: QColor, bold: bool = False) -> QTextCharFormat:
    f = QTextCharFormat()
    f.setForeground(color)
    if bold:
        f.setFontWeight(QFont.Bold)
    return f


class GalHighlighter(QSyntaxHighlighter):
    """.gal 语法高亮 (轻量正则, 不追求完备)。"""

    def __init__(self, doc):
        super().__init__(doc)
        self._rules = [
            # 注释 (行首 # 或 空格+#)
            (r"^\s*#.*$", _fmt(_COMMENT)),
            (r"(?<= )#.*$", _fmt(_COMMENT)),
            # 字符串
            (r'"[^"\\]*(\\.[^"\\]*)*"', _fmt(_STRING)),
            (r"'[^'\\]*(\\.[^'\\]*)*'", _fmt(_STRING)),
            # {@key} 占位符 / 富文本标记
            (r"\{@[^{}]+\}", _fmt(_PLACEHOLDER, True)),
            (r"\{[a-z]=[^}]*\}", _fmt(_PLACEHOLDER)),
            # 关键字 (整词)
            (r"\b(%s)\b" % "|".join(sorted(_KEYWORDS)), _fmt(_KEYWORD, True)),
            # 标签 (行首 word:)
            (r"^\s*[A-Za-z_][\w\-]*:", _fmt(_LABEL, True)),
            # 属性键 (缩进 key:)
            (r"^\s+[A-Za-z_][\w\-]*:", _fmt(_KEY)),
        ]

    def highlightBlock(self, text: str) -> None:
        import re
        for pattern, fmt in self._rules:
            for m in re.finditer(pattern, text):
                self.setFormat(m.start(), m.end() - m.start(), fmt)


class LineNumberArea(QWidget):
    """行号条 (经典 QPlainTextEdit 行号模式)。"""

    def __init__(self, editor: "ScriptEditor"):
        super().__init__(editor)
        self._editor = editor

    def sizeHint(self) -> QSize:
        return QSize(self._editor.line_number_width(), 0)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#1e1e28"))
        block = self._editor.firstVisibleBlock()
        number = block.blockNumber()
        top = round(self._editor.blockBoundingGeometry(block)
                    .translated(self._editor.contentOffset()).top())
        bottom = top + round(self._editor.blockBoundingRect(block).height())
        f = QFont("Consolas", 9)
        fm = QFontMetrics(f)
        while block.isValid() and top <= self._editor.viewport().height():
            if block.isVisible() and bottom >= 0:
                p.setFont(f)
                p.setPen(QColor("#5a5a6a"))
                p.drawText(0, top, self.width() - 6,
                           fm.height(), Qt.AlignRight, str(number + 1))
            block = block.next()
            top = bottom
            bottom = top + round(
                self._editor.blockBoundingRect(block).height())
            number += 1


class ScriptEditor(QPlainTextEdit):
    """带行号的脚本编辑器。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFont(QFont("Consolas", 10))
        self.setStyleSheet(
            "QPlainTextEdit { background:#14141c; color:#d8d8e0; }")
        self._line_area = LineNumberArea(self)
        self.blockCountChanged.connect(self._update_line_width)
        self.updateRequest.connect(self._update_line_area)
        self._update_line_width()

    def line_number_width(self) -> int:
        digits = max(2, len(str(self.blockCount())))
        return 14 + self.fontMetrics().horizontalAdvance("9") * digits

    def _update_line_width(self, *_a) -> None:
        self.setViewportMargins(self.line_number_width(), 0, 0, 0)

    def _update_line_area(self, rect, dy) -> None:
        if dy:
            self._line_area.scroll(0, dy)
        else:
            self._line_area.update(0, rect.y(), self._line_area.width(),
                                   rect.height())
        if rect.contains(self.viewport().rect()):
            self._update_line_width()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self._line_area.setGeometry(
            QRect(cr.left(), cr.top(), self.line_number_width(),
                  cr.height()))


class ScriptEditorDialog(QDialog):
    """.gal 脚本编辑对话框 (双击项目树脚本打开)。"""

    def __init__(self, project, rel: str, parent=None):
        super().__init__(parent)
        self.project = project
        self.rel = rel
        self.setWindowTitle("%s — %s" % (t("script_editor.title"), rel))
        self.resize(820, 640)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(os.path.join(project.root, rel)))
        self.editor = ScriptEditor()
        self.editor.setPlainText(self._read_text())
        GalHighlighter(self.editor.document())
        layout.addWidget(self.editor, 1)

        btns = QHBoxLayout()
        self.lbl_check = QLabel("")
        self.lbl_check.setStyleSheet("color:#888;")
        btns.addWidget(self.lbl_check)
        btns.addStretch(1)
        b_save = QPushButton(t("script_editor.save"))
        b_save.clicked.connect(self._save)
        b_cancel = QPushButton(t("script_editor.cancel"))
        b_cancel.clicked.connect(self.reject)
        btns.addWidget(b_save)
        btns.addWidget(b_cancel)
        layout.addLayout(btns)

    # ---- 读写 ---------------------------------------------------------
    def _read_text(self) -> str:
        path = os.path.join(self.project.root, self.rel)
        try:
            with open(path, encoding="utf-8") as fh:
                return fh.read()
        except OSError as exc:
            return "# 读取失败: %s" % exc

    def _save(self) -> None:
        text = self.editor.toPlainText()
        # 1. 解析 -> 校验 (往返)
        try:
            from framework.engine.parser import parse
            script = parse(text, self.rel)
        except Exception as exc:
            QMessageBox.critical(self, t("script_editor.parse_error"), str(exc))
            return
        from editor.compare import roundtrip_ok
        if not roundtrip_ok(script):
            self.lbl_check.setText(t("script_editor.roundtrip_warn"))
            # 往返失败仍允许保存 (警告即可, 不阻塞)
        # 2. 落盘 (保留原始文本, 含注释)
        path = os.path.join(self.project.root, self.rel)
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
        except OSError as exc:
            QMessageBox.critical(self, t("script_editor.write_error"), str(exc))
            return
        # 3. 更新模型
        self.project.scripts[self.rel] = script
        self.lbl_check.setText(t("script_editor.saved"))
        self.accept()
