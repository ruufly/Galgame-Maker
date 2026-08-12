"""Galgame Maker 编辑器入口。

用法::

    py -3.10 editor/app.py                 # 空编辑器
    py -3.10 editor/app.py <项目目录>       # 直接打开项目
"""

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from PySide6.QtWidgets import QApplication

from editor.ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Galgame Maker 编辑器")
    win = MainWindow()
    if len(sys.argv) > 1 and os.path.isdir(sys.argv[1]):
        win.open_project(os.path.abspath(sys.argv[1]))
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
