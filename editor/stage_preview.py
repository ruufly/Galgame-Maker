"""场景分镜引擎预览 (P3): 用真实 framework 引擎渲染 stage 节点。

原理:
- 由 stage 节点生成临时 .gal 脚本 (内联 char 定义 + 绝对路径素材,
  写到系统临时目录, 不污染项目)
- EnginePreviewThread 无头渲染数帧 -> 取帧显示
- 与游戏实际渲染完全一致 (WYSIWYG)

build_stage_script 为纯函数 (可测试)。
"""

import os
import tempfile

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel,
                               QListWidget, QListWidgetItem, QPushButton,
                               QVBoxLayout, QWidget)

from editor.preview import PreviewPanel, EnginePreviewThread
from editor.flow_editor import resolve_bg_image
from editor.definitions import CHAR_RESERVED, iter_defs
from editor.i18n import t

PREVIEW_W, PREVIEW_H = 1280, 720


def build_stage_script(project, node) -> str:
    """由 stage 节点生成临时 .gal 脚本文本。"""
    root = project.root
    # 收集项目 char 定义 (立绘 -> 绝对路径)
    char_defs = {}
    cast = project.scripts.get("cast.gal")
    if cast is not None:
        for c in iter_defs(cast, "char"):
            paths = {}
            for k, v in c.kwargs.items():
                if k in CHAR_RESERVED and k not in ("default",):
                    continue
                full = os.path.join(root, str(v))
                if os.path.isfile(full):
                    paths[k] = full.replace("\\", "/")
            if paths:
                char_defs[c.args[0]] = paths

    lines = ["window",
             "    width: %d" % PREVIEW_W,
             "    height: %d" % PREVIEW_H, ""]
    for cid, paths in char_defs.items():
        lines.append("char %s" % cid)
        for k, v in paths.items():
            lines.append('    %s: "%s"' % (k, v))
    lines.append("")
    lines.append("start:")

    bg_path = resolve_bg_image(project, node)
    if bg_path:
        lines.append('    bg "%s"' % bg_path.replace("\\", "/"))
    for act, char, expr, eff in node.data.get("sprites", []):
        if act == "clear":
            lines.append("    clear")
            continue
        suffix = " with %s" % eff if eff else ""
        if act == "show" and expr:
            lines.append("    show %s %s%s" % (char, expr, suffix))
        else:
            lines.append("    %s %s%s" % (act, char, suffix))
    lines.append('    text "%s"' % t("stage_preview.placeholder_text"))
    return "\n".join(lines) + "\n"




