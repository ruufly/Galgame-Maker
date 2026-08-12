"""gallery 插件 — 编辑器接口 (鉴赏系统)。"""

from editor.plugins_api import registry


def setup(reg):
    reg.register_plugin("gallery", meta={
        "name": "gallery",
        "description": "鉴赏: CG/BGM/角色/场景 (gallery 块由插件解析)",
    }).add_action("gallery_open").add_event("script_block")
