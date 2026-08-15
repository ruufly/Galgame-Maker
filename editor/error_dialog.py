"""编辑器全局异常处理: 弹窗 + 复制完整错误信息。

- sys.excepthook 接管未捕获异常 (含 PySide6 槽内异常):
  完整 traceback 自动复制到剪贴板 + 弹窗 (可展开详细信息)
- show_error(exc): 显式调用入口 (各面板 catch 后调用来兜底)
"""

import sys
import traceback

from PySide6.QtWidgets import QApplication, QMessageBox

from editor.i18n import t

_INSTALLED = False


def install_excepthook() -> None:
    """安装全局异常钩子 (app 启动时调用一次)。"""
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True
    sys.excepthook = _hook


def _hook(exc_type, exc_value, exc_tb) -> None:
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return
    tb_text = "".join(traceback.format_exception(exc_type, exc_value,
                                                 exc_tb))
    show_error(exc_value, tb_text)


def show_error(exc: BaseException, tb_text: str | None = None) -> None:
    """弹窗显示错误 + 自动复制完整信息 (不抛异常)。"""
    if tb_text is None:
        tb_text = "".join(traceback.format_exception(
            type(exc), exc, exc.__traceback__))
    # 自动复制完整错误到剪贴板
    try:
        QApplication.clipboard().setText(tb_text)
    except Exception:
        pass
    try:
        box = QMessageBox()
        box.setIcon(QMessageBox.Critical)
        box.setWindowTitle(t("error.title"))
        box.setText(t("error.occurred", exc=exc))
        box.setInformativeText(t("error.copied_hint"))
        box.setDetailedText(tb_text)
        box.addButton(t("error.copy_continue"), QMessageBox.AcceptRole)
        box.exec()
    except Exception:
        sys.__excepthook__(type(exc), exc, None)
