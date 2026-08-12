"""slot_thumbnails 插件 — 编辑器接口 (存档快照, 无注册项)。"""

from editor.plugins_api import registry


def setup(reg):
    reg.register_plugin("slot_thumbnails", meta={
        "name": "slot_thumbnails",
        "description": "存档画面快照 + 槽位缩略图 (引擎内部工作)",
    })
