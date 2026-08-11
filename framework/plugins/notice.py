"""通知插件 (notice): 合并 BGM 通知 + 场景切换通知。

* BGM 通知: 音乐播放/暂停/恢复/停止时右上角提示
* 场景通知: bg <场景> 切换时左上角提示

文案走插件语言表 (plugins/lang/<code>.json, ns="plugin")。
"""

import os

from framework.api import event_listener


def _name(path):
    return os.path.basename(str(path))


# ---- BGM 通知 (右上角) ------------------------------------------------
@event_listener("music_play")
def on_music_play(engine, name, path, loop, fade, **kw):
    label = name or _name(path)
    mode = engine.i18n.t("notice.loop" if loop else "notice.once",
                         ns="plugin", default="循环" if loop else "单次")
    text = engine.i18n.t("notice.bgm_play", ns="plugin",
                         default="♪ BGM 开始: {label} ({mode})",
                         label=label, mode=mode)
    if fade:
        text += engine.i18n.t("notice.bgm_fade_in", ns="plugin",
                              default=" 淡入 {fade}s", fade=fade)
    engine.display.show_notice(text, 2.0, pos="top-right")


@event_listener("music_pause")
def on_music_pause(engine, **kw):
    engine.display.show_notice(
        engine.i18n.t("notice.bgm_pause", ns="plugin",
                      default="♪ BGM 已暂停"),
        1.5, pos="top-right")


@event_listener("music_resume")
def on_music_resume(engine, **kw):
    engine.display.show_notice(
        engine.i18n.t("notice.bgm_resume", ns="plugin",
                      default="♪ BGM 已恢复"),
        1.5, pos="top-right")


@event_listener("music_stop")
def on_music_stop(engine, **kw):
    engine.display.show_notice(
        engine.i18n.t("notice.bgm_stop", ns="plugin",
                      default="♪ BGM 已停止"),
        1.5, pos="top-right")


# ---- 场景切换通知 (左上角) -------------------------------------------
@event_listener("scene_change")
def on_scene_change(engine, id, name, background, pose, **kw):
    label = engine.i18n.resolve(name or id)
    if pose:
        label = f"{label} · {pose}"
    engine.display.show_notice(
        engine.i18n.t("notice.scene_change", ns="plugin",
                      default="场景切换: {label}", label=label),
        2.0, pos="top-left")
