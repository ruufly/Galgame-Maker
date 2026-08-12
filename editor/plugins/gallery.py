"""gallery 插件 — 编辑器接口 (鉴赏系统)。

- gallery_open 动作
- gallery 块样式字段 (样式面板中可编辑)
"""

from editor.plugins_api import registry

_GALLERY_FIELDS = [
    ("unlock_ending", "解锁结局 (达成后开放鉴赏)", "text", ""),
    ("button_text", "标题按钮文本", "text", "鉴赏"),
    ("title", "鉴赏界面标题", "text", "鉴赏"),
    ("categories", "可用分类 (逗号分隔)", "text", "cg, bgm, character, scene"),
    ("locked_hint", "未解锁提示", "text", ""),
    ("bg", "界面背景图", "image", ""),
    ("cat_image", "分类按钮图 (默认, 焦点)", "text", ""),
    ("back_image", "返回按钮图", "text", ""),
    ("cat_text", "分类显示文字", "bool", "true"),
    ("cg_frame", "CG 插画框 (默认, 焦点)", "text", ""),
    ("cg_placeholder", "未解锁占位图", "image", ""),
]


def setup(reg):
    reg.register_plugin("gallery", meta={
        "name": "gallery",
        "description": "鉴赏: CG/BGM/角色/场景 (gallery 块由插件解析)",
    }).add_action("gallery_open").add_event("script_block") \
        .add_style_fields("gallery", _GALLERY_FIELDS)
