"""独立预览窗口: 以独立进程真实运行游戏 + 实时调试。

设计:
- 预览 = QProcess 启动 ``gamelauncher.py <脚本> --debug-port <端口>``
  (真实窗口/音频/键盘鼠标输入, 崩溃不拖垮编辑器; 可多开)
- 引擎通过 debug_server (framework/engine/debug_server.py) 每 0.5s
  推送状态: FPS / 帧耗时 / 引擎变量 / 当前标签 / 增量日志
- 本窗口为调试控制台: 日志实时滚动, 变量表双击可改 (set_var),
  性能页实时折线; 游戏本体在独立窗口运行

用法::

    win = PreviewWindow()
    win.set_script("/path/demo.gal")
    win.start()
"""

import json
import os
import socket
import sys

from PySide6.QtCore import QProcess, Qt, QThread, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (QHBoxLayout, QHeaderView, QLabel, QMainWindow,
                               QPlainTextEdit, QPushButton, QSplitter,
                               QTabWidget, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)

from editor.i18n import t

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def find_free_port() -> int:
    """向操作系统要一个空闲端口 (用于 debug server)。"""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


# ----------------------------------------------------------------------
# TCP 调试客户端 (后台线程读 JSON 行)
# ----------------------------------------------------------------------
class DebugClient(QThread):
    """连接引擎 debug server, 持续接收状态推送。"""

    state_received = Signal(dict)
    connection_changed = Signal(bool)   # True=已连接

    def __init__(self, port: int, parent=None):
        super().__init__(parent)
        self.port = port
        self._stop = False
        self._connected = False

    def stop(self) -> None:
        self._stop = True

    def run(self) -> None:
        while not self._stop:
            try:
                sock = socket.create_connection(("127.0.0.1", self.port),
                                                timeout=1)
            except OSError:
                if self._connected:
                    self._connected = False
                    self.connection_changed.emit(False)
                self.msleep(400)
                continue
            self._connected = True
            self.connection_changed.emit(True)
            sock.settimeout(0.5)
            buf = b""
            try:
                while not self._stop:
                    try:
                        chunk = sock.recv(8192)
                    except socket.timeout:
                        continue
                    except OSError:
                        break
                    if not chunk:
                        break
                    buf += chunk
                    while b"\n" in buf:
                        raw, buf = buf.split(b"\n", 1)
                        raw = raw.strip()
                        if not raw:
                            continue
                        try:
                            state = json.loads(raw.decode("utf-8"))
                        except ValueError:
                            continue
                        self.state_received.emit(state)
            finally:
                try:
                    sock.close()
                except OSError:
                    pass
            if self._connected:
                self._connected = False
                self.connection_changed.emit(False)
            self.msleep(400)

    def send(self, obj: dict) -> None:
        """向引擎发请求 (set_var 等)。连接断开时静默丢弃。"""
        if not self._connected:
            return
        try:
            sock = socket.create_connection(("127.0.0.1", self.port),
                                            timeout=1)
            sock.sendall((json.dumps(obj, ensure_ascii=False) + "\n")
                         .encode("utf-8"))
            sock.close()
        except OSError:
            pass


# ----------------------------------------------------------------------
# 性能页: FPS 历史折线 (自绘 QWidget, 不碰 QGraphicsItem)
# ----------------------------------------------------------------------
class PerfWidget(QWidget):
    """滚动 FPS / 帧耗时折线 (保留最近 300 采样)。"""

    MAX_POINTS = 300

    def __init__(self, parent=None):
        super().__init__(parent)
        self._fps: list = []
        self._ms: list = []
        self.setMinimumHeight(140)

    def push(self, fps: float, ms: float) -> None:
        self._fps.append(fps)
        self._ms.append(ms)
        if len(self._fps) > self.MAX_POINTS:
            self._fps.pop(0)
            self._ms.pop(0)
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        w, h = self.width(), self.height()
        p.fillRect(self.rect(), QColor("#14141c"))
        if not self._fps:
            p.setPen(QColor("#666"))
            p.drawText(self.rect(), Qt.AlignCenter, t("preview.perf_empty"))
            return
        # 网格
        p.setPen(QPen(QColor("#262636"), 1))
        for i in range(1, 4):
            y = h * i // 4
            p.drawLine(0, y, w, y)
        # FPS 折线 (左轴, 0-120)
        n = len(self._fps)
        pen_fps = QPen(QColor("#4e9a5a"), 2)
        p.setPen(pen_fps)
        prev = None
        for i, v in enumerate(self._fps):
            x = w * i / (n - 1) if n > 1 else 0
            y = h - (min(max(v, 0), 120) / 120) * (h - 20) - 6
            if prev is not None:
                p.drawLine(*prev, x, y)
            prev = (x, y)
        # 帧耗时折线 (右轴, 0-100ms), 颜色区分
        pen_ms = QPen(QColor("#d66b4e"), 2)
        p.setPen(pen_ms)
        prev = None
        for i, v in enumerate(self._ms):
            x = w * i / (n - 1) if n > 1 else 0
            y = h - (min(max(v, 0), 100) / 100) * (h - 20) - 6
            if prev is not None:
                p.drawLine(*prev, x, y)
            prev = (x, y)
        p.end()


