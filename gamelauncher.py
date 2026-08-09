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
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from framework.engine import log
from framework.engine.parser import parse_file
from framework import GameEngine


def extract_window_config(script_path: str) -> dict:
    """从脚本顶层解析 window 配置块 (无需运行脚本)。"""
    try:
        script = parse_file(script_path)
    except Exception as exc:
        log.warning(f"预解析脚本失败, 使用默认窗口配置: {exc}")
        return {}
    for stmt in script.statements:
        if stmt.op in ("window", "config"):
            return dict(stmt.kwargs)
    return {}


def launch(gal_file: str) -> int:
    """启动一个 .gal 游戏, 返回进程退出码。"""
    gal_file = os.path.abspath(gal_file)
    if not os.path.isfile(gal_file):
        log.error(f"脚本不存在: {gal_file}")
        return 1
    if not gal_file.lower().endswith((".gal", ".txt")):
        log.warning(f"文件后缀不是 .gal: {gal_file} (仍将尝试运行)")

    cfg = extract_window_config(gal_file)
    try:
        width = int(cfg.get("width", 1280))
        height = int(cfg.get("height", 720))
        fps = int(cfg.get("fps", 60))
    except (TypeError, ValueError) as exc:
        log.warning(f"窗口配置数值无效, 使用默认值: {exc}")
        width, height, fps = 1280, 720, 60
    title = str(cfg.get("title", "Galgame Maker Engine"))
    icon = cfg.get("icon")
    fullscreen = str(cfg.get("fullscreen", "false")).lower() in (
        "true", "1", "yes", "on")

    log.info(f"启动游戏: {gal_file}")
    log.info(f"窗口配置: {width}x{height} fps={fps} title={title!r}"
             f" fullscreen={fullscreen}")
    engine = GameEngine(width, height, title, fps, fullscreen=fullscreen)
    if icon:
        engine.script_dir = os.path.dirname(gal_file)
        engine.set_icon(icon)
    engine.run(gal_file)
    return 0


def main() -> None:
    if len(sys.argv) > 1:
        target = sys.argv[1]
    else:
        target = os.path.join(_ROOT, "test", "engine_demo", "demo.gal")
        log.info("未指定脚本, 运行内置演示")
    sys.exit(launch(target))


if __name__ == "__main__":
    main()
