"""引擎核心包。"""

import os
import sys
import time


class _Log:
    """极简日志: 带时间戳和级别前缀。

    同时输出到 console 与日志文件 (set_log_file);
    warning 可通过 on_warning 注册回调 (游戏界面提示)。
    """

    VERBOSE = False
    _file = None
    _warn_cbs = []

    def _fmt(self, level, msg):
        return "[GM:%s] %s: %s" % (time.strftime("%H:%M:%S"), level, msg)

    def set_log_file(self, path):
        """设置日志文件 (追加写入; None/空 = 仅 console)。"""
        if self._file:
            try:
                self._file.close()
            except Exception:
                pass
            self._file = None
        if path:
            try:
                d = os.path.dirname(os.path.abspath(path))
                if d:
                    os.makedirs(d, exist_ok=True)
                self._file = open(path, "a", encoding="utf-8")
            except Exception:
                self._file = None

    def on_warning(self, fn):
        """注册警告回调 (如游戏界面提示); 每次 WARN 时调用 fn(msg)。"""
        if fn not in self._warn_cbs:
            self._warn_cbs.append(fn)
        return fn

    def _emit(self, level, msg):
        line = self._fmt(level, msg)
        print(line)
        if self._file:
            try:
                self._file.write(line + "\n")
                self._file.flush()
            except Exception:
                pass
        if level == "WARN":
            for cb in list(self._warn_cbs):
                try:
                    cb(msg)
                except Exception:
                    pass

    def info(self, msg):
        self._emit("INFO", msg)

    def warning(self, msg):
        self._emit("WARN", msg)

    def error(self, msg):
        self._emit("ERROR", msg)

    def debug(self, msg):
        if self.VERBOSE:
            self._emit("DEBUG", msg)


log = _Log()
