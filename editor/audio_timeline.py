"""音乐轨时间线 (P3): 音频条目的横向时间线视图。

自绘 QWidget (规避 QGraphicsItem 渲染崩溃):
- 行 = 轨 (音乐/音效/音量/控制), 列 = 条目顺序 (虚拟时间轴)
- 条目 = 圆角块 (操作 + 对象 + 参数摘要), 按类型着色
- 交互: 点击选中 / 拖拽排序 / 双击回调 (编辑)
- set_items / items_data 纯数据往返 (可测试)
"""

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from editor.i18n import t

_ROW_DEFS = [("music", "audio.row_music", "#2d6cdf"),
             ("sfx", "audio.row_sfx", "#e8890c"),
             ("volume", "audio.row_volume", "#2e9e5b"),
             ("control", "audio.row_control", "#d64550")]

_PX_PER_SEC = 36          # 时间轴像素比例 (秒 -> px)
_MIN_DUR = {"music": 3.0, "sfx": 0.6, "volume": 0.5, "control": 0.5}
_ROW_H = 34
_PAD = 6
_SCALE_H = 22            # 顶部时间标尺高度
_ROW_X0 = 70             # 轨标签宽度


class AudioTimeline(QWidget):
    """音频轨时间线。"""

    item_activated = Signal(int)      # 双击条目 index
    reordered = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.items = []               # [{"row", "text", "op"}]
        self.selected = -1
        self._drag = -1
        self.setMinimumHeight(_SCALE_H + len(_ROW_DEFS) * _ROW_H + _PAD * 2 + 8)
        self.setStyleSheet("background:#1c1c28;")

    # ---- 数据 ---------------------------------------------------------
    def set_items(self, items):
        """items: audio 条目列表 (4 字段)。"""
        self.items = [self._to_disp(it) for it in items]
        self.selected = -1
        self.update()

    def items_data(self):
        return [list(d["data"]) for d in self.items]

    def _to_disp(self, row):
        row = (list(row) + ["", "", "", ""])[:4]
        op, a, b, c = row
        row_key = ("control" if op in ("pause", "resume", "stop")
                   else op if op in ("music", "sfx", "volume") else "control")
        text = {"music": "♪ %s" % a, "sfx": "◆ %s" % a,
                "volume": t("audio.volume_prefix", a=a,
                            extra="·%s" % b if a == "voice" else ""),
                }.get(op, "%s %s" % (op, a))
        if op == "music" and c:
            text += " fade %s" % c
        if op == "volume" and c:
            text += " %s" % c
        return {"row": row_key, "text": text, "op": op, "data": row}

    # ---- 几何 (横向时间轴) -------------------------------------------
    def _row_index(self, key):
        for i, (k, _l, _c) in enumerate(_ROW_DEFS):
            if k == key:
                return i
        return 3

    def _row_rect(self, row_idx):
        y = _SCALE_H + _PAD + row_idx * _ROW_H
        return QRectF(_ROW_X0, y, max(10, self.width() - _ROW_X0 - 8),
                      _ROW_H - 6)

    def _duration_of(self, d):
        """条目估算时长 (秒) —— 时间轴宽度依据。"""
        op = d["op"]
        data = d.get("data", [])
        c = data[3] if len(data) > 3 else ""
        if op == "music" and c:
            try:
                return max(2.0, float(c) * 2)
            except ValueError:
                pass
        return _MIN_DUR.get(d["row"], 0.5)

    def _layout(self):
        """按顺序累计起点时间, 返回 [(start_sec, dur_sec)]。"""
        out = []
        t = 0.0
        for d in self.items:
            dur = self._duration_of(d)
            out.append((t, dur))
            t += dur + 0.2
        return out

    def _block_rect(self, index):
        d = self.items[index]
        row = self._row_index(d["row"])
        r = self._row_rect(row)
        start, dur = self._layout()[index]
        x = r.x() + start * _PX_PER_SEC
        w = max(36, dur * _PX_PER_SEC)
        return QRectF(x, r.y() + 3, w, r.height() - 6)

    def total_seconds(self):
        lays = self._layout()
        return lays[-1][0] + lays[-1][1] if lays else 0.0

    # ---- 绘制 (时间轴) ------------------------------------------------
    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w = self.width()

        # 顶部时间标尺
        p.setPen(QColor("#8888a0"))
        step = max(1, int(60 / _PX_PER_SEC))     # 每 60px 一格
        for s in range(0, int(self.total_seconds()) + step, step):
            x = _ROW_X0 + s * _PX_PER_SEC
            if x > w - 4:
                break
            p.drawText(QRectF(x - 14, 2, 40, 14), Qt.AlignCenter,
                       "%ds" % s)
            p.setPen(QPen(QColor("#2a2a3a"), 1))
            p.drawLine(x, _SCALE_H, x, self.height() - 2)
            p.setPen(QColor("#8888a0"))

        # 轨标签 + 基准线
        for i, (key, label_key, color) in enumerate(_ROW_DEFS):
            r = self._row_rect(i)
            p.setPen(QColor("#8888a0"))
            p.drawText(QRectF(4, r.y(), 60, r.height()),
                       Qt.AlignVCenter | Qt.AlignLeft, t(label_key))
            p.setPen(QPen(QColor("#262638"), 1))
            p.drawLine(r.x(), r.y() + r.height() / 2, w - 4,
                       r.y() + r.height() / 2)

        # 条目块 (宽度 ∝ 时长, 起点 = 累计时间)
        lays = self._layout()
        for i, d in enumerate(self.items):
            r = self._block_rect(i)
            color = QColor(self._color(d["row"]))
            p.setPen(QPen(color, 1.5) if i == self.selected
                     else QPen(QColor("#00000000"), 0))
            p.setBrush(QColor(color.red(), color.green(),
                              color.blue(), 200))
            p.drawRoundedRect(r, 6, 6)
            p.setPen(Qt.white)
            p.drawText(r.adjusted(6, 0, -6, 0), Qt.AlignVCenter,
                       d["text"][:16])
            # 起始时间标签 (块上方)
            start = lays[i][0]
            p.setPen(QColor("#9a9ab0"))
            p.drawText(QRectF(r.x(), r.y() - 14, 50, 12),
                       Qt.AlignLeft, "%.1fs" % start)
        p.end()

    def _color(self, row):
        for k, _l, c in _ROW_DEFS:
            if k == row:
                return c
        return "#888888"

    # ---- 交互 ---------------------------------------------------------
    def _hit(self, pos):
        for i in range(len(self.items) - 1, -1, -1):
            if self._block_rect(i).contains(pos):
                return i
        return -1

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            idx = self._hit(event.position().toPoint()
                            if hasattr(event.position(), "toPoint")
                            else event.pos())
            self.selected = idx
            self._drag = idx
            self.update()
            if idx >= 0:
                self.setCursor(Qt.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        idx = self._hit(event.position().toPoint()
                        if hasattr(event.position(), "toPoint")
                        else event.pos())
        if idx >= 0:
            self.item_activated.emit(idx)
        super().mouseDoubleClickEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag >= 0:
            pos = event.position().toPoint() if hasattr(
                event.position(), "toPoint") else event.pos()
            target = self._hit(pos)
            if target >= 0 and target != self._drag:
                it = self.items.pop(self._drag)
                self.items.insert(target, it)
                self._drag = target
                self.selected = target
                self.reordered.emit()
                self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag = -1
        self.unsetCursor()
        super().mouseReleaseEvent(event)

    def remove_selected(self):
        if 0 <= self.selected < len(self.items):
            del self.items[self.selected]
            self.selected = -1
            self.update()

    def set_item_data(self, index, row):
        """编辑后回写 (保持显示)。"""
        if 0 <= index < len(self.items):
            self.items[index] = self._to_disp(row)
            self.update()
