"""Galgame Maker 引擎演示入口。

用法 (在 Galgame-Maker 项目根目录)::

    py -3.10 framework/run_demo.py

或指定自己的脚本::

    py -3.10 framework/run_demo.py path/to/your.gal

依赖: Python 3.10 + pygame (pip install pygame)
"""

import os
import sys

# 把项目根目录加入 sys.path, 以便 import framework
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from framework.engine import log
from framework.api import GameEngine


def main():
    if len(sys.argv) > 1:
        script = os.path.abspath(sys.argv[1])
    else:
        script = os.path.join(_ROOT, "test", "engine_demo", "demo.gal")
    if not os.path.isfile(script):
        log.e("log.launcher.script_missing", path=script)
        sys.exit(1)

    engine = GameEngine(1280, 720, "Galgame Maker Engine Demo")
    engine.run(script)


if __name__ == "__main__":
    main()