# ----------------------------------------------------------------------
# 预览窗口
# ----------------------------------------------------------------------
class PreviewWindow(QMainWindow):
    """预览 + 调试控制台。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(t("preview.window_title"))
        self.resize(720, 560)
        self._script = ""
        self._proc: QProcess | None = None
        self._client: DebugClient | None = None
        self._port = 0
        self._filling_vars = False

        self._build_ui()

    # ---- UI -----------------------------------------------------------
    def _build_ui(self) -> None:
        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # 顶部控制行
        top = QHBoxLayout()
        self.btn_start = QPushButton(t("preview.run"))
        self.btn_stop = QPushButton(t("preview.stop"))
        self.btn_stop.setEnabled(False)
        self.btn_start.clicked.connect(self.start)
        self.btn_stop.clicked.connect(self.stop)
        top.addWidget(self.btn_start)
        top.addWidget(self.btn_stop)
        self.lbl_state = QLabel(t("preview.idle"))
        self.lbl_state.setStyleSheet("color:#888;")
        top.addWidget(self.lbl_state)
        top.addStretch(1)
        self.lbl_fps = QLabel("")
        self.lbl_fps.setStyleSheet("color:#4e9a5a; font-weight:bold;")
        self.lbl_label = QLabel("")
        self.lbl_label.setStyleSheet("color:#888;")
        top.addWidget(self.lbl_fps)
        top.addWidget(self.lbl_label)
        layout.addLayout(top)

        # 提示: 游戏本体在独立窗口
        hint = QLabel(t("preview.separate_window"))
        hint.setStyleSheet("color:#777; padding:2px 4px;")
        layout.addWidget(hint)

        # 标签页: 日志 / 变量 / 性能
        self.tabs = QTabWidget()
        self.ed_log = QPlainTextEdit()
        self.ed_log.setReadOnly(True)
        self.ed_log.setMaximumBlockCount(4000)
        self.tabs.addTab(self.ed_log, t("preview.tab_log"))

        self.tbl_vars = QTableWidget(0, 2)
        self.tbl_vars.setHorizontalHeaderLabels(
            [t("preview.var_name"), t("preview.var_value")])
        self.tbl_vars.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeToContents)
        self.tbl_vars.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.Stretch)
        self.tbl_vars.itemChanged.connect(self._on_var_edited)
        self.tabs.addTab(self.tbl_vars, t("preview.tab_vars"))

        self.perf = PerfWidget()
        self.tabs.addTab(self.perf, t("preview.tab_perf"))
        layout.addWidget(self.tabs, 1)
        self.setCentralWidget(central)

    # ---- 对外 ---------------------------------------------------------
    def set_script(self, path: str) -> None:
        self._script = os.path.abspath(path)

    def apply_lang(self) -> None:
        """语言切换时刷新文案 (运行中不打断)。"""
        self.setWindowTitle(t("preview.window_title"))
        self.btn_start.setText(t("preview.run"))
        self.btn_stop.setText(t("preview.stop"))
        self.tabs.setTabText(0, t("preview.tab_log"))
        self.tabs.setTabText(1, t("preview.tab_vars"))
        self.tabs.setTabText(2, t("preview.tab_perf"))
        self.tbl_vars.setHorizontalHeaderLabels(
            [t("preview.var_name"), t("preview.var_value")])

    def start(self) -> None:
        if self._proc is not None and self._proc.state() != QProcess.NotRunning:
            return
        if not self._script:
            self.lbl_state.setText(t("preview.no_script"))
            return
        self._port = find_free_port()
        launcher = os.path.join(_ROOT, "gamelauncher.py")
        prog = sys.executable
        args = [launcher, self._script, "--debug-port", str(self._port)]
        self._proc = QProcess(self)
        self._proc.setProcessChannelMode(QProcess.MergedChannels)
        self._proc.readyReadStandardOutput.connect(self._on_proc_stdout)
        self._proc.finished.connect(self._on_proc_finished)
        self._proc.errorOccurred.connect(self._on_proc_error)
        self._proc.start(prog, args)
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.lbl_state.setText(t("preview.starting"))
        self.ed_log.appendPlainText(
            "%s %s" % (t("preview.launch"), " ".join(args)))
        # 调试客户端 (断线自动重连)
        if self._client is None:
            self._client = DebugClient(self._port)
            self._client.state_received.connect(self._on_state)
            self._client.connection_changed.connect(self._on_conn)
            self._client.start()

    def stop(self) -> None:
        if self._proc is not None:
            self._proc.terminate()
            if not self._proc.waitForFinished(2000):
                self._proc.kill()
        self._client_stop()
        self._set_idle()

    def is_running(self) -> bool:
        return (self._proc is not None
                and self._proc.state() != QProcess.NotRunning)

    def _client_stop(self) -> None:
        if self._client is not None:
            self._client.stop()
            self._client.wait(2000)
            self._client = None

    def _set_idle(self) -> None:
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.lbl_state.setText(t("preview.idle"))
        self.lbl_fps.setText("")
        self.lbl_label.setText("")

    # ---- 进程事件 -----------------------------------------------------
    def _on_proc_stdout(self) -> None:
        if self._proc is None:
            return
        data = bytes(self._proc.readAllStandardOutput()).decode(
            "utf-8", errors="replace")
        for line in data.splitlines():
            self.ed_log.appendPlainText(line)

    def _on_proc_finished(self, _code: int, _status) -> None:
        self.ed_log.appendPlainText(t("preview.process_exited"))
        self._client_stop()
        self._set_idle()

    def _on_proc_error(self, err) -> None:
        self.ed_log.appendPlainText(
            "%s: %s" % (t("preview.process_error"), err))

    def _on_conn(self, connected: bool) -> None:
        if connected:
            self.lbl_state.setText(t("preview.connected"))
        else:
            self.lbl_state.setText(t("preview.reconnecting"))

    # ---- 状态推送 -----------------------------------------------------
    def _on_state(self, state: dict) -> None:
        fps = state.get("fps", 0)
        ms = state.get("frame_ms", 0)
        self.lbl_fps.setText(t("preview.fps", fps=fps, ms=ms))
        label = state.get("label", "")
        self.lbl_label.setText(t("preview.label", label=label) if label
                               else "")
        self.perf.push(fps, ms)
        for entry in state.get("log", []):
            self.ed_log.appendPlainText(entry.get("line", ""))
        self._refresh_vars(state.get("vars", {}))

    def _refresh_vars(self, vars_: dict) -> None:
        self._filling_vars = True
        try:
            keys = sorted(vars_.keys())
            self.tbl_vars.setRowCount(len(keys))
            for i, k in enumerate(keys):
                v = vars_[k]
                self.tbl_vars.setItem(i, 0, QTableWidgetItem(k))
                self.tbl_vars.setItem(i, 1, QTableWidgetItem(
                    json.dumps(v, ensure_ascii=False)
                    if not isinstance(v, str) else v))
        finally:
            self._filling_vars = False

    def _on_var_edited(self, item: QTableWidgetItem) -> None:
        if self._filling_vars or item.column() != 1:
            return
        name_item = self.tbl_vars.item(item.row(), 0)
        if name_item is None or self._client is None:
            return
        self._client.send({"type": "set_var",
                           "name": name_item.text(),
                           "value": item.text()})

    def closeEvent(self, event):
        self.stop()
        super().closeEvent(event)
