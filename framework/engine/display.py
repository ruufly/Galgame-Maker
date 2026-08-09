"""渲染层: 背景 / 立绘图层 / 文本窗 / 选项 / 转场 / 震动。

绘制顺序:
    背景 -> 立绘(按创建顺序) -> 全局黑幕(fade) -> 文本窗或选项 -> 通知 -> 结束画面
随后由引擎把 buffer 贴到窗口 (支持全屏震动偏移)。
"""

import math
import os
import random

import pygame

from framework.engine import log


class _Sprite:
    __slots__ = (
        "id", "surface", "rect", "alpha", "target_alpha", "fade_speed",
        "visible", "props",
    )

    def __init__(self, sid, surface, rect, props=None):
        self.id = sid
        self.surface = surface
        self.rect = rect
        self.alpha = 255
        self.target_alpha = 255
        self.fade_speed = 0.0      # alpha/秒, >0 表示淡入中
        self.visible = False
        self.props = props or {}

    def update(self, dt):
        if self.fade_speed > 0 and self.alpha < self.target_alpha:
            self.alpha += self.fade_speed * dt
            if self.alpha >= self.target_alpha:
                self.alpha = self.target_alpha
                self.fade_speed = 0.0
            self.surface.set_alpha(int(self.alpha))


class Display:
    """负责一切画面绘制与交互命中的判定。"""

    FADE_DURATION = 1.0          # 淡入淡出默认时长(秒)
    TYPE_SPEED = 45.0            # 打字机字符/秒

    def __init__(self, engine, width: int, height: int) -> None:
        self.engine = engine
        self.width = width
        self.height = height
        self.buffer = pygame.Surface((width, height))

        # 背景
        self.bg_surface = None
        self.bg_alpha = 255
        self.bg_fading = False
        self.bg_fade_speed = 0.0

        # 立绘
        self.sprites = {}
        self.sprite_order = []

        # 文本
        self.text_active = False
        self.speaker = None
        self.full_text = ""
        self.reveal = 0.0
        self._font_size = 26

        # 选项
        self.choice_active = False
        self.choices = []          # [(text, label)]
        self.choice_rects = []
        self.hover_index = -1

        # 全局黑幕 (fadeout / fade)
        self.fade_alpha = 0.0
        self.fade_target = 0.0
        self.fade_speed = 255.0

        # 震动
        self.shake_time = 0.0
        self.shake_mag = 0.0
        self._shake_ox = 0
        self._shake_oy = 0

        # 通知条
        self.notice = None
        self.notice_ttl = 0.0

        # 结束画面
        self.ending = False
        self.ending_timer = 0.0

        self._font_title = engine.get_font(48)
        self._font_text = engine.get_font(self._font_size)
        self._font_speaker = engine.get_font(22)
        self._font_choice = engine.get_font(28)
        self._font_notice = engine.get_font(20)
        self._font_end = engine.get_font(32)

    # ==================================================================
    # 图片与坐标
    # ==================================================================
    def load_image(self, path: str):
        """加载图片并按 mode/scale 缩放。"""
        real = self.engine.resolve_path(path)
        if not os.path.isfile(real):
            log.warning(f"图片文件不存在: {real}")
            return None
        try:
            img = pygame.image.load(real).convert_alpha()
        except Exception as exc:
            log.warning(f"图片加载失败 {real}: {exc}")
            return None
        return img

    def _fit(self, img, mode=None, scale=None):
        """根据 mode/scale 把图片缩放到合适的尺寸。"""
        w, h = img.get_size()
        if scale is not None:
            try:
                s = float(scale)
                return pygame.transform.smoothscale(img, (int(w * s), int(h * s)))
            except (TypeError, ValueError):
                pass
        mode = (mode or "fit").lower()
        if mode == "full":
            return pygame.transform.smoothscale(img, (self.width, self.height))
        if mode == "fit":
            ratio = min(self.width / w, self.height / h)
            return pygame.transform.smoothscale(img, (max(1, int(w * ratio)), max(1, int(h * ratio))))
        if mode == "stretch":
            return pygame.transform.smoothscale(img, (self.width, self.height))
        return img

    def _pos_to_xy(self, pos, img_w, img_h):
        """把 pos 参数解析成图片左上角坐标。"""
        w, h = self.width, self.height
        if isinstance(pos, (list, tuple)) and len(pos) == 2:
            try:
                return float(pos[0]) - img_w / 2, float(pos[1]) - img_h / 2
            except (TypeError, ValueError):
                pass
        pos = str(pos or "center").lower()
        if pos == "left":
            return w * 0.25 - img_w / 2, h / 2 - img_h / 2
        if pos == "right":
            return w * 0.75 - img_w / 2, h / 2 - img_h / 2
        if pos == "top":
            return w / 2 - img_w / 2, h * 0.2 - img_h / 2
        if pos == "bottom":
            return w / 2 - img_w / 2, h * 0.8 - img_h / 2
        return w / 2 - img_w / 2, h / 2 - img_h / 2

    # ==================================================================
    # 背景
    # ==================================================================
    def set_bg(self, path: str, effect: str = None) -> None:
        img = self.load_image(path)
        if img is None:
            return
        self.bg_surface = self._fit(img, mode="full")
        if effect == "fade":
            self.bg_alpha = 0
            self.bg_fading = True
            self.bg_fade_speed = 255.0 / self.FADE_DURATION
        else:
            self.bg_alpha = 255
            self.bg_fading = False
        self.engine.emit("bg_change", path=path, effect=effect)

    def clear_bg(self) -> None:
        self.bg_surface = None
        self.bg_alpha = 255
        self.bg_fading = False

    # ==================================================================
    # 立绘
    # ==================================================================
    def show_sprite(self, sid: str, path: str = None, pos=None,
                    scale=None, mode=None, effect: str = None) -> bool:
        """显示/创建立绘。path 为空且已存在时仅更新位置/效果。"""
        if sid in self.sprites and path is None:
            spr = self.sprites[sid]
            if pos is not None:
                w, h = spr.surface.get_size()
                x, y = self._pos_to_xy(pos, w, h)
                spr.rect = pygame.Rect(int(x), int(y), w, h)
                spr.props["pos"] = pos
            if effect == "fade":
                spr.alpha = 0
                spr.target_alpha = 255
                spr.fade_speed = 255.0 / self.FADE_DURATION
            spr.visible = True
            self.engine.emit("sprite_show", id=sid, path=spr.props.get("image"))
            return True
        if path is None:
            log.warning(f"立绘 {sid} 不存在且未提供 image")
            return False

        img = self.load_image(path)
        if img is None:
            return False
        img = self._fit(img, mode=mode, scale=scale)
        w, h = img.get_size()
        x, y = self._pos_to_xy(pos, w, h)
        spr = _Sprite(sid, img, pygame.Rect(int(x), int(y), w, h),
                      props={"image": path, "pos": pos, "scale": scale, "mode": mode})
        if effect == "fade":
            spr.alpha = 0
            spr.target_alpha = 255
            spr.fade_speed = 255.0 / self.FADE_DURATION
        if sid not in self.sprites:
            self.sprite_order.append(sid)
        self.sprites[sid] = spr
        spr.visible = True
        self.engine.emit("sprite_show", id=sid, path=path)
        return True

    def hide_sprite(self, sid: str) -> bool:
        spr = self.sprites.get(sid)
        if spr is None:
            return False
        spr.visible = False
        self.engine.emit("sprite_hide", id=sid)
        return True

    def clear_sprites(self) -> None:
        for sid in list(self.sprite_order):
            if sid in self.sprites:
                self.sprites[sid].visible = False
                self.engine.emit("sprite_hide", id=sid)
        self.sprite_order = []

    def sprite_state(self) -> list:
        """导出立绘状态供存档。"""
        out = []
        for sid in self.sprite_order:
            spr = self.sprites[sid]
            if spr.visible:
                out.append({"id": sid, "props": dict(spr.props)})
        return out

    def restore_sprites(self, state: list) -> None:
        self.clear_sprites()
        for item in state:
            props = item.get("props", {})
            self.show_sprite(item["id"], props.get("image"), props.get("pos"),
                             props.get("scale"), props.get("mode"))

    # ==================================================================
    # 文本
    # ==================================================================
    def show_text(self, text: str, speaker: str = None) -> None:
        self.text_active = True
        self.speaker = speaker
        self.full_text = text
        self.reveal = 0.0
        self.engine.emit("text_show", text=text, speaker=speaker)

    def clear_text(self) -> None:
        self.text_active = False
        self.speaker = None
        self.full_text = ""

    def text_done(self) -> bool:
        return not self.text_active or self.reveal >= len(self.full_text)

    def finish_text(self) -> None:
        if self.text_active:
            self.reveal = len(self.full_text)

    # ==================================================================
    # 选项
    # ==================================================================
    def show_choices(self, options) -> None:
        """options: [(文本, 跳转标签), ...]"""
        self.choices = list(options)
        self.choice_rects = []
        self.choice_active = True
        self.hover_index = -1
        n = len(self.choices)
        bw, bh = int(self.width * 0.5), 56
        gap = 16
        total = n * bh + (n - 1) * gap
        start_y = (self.height - total) / 2
        bx = (self.width - bw) / 2
        for idx in range(n):
            rect = pygame.Rect(int(bx), int(start_y + idx * (bh + gap)), bw, bh)
            self.choice_rects.append(rect)
        self.engine.emit("choice_show", choices=[t for t, _ in options])

    def hit_choice(self, pos) -> int:
        if not self.choice_active:
            return -1
        for idx, rect in enumerate(self.choice_rects):
            if rect.collidepoint(pos):
                return idx
        return -1

    # ==================================================================
    # 转场 / 震动 / 通知 / 结束
    # ==================================================================
    def start_fadeout(self, duration: float = None) -> None:
        dur = duration or self.FADE_DURATION
        self.fade_target = 255.0
        self.fade_speed = 255.0 / dur

    def start_fadein(self, duration: float = None) -> None:
        dur = duration or self.FADE_DURATION
        self.fade_target = 0.0
        self.fade_speed = 255.0 / dur

    def shake(self, duration: float = 0.3, magnitude: int = 8) -> None:
        self.shake_time = max(self.shake_time, duration)
        self.shake_mag = magnitude

    def show_notice(self, text: str, seconds: float = 1.5) -> None:
        self.notice = text
        self.notice_ttl = seconds

    def show_ending(self) -> None:
        self.ending = True
        self.ending_timer = 0.0
        self.text_active = False
        self.choice_active = False

    # ==================================================================
    # 帧更新
    # ==================================================================
    def update(self, dt: float) -> None:
        # 背景淡入
        if self.bg_fading and self.bg_alpha < 255:
            self.bg_alpha += self.bg_fade_speed * dt
            if self.bg_alpha >= 255:
                self.bg_alpha = 255
                self.bg_fading = False
        # 立绘
        for spr in self.sprites.values():
            spr.update(dt)
        # 打字机
        if self.text_active and self.reveal < len(self.full_text):
            self.reveal += self.TYPE_SPEED * dt
            if self.reveal >= len(self.full_text):
                self.engine.emit("text_complete")
        # 黑幕
        if abs(self.fade_alpha - self.fade_target) > 0.5:
            step = self.fade_speed * dt
            if self.fade_alpha < self.fade_target:
                self.fade_alpha = min(self.fade_target, self.fade_alpha + step)
            else:
                self.fade_alpha = max(self.fade_target, self.fade_alpha - step)
        else:
            self.fade_alpha = self.fade_target
        # 震动
        if self.shake_time > 0:
            self.shake_time -= dt
            self._shake_ox = random.randint(-self.shake_mag, self.shake_mag)
            self._shake_oy = random.randint(-self.shake_mag, self.shake_mag)
            if self.shake_time <= 0:
                self._shake_ox = self._shake_oy = 0
        # 通知
        if self.notice_ttl > 0:
            self.notice_ttl -= dt
            if self.notice_ttl <= 0:
                self.notice = None
        # 结束画面
        if self.ending:
            self.ending_timer += dt
            if self.ending_timer >= 2.6:
                pygame.event.post(pygame.event.Event(pygame.QUIT))
                self.ending = False

    # ==================================================================
    # 绘制
    # ==================================================================
    def draw(self, surface) -> None:
        buf = self.buffer
        buf.fill((0, 0, 0))

        # 背景
        if self.bg_surface is not None:
            if self.bg_alpha < 255:
                tmp = self.bg_surface.copy()
                tmp.set_alpha(int(self.bg_alpha))
                buf.blit(tmp, (0, 0))
            else:
                buf.blit(self.bg_surface, (0, 0))

        # 立绘
        for sid in self.sprite_order:
            spr = self.sprites.get(sid)
            if spr is None or not spr.visible:
                continue
            buf.blit(spr.surface, spr.rect)

        # 全局黑幕
        if self.fade_alpha > 0.5:
            black = pygame.Surface((self.width, self.height))
            black.set_alpha(int(min(255, self.fade_alpha)))
            buf.blit(black, (0, 0))

        if self.choice_active:
            self._draw_choices(buf)
        elif self.text_active:
            self._draw_textbox(buf)

        # 通知
        if self.notice:
            self._draw_notice(buf)

        # 结束画面
        if self.ending:
            buf.fill((0, 0, 0))
            t1 = self._font_end.render("— 谢谢游玩 —", True, (255, 255, 255))
            buf.blit(t1, t1.get_rect(center=(self.width / 2, self.height / 2)))

        # 贴到窗口 (带震动偏移)
        surface.blit(buf, (self._shake_ox, self._shake_oy))

    # ------------------------------------------------------------------
    def _draw_textbox(self, buf) -> None:
        w, h = self.width, self.height
        box_h = int(h * 0.30)
        box_y = h - box_h - 12
        box_w = w - 24
        box_x = 12

        panel = pygame.Surface((box_w, box_h), pygame.SRCALPHA)
        panel.fill((0, 0, 0, 185))
        buf.blit(panel, (box_x, box_y))
        pygame.draw.rect(buf, (255, 255, 255, 60), (box_x, box_y, box_w, box_h), 2)

        text_x = box_x + 24
        text_y = box_y + 24
        avail_w = box_w - 48
        avail_h = box_h - 48

        # 角色名
        name_h = 0
        if self.speaker:
            name_surf = self._font_speaker.render(self.speaker, True, (255, 210, 130))
            name_bg = pygame.Surface((name_surf.get_width() + 24, name_surf.get_height() + 12), pygame.SRCALPHA)
            name_bg.fill((120, 40, 40, 220))
            buf.blit(name_bg, (text_x - 6, text_y - 14))
            buf.blit(name_surf, (text_x, text_y - 8))
            name_h = name_surf.get_height() + 8

        # 打字机正文 (自动换行)
        shown = self.full_text[: int(self.reveal)]
        lines = self._wrap_text(shown, avail_w)
        line_h = self._font_text.get_linesize()
        y = text_y + name_h
        for line in lines[: max(1, avail_h // line_h)]:
            surf = self._font_text.render(line, True, (245, 245, 245))
            buf.blit(surf, (text_x, y))
            y += line_h

        # 推进箭头
        if self.reveal >= len(self.full_text):
            t = pygame.time.get_ticks() / 500
            blink = 1 if int(t) % 2 == 0 else 0.35
            arrow = self._font_text.render("▼", True, (255, 255, 255))
            arrow.set_alpha(int(255 * blink))
            buf.blit(arrow, (box_x + box_w - 34, box_y + box_h - 34))

    def _wrap_text(self, text, max_width) -> list:
        if not text:
            return [""]
        lines = []
        cur = ""
        for ch in text:
            test = cur + ch
            if self._font_text.size(test)[0] > max_width and cur:
                lines.append(cur)
                cur = ch
            else:
                cur = test
        if cur:
            lines.append(cur)
        return lines

    def _draw_choices(self, buf) -> None:
        overlay = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        buf.blit(overlay, (0, 0))
        mouse = pygame.mouse.get_pos()
        self.hover_index = -1
        for idx, (text, label) in enumerate(self.choices):
            rect = self.choice_rects[idx]
            hovered = rect.collidepoint(mouse)
            if hovered:
                self.hover_index = idx
            bg = (70, 70, 85, 230) if hovered else (40, 40, 48, 220)
            panel = pygame.Surface(rect.size, pygame.SRCALPHA)
            panel.fill(bg)
            buf.blit(panel, rect.topleft)
            pygame.draw.rect(buf, (255, 220, 120) if hovered else (150, 150, 160),
                             rect, 2)
            surf = self._font_choice.render(text, True,
                                            (255, 255, 255) if hovered else (220, 220, 225))
            buf.blit(surf, surf.get_rect(center=rect.center))

    def _draw_notice(self, buf) -> None:
        surf = self._font_notice.render(self.notice, True, (255, 255, 255))
        bg = pygame.Surface((surf.get_width() + 40, surf.get_height() + 16), pygame.SRCALPHA)
        bg.fill((20, 20, 20, 210))
        rect = bg.get_rect(center=(self.width / 2, 48))
        buf.blit(bg, rect.topleft)
        buf.blit(surf, surf.get_rect(center=(rect.centerx, rect.centery)))
