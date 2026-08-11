"""Galgame Maker 启动器: 直接把 .gal 脚本交给引擎执行。

用法 (在 Galgame-Maker 项目根目录)::

    py -3.10 gamelauncher.py test/engine_demo/demo.gal
    py -3.10 gamelauncher.py path/to/your.gal
    py -3.10 gamelauncher.py          # 无参数时运行内置演示

也可以直接把 .gal 文件拖到本文件上运行。

脚本内的窗口配置 (放脚本顶层) 会在创建窗口前被读取::

    window
        title: "我的游戏"
        width: 1280
        height: 720
        icon: "materials/image/icon.png"
        fps: 60
        fullscreen: false

依赖: Python 3.10 + pygame
"""

import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
if getattr(sys, "frozen", False):
    # PyInstaller 打包: __file__ 指向临时解压目录,
    # 以 exe 所在目录为项目根 (demo/字体等外部数据与 exe 同放)
    _ROOT = os.path.dirname(sys.executable)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from framework.engine import log
from framework.engine.parser import parse_file
from framework import GameEngine


def extract_window_config(script_path: str) -> dict:
    """从脚本 (递归展开 import) 顶层解析 window 配置块。"""
    try:
        from framework.engine.loader import load_script_with_imports
        script = load_script_with_imports(script_path)
    except Exception as exc:
        log.w("log.launcher.preparse_failed", exc=exc)
        return {}
    for stmt in script.statements:
        if stmt.op in ("window", "config"):
            return dict(stmt.kwargs)
    return {}


def launch(gal_file: str) -> int:
    """启动一个 .gal 游戏, 返回进程退出码。"""
    gal_file = os.path.abspath(gal_file)
    if not os.path.isfile(gal_file):
        log.e("log.launcher.script_missing", path=gal_file)
        return 1
    if not gal_file.lower().endswith((".gal", ".txt")):
        log.w("log.launcher.ext_not_gal", path=gal_file)

    cfg = extract_window_config(gal_file)
    try:
        width = int(cfg.get("width", 1280))
        height = int(cfg.get("height", 720))
        fps = int(cfg.get("fps", 60))
    except (TypeError, ValueError) as exc:
        log.w("log.launcher.window_invalid", exc=exc)
        width, height, fps = 1280, 720, 60
    title = str(cfg.get("title", "Galgame Maker Engine"))
    icon = cfg.get("icon")
    fullscreen = str(cfg.get("fullscreen", "false")).lower() in (
        "true", "1", "yes", "on")
    resizable = str(cfg.get("resizable", "true")).lower() in (
        "true", "1", "yes", "on")

    log.i("log.launcher.launching", path=gal_file)
    log.i("log.launcher.window_cfg", w=width, h=height, fps=fps,
          title=title, fullscreen=fullscreen, resizable=resizable)
    engine = GameEngine(width, height, title, fps, fullscreen=fullscreen,
                        resizable=resizable)
    # 全局未捕获异常 -> 弹窗 (不崩溃)
    from framework.engine.error import install_excepthook
    install_excepthook(engine)
    engine.script_dir = os.path.dirname(gal_file)   # 先就绪 (font/icon 路径)
    engine.apply_config(cfg)   # 运行时选项 (含 font)
    if icon:
        engine.set_icon(icon)
    engine.run(gal_file)
    return 0


def main() -> None:
    if len(sys.argv) > 1:
        target = sys.argv[1]
    else:
        target = os.path.join(_ROOT, "test", "engine_demo", "demo.gal")
        log.i("log.launcher.no_script_demo")
    sys.exit(launch(target))


if __name__ == "__main__":
    main()
