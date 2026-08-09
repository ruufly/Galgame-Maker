"""示例插件 3: 场景切换时在左上角弹出通知。

订阅 scene_change 事件 (bg <场景id> [背景名] 触发),
用 display.show_notice(pos="top-left") 在左上角显示通知。
"""

from framework.api import event_listener


@event_listener("scene_change")
def on_scene_change(engine, id, name, background, pose, **kw):
    label = name or id
    if pose:
        label = f"{label} · {pose}"
    engine.display.show_notice(f"场景切换: {label}", 2.0, pos="top-left")
    print(f"[插件] 场景切换 -> {label} ({background})")
