"""BGM 通知插件: 音乐播放/暂停/恢复/停止/切换时弹出通知。

订阅 music_play / music_pause / music_resume / music_stop 事件,
在右上角显示提示 (曲名取文件名)。
"""

import os

from framework.api import event_listener


def _name(path):
    return os.path.basename(str(path))


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
