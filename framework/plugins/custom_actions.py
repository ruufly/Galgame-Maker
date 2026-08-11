"""自定义动作/效果插件 (custom_actions)。

提供:
* 动作 (register_action + do_action 指令): explode / quake / freeze /
  blackout
* 立绘登场/退场效果: wobble / sway / zoom_bounce / fade_rotate
* 文字显示模式: wave / bounce / speedup
* DSL 指令: do_action <类型> [k=v ...]
"""

import math
import time

import pygame

from framework.api import Plugin


class CustomActionsPlugin(Plugin):
    name = "custom_actions"
    version = "1.0"

    def on_load(self):
        engine = self.engine
        self._fx = None      # freeze/blackout 全屏覆盖 {"color","t0","dur"}

        # ---- 动作 -----------------------------------------------------
        def act_explode(engine, params, source):
            try:
                duration = float(params.get("duration", 0.5))
            except (TypeError, ValueError):
                duration = 0.5
            engine.display.shake(duration, 10)
            return False

        def act_quake(engine, params, source):
            try:
                duration = float(params.get("duration", 0.8))
            except (TypeError, ValueError):
                duration = 0.8
            try:
                mag = int(params.get("mag", 20))
            except (TypeError, ValueError):
                mag = 20
            engine.display.shake(duration, mag)
            engine.display.show_notice(
                engine.i18n.t("notice.quake"), 1.0)
            return False

        def act_freeze(engine, params, source):
            """freeze [dur=0.25] —— 全屏白闪定格。"""
            self._fx = {"color": (255, 255, 255), "t0": time.time(),
                        "dur": _num(params.get("dur"), 0.25)}
            return False

        def act_blackout(engine, params, source):
            """blackout [dur=0.3] —— 全屏黑闪。"""
            self._fx = {"color": (0, 0, 0), "t0": time.time(),
                        "dur": _num(params.get("dur"), 0.3)}
            return False

        engine.register_action("explode", act_explode)
        engine.register_action("quake", act_quake)
        engine.register_action("freeze", act_freeze)
        engine.register_action("blackout", act_blackout)

        # ---- DSL 指令: do_action <类型> [k=v ...] --------------------
        @self.add_command("do_action")
        def do_action(engine, stmt, **kw):
            """do_action <动作类型> [参数=值 ...] —— 触发任意已注册动作。"""
            if not stmt.args:
                return None
            atype = stmt.args[0]
            params = {}
            for a in stmt.args[1:]:
                if "=" in a:
                    k, v = a.split("=", 1)
                    params[k] = v
            engine.run_action({"type": atype, **params}, source="script")
            return None

        # ---- 立绘登场/退场效果 ---------------------------------------
        def _eff_wobble(spr, t, direction, display):
            base = spr.effect[4]
            if direction == "enter":
                spr.alpha = int(255 * t)
                offset = math.sin(t * math.pi * 4) * 30 * (1 - t)
            else:
                spr.alpha = int(255 * (1 - t))
                offset = math.sin(t * math.pi * 4) * 30 * t
            spr.center = [base[0] + offset, base[1]]
            spr._recalc()

        def _eff_sway(spr, t, direction, display):
            """sway: 大幅摇摆 + 淡入/淡出。"""
            base = spr.effect[4]
            k = 1 - t if direction == "exit" else t
            spr.alpha = int(255 * k)
            angle = math.sin(t * math.pi * 3) * 25 * (1 - t) \
                if direction == "enter" else \
                math.sin(t * math.pi * 3) * 25 * t
            spr.angle = angle
            spr.center = [base[0], base[1]]
            spr._recalc()

        def _eff_zoom_bounce(spr, t, direction, display):
            """zoom_bounce: 放大回弹登场 / 缩小退场。"""
            if direction == "enter":
                spr.alpha = int(255 * min(1.0, t * 2))
                spr.scale = 1.0 + 0.5 * (1 - t)
            else:
                spr.alpha = int(255 * (1 - t))
                spr.scale = 1.0 + 0.5 * t
            spr._recalc()

        def _eff_fade_rotate(spr, t, direction, display):
            """fade_rotate: 旋转 + 淡入/淡出。"""
            if direction == "enter":
                spr.alpha = int(255 * t)
                spr.angle = 360 * (1 - t)
            else:
                spr.alpha = int(255 * (1 - t))
                spr.angle = 360 * t
            spr._recalc()

        def _eff_float(spr, t, direction, display):
            """float: 上下漂浮 + 淡入/淡出。"""
            base = spr.effect[4]
            k = t if direction == "enter" else 1 - t
            spr.alpha = int(255 * k)
            spr.center = [base[0], base[1] + math.sin(t * math.pi * 2) * 14]
            spr._recalc()

        def _eff_squash(spr, t, direction, display):
            """squash: 垂直挤压回弹 (落地感)。"""
            base = spr.effect[4]
            if direction == "enter":
                spr.alpha = int(255 * min(1.0, t * 2))
                s = 1.0 + 0.35 * math.sin(t * math.pi * 2) * (1 - t)
                spr.scale = s
            else:
                spr.alpha = int(255 * (1 - t))
                spr.scale = 1.0 + 0.2 * t
            spr.center = list(base)
            spr._recalc()

        for name, fn, dur in (("wobble", _eff_wobble, 0.8),
                              ("sway", _eff_sway, 0.9),
                              ("zoom_bounce", _eff_zoom_bounce, 0.7),
                              ("fade_rotate", _eff_fade_rotate, 0.8),
                              ("float", _eff_float, 0.9),
                              ("squash", _eff_squash, 0.7)):
            engine.display.register_sprite_effect(name, fn, dur)

        # ---- 文字显示模式 ---------------------------------------------
        def _tm_wave(d, dt):
            d.reveal += d.type_speed * dt * (1.2 + 0.4 * math.sin(d.reveal * 0.3))

        def _tm_bounce(d, dt):
            """bounce: 跳跃节奏 (快-慢-快)。"""
            d.reveal += d.type_speed * dt * (0.6 + 0.8 * (
                abs(math.sin(d.reveal * 0.5))))

        def _tm_speedup(d, dt):
            """speedup: 越来越快。"""
            factor = 1.0 + min(3.0, d.reveal / 50.0)
            d.reveal += d.type_speed * dt * factor

        def _tm_rainbow(d, dt):
            """rainbow: 彩虹色逐段 (按 run 位置轮换色相)。"""
            d.reveal += d.type_speed * dt
            import colorsys
            idx = 0
            for run in d._runs:
                if run.math:
                    continue
                h = (idx / 8.0) % 1.0
                run.color = tuple(
                    int(c * 255) for c in colorsys.hsv_to_rgb(h, 0.75, 1.0))
                idx += 1

        def _tm_shiver(d, dt):
            """shiver: 颤抖节奏 (快慢交替)。"""
            d.reveal += d.type_speed * dt * (
                1.4 - 0.8 * abs(math.sin(d.reveal * 0.8)))

        for name, fn in (("wave", _tm_wave), ("bounce", _tm_bounce),
                         ("speedup", _tm_speedup),
                         ("rainbow", _tm_rainbow),
                         ("shiver", _tm_shiver)):
            engine.display.register_text_mode(name, {"update": fn})

        # 全屏特效覆盖 (freeze/blackout)
        engine.display.register_effect_overlay(self._overlay)

        from framework.engine import log
        log.i("log.plugin.loaded", name=self.name, version=self.version)

    def _overlay(self, surface):
        """freeze/blackout 全屏覆盖 (无特效时返回 None)。"""
        fx = self._fx
        if fx is None:
            return None
        el = time.time() - fx["t0"]
        k = min(1.0, el / max(0.05, fx["dur"]))
        if k >= 1.0:
            self._fx = None
            return None
        alpha = int(220 * (1 - k) ** 1.5)
        overlay = pygame.Surface(surface.get_size())
        overlay.fill(fx["color"])
        overlay.set_alpha(max(0, min(255, alpha)))
        surface.blit(overlay, (0, 0))
        return surface

    def on_unload(self):
        self._fx = None
        from framework.engine import log
        log.i("log.plugin.unloaded", name=self.name)


def _num(v, default):
    try:
        return max(0.05, float(v))
    except (TypeError, ValueError):
        return default
