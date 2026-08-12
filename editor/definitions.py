"""定义管理器 (P2): 角色 / 场景 / 声音 的类型化编辑。

约定 (与 engine_demo 一致):
- char/scene 定义 -> cast.gal
- sound 定义     -> audio.gal
- 定义块均为顶层属性块: op <id> + kwargs

纯逻辑 (可测试):
- iter_defs(script, op): 遍历某类定义块
- find_def(script, op, ident)
- add_def / update_def / remove_def
- def_file_for(op): 定义应写入的脚本文件名

DefinitionsPanel: 类型列表 + 新建/编辑/删除; 保存 = 改模型 + 序列化落盘。
"""

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QDialog, QDoubleSpinBox, QFileDialog,
                               QFormLayout, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QMessageBox,
                               QPushButton, QSpinBox, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from framework.engine.parser import Script, Statement, parse
from editor.serializer import serialize
from editor.project_settings import save_script
from editor.i18n import t

# char 保留键 (不视为立绘表情)
CHAR_RESERVED = {"name", "default", "voice_volume", "desc", "description",
                 "bio", "intro", "cv", "birthday", "height", "age"}
# scene 保留键
SCENE_RESERVED = {"name", "type", "default"}
# sound 保留键
SOUND_RESERVED = {"name", "type", "file", "volume"}

DEF_FILES = {"char": "cast.gal", "scene": "cast.gal", "sound": "audio.gal"}
DEF_LABELS = {"char": None, "scene": None, "sound": None}


def _def_label(op):
    return {"char": t("defs.type_char"), "scene": t("defs.type_scene"),
            "sound": t("defs.type_sound")}.get(op, op)


# ----------------------------------------------------------------------
# 纯逻辑 (可测试)
# ----------------------------------------------------------------------
def def_file_for(op: str) -> str:
    return DEF_FILES.get(op, "cast.gal")


def iter_defs(script: Script, op: str):
    """遍历顶层 op 类型定义块 (char/scene/sound...)。"""
    aliases = {"char": ("char", "character"),
               "scene": ("scene", "scenery")}.get(op, (op,))
    for stmt in script.statements:
        if stmt.op in aliases and stmt.args:
            yield stmt


def find_def(script: Script, op: str, ident: str):
    for stmt in iter_defs(script, op):
        if stmt.args[0] == ident:
            return stmt
    return None


def add_def(script: Script, op: str, ident: str, kwargs: dict) -> Statement:
    """新增定义块 (追加到顶层末尾), 返回新块。"""
    stmt = Statement(op=op, args=[ident], kwargs=dict(kwargs))
    script.statements.append(stmt)
    return stmt


def update_def(stmt: Statement, kwargs: dict) -> None:
    """整体替换 kwargs (保留 id)。"""
    stmt.kwargs.clear()
    stmt.kwargs.update(kwargs)


def remove_def(script: Script, op: str, ident: str) -> bool:
    aliases = {"char": ("char", "character"),
               "scene": ("scene", "scenery")}.get(op, (op,))
    for i, stmt in enumerate(script.statements):
        if stmt.op in aliases and stmt.args and stmt.args[0] == ident:
            del script.statements[i]
            return True
    return False


def char_expressions(stmt: Statement) -> list:
    """[(表情名, 路径)] (排除保留键)。"""
    return [(k, v) for k, v in stmt.kwargs.items()
            if k not in CHAR_RESERVED]


def scene_backgrounds(stmt: Statement) -> list:
    """[(背景名, 路径)] (排除保留键)。"""
    return [(k, v) for k, v in stmt.kwargs.items()
            if k not in SCENE_RESERVED]


