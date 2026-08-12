"""auto_skip 插件 — 编辑器接口 (自动模式/跳过剧情)。"""

from editor.plugins_api import registry


def setup(reg):
    reg.register_plugin("auto_skip", meta={
        "name": "auto_skip",
        "description": "自动模式 + 跳过剧情 (系统菜单按钮)",
    }).add_action("auto_toggle", "skip_once").add_menu_button(
        "auto_toggle").add_menu_button("skip_once")
