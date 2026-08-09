"""渲染层: 背景 / 立绘图层 / 文本窗 / 选项 / 转场 / 震动。

绘制顺序:
    背景 -> 立绘(按创建顺序) -> 全局黑幕(fade) -> 文本窗或选项 -> 通知 -> 结束画面
随后由引擎把 buffer 贴到窗口 (支持全屏震动偏移)。
"""

import math
import os
import random

import pygame

from framework.engine import log, ui


# ======================================================================
# 背景过渡效果 (Transition)
# ======================================================================
class Transition:
    """背景过渡基类。子类实现 draw_bg (背景层) 与可选的 draw_overlay
    (全屏覆盖层, 如 fade 的黑幕)。

    插件可通过 display.register_transition(name, cls) 注册自定义过渡。
    """

    name = "base"
    duration = 1.0

    def __init__(self, old_surface, new_surface, target_size):
        self.old = old_surface
        self.new = new_surface
        self.size = target_size
        self.t = 0.0
        self.done = False

    def update(self, dt: float) -> None:
        self.t += dt / self.duration
        if self.t >= 1.0:
            self.t = 1.0
            self.done = True

    def draw_bg(self, target) -> None:
        target.blit(self.new, (0, 0))

    def draw_overlay(self, target) -> None:
        pass


class FadeTransition(Transition):
    """黑幕淡出 -> 切换 -> 淡入。黑幕只在背景层, 不影响立绘与文本。"""

    name = "fade"
    duration = 1.0

    def __init__(self, old_surface, new_surface, target_size):
        super().__init__(old_surface, new_surface, target_size)
        self.overlay = pygame.Surface(target_size, pygame.SRCALPHA)
        self.overlay.fill((0, 0, 0, 255))

    def draw_bg(self, target):
        if self.t < 0.5:
            if self.old is not None:
                target.blit(self.old, (0, 0))
            a = int(255 * (self.t / 0.5))
        else:
            target.blit(self.new, (0, 0))
            a = int(255 * (1.0 - (self.t - 0.5) / 0.5))
        if a > 0:
            ov = self.overlay.copy()
            ov.set_alpha(min(255, a))
            target.blit(ov, (0, 0))


class DissolveTransition(Transition):
    """交叉溶解: 新背景透明度从 0 叠加到旧背景上。"""

    name = "dissolve"
    duration = 0.8

    def draw_bg(self, target):
        if self.old is not None:
            target.blit(self.old, (0, 0))
        new = self.new.copy()
        new.set_alpha(int(255 * min(1.0, self.t)))
        target.blit(new, (0, 0))


class BlindsTransition(Transition):
    """垂直百叶窗: 条带逐条显现。"""

    name = "blinds"
    duration = 0.7
    strips = 12

    def draw_bg(self, target):
        if self.old is not None:
            target.blit(self.old, (0, 0))
        w, h = self.new.get_size()
        strip_w = w / self.strips
        for i in range(self.strips):
            x0 = int(i * strip_w)
            x1 = int((i + 1) * strip_w)
            progress = self.t * self.strips - i
            a = int(255 * progress * 2)
            if a <= 0:
                continue
            sub = self.new.subsurface((x0, 0, max(1, x1 - x0), h)).copy()
            sub.set_alpha(min(255, a))
            target.blit(sub, (x0, 0))


class SlideTransition(Transition):
    """新背景从右侧滑入。"""

    name = "slide"
    duration = 0.6

    def draw_bg(self, target):
        if self.old is not None:
            target.blit(self.old, (0, 0))
        w, h = self.new.get_size()
        target.blit(self.new, (int(w * (1.0 - self.t)), 0))


