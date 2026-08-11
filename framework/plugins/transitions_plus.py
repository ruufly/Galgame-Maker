"""扩展背景过渡插件 (transitions_plus): 框架内置 7 种过渡之外的更多效果。

脚本里使用 ``bg ... with <效果名>``:

    wipe       水平擦除 (新背景从左往右覆盖)
    iris       圆形展开 (黑幕中圆洞从中心扩散露出新背景)
    curtain    双帷幕拉开 (两侧黑幕向两边退)
    sweep      斜向擦除 (右下三角逐渐露出新背景)
    fade_white 白幕淡入淡出 (比黑幕 fade 更亮)
"""

import pygame

from framework.api import Plugin
from framework.engine.display import Transition


class WipeTransition(Transition):
    """水平擦除: 新背景从左往右覆盖旧背景。"""

    name = "wipe"
    duration = 0.8

    def draw_bg(self, target):
        if self.old is not None:
            target.blit(self.old, (0, 0))
        w, h = self.new.get_size()
        x1 = int(w * min(1.0, self.t))
        if x1 > 0:
            sub = self.new.subsurface((0, 0, x1, h))
            target.blit(sub, (0, 0))


class IrisTransition(Transition):
    """圆形展开: 黑幕中圆洞从中心扩散, 露出新背景。"""

    name = "iris"
    duration = 0.9

    def draw_bg(self, target):
        target.blit(self.new, (0, 0))

    def draw_overlay(self, target):
        w, h = self.size
        r = int(max(w, h) * self.t / 2) + 1
        overlay = pygame.Surface((w, h), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 255))
        pygame.draw.circle(overlay, (0, 0, 0, 0),
                           (w // 2, h // 2), max(1, r))
        target.blit(overlay, (0, 0))


class CurtainTransition(Transition):
    """双帷幕拉开: 两侧黑幕向两边退, 中间露出新背景。"""

    name = "curtain"
    duration = 0.9

    def draw_bg(self, target):
        target.blit(self.new, (0, 0))

    def draw_overlay(self, target):
        w, h = self.size
        bw = int(w * (1 - self.t) / 2)
        overlay = pygame.Surface((w, h), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 255))
        if bw > 0:
            overlay.fill((0, 0, 0, 255), (0, 0, bw, h))
            overlay.fill((0, 0, 0, 255), (w - bw, 0, bw, h))
        target.blit(overlay, (0, 0))


class SweepTransition(Transition):
    """斜向擦除: 右下三角逐渐扩大露出新背景。"""

    name = "sweep"
    duration = 0.8

    def draw_bg(self, target):
        target.blit(self.new, (0, 0))

    def draw_overlay(self, target):
        w, h = self.size
        k = min(1.0, self.t)
        overlay = pygame.Surface((w, h), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 255))
        # 挖出右下三角 (顶点随 t 移动)
        pygame.draw.polygon(
            overlay, (0, 0, 0, 0),
            [(0, h), (int(w * k), h), (0, int(h * (1 - k)))])
        target.blit(overlay, (0, 0))


class FadeWhiteTransition(Transition):
    """白幕淡入淡出 (新背景经白幕切换)。"""

    name = "fade_white"
    duration = 1.0

    def __init__(self, old_surface, new_surface, target_size):
        super().__init__(old_surface, new_surface, target_size)
        self.overlay = pygame.Surface(target_size)
        self.overlay.fill((255, 255, 255))

    def draw_bg(self, target):
        if self.t < 0.5 and self.old is not None:
            target.blit(self.old, (0, 0))
        elif self.t >= 0.5:
            target.blit(self.new, (0, 0))

    def draw_overlay(self, target):
        if self.t < 0.5:
            alpha = int(255 * (self.t * 2))
        else:
            alpha = int(255 * (1 - (self.t - 0.5) * 2))
        if alpha > 0:
            self.overlay.set_alpha(min(255, alpha))
            target.blit(self.overlay, (0, 0))


class CheckerTransition(Transition):
    """棋盘格展开: 黑白方格逐个翻转为新背景。"""

    name = "checker"
    duration = 1.0

    def draw_bg(self, target):
        if self.old is not None:
            target.blit(self.old, (0, 0))
        w, h = self.size
        cell = 48
        k = min(1.0, self.t * 2.0)     # 前半程方块逐个出现
        for y in range(0, h, cell):
            for x in range(0, w, cell):
                # 按 (x+y) 排序的序号决定出现时机
                order = (x // cell + y // cell)
                n = (w // cell + 1)
                frac = min(1.0, k * n * 0.35 - order * 0.35)
                if frac > 0:
                    cw = max(1, int(cell * frac))
                    target.blit(self.new.subsurface(
                        (x, y, min(cell, w - x), min(cell, h - y))),
                        (x, y, cw, min(cell, h - y)))


class StripesTransition(Transition):
    """斜条纹擦除: 多条斜向条纹逐渐扩大覆盖新背景。"""

    name = "stripes"
    duration = 0.9

    def draw_bg(self, target):
        if self.old is not None:
            target.blit(self.old, (0, 0))
        w, h = self.size
        k = min(1.0, self.t)
        width = int(w * 0.12)
        step = int(w * 0.16)
        for x0 in range(-w, w, step):
            x = int(x0 + k * w)
            if x > w:
                continue
            target.blit(self.new, (x, 0, width, h),
                        (max(0, x), 0, min(width, w - x), h))


class TransitionPlugin(Plugin):
    name = "transitions_plus"
    version = "1.0"

    def on_load(self):
        for cls in (WipeTransition, IrisTransition, CurtainTransition,
                    SweepTransition, FadeWhiteTransition,
                    CheckerTransition, StripesTransition):
            self.engine.display.register_transition(cls.name, cls)
        print("[插件] 已注册扩展过渡: "
              "wipe, iris, curtain, sweep, fade_white, checker, stripes")
