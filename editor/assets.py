"""素材库面板 (P2): 浏览 / 导入 / 管理项目 materials/ 下的资源。

- 按分类浏览: 图片 / 音频 / 字体 / 其他 (拖入文件自动归类)
- 图片生成缩略图, 其余显示扩展名色块
- 支持: 按钮导入 + 系统文件拖拽导入
- 双击图片 = 放大预览 (P2 简化版), 后续接"用于角色/场景"
"""

import os
import shutil

from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtGui import QColor, QDragEnterEvent, QDropEvent, QPainter, QPixmap
from PySide6.QtWidgets import (QComboBox, QFileDialog, QHBoxLayout, QLabel,
                               QListWidget, QListWidgetItem, QMessageBox,
                               QPushButton, QVBoxLayout, QWidget)

from editor.i18n import t

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}
AUDIO_EXTS = {".wav", ".mp3", ".ogg", ".flac", ".m4a"}
FONT_EXTS = {".ttf", ".otf", ".ttc"}

_CATEGORY_DIRS = [(None, None), ("image", "image"), ("audio", "audio"),
                  ("font", "font"), ("other", "other")]

_CAT_LABELS = {
    None: lambda: t("assets.cat_all"),
    "image": lambda: t("assets.cat_image"),
    "audio": lambda: t("assets.cat_audio"),
    "font": lambda: t("assets.cat_font"),
    "other": lambda: t("assets.cat_other"),
}

_EXT_CATEGORY = {}
for _e in IMAGE_EXTS:
    _EXT_CATEGORY[_e] = "image"
for _e in AUDIO_EXTS:
    _EXT_CATEGORY[_e] = "audio"
for _e in FONT_EXTS:
    _EXT_CATEGORY[_e] = "font"


def categorize(path: str) -> str:
    """按扩展名归类: image / audio / font / other。"""
    return _EXT_CATEGORY.get(os.path.splitext(path)[1].lower(), "other")


def _make_thumb(path: str, size: int = 96) -> QPixmap:
    """图片缩略图; 非图片生成带扩展名文字的颜色块。"""
    ext = os.path.splitext(path)[1].lower()
    if ext in IMAGE_EXTS:
        pix = QPixmap(path)
        if not pix.isNull():
            return pix.scaled(size, size, Qt.KeepAspectRatio,
                              Qt.SmoothTransformation)
    pix = QPixmap(size, size)
    pix.fill(QColor("#3a3a4a"))
    p = QPainter(pix)
    p.setPen(QColor("#cccccc"))
    p.drawText(pix.rect(), Qt.AlignCenter,
               (ext[1:] or "file").upper()[:5])
    p.end()
    return pix


