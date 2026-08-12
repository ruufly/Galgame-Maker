"""transitions_plus 插件 — 编辑器接口 (扩展背景过渡)。"""

from editor.plugins_api import registry


def setup(reg):
    reg.register_plugin("transitions_plus", meta={
        "name": "transitions_plus",
        "description": "扩展背景过渡: wipe/iris/curtain/sweep/...",
    }).add_transition("wipe", "iris", "curtain", "sweep", "fade_white",
                      "checker", "stripes")
