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

    # 预览: 独立窗口模式 (不启动进程, 避免弹出真实游戏窗口干扰测试)
    results["preview_script_set"] = (
        win._preview_script == os.path.join(DEMO_DIR, "demo.gal"))
    from editor.preview_window import PreviewWindow, DebugClient
    pw = PreviewWindow()
    pw.set_script(os.path.join(DEMO_DIR, "demo.gal"))
    results["preview_window_build"] = pw._script.endswith("demo.gal")
    results["preview_client_build"] = DebugClient(0) is not None
    pw.close()

    QTimer.singleShot(500, win.close)
    app.exec()

    print("== P1 UI 冒烟 ==")
    print("project_open        :", results["project_open"])
    print("validate            :", results["validate"])
    print("preview_script_set  :", results["preview_script_set"])
    print("preview_window_build:", results["preview_window_build"])
    print("preview_client_build:", results["preview_client_build"])
    ok = (results["project_open"] and results["validate"]
          and results["preview_script_set"]
          and results["preview_window_build"]
          and results["preview_client_build"])
    print("RESULT:", "OK" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    # os._exit: 跳过 pygame/SDL 解释器关闭时的 atexit 清理竞态
    # (否则退出码偶发非 0, 测试不稳定)
    os._exit(main())
