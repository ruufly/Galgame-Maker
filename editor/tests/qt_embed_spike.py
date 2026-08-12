"""P1 技术验证: pygame 帧 -> QImage -> Qt 控件 的嵌入预览闭环。

自动运行约 6 秒后退出, 打印收到的帧数与最后帧尺寸。
若 frame_count > 5 且尺寸正确, 即验证通过 (Qt 主线程正常收帧)。

运行::

    py -3.10 editor/tests/qt_embed_spike.py
"""

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (QApplication, QLabel, QMainWindow, QPushButton,
                               QStatusBar, QVBoxLayout, QWidget)

from editor.preview import EnginePreviewThread

DEMO = os.path.join(_ROOT, "test", "engine_demo", "demo.gal")


class SpikeWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Qt 嵌入预览验证")
        self.frames = []

        central = QWidget()
        layout = QVBoxLayout(central)
        self.view = QLabel("等待引擎帧…")
        self.view.setAlignment(Qt.AlignCenter)
        self.view.setMinimumSize(480, 270)
        self.view.setStyleSheet("background:#202020; color:#ccc;")
        layout.addWidget(self.view, 1)
        self.btn = QPushButton("停止")
        layout.addWidget(self.btn)
        self.setCentralWidget(central)
        self.statusBar().showMessage("启动引擎…")

        self.thread = EnginePreviewThread(DEMO)   # 自动采用项目逻辑分辨率
        self.thread.frame_ready.connect(self._on_frame)
        self.thread.status_changed.connect(self.statusBar().showMessage)
        self.thread.start()
        self.btn.clicked.connect(self._stop)
        QTimer.singleShot(6000, self._finish)

    def _on_frame(self, img: QImage):
        self.frames.append(img)
        self.view.setPixmap(QPixmap.fromImage(img).scaled(
            self.view.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def _stop(self):
        self.thread.stop()

    def _finish(self):
        self._stop()
        self.thread.wait(5000)
        self.close()

    def closeEvent(self, event):
        self._stop()
        self.thread.wait(5000)
        super().closeEvent(event)


def main() -> int:
    app = QApplication(sys.argv)
    win = SpikeWindow()
    win.resize(860, 600)
    win.show()
    app.exec()

    n = len(win.frames)
    size = win.frames[-1].size() if win.frames else (0, 0)
    print(f"frames received : {n}")
    print(f"last frame size : {size.width()}x{size.height()} (期望 1280x720, 脚本 window 配置)")
    print(f"status          : {win.statusBar().currentMessage()}")
    if n >= 5 and size.width() == 1280 and size.height() == 720:
        print("RESULT: OK (Qt 线程正常接收引擎帧, 逻辑分辨率自动适配)")
        return 0
    print("RESULT: FAIL")
    return 1


if __name__ == "__main__":
    # os._exit: 跳过 pygame/SDL 解释器关闭时的 atexit 清理竞态
    os._exit(main())
