"""插件系统: 基类、装饰器与加载管理器。

一个插件就是一个 Python 模块 (或类), 放在 ``framework/plugins/``
目录下会被引擎自动发现加载。目录下以下划线开头的文件会被忽略。

推荐写法 (模块级函数 + 装饰器, 最简单)::

    # framework/plugins/my_plugin.py
    from framework.api import event_listener, command

    @event_listener("engine_start")
    def on_start(engine, **kw):
        print("插件加载完成!")

    @command("greet")
    def greet(engine, stmt, **kw):
        engine.say("插件", "这是一条由插件指令生成的对话")

也可以写类形式 (需要生命周期管理时)::

    class MyPlugin(Plugin):
        name = "my_plugin"
        version = "1.0"

        def on_load(self):
            # 订阅事件 / 注册指令
            pass

        def on_unload(self):
            pass
"""

import importlib.util
import inspect
import os
import sys
from typing import List, Optional

# 装饰器: 给函数打标记, 加载时由 PluginManager 统一注册
_EVENT_ATTR = "_gm_event"
_COMMAND_ATTR = "_gm_command"


def event_listener(event_name: str):
    """装饰器: 把函数标记为某事件的处理器。"""
    def deco(fn):
        setattr(fn, _EVENT_ATTR, event_name)
        return fn
    return deco


def command(name: str):
    """装饰器: 把函数标记为一条自定义 DSL 指令。"""
    def deco(fn):
        setattr(fn, _COMMAND_ATTR, name)
        return fn
    return deco


class Plugin:
    """插件基类 (可选继承)。"""

    name: str = "unnamed_plugin"
    version: str = "0.1"

    def __init__(self, engine) -> None:
        self.engine = engine
        self._event_handlers = []
        self._command_handlers = []

    # ---- 生命周期钩子 -------------------------------------------------
    def on_load(self) -> None:
        """引擎加载插件时调用 (此时事件/指令尚未注册)。"""
        pass

    def on_unload(self) -> None:
        """引擎卸载插件时调用。"""
        pass

    # ---- 注册辅助 ----------------------------------------------------
    def listen(self, event_name: str):
        """实例方法版事件订阅, 返回装饰器。"""
        def deco(fn):
            self.engine.events.on(event_name, fn)
            self._event_handlers.append(fn)
            return fn
        return deco

    def add_command(self, name: str):
        """实例方法版指令注册, 返回装饰器。"""
        def deco(fn):
            self.engine.commands.register(name, fn)
            self._command_handlers.append(fn)
            return fn
        return deco

    def _cleanup(self) -> None:
        for fn in self._event_handlers:
            # 取消订阅 (按函数对象移除)
            for ev in list(self.engine.events.names()):
                self.engine.events.off(ev, fn)
        for name, fn in list(self._command_handlers):
            pass
        self._event_handlers.clear()
        self._command_handlers.clear()


class PluginManager:
    """扫描并加载插件目录中的模块。"""

    def __init__(self, engine) -> None:
        self.engine = engine
        self.plugins: List[Plugin] = []
        self._modules = {}   # name -> module
        self._classes = {}   # name -> Plugin 类

    # ------------------------------------------------------------------
    def discover(self, directory: str) -> List[str]:
        """扫描目录下所有 ``*.py`` (排除下划线开头) 并加载, 返回模块名列表。"""
        loaded = []
        if not os.path.isdir(directory):
            return loaded
        for entry in sorted(os.listdir(directory)):
            if entry.startswith("_") or not entry.endswith(".py"):
                continue
            path = os.path.join(directory, entry)
            mod_name = "gm_plugin_" + os.path.splitext(entry)[0]
            if self.load_module_from_path(mod_name, path):
                loaded.append(mod_name)
        return loaded

    # ------------------------------------------------------------------
    def load_module_from_path(self, mod_name: str, path: str) -> bool:
        """从文件路径加载一个插件模块。"""
        try:
            spec = importlib.util.spec_from_file_location(mod_name, path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[mod_name] = module
            spec.loader.exec_module(module)
            self._modules[mod_name] = module
            self._register_from_module(module)
            return True
        except Exception as exc:
            from framework.engine import log
            log.warning(f"插件 {path} 加载失败: {exc}")
            return False

    def load(self, module) -> Optional[Plugin]:
        """加载一个已导入的模块 (或其内的 Plugin 子类)。"""
        if inspect.ismodule(module):
            self._register_from_module(module)
            return None
        return self._instantiate(module)

    # ------------------------------------------------------------------
    def _register_from_module(self, module) -> None:
        """扫描模块: 收集带装饰器标记的函数与 Plugin 子类。"""
        for attr_name in dir(module):
            obj = getattr(module, attr_name)
            if inspect.isclass(obj) and issubclass(obj, Plugin) and obj is not Plugin:
                self._instantiate(obj)
                continue
            if inspect.isfunction(obj):
                self._register_function(obj)

    def _register_function(self, fn) -> None:
        ev = getattr(fn, _EVENT_ATTR, None)
        if ev is not None:
            self.engine.events.on(ev, fn)
        cmd = getattr(fn, _COMMAND_ATTR, None)
        if cmd is not None:
            self.engine.commands.register(cmd, fn)

    def _instantiate(self, cls) -> Optional[Plugin]:
        try:
            inst = cls(self.engine)
        except Exception as exc:
            from framework.engine import log
            log.warning(f"插件类 {cls} 实例化失败: {exc}")
            return None
        if not isinstance(inst, Plugin):
            return None
        inst.on_load()
        # 重新扫描实例方法上的装饰器标记 (类形式插件也支持装饰器)
        for name in dir(inst):
            obj = getattr(inst, name)
            if callable(obj) and not name.startswith("__"):
                self._register_function(obj)
        self.plugins.append(inst)
        self._classes[inst.name] = inst
        from framework.engine import log
        log.info(f"插件已加载: {inst.name} v{inst.version}")
        return inst

    # ------------------------------------------------------------------
    def unload(self, plugin) -> None:
        try:
            plugin.on_unload()
        except Exception as exc:
            from framework.engine import log
            log.warning(f"插件 {plugin.name} 卸载时出错: {exc}")
        plugin._cleanup()
        if plugin in self.plugins:
            self.plugins.remove(plugin)
        self._classes.pop(plugin.name, None)

    def unload_all(self) -> None:
        for plugin in list(self.plugins):
            self.unload(plugin)
