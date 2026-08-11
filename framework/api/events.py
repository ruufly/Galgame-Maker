"""轻量事件总线: 插件通过它订阅引擎生命周期事件。"""

import inspect
from typing import Any, Callable, Dict, List


class EventBus:
    """同步事件总线。

    用法::

        bus = EventBus()

        # 装饰器订阅
        @bus.on("text_show")
        def on_text(text, speaker, **kwargs):
            print(f"{speaker}: {text}")

        # 手动订阅
        bus.on("bg_change", my_handler)

        # 发布事件
        bus.emit("text_show", text="你好", speaker="旁白")

    事件处理器如果返回 False, 会被当作 "阻止默认行为" 的标记
    (emit 会把这个值透传给调用方, 由引擎决定是否忽略)。
    """

    def __init__(self) -> None:
        self._handlers: Dict[str, List[Callable]] = {}

    # ------------------------------------------------------------------
    # 订阅
    # ------------------------------------------------------------------
    def on(self, event_name: str, handler: Callable = None):
        """注册事件处理器, 支持两种调用形式:

        * ``bus.on("name", fn)``
        * ``@bus.on("name")``
        """
        if handler is None:
            def deco(fn: Callable) -> Callable:
                self._register(event_name, fn)
                return fn
            return deco
        self._register(event_name, handler)
        return handler

    def _register(self, event_name: str, handler: Callable) -> None:
        if not callable(handler):
            raise TypeError("handler 必须是可调用对象")
        self._handlers.setdefault(event_name, []).append(handler)

    def off(self, event_name: str, handler: Callable = None) -> None:
        """取消订阅。handler 为空时清空该事件的全部处理器。"""
        if handler is None:
            self._handlers.pop(event_name, None)
            return
        hs = self._handlers.get(event_name, [])
        if handler in hs:
            hs.remove(handler)

    def clear(self) -> None:
        self._handlers.clear()

    # ------------------------------------------------------------------
    # 发布
    # ------------------------------------------------------------------
    def emit(self, event_name: str, **kwargs: Any) -> List[Any]:
        """发布事件, 返回所有处理器的返回值列表。

        处理器可以接收任意关键字参数; 引擎在 emit 时会传入与该事件
        相关的上下文。插件处理器应使用 ``**kwargs`` 兜底以向前兼容。
        """
        results: List[Any] = []
        for handler in list(self._handlers.get(event_name, [])):
            try:
                if inspect.iscoroutinefunction(handler):
                    raise TypeError(
                        f"事件处理器 {handler} 是异步函数, 引擎事件总线不支持异步"
                    )
                results.append(handler(**kwargs))
            except Exception as exc:  # 插件异常不能拖垮主循环
                from framework.engine import log
                log.w("log.event.handler_failed",
                      event=event_name, handler=handler, exc=exc)
        return results

    def has_handlers(self, event_name: str) -> bool:
        return bool(self._handlers.get(event_name))

    def names(self) -> List[str]:
        return list(self._handlers.keys())
