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


# 缓动函数 (动画插值)
_EASE_FUNCS = {
    "linear": lambda t: t,
    "in": lambda t: t * t,
    "out": lambda t: 1 - (1 - t) ** 3,
    "in_out": lambda t: t * t * (3 - 2 * t),
}


class _Sprite:
    """立绘精灵。

    位置真相源是 center (浮点, 动画平滑); 旋转/翻转作用于 base_surface,
    渲染面 surface 由 _recalc 生成, rect 始终以 center 为锚点。
    """

    __slots__ = ("id", "base_surface", "surface", "center", "angle",
                 "flip_h", "flip_v", "alpha", "target_alpha", "fade_speed",
                 "visible", "props", "rect", "anim_move", "anim_rotate")

    def __init__(self, sid, base_surface, center, props=None):
        self.id = sid
        self.base_surface = base_surface
        self.surface = base_surface
        self.center = [float(center[0]), float(center[1])]
        self.angle = 0.0
        self.flip_h = False
        self.flip_v = False
        self.alpha = 255
        self.target_alpha = 255
        self.fade_speed = 0.0
        self.visible = False
        self.props = props or {}
        self.rect = pygame.Rect(0, 0, 0, 0)
        self.anim_move = None    # [kind, t, duration, start, target, ease]
        self.anim_rotate = None  # 同上 (move 与 rotate 并行, 同类互相覆盖)
        self._recalc()

    def _recalc(self):
        """重新生成渲染面 (旋转/翻转), 并按中心点重算 rect。"""
        surf = self.base_surface
        if self.angle:
            surf = pygame.transform.rotate(surf, self.angle)
        if self.flip_h or self.flip_v:
            surf = pygame.transform.flip(surf, self.flip_h, self.flip_v)
        self.surface = surf
        self.surface.set_alpha(int(self.alpha))
        self.rect = surf.get_rect(center=(int(round(self.center[0])),
                                          int(round(self.center[1]))))

    def update(self, dt):
        # 淡入
        if self.fade_speed > 0 and self.alpha < self.target_alpha:
            self.alpha += self.fade_speed * dt
            if self.alpha >= self.target_alpha:
                self.alpha = self.target_alpha
                self.fade_speed = 0.0
            self.surface.set_alpha(int(self.alpha))
        # 移动动画
        if self.anim_move is not None:
            kind, t, duration, start, target, ease = self.anim_move
            self.anim_move[1] = t + dt
            k = min(1.0, self.anim_move[1] / duration) if duration > 0 else 1.0
            e = _EASE_FUNCS.get(ease, _EASE_FUNCS["linear"])(k)
            self.center[0] = start[0] + (target[0] - start[0]) * e
            self.center[1] = start[1] + (target[1] - start[1]) * e
            self.rect.center = (int(round(self.center[0])),
                                int(round(self.center[1])))
            if k >= 1.0:
                self.anim_move = None
        # 旋转动画
        if self.anim_rotate is not None:
            kind, t, duration, start, target, ease = self.anim_rotate
            self.anim_rotate[1] = t + dt
            k = min(1.0, self.anim_rotate[1] / duration) if duration > 0 else 1.0
            e = _EASE_FUNCS.get(ease, _EASE_FUNCS["linear"])(k)
            self.angle = start + (target - start) * e
            self._recalc()
            if k >= 1.0:
                self.anim_rotate = None


# 默认界面样式 (style 块未指定时的兜底)
DEFAULT_STYLE = {
    "textbox_bg": (0, 0, 0),
    "textbox_alpha": 185,
    "textbox_border": (255, 255, 255, 60),
    "textbox_border_width": 2,
    "textbox_radius": 0,
    "text_color": (245, 245, 245),
    "text_size": 26,
    "speaker_color": (255, 210, 130),
    "speaker_bg": (120, 40, 40, 220),
    "arrow_color": (255, 255, 255),
    "textbox_image": None,       # 文本框背景图 (9-slice), 优先于纯色
    "speaker_image": None,       # 角色名框背景图
    "choice_bg": (40, 40, 48, 220),
    "choice_bg_hover": (70, 70, 85, 230),
    "choice_border": (150, 150, 160),
    "choice_border_hover": (255, 220, 120),
    "choice_image": None,        # 选择支按钮背景图
    "choice_image_hover": None,
    "choice_text_size": 28,
    "choice_text_color": (230, 230, 235),
    "choice_text_color_hover": (255, 255, 255),
    "choice_width_ratio": 0.34,   # 选择支按钮宽度占窗口比例
    "choice_fit_image": True,     # 按钮高度按素材图比例 (避免拉伸变形)
    "choice_height": 56,          # 无图/禁用适配时的按钮高度
}

