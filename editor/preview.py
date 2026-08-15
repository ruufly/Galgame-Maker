"""引擎实时预览: 在 Qt 界面内嵌运行 framework 引擎 (无头渲染)。

原理 (P0 已验证):
- SDL dummy 驱动 + pygame, GameEngine 无窗口渲染
- 引擎跑在 QThread 里 (Qt 主线程负责 GUI 事件循环)
- 每帧经 register_frame_hook 取帧 -> Surface -> QImage -> 信号发回 UI
- 停止: 置 running=False, 主循环下一帧安全退出; 线程内 pygame.quit()

用法::

    thread = EnginePreviewThread(script_path)
    thread.frame_ready.connect(on_frame)      # QImage
    thread.status_changed.connect(on_status)  # str
    thread.start()
    ...
    thread.stop(); thread.wait(3000)
"""

import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
                               QWidget)
from editor.i18n import t

# framework 导入会连带 import pygame (仅模块导入, 不初始化 SDL)
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def surface_to_qimage(surface) -> QImage:
    """pygame.Surface -> QImage (RGB888 副本, 可跨线程传递)。"""
    w, h = surface.get_size()
    data = pygame.image.tostring(surface, "RGB")
    img = QImage(data, w, h, w * 3, QImage.Format_RGB888)
    return img.copy()


def detect_window_config(script_path: str) -> dict:
    """从脚本 (递归展开 import) 顶层解析 window 配置块。

    与 gamelauncher.extract_window_config 同源逻辑 —— 预览引擎
    必须以项目声明的逻辑分辨率构建, 否则坐标超过预览尺寸的内容
    (如 button_y: 340 的标题按钮) 会被画到画面外。
    """
    try:
        from framework.engine.loader import load_script_with_imports
        script = load_script_with_imports(script_path)
    except Exception:
        return {}
    for stmt in script.statements:
        if stmt.op in ("window", "config"):
            return dict(stmt.kwargs)
    return {}


def detect_logical_size(script_path: str, default=(1280, 720)):
    """脚本声明的逻辑分辨率; 无法解析/含变量时回退默认。"""
    cfg = detect_window_config(script_path)
    try:
        w = int(cfg.get("width", default[0]))
    except (TypeError, ValueError):
        w = default[0]
    try:
        h = int(cfg.get("height", default[1]))
    except (TypeError, ValueError):
        h = default[1]
    return w, h


class EnginePreviewThread(QThread):
    """单次使用: 一个线程跑一个引擎实例, 结束后须新建。"""

    frame_ready = Signal(QImage)
    status_changed = Signal(str)

    def __init__(self, script_path: str, width: int = None,
                 height: int = None, fps: int = None, parent=None):
        super().__init__(parent)
        self.script_path = os.path.abspath(script_path)
        if width is None or height is None:
            # 自动采用项目声明的逻辑分辨率 (否则内容画不全)
            width, height = detect_logical_size(self.script_path)
        if fps is None:
            cfg = detect_window_config(self.script_path)
            try:
                fps = int(cfg.get("fps", 60))
            except (TypeError, ValueError):
                fps = 60
        self.width, self.height, self.fps = width, height, fps
        self.frames_rendered = 0
        self.last_error: str = ""
        self._engine = None
        self._stop = False

    # ---- 控制 ---------------------------------------------------------
    def stop(self) -> None:
        """请求停止 (下一帧生效), 调用方随后 wait()。"""
        self._stop = True
        if self._engine is not None:
            self._engine.running = False

    # ---- 线程体 -------------------------------------------------------
    def run(self) -> None:
        global pygame
        import pygame  # 线程内导入并初始化 SDL (dummy 驱动)

        try:
            from framework.api import GameEngine
            engine = GameEngine(self.width, self.height,
                                t("preview.engine_title"),
                                fps=self.fps, autoload_plugins=True)
            self._engine = engine
            self.status_changed.emit(
                t("preview.starting_fmt", w=self.width, h=self.height,
                  fps=self.fps))

            def hook(dt):
                if self._stop:
                    engine.running = False
                    return
                self.frames_rendered += 1
                # 取上一帧 (hook 先于本帧绘制), 1 帧滞后可接受
                frame = engine.display.capture()
                self.frame_ready.emit(surface_to_qimage(frame))

            engine.register_frame_hook(hook)
            engine.run(self.script_path)
            self.status_changed.emit(
                t("preview.finished", n=self.frames_rendered))
        except Exception as exc:  # noqa: BLE001 - 预览不应拖垮编辑器
            self.last_error = repr(exc)
            self.status_changed.emit(t("preview.error", exc=exc))
        finally:
            try:
                pygame.quit()
            except Exception:
                pass


