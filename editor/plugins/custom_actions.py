"""custom_actions 插件 — 编辑器接口 (动作/立绘效果/文字模式)。"""

from editor.plugins_api import registry


def setup(reg):
    p = reg.register_plugin("custom_actions", meta={
        "name": "custom_actions",
        "description": "动作 (explode/quake/...) + do_action + 立绘效果 + 文字模式",
    })
    p.add_command("do_action")
    p.add_action("explode", "quake", "freeze", "blackout")
    p.add_sprite_effect("wobble", "sway", "zoom_bounce", "fade_rotate",
                        "float", "squash")
    p.add_text_mode("wave", "bounce", "speedup", "rainbow", "shiver")