class CircleTransition(Transition):
    """圆形从中心展开。"""

    name = "circle"
    duration = 0.7

    def draw_bg(self, target):
        if self.old is not None:
            target.blit(self.old, (0, 0))
        w, h = self.new.get_size()
        radius = int(max(w, h) * 0.75 * self.t)
        if radius <= 0:
            return
        mask = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.circle(mask, (255, 255, 255, 255),
                           (w // 2, h // 2), radius)
        # 先复制到带 alpha 的画布, 再按 mask 取 alpha (圆外透明)
        new = pygame.Surface((w, h), pygame.SRCALPHA)
        new.blit(self.new, (0, 0))
        new.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
        target.blit(new, (0, 0))


class PixelateTransition(Transition):
    """马赛克: 新背景从大像素块逐渐变清晰, 同时溶解显现。"""

    name = "pixelate"
    duration = 0.8

    def draw_bg(self, target):
        if self.old is not None:
            target.blit(self.old, (0, 0))
        w, h = self.new.get_size()
        block = max(2, int(24 * (1.0 - self.t)) + 1)
        small = pygame.transform.smoothscale(
            self.new, (max(1, w // block), max(1, h // block)))
        big = pygame.transform.scale(small, (w, h))
        big.set_alpha(int(255 * min(1.0, self.t)))
        target.blit(big, (0, 0))


class ZoomTransition(Transition):
    """缩放淡入: 新背景从 60% 放大到全屏。"""

    name = "zoom"
    duration = 0.8

    def draw_bg(self, target):
        if self.old is not None:
            target.blit(self.old, (0, 0))
        w, h = self.new.get_size()
        scale = 0.6 + 0.4 * self.t
        sw, sh = max(1, int(w * scale)), max(1, int(h * scale))
        scaled = pygame.transform.smoothscale(self.new, (sw, sh))
        scaled.set_alpha(int(255 * min(1.0, self.t * 1.5)))
        target.blit(scaled, ((w - sw) // 2, (h - sh) // 2))


# 内置过渡注册表 (插件可向 display.transitions 追加)
BUILTIN_TRANSITIONS = {
    "fade": FadeTransition,
    "dissolve": DissolveTransition,
    "blinds": BlindsTransition,
    "slide": SlideTransition,
    "circle": CircleTransition,
    "pixelate": PixelateTransition,
    "zoom": ZoomTransition,
}


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
        self._rich = engine.rich

        # 背景
        self.bg_surface = None
        self.bg_path = None
        self.bg_id = None          # 脚本对象 id (weight 创建), None 表示直接 bg 指令
        self.bg_scene = None       # 场景 id (scene 绑定背景), 否则 None
        self.bg_pose = None        # 场景内背景名 (None 表示默认背景)
        self.bg_alpha = 255
        self.bg_fading = False
        self.bg_fade_speed = 0.0
        self._transition = None       # 当前背景过渡 (Transition 实例)
        self.transitions = dict(BUILTIN_TRANSITIONS)  # 过渡注册表

        # 立绘
        self.sprites = {}
        self.sprite_order = []

        # 文本
        self.text_active = False
        self.speaker = None
        self.full_text = ""
        self._runs = []
        self.reveal = 0.0
        self._font_size = 26

        # 选项
        self.choice_active = False
        self.choices = []          # [(text, label)]
        self._choice_runs = []
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
        self.notice_pos = "top"       # top / top-left / top-right

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
    def register_transition(self, name: str, transition_cls) -> None:
        """注册自定义背景过渡效果 (供插件使用)。

        transition_cls 须为 Transition 子类 (实现 draw_bg, 可选 draw_overlay)。
        """
        self.transitions[name] = transition_cls
        log.info(f"过渡效果已注册: {name}")

    def set_bg(self, path: str, effect: str = None) -> None:
        """设置背景。

        effect: None/"none" 直接切换; 否则按注册表找过渡效果
                ("fade" / "dissolve" / "blinds" / 插件自定义)。
        """
        img = self.load_image(path)
        if img is None:
            return
        new_surface = self._fit(img, mode="full")
        self.bg_path = path
        cls = self.transitions.get(effect) if effect else None
        if cls is None:
            # 直接切换 (含 effect="none")
            self.bg_surface = new_surface
            self.bg_alpha = 255
            self.bg_fading = False
            self._transition = None
        else:
            self._transition = cls(self.bg_surface, new_surface,
                                   (self.width, self.height))
        self.engine.emit("bg_change", path=path, effect=effect)

    def clear_bg(self) -> None:
        self.bg_surface = None
        self.bg_path = None
        self.bg_id = None
        self.bg_scene = None
        self.bg_pose = None
        self.bg_alpha = 255
        self.bg_fading = False

    # ==================================================================
    # 立绘
    # ==================================================================
    def show_sprite(self, sid: str, path: str = None, pos=None,
                    scale=None, mode=None, effect: str = None) -> bool:
        """显示/创建立绘。

        path 为空且对象已存在时仅更新位置/特效;
        同 id 换图 (角色表情切换) 时保持原中心点, 图片原位替换。
        """
        old = self.sprites.get(sid)
        if old is not None and path is None:
            if pos is not None:
                w, h = old.surface.get_size()
                x, y = self._pos_to_xy(pos, w, h)
                old.rect = pygame.Rect(int(x), int(y), w, h)
                old.props["pos"] = pos
            if effect == "fade":
                old.alpha = 0
                old.target_alpha = 255
                old.fade_speed = 255.0 / self.FADE_DURATION
            old.visible = True
            self.engine.emit("sprite_show", id=sid, path=old.props.get("image"))
            return True
        if path is None:
            log.warning(f"立绘 {sid} 不存在且未提供 image")
            return False

        img = self.load_image(path)
        if img is None:
            return False
        img = self._fit(img, mode=mode, scale=scale)
        w, h = img.get_size()
        if old is not None and pos is None and scale is None and mode is None:
            # 同 id 换图 (表情切换): 保持原中心点
            x, y = old.rect.centerx - w // 2, old.rect.centery - h // 2
        else:
            x, y = self._pos_to_xy(pos, w, h)
        spr = _Sprite(sid, img, pygame.Rect(int(x), int(y), w, h),
                      props={"image": path, "pos": pos, "scale": scale,
                             "mode": mode, "pose": None})
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
        """导出立绘状态供存档: 只存脚本 id / 运行时位置 / 透明度 / 立绘名,
        不存图片路径 (路径以脚本中的对象定义为准)。"""
        out = []
        for sid in self.sprite_order:
            spr = self.sprites[sid]
            if spr.visible:
                out.append({"id": sid,
                            "pos": spr.props.get("pos"),
                            "alpha": spr.alpha,
                            "pose": spr.props.get("pose")})
        return out

    def restore_sprites(self, state: list) -> None:
        """从存档恢复立绘。存档只含 id/pose, 图片等属性从脚本对象注册表
        (runtime.script_objects) 与角色表 (runtime.characters) 取回;
        兼容旧格式 (直接存 image 路径)。"""
        # 彻底重置立绘层, 保证 sprite_order 与 sprites 一致
        self.sprites.clear()
        self.sprite_order.clear()
        objects = self.engine.runtime.script_objects
        characters = self.engine.runtime.characters
        for item in state:
            sid = item.get("id")
            obj = objects.get(sid) if sid else None
            pose = item.get("pose")
            img = pos = None
            scale = mode = None
            if characters.get(sid) and pose:
                # 角色立绘: 按立绘名恢复精确立绘
                char = characters[sid]
                img = char["sprites"].get(pose) or char.get("default")
                pos = item.get("pos") or char.get("pos")
                scale, mode = char.get("scale"), char.get("mode")
            elif obj is not None:
                img = obj.get("image")
                pos = item.get("pos") or obj.get("pos")
                scale, mode = obj.get("scale"), obj.get("mode")
            elif item.get("image"):
                # 旧存档兼容: 直接使用保存的路径
                img, pos = item["image"], item.get("pos")
            else:
                log.warning(f"读档: 立绘 {sid!r} 不在脚本对象注册表中")
                continue
            self.show_sprite(sid, img, pos, scale, mode)
            spr = self.sprites.get(sid)
            if spr is None:
                continue
            if pose:
                spr.props["pose"] = pose
            spr.alpha = int(item.get("alpha", 255))
            spr.surface.set_alpha(spr.alpha)
            if spr.alpha < 255:
                # 存档时若淡入未完成, 读档后继续淡入 (否则立绘会永久隐形)
                spr.target_alpha = 255
                spr.fade_speed = 255.0 / self.FADE_DURATION
            else:
                spr.fade_speed = 0.0

    def restore_state(self, data: dict) -> None:
        """从存档恢复视觉状态: 背景 / 立绘 / 正在显示的文本或选择支。"""
        bg_id = data.get("bg_id")
        bg_scene = data.get("bg_scene")
        if bg_id:
            obj = self.engine.runtime.script_objects.get(bg_id)
            if obj and obj.get("image"):
                self.set_bg(obj["image"])
                self.bg_id = bg_id
        elif bg_scene:
            scenes = self.engine.runtime.scenes
            scene = scenes.get(bg_scene)
            pose = data.get("bg_pose")
            img = None
            if scene:
                if pose and pose in scene["backgrounds"]:
                    img = scene["backgrounds"][pose]
                else:
                    img = scene.get("default")
            if img:
                self.set_bg(img)
                self.bg_scene = bg_scene
                self.bg_pose = pose if (pose and scene and
                                        pose in scene["backgrounds"]) else None
        elif data.get("bg"):
            self.set_bg(data["bg"])
        else:
            self.clear_bg()
        self.restore_sprites(data.get("sprites", []))
        self.clear_text()
        self.choice_active = False
        if data.get("blocked") == "text":
            self.show_text(data.get("text", ""), data.get("speaker"))
            self.reveal = len(self.full_text)   # 读档后文本完整显示
        elif data.get("blocked") == "choice":
            self.show_choices(data.get("choices", []) or [])

    # ==================================================================
    # 文本
    # ==================================================================
    def show_text(self, text: str, speaker: str = None) -> None:
        self.text_active = True
        self.speaker = speaker
        self.full_text = text
        self._runs = self._rich.parse(text, base_size=self._font_size)
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
        self._choice_runs = [self._rich.parse(t, base_size=28) for t, _ in options]
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

    def show_notice(self, text: str, seconds: float = 1.5,
                    pos: str = "top") -> None:
        """在屏幕顶部显示一条通知。

        pos: "top" (顶部居中) / "top-left" / "top-right"
        """
        self.notice = text
        self.notice_ttl = seconds
        self.notice_pos = pos

    def show_ending(self) -> None:
        self.ending = True
        self.ending_timer = 0.0
        self.text_active = False
        self.choice_active = False

    # ==================================================================
    # 帧更新
    # ==================================================================
    def update(self, dt: float) -> None:
        # 背景过渡
        if self._transition is not None:
            self._transition.update(dt)
            if self._transition.done:
                self.bg_surface = self._transition.new
                self.bg_alpha = 255
                self._transition = None
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
        if self._transition is not None:
            self._transition.draw_bg(buf)
        elif self.bg_surface is not None:
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

        # 过渡的全屏覆盖层 (fade 黑幕盖住全部内容)
        if self._transition is not None:
            self._transition.draw_overlay(buf)

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

        ui.panel(buf, (box_x, box_y, box_w, box_h),
                 bg_color=(0, 0, 0, 185), border_color=(255, 255, 255, 60),
                 border_width=2)

        text_x = box_x + 24
        text_y = box_y + 24
        avail_w = box_w - 48
        avail_h = box_h - 48

        # 角色名
        name_h = 0
        if self.speaker:
            name_surf = self._font_speaker.render(self.speaker, True, (255, 210, 130))
            ui.panel(buf, (text_x - 6, text_y - 14,
                           name_surf.get_width() + 24, name_surf.get_height() + 12),
                     bg_color=(120, 40, 40, 220))
            buf.blit(name_surf, (text_x, text_y - 8))
            name_h = name_surf.get_height() + 8

        # 打字机正文 (富文本, 自动换行; reveal 按可见字符截断)
        shown = self._rich.truncate(self._runs, int(self.reveal))
        line_h = self._font_text.get_linesize()
        self._rich.draw(buf, shown, text_x, text_y + name_h, avail_w,
                        line_height=line_h,
                        max_lines=max(1, avail_h // line_h))

        # 推进箭头
        if self.reveal >= len(self.full_text):
            t = pygame.time.get_ticks() / 500
            blink = 1 if int(t) % 2 == 0 else 0.35
            ui.text(buf, self._font_text, "▼", color=(255, 255, 255),
                    pos=(box_x + box_w - 34, box_y + box_h - 34),
                    alpha=255 * blink)

    def _draw_choices(self, buf) -> None:
        ui.dim_overlay(buf, 150)
        mouse = pygame.mouse.get_pos()
        self.hover_index = -1
        for idx, (text, label) in enumerate(self.choices):
            rect = self.choice_rects[idx]
            hovered = rect.collidepoint(mouse)
            if hovered:
                self.hover_index = idx
            ui.panel(buf, rect,
                     bg_color=(70, 70, 85, 230) if hovered else (40, 40, 48, 220),
                     border_color=(255, 220, 120) if hovered else (150, 150, 160),
                     border_width=2)
            runs = self._choice_runs[idx]
            self._rich.draw_centered(buf, runs, rect.centerx, rect.centery,
                                     alpha=255 if hovered else 210)

    def _draw_notice(self, buf) -> None:
        surf = self._font_notice.render(self.notice, True, (255, 255, 255))
        rect = pygame.Rect(0, 0, surf.get_width() + 40, surf.get_height() + 16)
        if self.notice_pos == "top-left":
            rect.topleft = (12, 12)
        elif self.notice_pos == "top-right":
            rect.topright = (self.width - 12, 12)
        else:
            rect.center = (self.width / 2, 48)
        ui.panel(buf, rect, bg_color=(20, 20, 20, 210))
        ui.text(buf, self._font_notice, self.notice, center=rect.center)