class PreviewPanel(QWidget):
    """可停靠的预览面板: 运行/停止按钮 + 引擎画面显示。

    用法::

        panel = PreviewPanel()
        panel.set_script("path/to/demo.gal")
        panel.start()          # 每次 start 新建引擎线程
        panel.stop()           # 请求停止 (线程随后结束)
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        self.view = QLabel(t("preview.not_started"))
        self.view.setAlignment(Qt.AlignCenter)
        self.view.setMinimumSize(480, 270)
        self.view.setStyleSheet(
            "background:#181818; color:#9a9a9a; font-size:13px;")
        layout.addWidget(self.view, 1)

        row = QHBoxLayout()
        self.btn_run = QPushButton(t("preview.run"))
        self.btn_stop = QPushButton(t("preview.stop"))
        self.btn_stop.setEnabled(False)
        row.addWidget(self.btn_run)
        row.addWidget(self.btn_stop)
        row.addStretch(1)
        layout.addLayout(row)

        self.btn_run.clicked.connect(self.start)
        self.btn_stop.clicked.connect(self.stop)

        self.setMinimumSize(520, 300)
        self._script: str = ""
        self._thread = None
        self.frames = 0
        # 帧显示缓存: 视图尺寸/帧尺寸未变时复用缩放结果, 省去每帧重缩放
        self._last_view_size = None
        self._last_img_size = None
        self._last_pixmap = None

    # ---- 对外接口 -----------------------------------------------------
    def set_script(self, path: str) -> None:
        self._script = path

    def script(self) -> str:
        return self._script

    def start(self) -> None:
        if self._thread is not None and self._thread.isRunning():
            return
        if not self._script:
            self.view.setText(t("preview.no_script"))
            return
        self.frames = 0
        self.view.setText(t("preview.starting"))
        self.btn_run.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self._thread = EnginePreviewThread(self._script)
        self._thread.frame_ready.connect(self._on_frame)
        self._thread.status_changed.connect(self._on_status)
        self._thread.finished.connect(self._on_finished)
        self._thread.start()

    def stop(self) -> None:
        if self._thread is not None:
            self._thread.stop()

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.isRunning()

    # ---- 内部 ---------------------------------------------------------
    def _on_frame(self, img: QImage) -> None:
        self.frames += 1
        view_size = self.view.size()
        img_size = img.size()
        if (self._last_pixmap is None or view_size != self._last_view_size
                or img_size != self._last_img_size):
            self._last_view_size = view_size
            self._last_img_size = img_size
            self._last_pixmap = QPixmap.fromImage(img).scaled(
                view_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.view.setPixmap(self._last_pixmap)

    def _on_status(self, msg: str) -> None:
        self.view.setToolTip(msg)

    def _on_finished(self) -> None:
        self.btn_run.setEnabled(True)
        self.btn_stop.setEnabled(False)
        if self._thread is not None:
            self._thread.deleteLater()
            self._thread = None

    def apply_lang(self):
        """语言切换时刷新文案。"""
        self.btn_run.setText(t("preview.run"))
        self.btn_stop.setText(t("preview.stop"))

    def closeEvent(self, event):
        self.stop()
        if self._thread is not None:
            self._thread.wait(5000)
        super().closeEvent(event)
