"""通知插件 (notice): 合并 BGM 通知 + 场景切换通知。

* BGM 通知: 音乐播放/暂停/恢复/停止时右上角提示
* 场景通知: bg <场景> 切换时左上角提示
"""

import os

from framework.api import event_listener


def _name(path):
    return os.path.basename(str(path))


# ---- BGM 通知 (右上角) ------------------------------------------------
@event_listener("music_play")
def on_music_play(engine, name, path, loop, fade, **kw):
    label = name or _name(path)
    mode = "循环" if loop else "单次"
    text = f"♪ BGM 开始: {label} ({mode})"
    if fade:
        text += f" 淡入 {fade}s"
    engine.display.show_notice(text, 2.0, pos="top-right")


@event_listener("music_pause")
def on_music_pause(engine, **kw):
    engine.display.show_notice("♪ BGM 已暂停", 1.5, pos="top-right")


@event_listener("music_resume")
def on_music_resume(engine, **kw):
    engine.display.show_notice("♪ BGM 已恢复", 1.5, pos="top-right")


@event_listener("music_stop")
def on_music_stop(engine, **kw):
    engine.display.show_notice("♪ BGM 已停止", 1.5, pos="top-right")


# ---- 场景切换通知 (左上角) -------------------------------------------
@event_listener("scene_change")
def on_scene_change(engine, id, name, background, pose, **kw):
    label = name or id
    if pose:
        label = f"{label} · {pose}"
    engine.display.show_notice(f"场景切换: {label}", 2.0, pos="top-left")
