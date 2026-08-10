"""FPS 浮层插件 (类形式: Plugin 基类 + 生命周期钩子)。

在画面右上角叠加显示插件名与实时帧率, 演示:
    * on_load / on_unload 生命周期
    * self.listen() 实例方法订阅
    * draw_overlay 渲染钩子 (每帧画面绘制完成后触发)
"""

import time

import pygame

from framework.api import Plugin


class FpsOverlayPlugin(Plugin):
    name = "fps_overlay"
    version = "1.0"

    def on_load(self):
        self.frames = 0
        self.last_time = time.time()
        self.fps = 60
        self.font = None

        # 订阅: 每帧绘制完成后在右上角画信息
        @self.listen("draw_overlay")
        def draw_overlay(surface, **kw):
            if self.font is None:
                self.font = self.engine.get_font(18)
            text = f"{self.name} v{self.version} | {self.fps:.0f} FPS"
            surf = self.font.render(text, True, (180, 255, 180))
            x = surface.get_width() - surf.get_width() - 10
            y = 8
            pygame.draw.rect(surface, (0, 0, 0, 160), (x - 6, y - 3,
                                                       surf.get_width() + 12,
                                                       surf.get_height() + 6))
            surface.blit(surf, (x, y))

        @self.listen("frame")
        def frame(**kw):
            now = time.time()
            self.frames += 1
            if now - self.last_time >= 0.5:
                self.fps = self.frames / (now - self.last_time)
                self.frames = 0
                self.last_time = now

    def on_unload(self):
        print("[插件] fps_overlay 已卸载")
