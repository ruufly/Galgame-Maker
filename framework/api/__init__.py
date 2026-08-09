"""插件 API 包: 事件 / 指令注册表 / 插件管理器。

GameEngine 通过模块级 __getattr__ 延迟导出 (PEP 562), 避免与
engine.core 产生循环导入。以下两种写法均可用::

    from framework import GameEngine
    from framework.api import GameEngine
"""

from framework.api.events import EventBus
from framework.api.commands import CommandRegistry
from framework.api.plugin import Plugin, PluginManager, event_listener, command

__all__ = [
    "EventBus",
    "CommandRegistry",
    "Plugin",
    "PluginManager",
    "event_listener",
    "command",
    "GameEngine",
]


def __getattr__(name):
    if name == "GameEngine":
        from framework.engine.core import GameEngine
        return GameEngine
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