# 通用选择列表 (selection) 的默认外观
DEFAULT_SELECTION_STYLE = {
    "width_ratio": 0.36,        # 按钮宽度占窗口比例
    "height": 56,               # 按钮高度
    "gap": 14,                  # 按钮间距
    "anchor_x": "center",       # 按钮区水平锚点 (center/left/right/数字)
    "anchor_y": "center",       # 垂直: center=整体居中 / 数字(第一个按钮顶部)
    "button_bg": (35, 35, 50, 220),
    "button_bg_hover": (60, 60, 90, 230),
    "button_border": (150, 150, 170),
    "button_border_hover": (255, 220, 120),
    "button_radius": 6,
    "text_size": 28,
    "caption_x": "center",      # 标题水平锚点
    "caption_y": 0.30,          # 标题垂直中心 (比例)
    "caption_size": 56,
    "dim_alpha": 120,
    "unhover_alpha": 215,       # 未悬停按钮文字透明度
    "button_image": None,       # 按钮背景图 (9-slice), 优先于纯色
    "button_image_hover": None, # 悬停按钮背景图
    "button_stretch": True,     # 按钮图是否拉伸 (False=原尺寸居中)
    "button_text": True,        # 是否渲染按钮文字 (图片自带文字时可关)
    "text_color": (245, 245, 245),      # 按钮文字色
    "text_color_hover": (255, 255, 255),
    "dialog_image": None,       # 对话框/槽位面板背景图
    "dialog_text_color": (245, 245, 245),  # 确认框文字色 (亮色主题用深色)
}


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

        # 标题画面
        self.title_active = False
        self.title_caption = ""
        self.title_image = None    # 标题图片 surface (可选)
        self.title_items = []      # [(label, action)], action: {"jump"|"load"|"quit"}
        self.title_rects = []
        self.title_anchor = (0, 0)  # 标题 (文字/图片) 中心点

        # 通用选择列表 (selection): 标题/系统菜单等按钮列表的统一实现
        self.selection_active = False
        self.selection_items = []     # [(text, action_dict)]
        self.selection_rects = []
        self.selection_caption = ""
        self.selection_image = None
        self.selection_anchor = (0, 0)
        self.selection_style = {}
        self.selection_style_overrides = {}   # 脚本 selection_style 语句的全局覆盖
        self._ui_cache = {}                   # UI 图片缓存 (path -> surface)
        self.theme_images = {}                # UI 主题素材: 组件 -> {default/focus: surface}

        # 确认对话框 (退出确认等)
        self.confirm_active = False
        self.confirm_text = ""
        self.confirm_yes = "是"
        self.confirm_no = "否"
        self.confirm_panel = pygame.Rect(0, 0, 0, 0)
        self.confirm_rects = []    # [是, 否]

        # 系统菜单 (ESC 打开)
        self.system_menu_active = False
        self.system_menu_items = []   # [(text, action)]
        self.system_menu_rects = []

        # 存档槽位选择界面 (save/load)
        self.slot_menu_active = False
        self.slot_menu_mode = "load"  # "save" / "load"
        self.slot_menu_slots = []     # [{slot, time, label, preview, empty}]
        self.slot_menu_rects = []
        self.slot_menu_back_rect = pygame.Rect(0, 0, 0, 0)

        # 错误弹窗 (运行时错误温和提示)
        self.error_active = False
        self.error_info = None        # ErrorHandler 快照
        self.error_panel = pygame.Rect(0, 0, 0, 0)
        self.error_rects = []         # [继续游戏, 复制错误, 退出游戏]

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

        # 当前界面样式 (由 use style 指令切换)
        self.style = dict(DEFAULT_STYLE)

    # ==================================================================
    # 样式
    # ==================================================================
    def apply_style(self, style_dict: dict) -> None:
        """应用样式 (只覆盖提供的键, 其余保持默认/当前值)。"""
        for key, value in style_dict.items():
            if key in DEFAULT_STYLE:
                self.style[key] = value
        # 正文字号变化时重建字体引用
        self._font_size = self.style["text_size"]
        self._font_text = self.engine.get_font(self._font_size)

    def reset_style(self) -> None:
        """恢复默认样式。"""
        self.style = dict(DEFAULT_STYLE)
        self._font_size = self.style["text_size"]
        self._font_text = self.engine.get_font(self._font_size)

    # ==================================================================
    # UI 图片 (9-slice) 加载
    # ==================================================================
    def _ui_image(self, path):
        """加载 UI 背景图 (带缓存), 路径相对脚本目录。"""
        if not path:
            return None
        if path in self._ui_cache:
            return self._ui_cache[path]
        real = self.engine.resolve_path(path)
        try:
            img = pygame.image.load(real).convert_alpha()
            self._ui_cache[path] = img
            return img
        except Exception as exc:
            log.warning(f"UI 图片加载失败 {path}: {exc}")
            self._ui_cache[path] = None
            return None

    def _panel_or_image(self, buf, rect, image, bg_color,
                        border_color=None, border_width=0, radius=0):
        """面板绘制: 有图片用 9-slice, 否则纯色面板。"""
        rect = pygame.Rect(rect)
        if image is not None:
            buf.blit(ui.nine_slice(image, rect), rect.topleft)
            return rect
        ui.panel(buf, rect, bg_color=bg_color, border_color=border_color,
                 border_width=border_width, radius=radius)
        return rect

    # ==================================================================
    # UI 主题素材 (素材切片)
    # ==================================================================
    def set_theme_image(self, comp: str, paths) -> None:
        """设置主题组件图。

        paths: {"default": 路径, "focus": 路径} 单组;
               或 [{...}, {...}] 列表 (按按钮索引取图)。
        """
        if isinstance(paths, list):
            items = []
            for group in paths:
                imgs = {}
                for state, p in group.items():
                    img = self._ui_image(p)
                    if img is not None:
                        imgs[state] = img
                if imgs:
                    items.append(imgs)
            if items:
                self.theme_images[comp] = items
            return
        imgs = {}
        for state, p in paths.items():
            img = self._ui_image(p)
            if img is not None:
                imgs[state] = img
        if imgs:
            self.theme_images[comp] = imgs

    def _theme(self, comp: str, state: str = "default", index: int = None):
        """取主题组件图 (无则 None)。

        comp 配置为列表时按 index 取对应按钮的图组 (不同按键不同图)。
        """
        d = self.theme_images.get(comp)
        if isinstance(d, list):
            if index is None or not d:
                return None
            item = d[min(index, len(d) - 1)] or {}
            return item.get(state) or item.get("default")
        d = d or {}
        img = d.get(state)
        if img is None and state != "default":
            img = d.get("default")
        return img

    def _style_image_or_theme(self, style_key: str, theme_comp: str):
        """组件背景图取值: style 键 (none=禁用 / 路径=该图) > 主题图 > None。

        用于文本框/名字框等 (style 的 textbox_image 等键)。
        """
        opt = self.style.get(style_key)
        if opt == "none":
            return None
        if opt:
            return self._ui_image(opt)
        return self._theme(theme_comp)

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
        """根据 mode/scale 把图片缩放到合适的尺寸。

        mode: fit 等比适配 / full,stretch 拉伸铺满 / center 原尺寸 / 其它原图
        scale: 数字倍率 (优先于 mode)
        """
        w, h = img.get_size()
        if scale is not None:
            try:
                s = float(scale)
                return pygame.transform.smoothscale(img, (int(w * s), int(h * s)))
            except (TypeError, ValueError):
                pass
        mode = (mode or "fit").lower()
        if mode == "full" or mode == "stretch":
            return pygame.transform.smoothscale(img, (self.width, self.height))
        if mode == "center":
            return img
        if mode == "cover":
            # 等比缩放铺满并居中裁剪 (不留边, 不变形)
            ratio = max(self.width / w, self.height / h)
            sw, sh = max(1, int(w * ratio)), max(1, int(h * ratio))
            scaled = pygame.transform.smoothscale(img, (sw, sh))
            x = (sw - self.width) // 2
            y = (sh - self.height) // 2
            return scaled.subsurface((x, y, self.width, self.height)).copy()
        if mode == "fit":
            ratio = min(self.width / w, self.height / h)
            return pygame.transform.smoothscale(img, (max(1, int(w * ratio)), max(1, int(h * ratio))))
        return img

    def _pos_to_xy(self, pos, img_w, img_h):
        """把 pos 参数解析成图片左上角坐标。"""
        w, h = self.width, self.height
        cy = h * 0.55          # 立绘默认中心偏下 (视觉居中)
        if isinstance(pos, (list, tuple)) and len(pos) == 2:
            try:
                return float(pos[0]) - img_w / 2, float(pos[1]) - img_h / 2
            except (TypeError, ValueError):
                pass
        pos = str(pos or "center").lower()
        if pos == "left":
            return w * 0.25 - img_w / 2, cy - img_h / 2
        if pos == "right":
            return w * 0.75 - img_w / 2, cy - img_h / 2
        if pos == "top":
            return w / 2 - img_w / 2, h * 0.25 - img_h / 2
        if pos == "bottom":
            return w / 2 - img_w / 2, h * 0.85 - img_h / 2
        return w / 2 - img_w / 2, cy - img_h / 2

    def _resolve_center(self, spr, pos):
        """把 pos 参数解析成立绘中心点坐标 (窗口坐标, 数字坐标为直接值)。"""
        w, h = self.width, self.height
        cy = h * 0.55          # 立绘默认中心偏下
        if isinstance(pos, (list, tuple)) and len(pos) == 2:
            try:
                return float(pos[0]), float(pos[1])
            except (TypeError, ValueError):
                pass
        p = str(pos or "center").lower()
        if p == "left":
            return w * 0.25, cy
        if p == "right":
            return w * 0.75, cy
        if p == "top":
            return w / 2, h * 0.25
        if p == "bottom":
            return w / 2, h * 0.85
        return w / 2, cy

    # ==================================================================
    # 背景
    # ==================================================================
    def register_transition(self, name: str, transition_cls) -> None:
        """注册自定义背景过渡效果 (供插件使用)。

        transition_cls 须为 Transition 子类 (实现 draw_bg, 可选 draw_overlay)。
        """
        self.transitions[name] = transition_cls
        log.info(f"过渡效果已注册: {name}")

    def set_bg(self, path: str, effect: str = None, mode: str = None) -> None:
        """设置背景。

        effect: None/"none" 直接切换; 否则按注册表找过渡效果
        mode: 适配模式 fit/full/center/stretch/数字倍率 (None=full)
        """
        img = self.load_image(path)
        if img is None:
            return
        new_surface = self._fit(img, mode=mode or "cover")
        self.bg_path = path
        self.bg_mode = mode
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
                cx, cy = self._resolve_center(old, pos)
                old.center = [cx, cy]
                old.rect.center = (int(round(cx)), int(round(cy)))
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
            # 同 id 换图 (角色表情切换): 保持原中心点
            cx, cy = old.center
        else:
            x, y = self._pos_to_xy(pos, w, h)
            cx, cy = x + w / 2.0, y + h / 2.0
        spr = _Sprite(sid, img, (cx, cy),
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

    # ==================================================================
    # 立绘变换: 位移 / 旋转 / 翻转
    # ==================================================================
    def move_sprite(self, sid: str, pos, duration: float = 0.0,
                    ease: str = "linear") -> bool:
        """移动立绘到目标位置。duration>0 时为缓动动画。"""
        spr = self.sprites.get(sid)
        if spr is None:
            log.warning(f"move: 立绘 {sid} 不存在")
            return False
        target = self._resolve_center(spr, pos)
        if duration and duration > 0:
            spr.anim_move = ["move", 0.0, float(duration),
                             (spr.center[0], spr.center[1]), target, ease]
        else:
            spr.center = [target[0], target[1]]
            spr.rect.center = (int(round(target[0])), int(round(target[1])))
        spr.props["pos"] = pos
        self.engine.emit("sprite_move", id=sid, pos=target, duration=duration)
        return True

    def rotate_sprite(self, sid: str, angle: float,
                      duration: float = 0.0, ease: str = "linear") -> bool:
        """旋转立绘到指定角度 (pygame 惯例, 逆时针为正)。"""
        spr = self.sprites.get(sid)
        if spr is None:
            log.warning(f"rotate: 立绘 {sid} 不存在")
            return False
        angle = float(angle) % 360
        if duration and duration > 0:
            spr.anim_rotate = ["rotate", 0.0, float(duration), spr.angle,
                               angle, ease]
        else:
            spr.angle = angle
            spr._recalc()
        self.engine.emit("sprite_rotate", id=sid, angle=angle,
                         duration=duration)
        return True

    def flip_sprite(self, sid: str, horizontal: bool = True,
                    vertical: bool = False) -> bool:
        """翻转立绘 (默认水平; 再次调用可恢复)。"""
        spr = self.sprites.get(sid)
        if spr is None:
            log.warning(f"flip: 立绘 {sid} 不存在")
            return False
        if horizontal:
            spr.flip_h = not spr.flip_h
        if vertical:
            spr.flip_v = not spr.flip_v
        spr._recalc()
        self.engine.emit("sprite_flip", id=sid, horizontal=horizontal,
                         vertical=vertical)
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
        """导出立绘状态供存档: 只存脚本 id / 位置 / 透明度 / 立绘名 /
        旋转 / 翻转 / 中心点, 不存图片路径 (路径以脚本中的对象定义为准)。"""
        out = []
        for sid in self.sprite_order:
            spr = self.sprites[sid]
            if spr.visible:
                out.append({
                    "id": sid,
                    "pos": spr.props.get("pos"),
                    "alpha": spr.alpha,
                    "pose": spr.props.get("pose"),
                    "angle": spr.angle,
                    "flip_h": spr.flip_h,
                    "flip_v": spr.flip_v,
                    "cx": spr.center[0],
                    "cy": spr.center[1],
                })
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
            # 恢复变换状态: 旋转 / 翻转 / 中心点
            if "angle" in item or "flip_h" in item or "flip_v" in item:
                spr.angle = float(item.get("angle", 0.0))
                spr.flip_h = bool(item.get("flip_h", False))
                spr.flip_v = bool(item.get("flip_v", False))
            if "cx" in item:
                spr.center = [float(item["cx"]), float(item["cy"])]
            spr._recalc()

    def clear_fade(self) -> None:
        """清除黑幕与未完成的背景过渡 (回标题/读档时调用)。"""
        self.fade_alpha = 0.0
        self.fade_target = 0.0
        self._transition = None
        self.ending = False
        self.ending_timer = 0.0

    def restore_state(self, data: dict) -> None:
        """从存档恢复视觉状态: 背景 / 立绘 / 正在显示的文本或选择支。"""
        self.clear_fade()   # 读档后不应残留黑幕/结束画面
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
        st = self.style
        self._runs = self._rich.parse(text, base_size=st["text_size"],
                                      base_color=st["text_color"])
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
        st = self.style
        self._choice_runs = [
            self._rich.parse(t, base_size=st["choice_text_size"],
                             base_color=st["choice_text_color"])
            for t, _ in options
        ]
        self.choice_active = True
        self.hover_index = -1
        n = len(self.choices)
        st = self.style
        bw = int(self.width * st.get("choice_width_ratio", 0.34))
        # 按钮高度: 有素材图时按图片比例 (不拉伸变形)
        img = None
        opt = st["choice_image_hover"] or st["choice_image"]
        if opt and opt != "none":
            img = self._ui_image(opt)
        elif not opt:
            img = self._theme("choice_button")
        if img is not None and st.get("choice_fit_image", True):
            bh = max(40, int(bw * img.get_height() / img.get_width()))
        else:
            bh = st.get("choice_height", 56)
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
    # 标题画面
    # ==================================================================
    def _resolve_title_x(self, token):
        """解析标题/按钮的水平锚点: center/left/right/数字(像素)。"""
        s = str(token or "center").strip().lower()
        if s == "left":
            return self.width * 0.25
        if s == "right":
            return self.width * 0.75
        try:
            return float(s)
        except ValueError:
            return self.width / 2

    def _resolve_title_y(self, token, default_ratio=0.30):
        """解析标题/按钮的垂直锚点: 数字(像素), 否则按比例。"""
        try:
            return float(token)
        except (TypeError, ValueError):
            return self.height * default_ratio

    def apply_selection_style(self, style_dict: dict) -> None:
        """设置 selection 全局样式覆盖 (供 selection_style 脚本语句/插件)。"""
        self.selection_style_overrides.update(style_dict)

    def show_title(self, caption, items, image=None, pos=None):
        """显示标题画面 (selection 的标题专用实例)。

        items: [(text, action, cfg), ...] 或 [(text, action), ...]
        pos:   {"title_x", "title_y", "button_x", "button_y",
                "button_stretch", "button_text"}
        """
        pos = pos or {}
        self.title_active = True
        self.title_caption = caption
        self.title_items = list(items)
        style = {
            "caption_x": pos.get("title_x", "center"),
            "caption_y": pos.get("title_y"),
            "anchor_x": pos.get("button_x", "center"),
            "anchor_y": pos.get("button_y"),
        }
        for bool_key in ("button_stretch", "button_text"):
            if bool_key in pos:
                style[bool_key] = str(pos[bool_key]).lower() in (
                    "true", "1", "yes", "on")
        self.show_selection(items, caption, image, style)
        self.title_anchor = self.selection_anchor
        self.title_image = self.selection_image
        self.engine.emit("title_show", caption=caption,
                         items=[t for t, *_ in items])

    def hit_title(self, pos) -> int:
        return self.hit_selection(pos) if self.title_active else -1

    def show_selection(self, items, caption: str = "", image: str = None,
                       style: dict = None) -> None:
        """通用选择列表: 一组按钮 + 可选标题 (文字/图片)。

        items 元素: (text, action_dict) 或 (text, action_dict, cfg)。
        cfg: 每按键独立配置 {width, height, image, image_focus,
             stretch, text_visible, ...} (覆盖全局 style)。
        """
        st = dict(DEFAULT_SELECTION_STYLE)
        st.update(self.selection_style_overrides)   # 脚本全局覆盖
        st.update(style or {})
        self.selection_style = st
        # 规范化 items: [(text, action, cfg)]
        norm = []
        for item in items:
            if len(item) >= 3:
                norm.append((item[0], item[1], item[2] or {}))
            else:
                norm.append((item[0], item[1], {}))
        self.selection_items = norm
        self.selection_caption = caption or ""
        self.selection_image = self.load_image(image) if image else None
        self.selection_active = True
        w, h = self.width, self.height
        self.selection_anchor = (
            self._resolve_title_x(st.get("caption_x", "center")),
            self._resolve_title_y(st.get("caption_y"), 0.30),
        )
        # 按钮区: 每项可独立尺寸 (高度可变, 纵向排列)
        n = len(norm)
        bx = self._resolve_title_x(st.get("anchor_x", "center"))
        by = st.get("anchor_y")
        gap = st["gap"]
        if str(by).lower() == "center":
            # 先算总高 (按各项高度)
            total = sum(int(cfg.get("height") or st["height"])
                        for _, _, cfg in norm)
            total += (n - 1) * gap
            by = (self.height - total) / 2
        else:
            by = self._resolve_title_y(by, 0.52)
        rects = []
        y = by
        for text, action, cfg in norm:
            bw = int(cfg.get("width") or st.get("width")
                     or w * st["width_ratio"])
            bh = int(cfg.get("height") or st["height"])
            rects.append(pygame.Rect(int(bx - bw / 2), int(y), bw, bh))
            y += bh + gap
        self.selection_rects = rects
        # 兼容旧字段 (标题画面/系统菜单)
        self.title_rects = self.selection_rects
        self.system_menu_rects = self.selection_rects
        self.engine.emit("selection_show", caption=caption,
                         items=[t for t, _, _ in norm])

    def hit_selection(self, pos) -> int:
        if not self.selection_active:
            return -1
        for idx, rect in enumerate(self.selection_rects):
            if rect.collidepoint(pos):
                return idx
        return -1

    def close_selection(self) -> None:
        self.selection_active = False
        self.selection_items = []
        self.title_active = False
        self.system_menu_active = False

    def _draw_selection(self, buf) -> None:
        st = self.selection_style
        ui.dim_overlay(buf, st.get("dim_alpha", 120))
        tx, ty = self.selection_anchor
        w, h = self.width, self.height
        # 标题图片 (等比缩放到宽度 70%)
        text_y = ty
        if self.selection_image is not None:
            img = self.selection_image
            max_w = int(w * 0.70)
            if img.get_width() > max_w:
                ratio = max_w / img.get_width()
                img = pygame.transform.smoothscale(
                    img, (max_w, int(img.get_height() * ratio)))
            buf.blit(img, img.get_rect(center=(int(tx), int(ty))))
            text_y = ty + img.get_height() / 2 + 18
        # 标题文字 (富文本 + 投影)
        if self.selection_caption:
            runs = self._rich.parse(str(self.selection_caption),
                                    base_size=st.get("caption_size", 56))
            self._rich.draw_centered(buf, runs, int(tx) + 3, int(text_y) + 3)
            self._rich.draw_centered(buf, runs, int(tx), int(text_y))
        # 按钮 (每按键可独立配置)
        mouse = pygame.mouse.get_pos()
        for idx, (label, action, cfg) in enumerate(self.selection_items):
            rect = self.selection_rects[idx]
            hovered = rect.collidepoint(mouse)
            # 标题画面用 title_buttons 主题图 (多按钮图组, 按索引取),
            # ESC 菜单用 menu_buttons 主题图; cfg 的 image 优先
            theme_comp = ("title_buttons" if self.title_active
                          else "menu_buttons")
            cfg_img = cfg.get("image_focus") if hovered else cfg.get("image")
            if cfg_img:
                img = self._ui_image(cfg_img)
            else:
                img = (self._theme(theme_comp, "focus" if hovered
                                   else "default", index=idx)
                       or self._ui_image(st.get("button_image_hover")
                                         if hovered
                                         else st.get("button_image")))
            stretch = cfg.get("stretch", st.get("button_stretch", True))
            if img is not None:
                if stretch:
                    buf.blit(ui.nine_slice(img, rect), rect.topleft)
                else:
                    # 原尺寸居中 (按钮图自带文字时)
                    buf.blit(img, img.get_rect(center=rect.center))
            else:
                ui.panel(buf, rect,
                         bg_color=st["button_bg_hover"] if hovered
                         else st["button_bg"],
                         border_color=st["button_border_hover"] if hovered
                         else st["button_border"],
                         border_width=2, radius=st.get("button_radius", 6))
            if cfg.get("text_visible", st.get("button_text", True)):
                runs_b = self._rich.parse(
                    str(label), base_size=st.get("text_size", 28),
                    base_color=st.get("text_color_hover") if hovered
                    else st.get("text_color", (245, 245, 245)))
                self._rich.draw_centered(buf, runs_b, rect.centerx,
                                         rect.centery,
                                         alpha=255 if hovered
                                         else st.get("unhover_alpha", 215))

    def show_system_menu(self, items) -> None:
        """显示系统菜单 (游戏内 ESC, selection 的菜单专用实例)。

        完全跟随全局 selection 样式 (selection_style 语句可调整)。
        """
        self.system_menu_active = True
        self.system_menu_items = list(items)
        self.show_selection(items)

    def hit_system_menu(self, pos) -> int:
        return self.hit_selection(pos) if self.system_menu_active else -1

    def show_slot_menu(self, slots, mode: str = "load") -> None:
        """显示存档槽位选择界面。slots: [{slot,time,label,preview,empty}]"""
        self.slot_menu_active = True
        self.slot_menu_mode = mode
        self.slot_menu_slots = list(slots)
        w, h = self.width, self.height
        cols = 2
        rows = max(1, (len(slots) + 1) // 2)
        panel_w, panel_h = int(w * 0.72), int(h * 0.66)
        px, py = (w - panel_w) // 2, int(h * 0.16)
        gw, gh = int(panel_w * 0.42), int((panel_h - 80) / rows)
        gap_x, gap_y = int(panel_w * 0.08), 10
        x0 = px + int(panel_w * 0.045)
        y0 = py + 46
        self.slot_menu_rects = []
        for i in range(len(slots)):
            r, c = divmod(i, cols)
            self.slot_menu_rects.append(
                pygame.Rect(x0 + c * (gw + gap_x), y0 + r * (gh + gap_y),
                            gw, gh))
        self.slot_menu_back_rect = pygame.Rect(
            px + panel_w - 110, py + panel_h - 44, 90, 34)

    def hit_slot_menu(self, pos):
        """返回槽位索引 / "back" / None。"""
        if not self.slot_menu_active:
            return None
        if self.slot_menu_back_rect.collidepoint(pos):
            return "back"
        for idx, rect in enumerate(self.slot_menu_rects):
            if rect.collidepoint(pos):
                return idx
        return None

    def _draw_slot_menu(self, buf) -> None:
        ui.dim_overlay(buf, 160)
        w, h = self.width, self.height
        panel_w, panel_h = int(w * 0.72), int(h * 0.66)
        px, py = (w - panel_w) // 2, int(h * 0.16)
        dlg_img = self._ui_image(
            self.selection_style_overrides.get("dialog_image"))
        self._panel_or_image(buf, (px, py, panel_w, panel_h), dlg_img,
                             bg_color=(25, 25, 38, 245),
                             border_color=(200, 200, 220),
                             border_width=2, radius=10)
        title = "选择存档" if self.slot_menu_mode == "save" else "选择读档"
        runs_t = self._rich.parse(title, base_size=30)
        self._rich.draw_centered(buf, runs_t, w // 2, py + 22)
        # 槽位格子
        mouse = pygame.mouse.get_pos()
        for idx, info in enumerate(self.slot_menu_slots):
            rect = self.slot_menu_rects[idx]
            hovered = rect.collidepoint(mouse)
            empty = info.get("empty")
            img = self._theme("slot_frame", "focus" if hovered
                              else "default")
            self._panel_or_image(
                buf, rect, img,
                bg_color=(55, 55, 75, 235) if hovered
                else (40, 40, 55, 220),
                border_color=(255, 220, 120) if hovered
                else (140, 140, 160),
                border_width=2, radius=8)
            slot_no = info.get("slot", idx) + 1
            if empty:
                text1 = f"槽位 {slot_no}"
                text2 = "（空存档）"
                color = (150, 150, 160)
            else:
                text1 = f"槽位 {slot_no}   {info.get('time', '')}"
                text2 = str(info.get("preview") or info.get("label") or "")
                color = (235, 235, 240)
            self._rich.draw(buf, self._rich.parse(text1, base_size=20),
                            rect.x + 12, rect.y + 8, rect.w - 24)
            self._rich.draw(buf, self._rich.parse(text2, base_size=18),
                            rect.x + 12, rect.y + 34, rect.w - 24,
                            max_lines=2)
        # 返回按钮
        back = self.slot_menu_back_rect
        hovered = back.collidepoint(mouse)
        ui.panel(buf, back,
                 bg_color=(80, 60, 60, 235) if hovered else (60, 45, 45, 220),
                 border_color=(255, 200, 140) if hovered else (160, 130, 120),
                 border_width=2, radius=6)
        runs_b = self._rich.parse("返回", base_size=20)
        self._rich.draw_centered(buf, runs_b, back.centerx, back.centery)

    def show_confirm(self, text: str, yes_text: str = "是",
                     no_text: str = "否") -> None:
        """显示确认对话框 (如退出确认), 阻塞交互直到选择。"""
        self.confirm_active = True
        self.confirm_text = text
        self.confirm_yes = yes_text
        self.confirm_no = no_text
        w, h = self.width, self.height
        pw, ph = int(w * 0.5), int(h * 0.30)
        self.confirm_panel = pygame.Rect((w - pw) // 2, (h - ph) // 2, pw, ph)
        bw, bh = int(pw * 0.30), 46
        gap = 18
        total = bw * 2 + gap
        x0 = (w - total) // 2
        y = self.confirm_panel.bottom - bh - 22
        self.confirm_rects = [
            pygame.Rect(x0, y, bw, bh),
            pygame.Rect(x0 + bw + gap, y, bw, bh),
        ]
        self.engine.emit("confirm_show", text=text)

    def hit_confirm(self, pos) -> int:
        if not self.confirm_active:
            return -1
        for idx, rect in enumerate(self.confirm_rects):
            if rect.collidepoint(pos):
                return idx
        return -1

    def show_error(self, info: dict) -> None:
        """显示运行时错误弹窗 (ErrorHandler 快照)。"""
        self.error_active = True
        self.error_info = info
        w, h = self.width, self.height
        pw, ph = int(w * 0.72), int(h * 0.60)
        self.error_panel = pygame.Rect((w - pw) // 2, (h - ph) // 2, pw, ph)
        bw, bh = int(pw * 0.26), 44
        gap = 16
        total = bw * 3 + gap * 2
        x0 = self.error_panel.centerx - total // 2
        y = self.error_panel.bottom - bh - 20
        self.error_rects = [
            pygame.Rect(x0 + i * (bw + gap), y, bw, bh) for i in range(3)
        ]
        self.engine.emit("error_show", text=info.get("text"))

    def hit_error(self, pos) -> int:
        if not self.error_active:
            return -1
        for idx, rect in enumerate(self.error_rects):
            if rect.collidepoint(pos):
                return idx
        return -1

    def _draw_confirm(self, buf) -> None:
        ui.dim_overlay(buf, 170)
        dlg_img = (self._theme("confirm_panel")
                   or self._ui_image(
                       self.selection_style_overrides.get("dialog_image")))
        self._panel_or_image(buf, self.confirm_panel, dlg_img,
                             bg_color=(25, 25, 38, 245),
                             border_color=(200, 200, 220),
                             border_width=2, radius=10)
        # 提示文本 (富文本, 居中换行; 颜色用 dialog_text_color)
        dlg_color = self.selection_style_overrides.get(
            "dialog_text_color", (245, 245, 245))
        runs = self._rich.parse(str(self.confirm_text), base_size=28,
                                base_color=dlg_color)
        pad = 24
        self._rich.draw(buf, runs, self.confirm_panel.x + pad,
                        self.confirm_panel.y + 30,
                        self.confirm_panel.w - pad * 2, align="center")
        # 是/否按钮
        mouse = pygame.mouse.get_pos()
        for idx, label in enumerate((self.confirm_yes, self.confirm_no)):
            rect = self.confirm_rects[idx]
            hovered = rect.collidepoint(mouse)
            accent = (0, 170, 90) if idx == 0 else (170, 60, 60)
            img = self._theme("confirm_button", "focus" if hovered
                              else "default")
            self._panel_or_image(
                buf, rect, img,
                bg_color=(*accent, 235) if hovered else (*accent, 200),
                border_color=(255, 255, 255, 160) if hovered
                else (0, 0, 0, 120),
                border_width=2, radius=6)
            runs_b = self._rich.parse(str(label), base_size=24,
                                      base_color=dlg_color)
            self._rich.draw_centered(buf, runs_b, rect.centerx,
                                     rect.centery)

    # ==================================================================
    # 转场 / 震动 / 通知 / 结束
    # ==================================================================
    def _draw_error(self, buf) -> None:
        ui.dim_overlay(buf, 175)
        dlg_img = self._ui_image(
            self.selection_style_overrides.get("dialog_image"))
        self._panel_or_image(buf, self.error_panel, dlg_img,
                             bg_color=(40, 15, 15, 248),
                             border_color=(255, 90, 90),
                             border_width=3, radius=10)
        pw = self.error_panel.w
        pad = 26
        runs_t = self._rich.parse("{c=#ff6060}⚠ 运行时错误{/c}",
                                  base_size=30)
        self._rich.draw(buf, runs_t, self.error_panel.x + pad,
                        self.error_panel.y + 18, pw - pad * 2)
        text = str(self.error_info.get("text", "未知错误"))
        if len(text) > 400:
            text = text[:400] + " ……"
        runs = self._rich.parse(text, base_size=20)
        self._rich.draw(buf, runs, self.error_panel.x + pad,
                        self.error_panel.y + 62, pw - pad * 2,
                        max_lines=8)
        file_hint = (f"完整报错已写入: {self.error_info.get('file')}"
                     if self.error_info.get("file") else "")
        runs_h = self._rich.parse(file_hint, base_size=16,
                                  base_color=(200, 180, 160))
        self._rich.draw(buf, runs_h, self.error_panel.x + pad,
                        self.error_panel.y + self.error_panel.h - 78,
                        pw - pad * 2, max_lines=2)
        mouse = pygame.mouse.get_pos()
        labels = ("继续游戏", "复制错误", "退出游戏")
        for idx, label in enumerate(labels):
            rect = self.error_rects[idx]
            hovered = rect.collidepoint(mouse)
            accent = ((0, 150, 90), (120, 110, 40), (170, 50, 50))[idx]
            self._panel_or_image(
                buf, rect, None,
                bg_color=(*accent, 250) if hovered else (*accent, 205),
                border_color=(255, 255, 255, 200) if hovered
                else (0, 0, 0, 120), border_width=2, radius=6)
            runs_b = self._rich.parse(label, base_size=20)
            self._rich.draw_centered(buf, runs_b, rect.centerx,
                                     rect.centery)

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
                self.ending = False
                self.engine.goto_title()   # 结束后回到标题画面

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

        if self.error_active:
            self._draw_error(buf)
        elif self.confirm_active:
            self._draw_confirm(buf)
        elif self.slot_menu_active:
            self._draw_slot_menu(buf)
        elif self.selection_active:
            self._draw_selection(buf)
        elif self.choice_active:
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
        st = self.style

        bg = st["textbox_bg"]
        self._panel_or_image(
            buf, (box_x, box_y, box_w, box_h),
            self._style_image_or_theme("textbox_image", "textbox"),
            bg_color=(*bg, st["textbox_alpha"]),
            border_color=st["textbox_border"],
            border_width=st["textbox_border_width"],
            radius=st["textbox_radius"])

        text_x = box_x + 24
        text_y = box_y + 24
        avail_w = box_w - 48
        avail_h = box_h - 48

        # 角色名
        name_h = 0
        if self.speaker:
            name_surf = self._font_speaker.render(
                self.speaker, True, st["speaker_color"])
            self._panel_or_image(buf,
                                 (text_x - 6, text_y - 14,
                                  name_surf.get_width() + 24,
                                  name_surf.get_height() + 12),
                                 self._style_image_or_theme(
                                     "speaker_image", "speaker"),
                                 bg_color=st["speaker_bg"])
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
            ui.text(buf, self._font_text, "▼", color=st["arrow_color"],
                    pos=(box_x + box_w - 34, box_y + box_h - 34),
                    alpha=255 * blink)

    def _draw_choices(self, buf) -> None:
        ui.dim_overlay(buf, 150)
        st = self.style
        mouse = pygame.mouse.get_pos()
        self.hover_index = -1
        for idx, (text, label) in enumerate(self.choices):
            rect = self.choice_rects[idx]
            hovered = rect.collidepoint(mouse)
            if hovered:
                self.hover_index = idx
            img = None
            opt = st["choice_image_hover" if hovered else "choice_image"]
            if opt == "none":
                img = None
            elif opt:
                img = self._ui_image(opt)
            else:
                img = self._theme("choice_button", "focus" if hovered
                                  else "default")
            self._panel_or_image(buf, rect, img,
                                 bg_color=st["choice_bg_hover"] if hovered
                                 else st["choice_bg"],
                                 border_color=st["choice_border_hover"]
                                 if hovered else st["choice_border"],
                                 border_width=2, radius=6)
            runs = self._choice_runs[idx]
            color = st["choice_text_color_hover"] if hovered \
                else st["choice_text_color"]
            # 未着色的 run 用当前按钮文字色 (复制 run, 不污染缓存)
            from framework.engine.rich import Run
            runs_final = []
            for run in runs:
                if run.color == st["choice_text_color"]:
                    runs_final.append(
                        Run(run.text, color, run.size, run.bold, run.italic,
                            run.underline, run.outline, run.outline_width,
                            run.math))
                else:
                    runs_final.append(run)
            self._rich.draw_centered(buf, runs_final, rect.centerx,
                                     rect.centery,
                                     alpha=255 if hovered else 235)

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
