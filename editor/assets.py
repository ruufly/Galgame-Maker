"""素材库面板 (P4 重写): 递归目录树 + 预览 + 右键管理。

- 树视图按**素材目录原样**组织 (递归遍历项目根, 跳过运行时/代码文件)
- 双击: 图片放大预览 / 音频播放 / 字体样例 / 其它打开所在文件夹
- 右键: 重命名 / 删除 / 复制相对路径 / 打开所在文件夹
- 顶栏: 分类过滤 + 导入 + 刷新; 支持系统文件拖拽导入
"""

import os
import shutil

from PySide6.QtCore import QFileInfo, Qt, QSize, Signal
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (QComboBox, QDialog, QFileDialog, QFileIconProvider,
                               QHBoxLayout, QInputDialog, QLabel, QListWidget,
                               QListWidgetItem, QMenu, QMessageBox,
                               QPushButton, QTreeWidget, QTreeWidgetItem,
                               QVBoxLayout, QWidget)

from editor.i18n import t

_ICON_PROVIDER = QFileIconProvider()

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}
AUDIO_EXTS = {".wav", ".mp3", ".ogg", ".flac", ".m4a"}
FONT_EXTS = {".ttf", ".otf", ".ttc"}
_RESOURCE_EXTS = (IMAGE_EXTS | AUDIO_EXTS | FONT_EXTS
                  | {".zip", ".rar", ".7z", ".txt", ".json", ".csv"})
_SKIP_DIRS = {"save", "logs", "__pycache__", "nowfiletmp", ".git", "lang",
              "framework", "editor", "test", "fonts"}
_SKIP_EXTS = {".py", ".pyc", ".gal", ".yml", ".yaml", ".md", ".gitignore"}

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


def _make_thumb(path: str, size: int = 64) -> QPixmap:
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


def _file_icon(path: str):
    """文件图标: 图片用缩略图, 其它用系统文件图标。"""
    ext = os.path.splitext(path)[1].lower()
    if ext in IMAGE_EXTS:
        pix = _make_thumb(path, 24)
        from PySide6.QtGui import QIcon
        return QIcon(pix)
    info = os.path.abspath(path)
    return _ICON_PROVIDER.icon(QFileInfo(info))