class LayoutCanvas(QWidget):
    """立绘排布画布: 背景 + 可拖动立绘 (自绘, 不使用 QGraphicsItem)。

    坐标: 位置存归一化比例 (0-1, 相对画布), 应用时换算引擎逻辑分辨率。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._bg = None               # QPixmap 背景
        self._sprites = []            # [{"char", "path", "x", "y", "h_ratio"}]
        self._drag_index = -1
        self.setMinimumSize(560, 315)
        self.setStyleSheet("background:#101018;")

    # ---- 数据 ---------------------------------------------------------
    def set_background(self, path):
        self._bg = QPixmap(path) if path and os.path.isfile(path) else None
        self.update()

    def set_sprite_list(self, sprites):
        """sprites: [{"char", "path"}] 重置为底部默认排布。"""
        self._sprites = []
        n = max(1, len(sprites))
        for i, sp in enumerate(sprites):
            pix = QPixmap(sp["path"]) if os.path.isfile(sp["path"]) else None
            self._sprites.append({"char": sp["char"], "path": sp["path"],
                                  "pix": pix,
                                  "x": (i + 1) / (n + 1), "y": 1.0})
        self.update()

    def add_sprite(self, char, path):
        pix = QPixmap(path) if os.path.isfile(path) else None
        self._sprites.append({"char": char, "path": path, "pix": pix,
                              "x": 0.5, "y": 1.0})
        self.update()

    def positions(self):
        """{char: (x_norm, y_norm)}。"""
        return {s["char"]: (round(s["x"], 3), round(s["y"], 3))
                for s in self._sprites}

    # ---- 绘制 ---------------------------------------------------------
    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        w, h = self.width(), self.height()
        # 背景 (cover 缩放)
        if self._bg is not None and not self._bg.isNull():
            scale = max(w / self._bg.width(), h / self._bg.height())
            nw, nh = int(self._bg.width() * scale), int(self._bg.height() * scale)
            p.drawPixmap((w - nw) // 2, (h - nh) // 2, nw, nh,
                         self._bg)
        else:
            p.fillRect(0, 0, w, h, QColor("#20203a"))
        # 立绘 (底部对齐, 高度 = 画布高)
        for s in self._sprites:
            pix = s.get("pix")
            sh = int(h * 0.92)
            sw = int(pix.width() * sh / pix.height()) if pix else 60
            x = int(s["x"] * w) - sw // 2
            y = int(s["y"] * h) - sh
            s["_rect"] = (x, y, sw, sh)
            if pix and not pix.isNull():
                p.drawPixmap(x, y, sw, sh, pix)
            else:
                p.fillRect(x, y, sw, sh, QColor("#44445a"))
                p.setPen(QColor("#ccc"))
                p.drawText(x, y, sw, sh, Qt.AlignCenter, s["char"][:6])
            # 名字
            p.setPen(QColor("#ffffff"))
            p.drawText(x, y - 16, sw, 16, Qt.AlignCenter, s["char"])
        p.end()

    # ---- 交互 (拖动立绘) ---------------------------------------------
    def _hit(self, pos):
        for i, s in enumerate(self._sprites):
            r = s.get("_rect")
            if r and r[0] <= pos.x() <= r[0] + r[2]                     and r[1] <= pos.y() <= r[1] + r[3]:
                return i
        return -1

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_index = self._hit(event.position().toPoint()
                                         if hasattr(event.position(), "toPoint")
                                         else event.pos())
            self.setCursor(Qt.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_index >= 0 and self._drag_index < len(self._sprites):
            pos = event.position().toPoint() if hasattr(event.position(), "toPoint") else event.pos()
            s = self._sprites[self._drag_index]
            s["x"] = min(1.0, max(0.0, pos.x() / max(1, self.width())))
            s["y"] = min(1.0, max(0.0, pos.y() / max(1, self.height())))
            self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_index = -1
        self.unsetCursor()
        super().mouseReleaseEvent(event)

class StagePreviewDialog(QDialog):
    """场景预览 + 立绘排布 (引擎真实渲染 + 拖放定位)。"""

    def __init__(self, project, node, parent=None, on_apply=None):
        super().__init__(parent)
        self.setWindowTitle(t("stage_preview.title"))
        self.resize(980, 640)
        self._tmp_path = ""
        self._on_apply = on_apply

        layout = QVBoxLayout(self)
        hint = QLabel(t("stage_preview.hint"))
        hint.setStyleSheet("color:#888;")
        layout.addWidget(hint)

        self.preview = PreviewPanel()
        layout.addWidget(self.preview, 1)

        # ---- 立绘排布区 ----
        row = QHBoxLayout()
        left = QVBoxLayout()
        lbl = QLabel(t("stage_preview.sprite_source"))
        left.addWidget(lbl)
        self.sprite_list = QListWidget()
        self.sprite_list.itemDoubleClicked.connect(self._add_sprite)
        left.addWidget(self.sprite_list, 1)
        btn_apply = QPushButton(t("stage_preview.apply_positions"))
        btn_apply.clicked.connect(self._apply_positions)
        left.addWidget(btn_apply)
        row.addLayout(left, 1)

        self.canvas = LayoutCanvas()
        row.addWidget(self.canvas, 3)
        layout.addLayout(row)

        # 载入背景与立绘源
        self._load_sources(project, node)

        # 生成临时脚本
        try:
            script_text = build_stage_script(project, node)
            fd, self._tmp_path = tempfile.mkstemp(
                suffix=".gal", prefix="stage_preview_")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(script_text)
            self.preview.set_script(self._tmp_path)
            self.preview.start()
        except Exception as exc:
            self.preview.view.setText(t("stage_preview.gen_failed", exc=exc))

    def _load_sources(self, project, node):
        """载入背景图 + 项目立绘源列表。"""
        bg = resolve_bg_image(project, node)
        self.canvas.set_background(bg)
        # 立绘源: 项目 char 定义的表情路径
        self._char_paths = {}
        cast = project.scripts.get("cast.gal") if project else None
        if cast is not None:
            from editor.definitions import CHAR_RESERVED, iter_defs
            for c in iter_defs(cast, "char"):
                cid = c.args[0]
                paths = []
                for k, v in c.kwargs.items():
                    if k in CHAR_RESERVED and k not in ("default",):
                        continue
                    full = os.path.join(project.root, str(v))
                    if os.path.isfile(full):
                        paths.append((k, full))
                if paths:
                    self._char_paths[cid] = paths
                    for expr, path in paths:
                        it = QListWidgetItem("%s [%s]" % (cid, expr))
                        it.setData(Qt.UserRole, (cid, path))
                        self.sprite_list.addItem(it)

    def _add_sprite(self, item):
        data = item.data(Qt.UserRole)
        if data:
            cid, path = data
            self.canvas.add_sprite(cid, path)

    def _apply_positions(self):
        if self._on_apply is not None:
            moves = []
            for char, (x, y) in self.canvas.positions().items():
                # 归一化 -> 引擎逻辑分辨率 (1280x720)
                px = int(x * PREVIEW_W)
                py = int(y * PREVIEW_H)
                moves.append([char, "%d,%d" % (px, py), "0", "", ""])
            self._on_apply(moves)
            self.preview.view.setToolTip(
                t("stage_preview.applied", n=len(moves)))

    def closeEvent(self, event):
        self.preview.stop()
        if self.preview._thread is not None:
            self.preview._thread.wait(3000)
        if self._tmp_path and os.path.isfile(self._tmp_path):
            try:
                os.remove(self._tmp_path)
            except OSError:
                pass
        super().closeEvent(event)
