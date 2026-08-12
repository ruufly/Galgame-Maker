"""富文本预览 (多语言条目右键): 用框架核心渲染文本效果。

设计 (插件友好): 标记解析**直接调用框架** ``framework.engine.rich.parse_rich``
返回的 Run 列表 (颜色/字号/粗体/斜体/下划线/math), Qt 侧只做自绘。
日后核心新增标记或插件扩展标记, 编辑器无需改动。

用法::

    RichPreviewDialog(gl, "{@welcome}", parent).exec()
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QPushButton,
                               QVBoxLayout, QWidget)

from editor.i18n import t

try:
    from framework.engine.rich import parse_rich as _framework_parse_rich
except Exception:  # 框架不可用时不崩溃
    _framework_parse_rich = None


class RichPreviewWidget(QWidget):
    """按框架 Run 列表自绘富文本 (换行/样式/math 占位)。"""

    def __init__(self, text: str, base_size: int = 24, parent=None):
        super().__init__(parent)
        self._text = text
        self._base = base_size
        self.setMinimumSize(480, 160)
        self._runs = []
        if _framework_parse_rich is not None:
            try:
                self._runs = _framework_parse_rich(
                    text, base_size=base_size,
                    base_color=(235, 235, 235))
            except Exception:
                self._runs = []
        self._layout_cache = None   # (width, [(text, fmt, w, h), ...])

    def paintEvent(self, _event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#14141c"))
        if not self._runs:
            p.setPen(QColor("#888"))
            p.drawText(self.rect(), Qt.AlignCenter, t("richpreview.empty"))
            return
        p.setRenderHint(QPainter.Antialiasing)
        lines = self._layout(self.width() - 24)
        y = 16
        for line in lines:
            x = 12
            max_h = 0
            for text, fmt, w, h in line:
                f = QFont("Microsoft YaHei", 10)
                if fmt.get("size"):
                    f.setPixelSize(int(fmt["size"]))
                if fmt.get("bold"):
                    f.setBold(True)
                if fmt.get("italic"):
                    f.setItalic(True)
                f.setUnderline(bool(fmt.get("underline")))
                p.setFont(f)
                col = fmt.get("color") or (235, 235, 235)
                p.setPen(QColor(*[int(c) for c in col[:3]]))
                if fmt.get("math"):
                    p.setPen(QColor("#e88ad0"))
                p.drawText(x, y, text)
                x += w
                max_h = max(max_h, h)
            y += max_h + 6

    def _layout(self, max_w: int):
        """Runs -> 行列表 (按宽度换行)。"""
        if self._layout_cache and self._layout_cache[0] == max_w:
            return self._layout_cache[1]
        from PySide6.QtGui import QFontMetrics
        lines = []
        cur = []
        x = 0
        for run in self._runs:
            text = run.text if not run.math else "[公式]"
            f = QFont("Microsoft YaHei", 10)
            if run.size:
                f.setPixelSize(int(run.size))
            if run.bold:
                f.setBold(True)
            if run.italic:
                f.setItalic(True)
            f.setUnderline(run.underline)
            fm = QFontMetrics(f)
            w = fm.horizontalAdvance(text)
            h = fm.height()
            # 公式按源码宽度估算 (占位)
            if run.math:
                w = fm.horizontalAdvance("[公式: %s]" % run.text[:12]) + 8
                text = "[公式: %s]" % run.text[:12]
            if cur and x + w > max_w:
                lines.append(cur)
                cur = []
                x = 0
            cur.append((text, {"color": run.color, "size": run.size,
                               "bold": run.bold, "italic": run.italic,
                               "underline": run.underline, "math": run.math},
                        w, h))
            x += w + 2
        if cur:
            lines.append(cur)
        self._layout_cache = (max_w, lines)
        return lines


class RichPreviewDialog(QDialog):
    """富文本预览对话框 (显示某段文本在当前引擎标记下的效果)。"""

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(t("richpreview.title"))
        self.resize(560, 300)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(t("richpreview.hint")))
        self.widget = RichPreviewWidget(text)
        lay.addWidget(self.widget, 1)
        btn = QPushButton(t("richpreview.close"))
        btn.clicked.connect(self.accept)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(btn)
        lay.addLayout(row)