# ----------------------------------------------------------------------
# 预览对话框
# ----------------------------------------------------------------------
class ImagePreviewDialog(QDialog):
    """图片放大预览 (滚轮缩放, 显示尺寸信息)。"""

    def __init__(self, path: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(os.path.basename(path))
        self.resize(720, 560)
        lay = QVBoxLayout(self)
        self.lbl = QLabel()
        self.lbl.setAlignment(Qt.AlignCenter)
        self.lbl.setStyleSheet("background:#14141c;")
        lay.addWidget(self.lbl, 1)
        pix = QPixmap(path)
        self._orig = pix
        self._scale = 1.0
        info = "%d × %d" % (pix.width(), pix.height())
        self.lbl_info = QLabel(info)
        self.lbl_info.setStyleSheet("color:#888;")
        lay.addWidget(self.lbl_info)
        self._render()

    def _render(self) -> None:
        w = max(1, int(self._orig.width() * self._scale))
        h = max(1, int(self._orig.height() * self._scale))
        self.lbl.setPixmap(self._orig.scaled(
            w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def wheelEvent(self, event):
        self._scale *= 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self._scale = min(max(self._scale, 0.1), 8.0)
        self._render()
        event.accept()


class FontPreviewDialog(QDialog):
    """字体预览: 用字体渲染样例文本。"""

    def __init__(self, path: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(os.path.basename(path))
        self.resize(560, 300)
        lay = QVBoxLayout(self)
        f = QFont(path, 28)
        lbl = QLabel("Galgame Maker 预览\n中文示例: 你好，世界！\nThe quick brown fox 0123456789")
        lbl.setFont(f)
        lbl.setStyleSheet("color:#eaeaea; background:#14141c; padding:16px;")
        lay.addWidget(lbl, 1)


def open_audio_preview(path: str, parent=None) -> None:
    """音频播放对话框; QtMultimedia 不可用时用系统默认程序打开。"""
    try:
        from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
    except ImportError:
        os.startfile(path)   # noqa: S606 - 系统默认播放器
        return
    dlg = QDialog(parent)
    dlg.setWindowTitle(os.path.basename(path))
    dlg.resize(420, 120)
    lay = QVBoxLayout(dlg)
    lbl = QLabel(os.path.basename(path))
    lay.addWidget(lbl)
    row = QHBoxLayout()
    player = QMediaPlayer(dlg)
    out = QAudioOutput(dlg)
    player.setAudioOutput(out)
    from PySide6.QtCore import QUrl
    player.setSource(QUrl.fromLocalFile(os.path.abspath(path)))
    btn_play = QPushButton(t("assets.play"))
    btn_stop = QPushButton(t("assets.stop"))
    btn_play.clicked.connect(player.play)
    btn_stop.clicked.connect(player.stop)
    row.addWidget(btn_play)
    row.addWidget(btn_stop)
    row.addStretch(1)
    lay.addLayout(row)
    dlg.finished.connect(lambda _r: player.stop())
    player.play()
    dlg.exec()


# ----------------------------------------------------------------------
# 面板
# ----------------------------------------------------------------------
class AssetPanel(QWidget):
    """素材树面板 (递归目录组织 + 预览 + 右键管理)。"""

    status = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.project = None
        self._root = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)

        bar = QHBoxLayout()
        self.cb_cat = QComboBox()
        for _label, d in ((None, None), ("image", "image"),
                          ("audio", "audio"), ("font", "font"),
                          ("other", "other")):
            self.cb_cat.addItem(_CAT_LABELS[d](), d)
        self.cb_cat.currentIndexChanged.connect(self.refresh)
        btn_import = QPushButton(t("assets.import"))
        btn_import.clicked.connect(self._import_dialog)
        btn_newdir = QPushButton(t("assets.new_dir"))
        btn_newdir.clicked.connect(self._new_dir)
        btn_refresh = QPushButton(t("assets.refresh"))
        btn_refresh.clicked.connect(self.refresh)
        bar.addWidget(self.cb_cat)
        bar.addWidget(btn_import)
        bar.addWidget(btn_newdir)
        bar.addWidget(btn_refresh)
        bar.addStretch(1)
        self.lbl_path = QLabel("")
        self.lbl_path.setStyleSheet("color:#888;")
        bar.addWidget(self.lbl_path)
        layout.addLayout(bar)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels([t("assets.col_name"), t("assets.col_type")])
        self.tree.setColumnWidth(0, 320)
        self.tree.itemDoubleClicked.connect(self._on_double)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._context_menu)
        self.tree.setDragDropMode(QTreeWidget.DropOnly)
        layout.addWidget(self.tree, 1)

        self.setAcceptDrops(True)
        self.tree.setAcceptDrops(True)
        self.tree.dragEnterEvent = self._drag_enter
        self.tree.dropEvent = self._drop

    # ---- 语言刷新 -----------------------------------------------------
    def apply_lang(self) -> None:
        idx = self.cb_cat.currentIndex()
        self.cb_cat.clear()
        for _label, d in ((None, None), ("image", "image"),
                          ("audio", "audio"), ("font", "font"),
                          ("other", "other")):
            self.cb_cat.addItem(_CAT_LABELS[d](), d)
        self.cb_cat.setCurrentIndex(min(idx, self.cb_cat.count() - 1))
        self.refresh()

    # ---- 数据 ---------------------------------------------------------
    def set_project(self, project) -> None:
        self.project = project
        self._root = project.root if project else ""
        self.refresh()

    def refresh(self) -> None:
        self.tree.clear()
        if not self._root or not os.path.isdir(self._root):
            return
        cat = self.cb_cat.currentData()
        root_item = QTreeWidgetItem([os.path.basename(self._root) or "project"])
        root_item.setIcon(0, _ICON_PROVIDER.icon(QFileIconProvider.Folder))
        self._walk(self._root, root_item, cat)
        self.tree.addTopLevelItem(root_item)
        root_item.setExpanded(True)
        self.lbl_path.setText(self._root)
        count = self._count_files(root_item)
        self.status.emit(t("assets.count", n=count))

    @staticmethod
    def _count_files(item: QTreeWidgetItem) -> int:
        n = 0
        for i in range(item.childCount()):
            child = item.child(i)
            n += 1 if child.data(0, Qt.UserRole) else 0
            n += AssetPanel._count_files(child)
        return n

    def _walk(self, dir_path: str, parent: QTreeWidgetItem, cat) -> None:
        try:
            entries = sorted(os.listdir(dir_path),
                             key=lambda n: (not os.path.isdir(
                                 os.path.join(dir_path, n)), n.lower()))
        except OSError:
            return
        for name in entries:
            full = os.path.join(dir_path, name)
            if os.path.isdir(full):
                if name in _SKIP_DIRS:
                    continue
                node = QTreeWidgetItem([name, ""])
                node.setIcon(0, _ICON_PROVIDER.icon(QFileIconProvider.Folder))
                parent.addChild(node)
                self._walk(full, node, cat)
            else:
                ext = os.path.splitext(name)[1].lower()
                if ext in _SKIP_EXTS:
                    continue
                if cat and categorize(full) != cat:
                    continue
                rel = os.path.relpath(full, self._root).replace("\\", "/")
                c = categorize(full)
                node = QTreeWidgetItem(
                    [name, {"image": t("assets.cat_image"),
                            "audio": t("assets.cat_audio"),
                            "font": t("assets.cat_font"),
                            "other": t("assets.cat_other")}.get(c, c)])
                # 图片用缩略图, 其它用系统文件图标
                node.setIcon(0, _file_icon(full))
                node.setData(0, Qt.UserRole, rel)
                node.setToolTip(0, rel)
                parent.addChild(node)

    # ---- 选中/路径 ----------------------------------------------------
    def _selected_rel(self) -> str | None:
        it = self.tree.currentItem()
        if it is None:
            return None
        rel = it.data(0, Qt.UserRole)
        return rel if rel else None

    def _selected_dir(self) -> str | None:
        """当前选中目录的绝对路径 (文件则取其所在目录)。"""
        return self._dir_of_item(self.tree.currentItem())

    # ---- 交互 ---------------------------------------------------------
    def _on_double(self, item: QTreeWidgetItem, _col: int) -> None:
        rel = item.data(0, Qt.UserRole)
        if not rel:
            return
        path = os.path.join(self._root, rel)
        ext = os.path.splitext(rel)[1].lower()
        if ext in IMAGE_EXTS:
            ImagePreviewDialog(path, self).exec()
        elif ext in FONT_EXTS:
            FontPreviewDialog(path, self).exec()
        elif ext in AUDIO_EXTS:
            open_audio_preview(path, self)
        else:
            os.startfile(os.path.dirname(path))   # noqa: S606

    def _context_menu(self, pos) -> None:
        it = self.tree.itemAt(pos)
        if it is None:
            return
        menu = QMenu(self)
        rel = it.data(0, Qt.UserRole)
        if rel:
            a_open = QAction(t("assets.open_folder"), self)
            a_open.triggered.connect(
                lambda: os.startfile(os.path.dirname(
                    os.path.join(self._root, rel))))
            a_ren = QAction(t("assets.rename"), self)
            a_ren.triggered.connect(lambda: self._rename(rel))
            a_del = QAction(t("assets.delete"), self)
            a_del.triggered.connect(lambda: self._delete(rel))
            a_copy = QAction(t("assets.copy_path"), self)
            a_copy.triggered.connect(
                lambda: self._copy_path(rel))
            menu.addAction(a_open)
            menu.addAction(a_ren)
            menu.addAction(a_del)
            menu.addSeparator()
            menu.addAction(a_copy)
        else:
            a_import_here = QAction(t("assets.import_here"), self)
            a_import_here.triggered.connect(self._import_here)
            a_newdir = QAction(t("assets.new_dir_here"), self)
            a_newdir.triggered.connect(self._new_dir)
            menu.addAction(a_import_here)
            menu.addAction(a_newdir)
        menu.exec(self.tree.viewport().mapToGlobal(pos))

    def _import_here(self) -> None:
        files, _f = QFileDialog.getOpenFileNames(
            self, "导入素材", "",
            "素材文件 (*.png *.jpg *.jpeg *.gif *.bmp *.webp "
            "*.wav *.mp3 *.ogg *.flac *.m4a *.ttf *.otf *.ttc)")
        if files:
            self._import_files(files, target_dir=self._selected_dir())

    def _rename(self, rel: str) -> None:
        old = os.path.join(self._root, rel)
        base = os.path.basename(rel)
        new_name, ok = QInputDialog.getText(self, t("assets.rename"), "",
                                            text=base)
        if not ok or not new_name.strip() or new_name.strip() == base:
            return
        new_name = new_name.strip()
        new_path = os.path.join(os.path.dirname(old), new_name)
        try:
            os.rename(old, new_path)
            self.refresh()
            self.status.emit(t("assets.renamed", name=new_name))
        except OSError as exc:
            QMessageBox.critical(self, t("assets.rename"), str(exc))

    def _delete(self, rel: str) -> None:
        path = os.path.join(self._root, rel)
        if QMessageBox.question(self, t("assets.delete"),
                                t("assets.delete_confirm", name=rel)) \
                != QMessageBox.Yes:
            return
        try:
            os.remove(path)
            self.refresh()
            self.status.emit(t("assets.deleted", name=rel))
        except OSError as exc:
            QMessageBox.critical(self, t("assets.delete"), str(exc))

    def _copy_path(self, rel: str) -> None:
        from PySide6.QtGui import QGuiApplication
        QGuiApplication.clipboard().setText(rel)
        self.status.emit(t("assets.copied", path=rel))

    def _new_dir(self) -> None:
        base = self._selected_dir() or self._root
        name, ok = QInputDialog.getText(self, t("assets.new_dir"), "")
        if not ok or not name.strip():
            return
        try:
            os.makedirs(os.path.join(base, name.strip()), exist_ok=True)
            self.refresh()
        except OSError as exc:
            QMessageBox.critical(self, t("assets.new_dir"), str(exc))

    # ---- 导入 ---------------------------------------------------------
    def _import_dialog(self) -> None:
        files, _f = QFileDialog.getOpenFileNames(
            self, "导入素材", "",
            "素材文件 (*.png *.jpg *.jpeg *.gif *.bmp *.webp "
            "*.wav *.mp3 *.ogg *.flac *.m4a *.ttf *.otf *.ttc)")
        if files:
            # 导入到当前选中的目录 (文件夹化组织)
            self._import_files(files, target_dir=self._selected_dir())

    def _import_files(self, paths: list, target_dir: str | None = None) -> int:
        """导入素材文件。

        target_dir 显式指定 -> 导入到该目录 (文件夹化组织);
        target_dir=None -> 兼容旧行为: 导入到 materials/<分类>/。
        重名自动 _N 改名。测试依赖此方法。
        """
        if not self.project:
            self.status.emit(t("assets.no_project"))
            return 0
        if target_dir is None:
            target_dir = os.path.join(self._root, "materials")
            os.makedirs(target_dir, exist_ok=True)
        else:
            os.makedirs(target_dir, exist_ok=True)
        imported = 0
        for src in paths:
            if not os.path.isfile(src):
                continue
            cat = categorize(src)
            # 目标为 materials 根时按分类归档 (兼容); 其它目录原样放入
            if os.path.abspath(target_dir) == os.path.abspath(
                    os.path.join(self._root, "materials")):
                d = os.path.join(target_dir, cat)
            else:
                d = target_dir
            os.makedirs(d, exist_ok=True)
            dst = os.path.join(d, os.path.basename(src))
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
    def _drag_enter(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def _drop(self, event) -> None:
        paths = [u.toLocalFile() for u in event.mimeData().urls()]
        paths = [p for p in paths if os.path.isfile(p)]
        if not paths:
            return
        # 拖到目录节点 -> 导入到该目录; 否则导入到选中目录/materials
        item = self.tree.itemAt(event.position().toPoint())
        target = self._dir_of_item(item)
        if target is None:
            target = self._selected_dir()
        self._import_files(paths, target_dir=target)
        event.acceptProposedAction()

    def _dir_of_item(self, item) -> str | None:
        """目录节点 -> 绝对路径; 文件节点 -> 其所在目录; None=无法确定。"""
        if item is None:
            return None
        rel = item.data(0, Qt.UserRole)
        if rel:
            return os.path.dirname(os.path.join(self._root, rel))
        # 目录节点: 从树路径反推
        parts = []
        node = item
        while node is not None:
            if node.data(0, Qt.UserRole) is None:
                parts.insert(0, node.text(0))
            node = node.parent()
        if parts and parts[0] == (os.path.basename(self._root) or "project"):
            parts = parts[1:]
        return os.path.join(self._root, *parts) if parts else self._root
