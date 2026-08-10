"""指令注册表: 插件可以通过它向 DSL 添加自定义指令 (支持命名空间)。

命名空间规则:
    builtin::<指令>      引擎内置指令
    main::<指令>         项目自定义 (目前仅引擎 API 直接注册时)
    <插件名>::<指令>     插件注册的指令 (无 using 时必须显式命名空间)
    无命名空间: 先查 main:: 再查 builtin::, 再查已 using 的插件
"""

from typing import Any, Callable, Dict, Optional


class CommandRegistry:
    """DSL 指令注册表 (按命名空间分组)。"""

    def __init__(self, engine=None) -> None:
        self._engine = engine
        self._by_ns: Dict[str, Dict[str, Callable]] = {"main": {}, "builtin": {}}

    # ------------------------------------------------------------------
    def register(self, name: str, handler: Callable = None,
                 ns: str = "main"):
        """注册指令, 支持 ``register("x", fn)`` 或 ``@register("x")``。"""
        if handler is None:
            def deco(fn: Callable) -> Callable:
                self._by_ns.setdefault(ns, {})[name] = fn
                return fn
            return deco
        if not callable(handler):
            raise TypeError(f"指令 {name} 的处理器必须是可调用对象")
        self._by_ns.setdefault(ns, {})[name] = handler
        return handler

    def register_builtin(self, name: str, handler: Callable) -> None:
        """注册内置指令 (builtin:: 命名空间)。"""
        self._by_ns["builtin"][name] = handler

    def unregister(self, name: str, ns: str = "main") -> None:
        d = self._by_ns.get(ns, {})
        d.pop(name, None)

    def has(self, name: str, ns: str = None) -> bool:
        """ns=None 时检查所有命名空间 (代码调用宽松); DSL 层应传具体 ns。"""
        if ns is not None:
            return name in self._by_ns.get(ns, {})
        return any(name in d for d in self._by_ns.values())

    def get(self, name: str, ns: str = None):
        if ns is not None:
            return self._by_ns.get(ns, {}).get(name)
        for d in self._by_ns.values():
            if name in d:
                return d[name]
        return None

    def find(self, name: str) -> list:
        """找指令存在于哪些命名空间, 返回 [(ns, name), ...] (提示用)。"""
        out = []
        for ns, d in self._by_ns.items():
            if name in d:
                out.append((ns, name))
        return out

    def names(self, ns: str = None) -> list:
        if ns is not None:
            return list(self._by_ns.get(ns, {}).keys())
        out = []
        for d in self._by_ns.values():
            out.extend(d.keys())
        return out

    def call(self, name: str, stmt: Any, ns: str = None) -> Optional[str]:
        """调用指令 (ns=None 时按注册顺序在任一命名空间找)。"""
        handler = self.get(name, ns)
        if handler is None:
            return None
        return handler(self._engine, stmt)