class AssetPanel(QWidget):
    """素材库面板。"""

    status = Signal(str)   # 状态消息 (可接主窗口状态栏/输出)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.project = None
        self._root = ""            # materials 根目录

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)

        # 顶栏: 分类 + 导入 + 刷新
        bar = QHBoxLayout()
        self.cb_cat = QComboBox()
        for _label, _d in _CATEGORY_DIRS:
            self.cb_cat.addItem(_CAT_LABELS[_d]())
        self.cb_cat.currentIndexChanged.connect(self.refresh)
        btn_import = QPushButton(t("assets.import"))
        btn_import.clicked.connect(self._import_dialog)
        btn_refresh = QPushButton(t("assets.refresh"))
        btn_refresh.clicked.connect(self.refresh)
        hint = QLabel(t("assets.hint"))
        hint.setStyleSheet("color:#888;")
        bar.addWidget(self.cb_cat)
        bar.addWidget(btn_import)
        bar.addWidget(btn_refresh)
        bar.addStretch(1)
        bar.addWidget(hint)
        layout.addLayout(bar)

        # 素材网格
        self.list = QListWidget()
        self.list.setViewMode(QListWidget.IconMode)
        self.list.setIconSize(QSize(96, 96))
        self.list.setGridSize(QSize(116, 118))
        self.list.setResizeMode(QListWidget.Adjust)
        self.list.setMovement(QListWidget.Static)
        self.list.setWordWrap(True)
        self.list.itemDoubleClicked.connect(self._on_double)
        layout.addWidget(self.list, 1)

        self.setAcceptDrops(True)
        self.list.setAcceptDrops(True)
        self.list.dragEnterEvent = self._drag_enter
        self.list.dropEvent = self._drop

    # ---- 语言刷新 -----------------------------------------------------
    def apply_lang(self) -> None:
        idx = self.cb_cat.currentIndex()
        self.cb_cat.clear()
        for _label, d in _CATEGORY_DIRS:
            self.cb_cat.addItem(_CAT_LABELS[d]())
        self.cb_cat.setCurrentIndex(min(idx, self.cb_cat.count() - 1))
        self.refresh()

    # ---- 数据 ---------------------------------------------------------
    def set_project(self, project) -> None:
        self.project = project
        self._root = os.path.join(project.root, "materials") if project else ""
        self.refresh()

    def _category_dir(self) -> str | None:
        _label, sub = _CATEGORY_DIRS[self.cb_cat.currentIndex()]
        return sub

    def refresh(self) -> None:
        self.list.clear()
        if not self._root or not os.path.isdir(self._root):
            self.list.addItem(_item_placeholder(t("assets.empty_no_mats")))
            return
        sub = self._category_dir()
        count = 0
        for d in sorted(os.listdir(self._root)):
            full = os.path.join(self._root, d)
            if not os.path.isdir(full):
                continue
            if sub and d != sub:
                continue
            for f in sorted(os.listdir(full)):
                if f.startswith("."):
                    continue
                p = os.path.join(full, f)
                rel = os.path.relpath(p, self.project.root).replace("\\", "/")
                it = QListWidgetItem(_make_thumb(p), f)
                it.setData(Qt.UserRole, rel)
                it.setToolTip(rel)
                self.list.addItem(it)
                count += 1
        if count == 0:
            self.list.addItem(_item_placeholder(
                t("assets.empty_cat")))
        self.status.emit(t("assets.count", n=count))

    # ---- 导入 ---------------------------------------------------------
    def _import_dialog(self) -> None:
        files, _f = QFileDialog.getOpenFileNames(
            self, "导入素材",
            "",
            "素材文件 (*.png *.jpg *.jpeg *.gif *.bmp *.webp "
            "*.wav *.mp3 *.ogg *.flac *.m4a *.ttf *.otf *.ttc)")
        if files:
            self._import_files(files)

    def _import_files(self, paths: list) -> int:
        if not self.project:
            QMessageBox.information(self, t("status.no_project"), t("assets.no_project"))
            return 0
        os.makedirs(self._root, exist_ok=True)
        imported = 0
        for src in paths:
            if not os.path.isfile(src):
                continue
            cat = categorize(src)
            d = os.path.join(self._root, cat)
            os.makedirs(d, exist_ok=True)
            dst = os.path.join(d, os.path.basename(src))
            # 重名自动改名: name_1.ext
            base, ext = os.path.splitext(dst)
            n = 1
            while os.path.exists(dst):
                dst = "%s_%d%s" % (base, n, ext)
                n += 1
            shutil.copy2(src, dst)
            imported += 1
        self.refresh()
        self.status.emit(t("assets.imported", n=imported))
        return imported

    # ---- 拖拽 ---------------------------------------------------------
    def _drag_enter(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def _drop(self, event: QDropEvent) -> None:
        paths = [u.toLocalFile() for u in event.mimeData().urls()]
        paths = [p for p in paths if os.path.isfile(p)]
        if paths:
            self._import_files(paths)
            event.acceptProposedAction()

    # ---- 交互 ---------------------------------------------------------
    def _on_double(self, item: QListWidgetItem) -> None:
        rel = item.data(Qt.UserRole)
        if not rel:
            return
        path = os.path.join(self.project.root, rel)
        if os.path.splitext(rel)[1].lower() in IMAGE_EXTS:
            # P2 简化预览: 状态栏显示路径 (后续放大预览/接角色场景)
            self.status.emit("素材: %s" % rel)
        else:
            self.status.emit("素材: %s" % rel)


def _item_placeholder(text: str) -> QListWidgetItem:
    it = QListWidgetItem(text)
    it.setFlags(Qt.NoItemFlags)
    it.setSizeHint(QSize(400, 120))
    return it
