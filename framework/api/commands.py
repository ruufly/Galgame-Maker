"""指令注册表: 插件可以通过它向 DSL 添加自定义指令。"""

from typing import Any, Callable, Dict, Optional


class CommandRegistry:
    """DSL 指令注册表。

    引擎执行脚本时, 遇到一条语句:

    1. 先查内置指令表 (runtime 内部实现);
    2. 未命中则查本注册表 (插件指令);
    3. 仍未命中则输出警告并跳过该行。

    插件用法::

        @engine.commands.register("shake")
        def shake(engine, stmt, **kw):
            engine.display.shake(0.3, 8)

    指令函数的签名约定::

        def handler(engine, stmt, **kwargs) -> Optional[str]:
            # engine : GameEngine 实例
            # stmt   : 解析后的 Statement (含 .args / .kwargs / .line)
            # 返回 None        -> 指令执行完毕, 继续下一条
            # 返回 "block"     -> 阻塞, 等待引擎外部事件 (如点击) 后
            #                    由 handler 自己调用 engine.runtime.advance()
    """

    def __init__(self, engine=None) -> None:
        self._engine = engine
        self._commands: Dict[str, Callable] = {}

    # ------------------------------------------------------------------
    def register(self, name: str, handler: Callable = None):
        """注册指令, 支持两种形式: ``register("x", fn)`` 或 ``@register("x")``。"""
        if handler is None:
            def deco(fn: Callable) -> Callable:
                self._commands[name] = fn
                return fn
            return deco
        if not callable(handler):
            raise TypeError(f"指令 {name} 的处理器必须是可调用对象")
        self._commands[name] = handler
        return handler

    def unregister(self, name: str) -> None:
        self._commands.pop(name, None)

    def has(self, name: str) -> bool:
        return name in self._commands

    def names(self) -> list:
        return list(self._commands.keys())

    def call(self, name: str, stmt: Any) -> Optional[str]:
        """调用插件指令。找不到时返回 None 并由调用方继续兜底。"""
        handler = self._commands.get(name)
        if handler is None:
            return None
        return handler(self._engine, stmt)
