"""
Galgame Maker 运行时引擎 (framework)
====================================

设计目标:
    * 解析并运行 .gal 视觉小说脚本 (兼容 Galgame-Maker 编辑器语法风格)
    * 提供基础视觉小说功能: 背景/立绘/对话/选项分支/变量/存档
    * 预留插件 API: 事件订阅、自定义 DSL 指令、渲染钩子

用法::

    from framework.api import GameEngine

    engine = GameEngine(1280, 720, "My Game")
    engine.run("test/engine_demo/demo.gal")

依赖: Python 3.10 + pygame
"""

from framework.engine.core import GameEngine
from framework.api.plugin import Plugin, event_listener, command
from framework.api.events import EventBus

__all__ = [
    "GameEngine",
    "Plugin",
    "event_listener",
    "command",
    "EventBus",
    "__version__",
]

__version__ = "0.1.0"
