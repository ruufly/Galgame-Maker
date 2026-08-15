"""编译与打包 (P3): 校验 / 导出 zip / PyInstaller 发行。

纯逻辑 (可测试):
- export_project_zip(root, dest): 打包项目 (排除 save/logs/__pycache__)

BuildPanel (编译 Tab):
- 校验项目 (往返 + 合并加载, 复用主窗口逻辑风格)
- 导出项目包 (zip)
- PyInstaller 打包 (QProcess 执行, 输出实时进日志)
"""

import os
import zipfile

from PySide6.QtCore import QProcess, Qt, Signal
from PySide6.QtWidgets import (QFileDialog, QFormLayout, QHBoxLayout, QLabel,
                               QLineEdit, QMessageBox, QPlainTextEdit,
                               QPushButton, QVBoxLayout, QWidget)

from framework.engine.loader import load_script_with_imports
from editor.compare import roundtrip_ok
from editor.i18n import t

_EXCLUDE_DIRS = {"save", "logs", "__pycache__", "nowfiletmp"}


def export_project_zip(root: str, dest_zip: str) -> int:
    """打包项目目录为 zip, 返回文件数。"""
    root = os.path.abspath(root)
    count = 0
    with zipfile.ZipFile(dest_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for dirpath, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if d not in _EXCLUDE_DIRS]
            for f in files:
                full = os.path.join(dirpath, f)
                rel = os.path.relpath(full, root).replace("\\", "/")
                zf.write(full, rel)
                count += 1
    return count


class BuildPanel(QWidget):
    """编译 Tab: 校验 / 导出 / PyInstaller 打包。"""

    log = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.project = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        info = QLabel(t("build.info"))
        info.setStyleSheet("color:#888;")
        layout.addWidget(info)

        form = QFormLayout()
        self.ed_name = QLineEdit("MyGame")
        self.ed_name.setMaximumWidth(220)
        form.addRow(t("build.name"), self.ed_name)
        layout.addLayout(form)

        btns = QHBoxLayout()
        self.btn_check = QPushButton(t("build.check"))
        self.btn_check.clicked.connect(self.validate)
        self.btn_zip = QPushButton(t("build.export"))
        self.btn_zip.clicked.connect(self.export_zip)
        self.btn_pack = QPushButton(t("build.pack"))
        self.btn_pack.clicked.connect(self.pack)
        btns.addWidget(self.btn_check)
        btns.addWidget(self.btn_zip)
        btns.addWidget(self.btn_pack)
        btns.addStretch(1)
        layout.addLayout(btns)

        self.out = QPlainTextEdit()
        self.out.setReadOnly(True)
        self.out.setMaximumBlockCount(2000)
        layout.addWidget(self.out, 1)

    def apply_lang(self) -> None:
        self.btn_check.setText(t("build.check"))
        self.btn_zip.setText(t("build.export"))
        self.btn_pack.setText(t("build.pack"))

    def set_project(self, project) -> None:
        self.project = project
        if project is not None:
            self.ed_name.setText(os.path.basename(project.root))
            self._msg(t("build.project_info",
                        path=project.root, n=len(project.scripts)))

    # ---- 校验 ---------------------------------------------------------
    def validate(self) -> None:
        if self.project is None:
            self._msg(t("build.no_project"))
            return
        ok, bad = 0, []
        for rel, script in self.project.scripts.items():
            if roundtrip_ok(script):
                ok += 1
            else:
                bad.append(rel)
        self._msg(t("build.validate_result", ok=ok,
                    total=len(self.project.scripts))
                  + (t("build.validate_fail", names=", ".join(bad))
                     if bad else ""))
        try:
            merged = load_script_with_imports(
                os.path.join(self.project.root, self.project.main))
            self._msg(t("build.merge_ok", n=len(merged.statements),
                        labels=len(merged.labels)))
        except Exception as exc:
            self._msg(t("build.merge_fail", exc=exc))

    # ---- 导出 zip -----------------------------------------------------
    def export_zip(self) -> None:
        if self.project is None:
            self._msg(t("build.no_project"))
            return
        default = os.path.join(os.path.dirname(self.project.root),
                               os.path.basename(self.project.root) + ".zip")
        dest, _f = QFileDialog.getSaveFileName(self, t("build.export_title"),
                                               default,
                                               t("build.zip_filter"))
        if not dest:
            return
        if not dest.lower().endswith(".zip"):
            dest += ".zip"
        try:
            n = export_project_zip(self.project.root, dest)
            self._msg(t("build.exported", n=n, path=dest))
        except Exception as exc:
            QMessageBox.critical(self, t("build.export_fail_title"),
                                 str(exc))

    # ---- PyInstaller --------------------------------------------------
    def pack(self) -> None:
        if self.project is None:
            self._msg("请先打开项目")
            return
        name = self.ed_name.text().strip() or "MyGame"
        root = self.project.root
        launcher = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "..", "gamelauncher.py")
        launcher = os.path.abspath(launcher)
        if not os.path.isfile(launcher):
            self._msg(t("build.launcher_missing"))
            return
        plugins = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "..", "framework", "plugins")
        plugins = os.path.abspath(plugins)
        release = os.path.join(root, "release")
        os.makedirs(release, exist_ok=True)
        cmd = [
            "py", "-3.10", "-m", "PyInstaller", "--noconfirm", "--onedir",
            "--name", name,
            "--distpath", os.path.join(release, "dist"),
            "--workpath", os.path.join(release, "build"),
            "--specpath", release,
            "--add-data", plugins + os.pathsep + os.path.join("framework",
                                                              "plugins"),
            "--paths", os.path.dirname(os.path.dirname(launcher)),
            launcher,
        ]
        self._msg(t("build.pack_start", cmd=" ".join(cmd)))
        self._proc = QProcess(self)
        self._proc.setWorkingDirectory(root)
        self._proc.readyReadStandardOutput.connect(
            lambda: self._msg(self._proc.readAllStandardOutput().data()
                              .decode("utf-8", "ignore").rstrip()))
        self._proc.readyReadStandardError.connect(
            lambda: self._msg(self._proc.readAllStandardError().data()
                              .decode("utf-8", "ignore").rstrip()))
        self._proc.finished.connect(
            lambda code, _s: self._msg(t("build.pack_finished", code=code)))
        self._proc.start("py", cmd[1:])   # cmd[0]='py' 已在 program 参数
        self._proc.waitForStarted(3000)

    # ---- 日志 ---------------------------------------------------------
    def _msg(self, text: str) -> None:
        self.out.appendPlainText(text)
        self.log.emit(text)
