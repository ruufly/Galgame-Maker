"""错误处理: 记录完整 traceback 到日志文件, 供引擎弹窗展示。

引擎捕获所有未处理异常 -> ErrorHandler.record() 写日志 (logs/errors.log)
并保存快照 -> 游戏内弹窗显示 (可复制完整报错/继续/退出)。

同时提供 sys.excepthook 兜底, 主线程任何未捕获异常都不会静默崩溃。
"""

import os
import sys
import time
import traceback

from framework.engine import log

_CURRENT_ENGINE = None   # 供 excepthook 定位当前引擎实例


def install_excepthook(engine=None):
    """安装全局未捕获异常处理器 (主线程异常 -> 弹窗而非崩溃)。

    可在 gamelauncher 启动时调用, engine 为 None 时只记录。
    """
    global _CURRENT_ENGINE
    if engine is not None:
        _CURRENT_ENGINE = engine

    def hook(exc_type, exc_value, exc_tb):
        if _CURRENT_ENGINE is not None:
            try:
                _CURRENT_ENGINE.handle_error(exc_value)
                return
            except Exception:
                pass
        # 无引擎或弹窗失败: 打印完整 traceback (不崩溃)
        traceback.print_exception(exc_type, exc_value, exc_tb)

    sys.excepthook = hook


class ErrorHandler:
    """收集并持久化错误信息。"""

    def __init__(self, engine) -> None:
        self.engine = engine
        self.count = 0
        self.last_error = None      # {"text", "traceback", "time"}
        self.log_path = None

    def ensure_log(self) -> str:
        """日志文件: <项目目录>/logs/errors.log"""
        if self.log_path:
            return self.log_path
        d = os.path.join(self.engine.project_dir, "logs")
        try:
            os.makedirs(d, exist_ok=True)
            self.log_path = os.path.join(d, "errors.log")
        except Exception:
            self.log_path = os.path.join(os.getcwd(), "errors.log")
        return self.log_path

    def record(self, error, level: str = "error") -> dict:
        """记录一次错误 (异常对象或文本), 返回快照 dict。

        level: "error" (严重, 配合弹窗) / "warn" (可恢复, 仅记录)
        """
        self.count += 1
        if isinstance(error, BaseException):
            text = f"{type(error).__name__}: {error}"
            tb_text = "".join(traceback.format_exception(
                type(error), error, error.__traceback__))
        else:
            text = str(error)
            tb_text = text
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        entry = (f"[{stamp}] {level.upper()} #{self.count}\n{tb_text}\n"
                 + "=" * 60 + "\n")
        path = self.ensure_log()
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(entry)
        except Exception:
            pass
        self.last_error = {"text": text, "traceback": tb_text,
                           "time": stamp, "file": path, "level": level}
        first = text.splitlines()[0] if text else "未知错误"
        if level == "warn":
            log.warning(first)
        else:
            log.error(first)
        return self.last_error
