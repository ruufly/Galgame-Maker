"""新建项目向导 (P2): 从 engine_demo 模板创建新项目。

核心逻辑 create_project() 是纯函数 (可测试, 不依赖 Qt);
NewProjectDialog 是向导界面。

模板处理:
- 复制 test/engine_demo 骨架 (排除 save/logs/__pycache__)
- 复制项目根 fonts/ (引擎默认字体, 保证项目自包含)
- 替换项目身份: 脚本 meta name / window 标题 / language 默认语言,
  main.yml name —— 通过模型 + 序列化器写回 (不经手文本替换)
"""

import os
import re
import shutil
import sys

from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFileDialog,
                               QFormLayout, QHBoxLayout, QLineEdit, QMessageBox,
                               QPushButton, QVBoxLayout)

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE_DIR = os.path.join(_ROOT, "test", "engine_demo")

RESOLUTIONS = [
    ("1280 × 720 (16:9)", 1280, 720),
    ("1920 × 1080 (16:9)", 1920, 1080),
    ("960 × 540 (16:9)", 960, 540),
    ("1280 × 800 (16:10)", 1280, 800),
]
LANGUAGES = [
    ("简体中文", "zh-CN"),
    ("English", "en"),
]
_NAME_RE = re.compile(r"^[\w\u4e00-\u9fff][\w\u4e00-\u9fff ._-]*$")


def create_project(name: str, target_dir: str, resolution=(1280, 720),
                   language: str = "zh-CN", with_materials: bool = True) -> str:
    """从模板创建新项目目录, 返回项目根路径。"""
    name = name.strip()
    if not _NAME_RE.match(name):
        raise ValueError("项目名只能包含 中英文/数字/空格/._-")
    target_dir = os.path.abspath(target_dir)
    if os.path.exists(target_dir) and os.listdir(target_dir):
        raise FileExistsError("目标目录已存在且非空: %s" % target_dir)

    # ---- 复制模板 ----
    shutil.copytree(TEMPLATE_DIR, target_dir,
                    ignore=shutil.ignore_patterns("save", "logs",
                                                  "__pycache__"))
    # 字体自包含
    fonts_src = os.path.join(_ROOT, "fonts")
    if os.path.isdir(fonts_src):
        shutil.copytree(fonts_src, os.path.join(target_dir, "fonts"),
                        dirs_exist_ok=True)
    if not with_materials:
        shutil.rmtree(os.path.join(target_dir, "materials"), ignore_errors=True)
        os.makedirs(os.path.join(target_dir, "materials", "image"))
        os.makedirs(os.path.join(target_dir, "materials", "audio"))

    # ---- 替换项目身份 (模型 + 序列化器写回) ----
    sys.path.insert(0, _ROOT)
    from editor.model import Project
    from editor.serializer import serialize

    project = Project(target_dir).load()
    for rel, script in project.scripts.items():
        changed = False
        if rel == project.main:
            script.meta["name"] = name
            changed = True
            for stmt in script.statements:
                if stmt.op == "window" and not stmt.args:
                    # 主 window 块标题 -> 项目名
                    if stmt.kwargs.get("title"):
                        stmt.kwargs["title"] = name
                        changed = True
                elif stmt.op == "language":
                    if stmt.kwargs.get("default"):
                        stmt.kwargs["default"] = language
                        changed = True
        if changed:
            with open(os.path.join(target_dir, rel), "w",
                      encoding="utf-8") as fh:
                fh.write(serialize(script))

    # main.yml 项目名
    yml = os.path.join(target_dir, "main.yml")
    if os.path.isfile(yml):
        with open(yml, encoding="utf-8") as fh:
            text = fh.read()
        text = re.sub(r"^name:.*$", "name: %s" % name, text, count=1,
                      flags=re.MULTILINE)
        with open(yml, "w", encoding="utf-8") as fh:
            fh.write(text)

    return target_dir


class NewProjectDialog(QDialog):
    """新建项目向导。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("新建 Galgame 项目")
        self.setMinimumWidth(480)
        self._result_path = ""

        form = QFormLayout()
        self.ed_name = QLineEdit()
        self.ed_name.setPlaceholderText("例如: 我的第一个游戏")
        form.addRow("项目名称", self.ed_name)

        loc_row = QHBoxLayout()
        self.ed_loc = QLineEdit()
        self.ed_loc.setText(os.path.expanduser("~/Documents/GalgameProjects"))
        btn_browse = QPushButton("浏览…")
        btn_browse.clicked.connect(self._browse)
        loc_row.addWidget(self.ed_loc, 1)
        loc_row.addWidget(btn_browse)
        form.addRow("保存位置", loc_row)

        self.cb_res = QComboBox()
        for label, _w, _h in RESOLUTIONS:
            self.cb_res.addItem(label)
        form.addRow("分辨率", self.cb_res)

        self.cb_lang = QComboBox()
        for label, code in LANGUAGES:
            self.cb_lang.addItem(label, code)
        form.addRow("默认语言", self.cb_lang)

        self.chk_materials = QCheckBox("复制演示素材 (背景/立绘/音频/UI)")
        self.chk_materials.setChecked(True)
        form.addRow("", self.chk_materials)

        btns = QHBoxLayout()
        btn_ok = QPushButton("创建项目")
        btn_cancel = QPushButton("取消")
        btn_ok.clicked.connect(self._create)
        btn_cancel.clicked.connect(self.reject)
        btns.addStretch(1)
        btns.addWidget(btn_ok)
        btns.addWidget(btn_cancel)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addLayout(btns)

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "选择保存位置",
                                             self.ed_loc.text())
        if d:
            self.ed_loc.setText(d)

    def _create(self):
        name = self.ed_name.text().strip()
        base = self.ed_loc.text().strip()
        if not name:
            QMessageBox.warning(self, "提示", "请填写项目名称")
            return
        if not base:
            QMessageBox.warning(self, "提示", "请选择保存位置")
            return
        _label, w, h = RESOLUTIONS[self.cb_res.currentIndex()]
        lang = self.cb_lang.currentData()
        try:
            path = create_project(name, os.path.join(base, name),
                                  resolution=(w, h), language=lang,
                                  with_materials=self.chk_materials.isChecked())
        except Exception as exc:
            QMessageBox.critical(self, "创建失败", str(exc))
            return
        self._result_path = path
        self.accept()

    def result_path(self) -> str:
        return self._result_path
