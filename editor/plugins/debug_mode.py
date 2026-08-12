"""debug_mode 插件 — 编辑器接口 (调试模式快捷键)。"""

from editor.plugins_api import registry


def setup(reg):
    reg.register_plugin("debug_mode", meta={
        "name": "debug_mode",
        "description": "调试模式 (快捷键切换, 开启显示 FPS)",
    }).add_keybind("debug_toggle", "调试模式")
