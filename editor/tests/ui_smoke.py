"""P1 UI 冒烟测试: 主窗口骨架 + 打开项目 + 校验 + 内嵌预览。

自动运行约 5 秒后退出; 断言:
- 项目树已填充 (含脚本节点)
- 校验通过 (往返 + 合并加载)
- 预览收到引擎帧 (frames > 0)

运行::

    py -3.10 editor/tests/ui_smoke.py
"""

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from editor.ui.main_window import MainWindow

DEMO_DIR = os.path.join(_ROOT, "test", "engine_demo")

results = {}


def main() -> int:
    app = QApplication(sys.argv)
    win = MainWindow()
    win.resize(1100, 760)
    win.show()

    win.open_project(DEMO_DIR)
    results["project_open"] = win.project is not None and len(win.project.scripts) > 0

    win.validate()
    results["validate"] = "校验完成" in win.output.toPlainText() \
        and "合并加载 OK" in win.output.toPlainText()

    win.preview.start()
    QTimer.singleShot(4000, win.close)
    app.exec()

    results["preview_frames"] = win.preview.frames

    print("== P1 UI 冒烟 ==")
    print("project_open   :", results["project_open"])
    print("validate       :", results["validate"])
    print("preview_frames :", results["preview_frames"])
    ok = (results["project_open"] and results["validate"]
          and results["preview_frames"] > 10)
    print("RESULT:", "OK" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    # os._exit: 跳过 pygame/SDL 解释器关闭时的 atexit 清理竞态
    # (否则退出码偶发非 0, 测试不稳定)
    os._exit(main())
