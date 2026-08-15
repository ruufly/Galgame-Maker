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
    # 全局异常处理: 弹窗 + 复制完整错误 (避免直接崩溃无提示)
    from editor.error_dialog import install_excepthook
    install_excepthook()
    app = QApplication(sys.argv)
    from editor.i18n import t
    app.setApplicationName(t("app.title"))
    win = MainWindow()
    if len(sys.argv) > 1 and os.path.isdir(sys.argv[1]):
        win.open_project(os.path.abspath(sys.argv[1]))
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