# ----------------------------------------------------------------------
# 定义面板
# ----------------------------------------------------------------------
class DefinitionsPanel(QWidget):
    """角色 / 场景 / 声音 定义浏览器 + 编辑入口。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.project = None
        self._script = None          # 当前类型对应的脚本 (cast.gal/audio.gal)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)

        bar = QHBoxLayout()
        self.cb_type = QComboBox()
        self.cb_type.addItem(t("defs.type_char"), "char")
        self.cb_type.addItem(t("defs.type_scene"), "scene")
        self.cb_type.addItem(t("defs.type_sound"), "sound")
        self.cb_type.currentIndexChanged.connect(self.refresh)
        btn_new = QPushButton(t("defs.new"))
        btn_edit = QPushButton(t("defs.edit"))
        btn_del = QPushButton(t("defs.delete"))
        btn_new.clicked.connect(self._new)
        btn_edit.clicked.connect(self._edit)
        btn_del.clicked.connect(self._delete)
        hint = QLabel(t("defs.hint"))
        hint.setStyleSheet("color:#888;")
        bar.addWidget(self.cb_type)
        bar.addWidget(btn_new)
        bar.addWidget(btn_edit)
        bar.addWidget(btn_del)
        bar.addStretch(1)
        bar.addWidget(hint)
        layout.addLayout(bar)

        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(lambda _i: self._edit())
        layout.addWidget(self.list, 1)

    # ---- 语言刷新 -----------------------------------------------------
    def apply_lang(self) -> None:
        idx = self.cb_type.currentIndex()
        self.cb_type.clear()
        self.cb_type.addItem(t("defs.type_char"), "char")
        self.cb_type.addItem(t("defs.type_scene"), "scene")
        self.cb_type.addItem(t("defs.type_sound"), "sound")
        self.cb_type.setCurrentIndex(min(idx, self.cb_type.count() - 1))
        self.refresh()

    # ---- 数据 ---------------------------------------------------------
    def set_project(self, project) -> None:
        self.project = project
        self.refresh()

    def _op(self) -> str:
        return self.cb_type.currentData()

    def _load_script(self) -> Script | None:
        """当前类型对应的脚本 (不存在则创建空 Script)。"""
        if self.project is None:
            return None
        fname = def_file_for(self._op())
        script = self.project.scripts.get(fname)
        if script is None:
            script = parse("", fname)
            self.project.add_script(fname, script)
        return script

    def refresh(self) -> None:
        self.list.clear()
        if self.project is None:
            return
        op = self._op()
        script = self.project.scripts.get(def_file_for(op))
        if script is None:
            self.list.addItem(_placeholder(t("defs.none", type=_def_label(op))))
            return
        items = list(iter_defs(script, op))
        if not items:
            self.list.addItem(_placeholder(t("defs.empty", type=_def_label(op))))
            return
        for stmt in items:
            ident = stmt.args[0]
            display = stmt.kwargs.get("name") or ident
            label = "%s  (%s)" % (display, ident)
            if op == "sound" and stmt.kwargs.get("type"):
                label = "%s  [%s]" % (display, stmt.kwargs["type"])
            it = QListWidgetItem(label)
            it.setData(0x0100, ident)   # Qt.UserRole
            self.list.addItem(it)

    def _selected_ident(self) -> str | None:
        it = self.list.currentItem()
        if it is None:
            return None
        return it.data(0x0100)

    # ---- 操作 ---------------------------------------------------------
    def _new(self):
        dlg = DefDialog(self._op(), None, self.project, self)
        if dlg.exec() == DefDialog.Accepted:
            script = self._load_script()
            add_def(script, self._op(), dlg.ident(), dlg.values())
            self._save()
            self.refresh()

    def _edit(self):
        ident = self._selected_ident()
        if not ident:
            return
        script = self.project.scripts.get(def_file_for(self._op()))
        stmt = find_def(script, self._op(), ident)
        if stmt is None:
            return
        dlg = DefDialog(self._op(), stmt, self.project, self)
        if dlg.exec() == DefDialog.Accepted:
            update_def(stmt, dlg.values())
            self._save()
            self.refresh()

    def _delete(self):
        ident = self._selected_ident()
        if not ident:
            return
        if QMessageBox.question(self, t("defs.delete"),
                            t("defs.delete_confirm", id=ident)) != QMessageBox.Yes:
            return
        script = self.project.scripts.get(def_file_for(self._op()))
        if script is not None and remove_def(script, self._op(), ident):
            self._save()
            self.refresh()

    def _save(self):
        fname = def_file_for(self._op())
        script = self.project.scripts[fname]
        save_script(script, os.path.join(self.project.root, fname))


def _placeholder(text: str) -> QListWidgetItem:
    it = QListWidgetItem(text)
    it.setFlags(Qt.NoItemFlags)
    return it


# ----------------------------------------------------------------------
# 定义编辑对话框 (char/scene/sound 三合一)
# ----------------------------------------------------------------------
class DefDialog(QDialog):
    """按类型构建表单。新建时传 stmt=None。"""

    def __init__(self, op: str, stmt: Statement | None, project, parent=None):
        super().__init__(parent)
        self.op = op
        self.stmt = stmt
        self.project = project
        self.setWindowTitle(("%s — %s" % (_def_label(op), stmt.args[0]))
                            if stmt else t("defs.new") + " " + _def_label(op))
        self.setMinimumWidth(520)

        self._extra_paths = {}
        self.ed_extra = {}
        self.table_ref = None

        k = stmt.kwargs if stmt else {}
        form = QFormLayout()

        self.ed_id = QLineEdit(stmt.args[0] if stmt else "")
        self.ed_id.setEnabled(stmt is None)      # 编辑时 id 不可改
        form.addRow("ID (unique in script)", self.ed_id)

        self.ed_name = QLineEdit(str(k.get("name", "")))
        form.addRow("Name", self.ed_name)

        if op in ("char", "scene"):
            self.cb_type = None
            if op == "scene":
                self.cb_type = QComboBox()
                self.cb_type.addItems(["normal", "cg"])
                self.cb_type.setCurrentText(str(k.get("type", "normal")))
                form.addRow("Type", self.cb_type)
            # 默认素材
            form.addRow(("Default sprite" if op == "char" else "Default bg"),
                        self._path_row("default", str(k.get("default", ""))))
        elif op == "sound":
            self.cb_sound_type = QComboBox()
            self.cb_sound_type.addItems(["music", "sfx_ui", "sfx_story", "voice"])
            self.cb_sound_type.setCurrentText(str(k.get("type", "sfx_ui")))
            form.addRow("Sound type", self.cb_sound_type)
            form.addRow("File", self._path_row("file", str(k.get("file", ""))))
            self.sp_vol = QDoubleSpinBox()
            self.sp_vol.setRange(0, 1)
            self.sp_vol.setSingleStep(0.05)
            self.sp_vol.setValue(float(k.get("volume", 1.0)))
            form.addRow("Volume", self.sp_vol)

        # 附加字段
        self.ed_extra = {}
        if op == "char":
            form.addRow("Voice volume", self._vol_row(k.get("voice_volume", "1.0")))
            form.addRow("Desc (gallery)", self._ed("desc", k, form))
            form.addRow("CV/birthday/height…", self._ed("cv", k, form))

        btns = QHBoxLayout()
        btn_ok = QPushButton("保存")
        btn_cancel = QPushButton("取消")
        btn_ok.clicked.connect(self._validate_ok)
        btn_cancel.clicked.connect(self.reject)
        btns.addStretch(1)
        btns.addWidget(btn_ok)
        btns.addWidget(btn_cancel)

        # 表情/背景 表格 (char/scene)
        self.table = None
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        if op in ("char", "scene"):
            self.table = self._build_table(k, "立绘" if op == "char" else "背景")
            layout.addWidget(self.table, 1)
        layout.addLayout(btns)

    # ---- 构件 ---------------------------------------------------------
    def _path_row(self, key: str, value: str) -> QWidget:
        row = QHBoxLayout()
        ed = QLineEdit(value)
        btn = QPushButton("浏览…")
        btn.clicked.connect(lambda: self._browse(ed))
        row.addWidget(ed, 1)
        row.addWidget(btn)
        self._extra_paths[key] = ed
        w = QWidget()
        w.setLayout(row)
        return w

    def _vol_row(self, value) -> QWidget:
        self.sp_voice = QDoubleSpinBox()
        self.sp_voice.setRange(0, 1)
        self.sp_voice.setSingleStep(0.05)
        try:
            self.sp_voice.setValue(float(value))
        except (TypeError, ValueError):
            self.sp_voice.setValue(1.0)
        return self.sp_voice

    def _ed(self, key, k, form) -> QLineEdit:
        ed = QLineEdit(str(k.get(key, "")))
        self.ed_extra[key] = ed
        return ed

    def _build_table(self, k, title: str) -> QTableWidget:
        t = QTableWidget(0, 2)
        t.setHorizontalHeaderLabels(["名称", "文件路径"])
        t.horizontalHeader().setStretchLastSection(True)
        rows = [(name, path) for name, path in k.items()
                if name not in (CHAR_RESERVED if self.op == "char"
                                else SCENE_RESERVED)]
        for name, path in rows:
            self._add_row(t, name, path)
        btn_add = QPushButton("添加一行")
        btn_add.clicked.connect(lambda: self._add_row(t, "", ""))
        wrap = QVBoxLayout()
        lbl = QLabel("%s (除默认外, 其余名称对应文件路径)" % title)
        wrap.addWidget(lbl)
        wrap.addWidget(t, 1)
        row_btn = QHBoxLayout()
        row_btn.addWidget(btn_add)
        row_btn.addStretch(1)
        wrap.addLayout(row_btn)
        w = QWidget()
        w.setLayout(wrap)
        self.table_ref = t
        return w

    @staticmethod
    def _add_row(t, name, path):
        r = t.rowCount()
        t.insertRow(r)
        t.setItem(r, 0, QTableWidgetItem(name))
        t.setItem(r, 1, QTableWidgetItem(path))

    def _browse(self, ed: QLineEdit):
        start = os.path.join(self.project.root, "materials") if self.project else ""
        f, _ = QFileDialog.getOpenFileName(self, "选择素材", start)
        if f and self.project:
            rel = os.path.relpath(f, self.project.root).replace("\\", "/")
            ed.setText(rel)
        elif f:
            ed.setText(f)

    # ---- 取值 ---------------------------------------------------------
    def ident(self) -> str:
        return self.ed_id.text().strip()

    def values(self) -> dict:
        v = {}
        if self.ed_name.text().strip():
            v["name"] = self.ed_name.text().strip()
        if self.op == "char":
            if self._extra_paths.get("default").text().strip():
                v["default"] = self._extra_paths["default"].text().strip()
            if self.sp_voice.value() != 1.0:
                v["voice_volume"] = str(self.sp_voice.value())
            for key, ed in self.ed_extra.items():
                if ed.text().strip():
                    v[key] = ed.text().strip()
            for r in range(self.table_ref.rowCount()):
                name = self.table_ref.item(r, 0)
                path = self.table_ref.item(r, 1)
                if name and path and name.text().strip() and path.text().strip():
                    v[name.text().strip()] = path.text().strip()
        elif self.op == "scene":
            if self._extra_paths.get("default").text().strip():
                v["default"] = self._extra_paths["default"].text().strip()
            if self.cb_type.currentText() != "normal":
                v["type"] = self.cb_type.currentText()
            for r in range(self.table_ref.rowCount()):
                name = self.table_ref.item(r, 0)
                path = self.table_ref.item(r, 1)
                if name and path and name.text().strip() and path.text().strip():
                    v[name.text().strip()] = path.text().strip()
        elif self.op == "sound":
            v["type"] = self.cb_sound_type.currentText()
            if self._extra_paths.get("file").text().strip():
                v["file"] = self._extra_paths["file"].text().strip()
            if self.sp_vol.value() != 1.0:
                v["volume"] = str(self.sp_vol.value())
        return v

    # ---- 校验 ---------------------------------------------------------
    def _validate_ok(self):
        if not self.ed_id.text().strip():
            QMessageBox.warning(self, "提示", "请填写 ID")
            return
        if self.op == "sound" and not self._extra_paths.get("file").text().strip():
            QMessageBox.warning(self, "提示", "声音需要指定文件")
            return
        self.accept()
