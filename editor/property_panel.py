"""属性面板 (右 Dock): 显示并快捷编辑选中对象的属性。

当前范围:
- 流程节点 (dialogue/choice/jump/ending/label/stage/action/raw/if):
  通用字段直接编辑; 复杂编辑提供"打开完整编辑对话框"按钮
- 素材文件: 路径/类型/大小/图片尺寸 + 预览/重命名/删除/打开文件夹
- 定义 (角色/场景/声音): 字段概览 + "打开完整编辑…" (DefDialog)
"""

import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFormLayout, QHBoxLayout,
                               QLabel, QLineEdit, QPushButton, QVBoxLayout,
                               QWidget, QInputDialog, QMessageBox)

from editor.i18n import t
from editor.lang_dialog import make_lang_edit_widget


class PropertyPanel(QWidget):
    """右侧属性面板。"""

    changed = Signal(str)   # "assets" / "defs" -> 主窗口刷新对应面板

    def __init__(self, parent=None):
        super().__init__(parent)
        self._gl = None          # GameLang (多语言显示)
        self._node = None
        self._flow_scene = None
        self.project = None      # 素材/定义编辑用
        self._rebuilding = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        self.title = QLabel(t("props.empty"))
        self.title.setStyleSheet("font-weight:bold; color:#d8d8e0;")
        self.title.setWordWrap(True)
        layout.addWidget(self.title)
        self.body = QVBoxLayout()
        layout.addLayout(self.body)
        layout.addStretch(1)

    # ---- 绑定 ---------------------------------------------------------
    def set_lang(self, gl) -> None:
        self._gl = gl

    def set_project(self, project) -> None:
        self.project = project

    def set_flow_scene(self, scene) -> None:
        self._flow_scene = scene

    def show_message(self, text: str) -> None:
        self.title.setText(text)
        self._clear_body()
        self._node = None

    # ---- 素材文件 -----------------------------------------------------
    def show_asset(self, rel) -> None:
        self._clear_body()
        self._node = None
        if not rel or self.project is None:
            self.title.setText(t("props.no_selection"))
            return
        path = os.path.join(self.project.root, rel)
        if not os.path.isfile(path):
            self.title.setText(t("props.asset_missing"))
            return
        self.title.setText("%s [%s]" % (t("props.asset"), rel))
        form = QFormLayout()
        form.addRow(t("props.path"), QLabel(rel))
        ext = os.path.splitext(rel)[1].lower()
        form.addRow(t("props.type"), QLabel(_cat_label(ext)))
        try:
            size = os.path.getsize(path)
            form.addRow(t("props.size"),
                        QLabel("%.1f KB" % (size / 1024.0)))
        except OSError:
            pass
        if ext in (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"):
            from PySide6.QtGui import QPixmap
            pix = QPixmap(path)
            if not pix.isNull():
                form.addRow(t("props.dimension"),
                            QLabel("%d × %d" % (pix.width(), pix.height())))
        self.body.addLayout(form)

        row = QHBoxLayout()
        b_preview = QPushButton(t("props.preview"))
        b_preview.clicked.connect(lambda: _preview_asset(path, ext, self))
        b_open = QPushButton(t("assets.open_folder"))
        b_open.clicked.connect(
            lambda: os.startfile(os.path.dirname(path)))
        b_copy = QPushButton(t("assets.copy_path"))
        b_copy.clicked.connect(
            lambda: _copy_text(rel))
        row.addWidget(b_preview)
        row.addWidget(b_open)
        row.addWidget(b_copy)
        self.body.addLayout(row)

        row2 = QHBoxLayout()
        b_ren = QPushButton(t("assets.rename"))
        b_ren.clicked.connect(lambda: self._rename_asset(rel, path))
        b_del = QPushButton(t("assets.delete"))
        b_del.clicked.connect(lambda: self._delete_asset(rel, path))
        row2.addWidget(b_ren)
        row2.addWidget(b_del)
        row2.addStretch(1)
        self.body.addLayout(row2)

    def _rename_asset(self, rel: str, path: str) -> None:
        new_name, ok = QInputDialog.getText(
            self, t("assets.rename"), "", text=os.path.basename(rel))
        if not ok or not new_name.strip() or new_name.strip() == \
                os.path.basename(rel):
            return
        try:
            os.rename(path, os.path.join(os.path.dirname(path),
                                         new_name.strip()))
            self.changed.emit("assets")
        except OSError as exc:
            QMessageBox.critical(self, t("assets.rename"), str(exc))

    def _delete_asset(self, rel: str, path: str) -> None:
        if QMessageBox.question(
                self, t("assets.delete"),
                t("assets.delete_confirm", name=rel)) != QMessageBox.Yes:
            return
        try:
            os.remove(path)
            self.changed.emit("assets")
            self.show_message(t("props.no_selection"))
        except OSError as exc:
            QMessageBox.critical(self, t("assets.delete"), str(exc))

    # ---- 定义 (角色/场景/声音) ----------------------------------------
    def show_definition(self, payload) -> None:
        self._clear_body()
        self._node = None
        if not payload or self.project is None:
            self.title.setText(t("props.no_selection"))
            return
        op, ident = payload
        from editor.definitions import (def_file_for, find_def, iter_defs)
        script = self.project.scripts.get(def_file_for(op))
        stmt = find_def(script, op, ident) if script is not None else None
        if stmt is None:
            self.title.setText(t("props.def_missing", id=ident))
            return
        self.title.setText("%s [%s]" % (
            {"char": t("props.char"), "scene": t("props.scene"),
             "sound": t("props.sound")}.get(op, op), ident))
        form = QFormLayout()
        name = stmt.kwargs.get("name", "")
        if self._gl is not None:
            name = self._gl.resolve(name)
        form.addRow(t("props.name"), QLabel(name or ident))
        if op == "scene":
            form.addRow(t("props.type"),
                        QLabel(stmt.kwargs.get("type", "normal")))
        if op == "sound":
            form.addRow(t("props.type"),
                        QLabel(stmt.kwargs.get("type", "sfx_ui")))
            form.addRow(t("props.file"),
                        QLabel(stmt.kwargs.get("file", "")))
        elif stmt.kwargs.get("default"):
            form.addRow(t("props.default"),
                        QLabel(stmt.kwargs["default"]))
        # 其它键 (表情表/背景表等) 摘要
        reserved = {"name", "type", "default", "file", "volume",
                    "voice_volume", "desc", "cv", "description", "bio",
                    "intro", "birthday", "height", "age"}
        others = [k for k in stmt.kwargs if k not in reserved]
        if others:
            form.addRow(t("props.extra"),
                        QLabel(t("props.extra_n", n=len(others),
                                 names=", ".join(others[:6]))))
        self.body.addLayout(form)
        btn = QPushButton(t("props.open_editor"))
        btn.clicked.connect(lambda: self._open_def_editor(op, stmt))
        self.body.addWidget(btn)

    def _open_def_editor(self, op: str, stmt) -> None:
        from editor.definitions import DefDialog, update_def
        dlg = DefDialog(op, stmt, self.project, self)
        if dlg.exec() == DefDialog.Accepted:
            update_def(stmt, dlg.values())
            from editor.project_settings import save_script
            from editor.definitions import def_file_for
            fname = def_file_for(op)
            script = self.project.scripts.get(fname)
            if script is not None:
                save_script(script,
                            os.path.join(self.project.root, fname))
                self.project.load()
            self.changed.emit("defs")
            self.show_definition((op, stmt.args[0]))

    # ---- 流程节点 -----------------------------------------------------
    def show_flow_node(self, node) -> None:
        self._node = node
        self._clear_body()
        if node is None:
            self.title.setText(t("props.no_selection"))
            return
        kind = node.kind
        name = {"dialogue": t("props.dialogue"), "choice": t("props.choice"),
                "jump": t("props.jump"), "ending": t("props.ending"),
                "label": t("props.label"), "stage": t("props.stage"),
                "action": t("props.action"), "raw": t("props.raw")}.get(
                    kind, kind)
        self.title.setText("%s  [%s]" % (name, node.node_id))

        form = QFormLayout()
        if kind == "dialogue":
            self._dialogue_form(form, node)
        elif kind == "jump":
            self._jump_form(form, node)
        elif kind == "ending":
            self._text_form(form, node, "name")
        elif kind == "label":
            self._text_form(form, node, "text")
        else:
            form.addRow(t("props.hint_edit"),
                        QLabel(self._node_summary(node)))
        self.body.addLayout(form)

        # 完整编辑对话框按钮
        if self._flow_scene is not None and kind in (
                "dialogue", "choice", "jump", "ending", "label", "stage",
                "action", "raw"):
            btn = QPushButton(t("props.open_editor"))
            btn.clicked.connect(self._open_full_editor)
            self.body.addWidget(btn)

    def _node_summary(self, node) -> str:
        from editor.flow_editor import _summary_lines
        lines = _summary_lines(node, self._gl)
        return "\n".join(lines[:6])

    # ---- 各类型表单 ---------------------------------------------------
    def _dialogue_form(self, form, node) -> None:
        ed_speaker = QLineEdit(node.data.get("speaker", ""))
        ed_speaker.setPlaceholderText(t("flow.speaker_hint"))
        ed_speaker.textChanged.connect(
            lambda s: self._apply(lambda: node.data.update(
                {"speaker": s.strip(),
                 "op": "say" if s.strip() else "text"})))
        form.addRow(t("props.speaker"), ed_speaker)
        # 文本: 显示效果 + 多语言编辑, 保存后写回节点
        _w, _getter = make_lang_edit_widget(
            self._gl, node.data.get("text", ""),
            on_commit=lambda new_text: self._apply(
                lambda: node.data.__setitem__("text", new_text)))
        form.addRow(t("props.text"), _w)

    def _jump_form(self, form, node) -> None:
        ids = [nid for nid in self._flow_scene.graph.order
               if nid != node.node_id] if self._flow_scene else []
        cb = QComboBox()
        cb.addItems(ids)
        cur = node.data.get("target")
        if cur in ids:
            cb.setCurrentText(cur)
        cb.currentTextChanged.connect(
            lambda s: self._apply(
                lambda: node.data.__setitem__("target", s or None)))
        form.addRow(t("props.target"), cb)
        chk = QCheckBox(t("props.is_call"))
        chk.setChecked(bool(node.data.get("is_call")))
        chk.toggled.connect(
            lambda v: self._apply(
                lambda: node.data.__setitem__("is_call", v)))
        form.addRow("", chk)

    def _text_form(self, form, node, key: str) -> None:
        _w, _getter = make_lang_edit_widget(
            self._gl, node.data.get(key, ""),
            on_commit=lambda new_text: self._apply(
                lambda: node.data.__setitem__(key, new_text)))
        form.addRow(t("props.value"), _w)

    # ---- 应用/清理 ----------------------------------------------------
    def _apply(self, fn) -> None:
        """编辑后应用: 更新模型并重建画布 (撤销由完整编辑对话框负责)。"""
        if self._node is not None and self._flow_scene is not None:
            fn()
            self._flow_scene.set_graph(self._flow_scene.graph)

    def _open_full_editor(self) -> None:
        if self._node is not None and self._flow_scene is not None:
            self._flow_scene.edit_node(self._node)

    def _clear_body(self) -> None:
        while self.body.count():
            item = self.body.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
            elif item.layout() is not None:
                self._clear_layout(item.layout())

    @staticmethod
    def _clear_layout(layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
            elif item.layout() is not None:
                PropertyPanel._clear_layout(item.layout())


# ----------------------------------------------------------------------
# 模块级辅助
# ----------------------------------------------------------------------
def _cat_label(ext: str) -> str:
    return {"image": t("assets.cat_image"), "audio": t("assets.cat_audio"),
            "font": t("assets.cat_font"), "other": t("assets.cat_other")}.get(
                _cat_of(ext), ext)


def _cat_of(ext: str) -> str:
    from editor.assets import IMAGE_EXTS, AUDIO_EXTS, FONT_EXTS
    if ext in IMAGE_EXTS:
        return "image"
    if ext in AUDIO_EXTS:
        return "audio"
    if ext in FONT_EXTS:
        return "font"
    return "other"


def _preview_asset(path: str, ext: str, parent=None) -> None:
    from editor.assets import (ImagePreviewDialog, FontPreviewDialog,
                               open_audio_preview, IMAGE_EXTS, FONT_EXTS,
                               AUDIO_EXTS)
    if ext in IMAGE_EXTS:
        ImagePreviewDialog(path, parent).exec()
    elif ext in FONT_EXTS:
        FontPreviewDialog(path, parent).exec()
    elif ext in AUDIO_EXTS:
        open_audio_preview(path, parent)
    else:
        os.startfile(os.path.dirname(path))


def _copy_text(text: str) -> None:
    from PySide6.QtGui import QGuiApplication
    QGuiApplication.clipboard().setText(text)
