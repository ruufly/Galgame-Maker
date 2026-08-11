"""屏幕特效插件 (fx): 震动 / 白闪 / 黑闪 / 染色 / 频闪 / 脉冲。

DSL 指令 (命名空间 fx, 脚本 using fx 后可直接调用):

    shake 0.3 8            # 屏幕震动 (时长秒, 幅度像素)
    flash 0.15             # 白闪 (默认 0.15s)
    blackflash 0.3         # 黑闪 (默认 0.3s)
    tint 255,0,0 0.5       # 全屏染色闪烁 (r,g,b + 秒数)
    strobe 0.8             # 频闪 (黑白交替闪烁)
    pulse 0,255,128 1.0    # 正弦脉冲染色 (柔和呼吸感)
"""

import math
import time

import pygame

from framework.api import Plugin


class FxPlugin(Plugin):
    name = "fx"
    version = "1.0"

    def on_load(self):
        self._fx = None          # {"kind","color","t0","duration"}
        self.engine.display.register_effect_overlay(self._overlay)

        @self.add_command("shake")
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

        @self.add_command("flash")
        def cmd_flash(engine, stmt, **kw):
            """flash [秒] —— 屏幕白闪一瞬。"""
            self._fx = {"kind": "flash", "color": (255, 255, 255),
                        "t0": time.time(),
                        "duration": self._sec(stmt.args, 0.15)}

        @self.add_command("blackflash")
        def cmd_blackflash(engine, stmt, **kw):
            """blackflash [秒] —— 屏幕黑闪。"""
            self._fx = {"kind": "blackflash", "color": (0, 0, 0),
                        "t0": time.time(),
                        "duration": self._sec(stmt.args, 0.3)}

        @self.add_command("tint")
        def cmd_tint(engine, stmt, **kw):
            """tint <r,g,b> [秒] —— 全屏染色闪烁 (如受伤红闪)。"""
            color = (255, 0, 0)
            dur = 0.5
            if stmt.args:
                try:
                    parts = [int(x) for x in stmt.args[0].replace(
                        " ", "").split(",")]
                    if len(parts) == 3:
                        color = tuple(max(0, min(255, c)) for c in parts)
                except ValueError:
                    pass
                if len(stmt.args) > 1:
                    dur = self._sec(stmt.args[1:], 0.5)
            self._fx = {"kind": "tint", "color": color,
                        "t0": time.time(), "duration": dur}

        @self.add_command("strobe")
        def cmd_strobe(engine, stmt, **kw):
            """strobe [秒] —— 频闪 (黑白交替, 默认 0.8s)。"""
            self._fx = {"kind": "strobe", "color": (255, 255, 255),
                        "t0": time.time(),
                        "duration": self._sec(stmt.args, 0.8)}

        @self.add_command("pulse")
        def cmd_pulse(engine, stmt, **kw):
            """pulse <r,g,b> [秒] —— 正弦脉冲染色 (柔和呼吸, 默认 1s)。"""
            color = (0, 255, 128)
            dur = 1.0
            if stmt.args:
                try:
                    parts = [int(x) for x in stmt.args[0].replace(
                        " ", "").split(",")]
                    if len(parts) == 3:
                        color = tuple(max(0, min(255, c)) for c in parts)
                except ValueError:
                    pass
                if len(stmt.args) > 1:
                    dur = self._sec(stmt.args[1:], 1.0)
            self._fx = {"kind": "pulse", "color": color,
                        "t0": time.time(), "duration": dur}

    @staticmethod
    def _sec(args, default):
        try:
            return max(0.05, float(args[0]))
        except (ValueError, IndexError):
            return default

    # ------------------------------------------------------------------
    def _overlay(self, surface):
        """全屏特效覆盖 (由 display 每帧调用; 无特效时返回 None)。"""
        fx = self._fx
        if fx is None:
            return None
        el = time.time() - fx["t0"]
        dur = fx["duration"]
        k = min(1.0, el / dur)
        if k >= 1.0:
            self._fx = None
            return None
        # 白/黑闪: 快速衰减; 染色: 正弦脉冲; 频闪: 方波交替
        if fx["kind"] == "tint":
            alpha = int(120 * (1 - k))
        elif fx["kind"] == "pulse":
            alpha = int(110 * abs(math.sin(el * math.pi / max(0.05, dur))))
        elif fx["kind"] == "strobe":
            alpha = 230 if int(el / 0.09) % 2 == 0 else 0
        else:
            alpha = int(255 * (1 - k) ** 2)
        overlay = pygame.Surface(surface.get_size())
        overlay.fill(fx["color"])
        overlay.set_alpha(max(0, min(255, alpha)))
        surface.blit(overlay, (0, 0))
        return surface

    def on_unload(self):
        self._fx = None
        print("[插件] fx 已卸载")
