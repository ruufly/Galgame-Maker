"""notice 插件 — 编辑器接口 (BGM/场景切换通知)。"""

from editor.plugins_api import registry


def setup(reg):
    reg.register_plugin("notice", meta={
        "name": "notice",
        "description": "通知: BGM 播放/暂停/恢复/停止 (右上) + 场景切换 (左上)",
    }).add_event("music_play", "music_pause", "music_stop",
                 "scene_change")
