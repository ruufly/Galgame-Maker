"""引擎核心包。"""

import sys
import time


class _Log:
    """极简日志: 带时间戳和级别前缀。"""

    VERBOSE = False

    def _fmt(self, level, msg):
        return "[GM:%s] %s: %s" % (time.strftime("%H:%M:%S"), level, msg)

    def info(self, msg):
        print(self._fmt("INFO", msg))

    def warning(self, msg):
        print(self._fmt("WARN", msg))

    def error(self, msg):
        print(self._fmt("ERROR", msg))

    def debug(self, msg):
        if self.VERBOSE:
            print(self._fmt("DEBUG", msg))


log = _Log()
