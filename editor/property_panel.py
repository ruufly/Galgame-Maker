"""属性面板 (右 Dock): 显示并快捷编辑选中对象的属性。

当前范围: 流程节点 (dialogue/choice/jump/ending/label/stage/action/raw)。
通用字段直接编辑; 复杂编辑 (stage 分镜/选择支/多语言) 提供
"打开完整编辑对话框" 按钮 (复用 FlowScene.edit_node)。

其它对象 (素材/定义) 的属性编辑沿用各自面板, 本面板显示提示。
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFormLayout, QHBoxLayout,
                               QLabel, QLineEdit, QPushButton, QVBoxLayout,
                               QWidget)

from editor.i18n import t
from editor.lang_dialog import make_lang_edit_widget


class PropertyPanel(QWidget):
    """右侧属性面板。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._gl = None          # GameLang (多语言显示)
        self._node = None
        self._flow_scene = None
        self._rebuilding = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        self.title = QLabel(t("props.empty"))
        self.title.setStyleSheet("font-weight:bold; color:#d8d8e0;")
        layout.addWidget(self.title)
        self.body = QVBoxLayout()
        layout.addLayout(self.body)
        layout.addStretch(1)

    # ---- 绑定 ---------------------------------------------------------
    def set_lang(self, gl) -> None:
        self._gl = gl

    def set_flow_scene(self, scene) -> None:
        self._flow_scene = scene

    def show_message(self, text: str) -> None:
        self.title.setText(text)
        self._clear_body()
        self._node = None

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
