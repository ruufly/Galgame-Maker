"""震动/闪屏指令插件 (装饰器写法)。

提供 DSL 指令:
    shake <时长秒> <幅度像素>  —— 屏幕震动
    flash                    —— 屏幕白闪 (触发 flash_requested 事件)
并订阅若干引擎事件打印日志。
"""

import random

import pygame

from framework.api import command, event_listener


@command("shake")
def cmd_shake(engine, stmt, **kw):
    """shake <时长秒> <幅度像素> —— 屏幕震动。"""
    try:
        duration = float(stmt.args[0]) if stmt.args else 0.3
    except ValueError:
        duration = 0.3
    try:
        magnitude = int(stmt.args[1]) if len(stmt.args) > 1 else 8
    except ValueError:
        magnitude = 8
    engine.display.shake(duration, magnitude)
    engine.show_notice(f"插件指令 shake: {duration}s / {magnitude}px")


@command("flash")
def cmd_flash(engine, stmt, **kw):
    """flash —— 屏幕白闪一瞬 (演示事件 + 直接访问引擎状态)。"""
    engine.emit("flash_requested")


@event_listener("script_start")
def on_script_start(engine, **kw):
    print("[插件] 脚本开始运行!")


@event_listener("bg_change")
def on_bg_change(path, **kw):
    print(f"[插件] 背景切换: {path}")


@event_listener("choice_made")
def on_choice_made(index, label, text, **kw):
    print(f"[插件] 玩家选择了 {index}: {text!r} -> {label}")
