"""调试模式插件 (debug_mode)。

注册快捷键 (进入 engine.keybinds, 可在设置界面调整): 默认 F3 切换
调试模式; **调试模式开启时才显示** 右上角 FPS 等调试信息浮层。
"""

import time

import pygame

from framework.api import Plugin


class DebugModePlugin(Plugin):
    name = "debug_mode"
    version = "1.0"

    DEFAULT_KEY = "f3"          # 默认快捷键 (可在设置界面调整/留空)

    def on_load(self):
        self.enabled = False
        self.frames = 0
        self.last_time = time.time()
        self.fps = 0.0
        self.font = None

        # 注册快捷键 (自动生成设置项, "按键"分栏)
        self.engine.keybinds.register(
            "debug_toggle", "调试模式",
            lambda key: self._toggle(),
            primary=self.DEFAULT_KEY)

        @self.listen("draw_overlay")
        def draw_overlay(surface, **kw):
            if not self.enabled:
                return
            if self.font is None:
                self.font = self.engine.get_font(18)
            now = time.time()
            self.frames += 1
            if now - self.last_time >= 0.5:
                self.fps = self.frames / (now - self.last_time)
                self.frames = 0
                self.last_time = now
            rt = self.engine.runtime
            label = getattr(rt, "current_label", None) or ""
            text = (f"debug | {self.fps:.0f} FPS | "
                    f"{self.engine.width}x{self.engine.height}"
                    + (f" | {label}" if label else ""))
            surf = self.font.render(text, True, (180, 255, 180))
            x = surface.get_width() - surf.get_width() - 10
            y = 8
            pygame.draw.rect(surface, (0, 0, 0, 160),
                             (x - 6, y - 3, surf.get_width() + 12,
                              surf.get_height() + 6))
            surface.blit(surf, (x, y))

    def _toggle(self) -> bool:
        self.enabled = not self.enabled
        self.frames = 0
        self.last_time = time.time()
        self.engine.display.show_notice(
            "调试模式：开" if self.enabled else "调试模式：关", 1.2)
        return True

    def on_unload(self):
        print("[插件] debug_mode 已卸载")
