"""鉴赏插件 (gallery): 向标题菜单添加"鉴赏"按钮, 提供 CG/BGM/角色/场景鉴赏。

解锁机制:
    gallery 配置里的 unlock_ending 指定的结局达成后解锁鉴赏按钮
    (未达成时按钮呈禁用态, 点击无效)。结局用 ``ending <名>`` 指令达成。

配置 (独立 .gal 文件, 由本插件解析, 引擎广播 script_block 事件):

    gallery
        unlock_ending: "真结局"          # 达成此结局解锁 (空=不锁)
        button_text: "鉴赏"              # 标题菜单按钮文本
        title: "鉴赏"                    # 鉴赏界面标题
        categories: "cg, bgm, character, scene"   # 可用分类
        locked_hint: "达成真结局后解锁"   # 解锁提示

按钮样式: 在 ui.gal 的 ``menu title`` 中定义 (action: gallery_open,
样式照常配置: image/width/height/text_visible...), 插件只负责挂接与解锁;
未在脚本中定义时插件自动添加 (默认样式)。

数据来源:
    * CG 鉴赏   —— scene type: cg 的场景 (bg 指令展示时自动记入全局收集)
    * BGM 鉴赏  —— sound 注册表 type: music 的声音
    * 角色鉴赏  —— char 定义 (name/立绘/meta.desc 等描述性信息)
    * 场景鉴赏  —— scene 定义 (name/默认背景)

依赖引擎扩展: register_menu_button / set_menu_button_state /
register_action / record_ending / record_cg / get_unlocked_cgs /
engine_click / engine_escape / draw_overlay (逻辑坐标 buffer)。
"""

import os

import pygame

from framework.api import Plugin
from framework.engine import log

# 分类显示名 (键 = 数据来源)
CATEGORY_NAMES = [
    ("cg", "CG 鉴赏"),
    ("bgm", "BGM 鉴赏"),
    ("character", "角色鉴赏"),
    ("scene", "场景鉴赏"),
]


class GalleryPlugin(Plugin):
    name = "gallery"
    version = "1.0"

    DEFAULT_CONFIG = {
        "unlock_ending": None,
        "button_text": "鉴赏",
        "title": "鉴赏",
        "categories": "cg, bgm, character, scene",
        "locked_hint": "",
    }

    def on_load(self):
        # 鉴赏配置由本插件管理 (gallery 块由引擎广播 script_block 事件)
        if not hasattr(self.engine, "gallery_config"):
            self.engine.gallery_config = dict(self.DEFAULT_CONFIG)
        self._cfg = dict(self.engine.gallery_config)
        self._active = False          # 鉴赏界面是否打开
        self._category = "cg"         # 当前分类
        self._view = None             # CG 大图: {"scene","pose","path"}
        self._img_cache = {}
        self._btn_registered = False
        self._grid_rects = []         # 内容区可点击项 rects
        self._grid_items = []         # [(kind, payload), ...]
        self._cat_rects = []          # 分类/返回按钮 rects
        self._cat_names = []
        self._bgm_pending = None      # {"name","t0"}: 待切换 BGM (先显示后播放)

        # 打开动作 (标题菜单按钮 action: gallery_open)
        self.engine.register_action("gallery_open", self._open)

        @self.listen("script_block")
        def _on_block(op, stmt, **kw):
            # 引擎广播的未处理属性块: gallery 块由本插件解析
            if op == "gallery":
                self._apply_gallery_block(stmt)

        @self.listen("script_load")
        def _on_script_load(**kw):
            # 脚本已加载, 菜单定义就绪: 挂接/禁用鉴赏按钮
            self._ensure_button()

        @self.listen("ending_recorded")
        def _on_ending(name, endings, **kw):
            target = self._cfg.get("unlock_ending")
            if target and name == target:
                self._unlock()

        @self.listen("engine_click")
        def _on_click(pos, **kw):
            d = self.engine.display
            if d.confirm_active or d.error_active or d.slot_menu_active:
                return None        # 确认框/错误弹窗/槽位界面优先, 不拦截
            if self._view is not None:
                # CG 大图: 点击轮播下一形态, 播完退出
                v = self._view
                v["idx"] += 1
                if v["idx"] >= len(v["poses"]):
                    self._view = None
                return False
            if self._active:
                return self._handle_click(pos)
            return None

        @self.listen("engine_escape")
        def _on_escape(**kw):
            if self._view is not None:
                self._view = None
                return False
            if self._active:
                self.close_gallery()
                return False
            return None

        @self.listen("draw_overlay")
        def _on_draw(surface, **kw):
            if self._view is not None:
                self._draw_view(surface)
            elif self._active:
                self._draw_gallery(surface)

    def on_unload(self):
        self.engine.actions.pop("gallery_open", None)
        self._img_cache.clear()
        print("[插件] gallery 已卸载")

    def _apply_gallery_block(self, stmt):
        """解析 gallery 配置块 (引擎广播 script_block 事件):

        gallery
            unlock_ending: "真结局"          # 达成此结局解锁鉴赏按钮 (空=不锁)
            button_text: "鉴赏"              # 标题菜单按钮文本
            title: "鉴赏"                    # 鉴赏界面标题
            categories: "cg, bgm, character, scene"   # 可用分类
            locked_hint: "达成真结局后解锁"   # 锁定提示
            # --- 界面样式 (可选, 相对脚本目录) ---
            bg: "materials/.../bg.png"       # 界面背景图 (cover 铺满)
            cat_image: "默认.png, 焦点.png"  # 分类按钮图 (默认, 焦点)
            back_image: "默认.png, 焦点.png" # 返回按钮图
            cat_text: false                  # 图自带文字时不渲染分类文案
            cg_frame: "默认.png, 焦点.png"   # CG 插画框 (九宫格)
            cg_placeholder: "占位.png"       # 未解锁 CG 占位图
        """
        base = dict(self.engine.gallery_config)
        base.update({k: str(v) for k, v in stmt.kwargs.items()})
        self.engine.gallery_config = base
        self._cfg = dict(base)
        self._ensure_button()
        from framework.engine import log
        log.info(f"鉴赏配置已应用: {base}")

    # ------------------------------------------------------------------
    # 按钮: 挂接 / 解锁
    # ------------------------------------------------------------------
    def _is_unlocked(self) -> bool:
        target = self._cfg.get("unlock_ending")
        if not target:
            return True
        return target in self.engine.get_endings()

    def _find_gallery_button(self):
        """找脚本 menu title 中 action 为 gallery_open 的按钮 (name/text)。"""
        try:
            items = self.engine.runtime._menu_items("title")
        except Exception:
            return None
        if not items:
            return None
        for text, action, cfg in items:
            if isinstance(action, dict) and \
                    action.get("type") == "gallery_open":
                return cfg.get("name") or text
        return None

    def _ensure_button(self):
        """挂接/添加标题菜单鉴赏按钮, 并按解锁状态设置启用/禁用。

        脚本已在 menu title 中定义 (action: gallery_open) 时只改状态;
        否则自动追加一个默认样式按钮 (脚本 menu 块注册可能覆盖自动按钮,
        故每次检查后重新确保)。
        """
        unlocked = self._is_unlocked()
        try:
            items = self.engine.runtime._menu_items("title") or []
        except Exception:
            items = []
        # 1) 脚本定义的鉴赏按钮 (action: gallery_open)
        for text, action, cfg in items:
            if isinstance(action, dict) and \
                    action.get("type") == "gallery_open":
                self._btn_registered = True
                self.engine.set_menu_button_state(
                    "title", cfg.get("name") or text, unlocked)
                return
        # 2) 已自动添加的按钮 (name=gallery) 仍存在 -> 只改状态
        if any(c.get("name") == "gallery" for _t, _a, c in items):
            self.engine.set_menu_button_state("title", "gallery", unlocked)
            return
        # 3) 自动添加 (可能被脚本 menu 块覆盖后丢失, 重新添加)
        self._btn_registered = True
        self.engine.register_menu_button(
            "title", self._cfg.get("button_text") or "鉴赏",
            {"type": "gallery_open"},
            cfg={"enabled": unlocked, "name": "gallery"})

    def _unlock(self):
        self._ensure_button()
        hint = self._cfg.get("locked_hint")
        self.engine.display.show_notice(
            hint or "鉴赏已解锁！", 2.0)

    # ------------------------------------------------------------------
    # 打开 / 关闭
    # ------------------------------------------------------------------
    def _open(self, engine, params, source):
        """action gallery_open: 打开鉴赏界面 (标题菜单点击进入)。"""
        engine.display.close_selection()   # 关闭标题菜单
        engine.paused = True               # 暂停游戏逻辑 (界面自绘)
        self._active = True
        self._category = "cg"
        self._view = None
        self.engine.emit("gallery_open")
        return True

    def close_gallery(self):
        self._active = False
        self._view = None
        self._bgm_pending = None
        self.engine.paused = False
        # 停止鉴赏期间播放的 BGM; 回标题后由 start 块重放标题 BGM (如有)
        if self.engine.audio.current_bgm is not None:
            self.engine.stop_music()
        self.engine.goto_title()           # 返回标题画面

    # ------------------------------------------------------------------
    # 交互
    # ------------------------------------------------------------------
    def _handle_click(self, pos):
        # 分类按钮 / 返回
        for i, rect in enumerate(self._cat_rects):
            if rect.collidepoint(pos):
                name = self._cat_names[i]
                if name == "back":
                    self.close_gallery()
                elif name in ("cg", "bgm", "character", "scene"):
                    self._category = name
                    self._grid_rects = []
                return False
        # 内容区
        for i, rect in enumerate(self._grid_rects):
            if rect.collidepoint(pos):
                self._on_grid_click(i)
                return False
        return False

    def _on_grid_click(self, i):
        kind, payload = self._grid_items[i]
        if kind == "cg":
            sid, poses, _total = payload
            if not poses:
                return            # 未解锁 CG: 不可点
            self._view = {"scene": sid, "poses": list(poses), "idx": 0}
        elif kind == "bgm":
            # 先显示"正在切换"提示, 稍后再实际切换 (见 _draw_bgm)
            self._bgm_pending = {"name": payload,
                                 "t0": pygame.time.get_ticks()}

    # ------------------------------------------------------------------
    # 数据
    # ------------------------------------------------------------------
    def _categories(self):
        raw = str(self._cfg.get("categories", "cg, bgm, character, scene"))
        cats = [c.strip() for c in raw.split(",") if c.strip()]
        return [c for c, _label in CATEGORY_NAMES if c in cats]

    def _cg_entries(self):
        """CG 条目 (按场景合并): [(scene_id, poses, total, thumb_path)]。

        poses: 已解锁形态列表 (含 "" 表示默认背景);
        total: 该场景总形态数 (backgrounds 键数, 至少 1);
        thumb: 缩略图路径 (已解锁取首个形态, 未解锁为 None)。
        """
        out = []
        unlocked = self.engine.get_unlocked_cgs()
        scenes = self.engine.runtime.scenes
        for sid, scene in scenes.items():
            if scene.get("type") != "cg":
                continue
            poses = unlocked.get(sid, [])
            # 形态总数 = 背景名键数 + 默认背景 (default 也算一个形态)
            all_poses = list(scene["backgrounds"].keys())
            total = len(all_poses) + (1 if scene.get("default") else 0)
            thumb = None
            if poses:
                first = poses[0]
                thumb = (scene["backgrounds"].get(first)
                         if first in scene["backgrounds"]
                         else scene.get("default"))
            out.append((sid, list(poses), total, thumb))
        return out

    def _bgm_entries(self):
        return [(n, s.get("file", "")) for n, s
                in self.engine.runtime.sounds.items()
                if s.get("type") == "music"]

    # ------------------------------------------------------------------
    # 图片
    # ------------------------------------------------------------------
    def _load_img(self, path):
        if not path:
            return None
        if path in self._img_cache:
            return self._img_cache[path]
        real = self.engine.resolve_path(path)
        img = None
        try:
            img = pygame.image.load(real).convert_alpha()
        except Exception as exc:
            log.warning(f"鉴赏图片加载失败 {path}: {exc}")
        self._img_cache[path] = img
        return img

    def _scaled(self, path, w, h):
        """加载图片并等比缩放到 (w, h) 内 (保持比例)。"""
        img = self._load_img(path)
        if img is None:
            return None
        iw, ih = img.get_size()
        scale = min(w / iw, h / ih)
        tw, th = max(1, int(iw * scale)), max(1, int(ih * scale))
        if (tw, th) != (iw, ih):
            return pygame.transform.smoothscale(img, (tw, th))
        return img

    def _theme_img(self, key):
        """解析配置图 "默认, 焦点" -> (default_surface, focus_surface)。"""
        v = self._cfg.get(key)
        if not v:
            return (None, None)
        parts = [p.strip() for p in str(v).split(",") if p.strip()]
        d = self._load_img(parts[0]) if parts else None
        f = self._load_img(parts[1]) if len(parts) > 1 else None
        return (d, f)

    # ------------------------------------------------------------------
    # 绘制
    # ------------------------------------------------------------------
    def _draw_gallery(self, surface):
        ui = self.engine.ui
        w, h = surface.get_size()
        # 确认框/错误弹窗打开时: 完全让出绘制 (确认框自带遮罩)
        if (self.engine.display.confirm_active
                or self.engine.display.error_active):
            return
        # 界面背景图 (cover 铺满) / 纯色底
        bg_img = self._load_img(self._cfg.get("bg"))
        if bg_img:
            iw, ih = bg_img.get_size()
            scale = max(w / iw, h / ih)
            tw, th = max(1, int(iw * scale)), max(1, int(ih * scale))
            shown = pygame.transform.smoothscale(bg_img, (tw, th))
            surface.blit(shown, shown.get_rect(center=(w // 2, h // 2)))
        else:
            surface.fill((8, 8, 14))
        # 标题
        ui.text(surface, self.engine.get_font(40),
                str(self._cfg.get("title") or "鉴赏"),
                color=(255, 220, 130), center=(w // 2, 40))
        # 分类按钮行
        self._build_cat_layout(w)
        font_b = self.engine.get_font(22)
        mouse = self.engine.display.mouse_pos()
        cat_d, cat_f = self._theme_img("cat_image")
        back_d, back_f = self._theme_img("back_image")
        for i, rect in enumerate(self._cat_rects):
            name = self._cat_names[i]
            hovered = rect.collidepoint(mouse)
            if name == "back":
                label = "← 返回"
                img = back_f if hovered else back_d
                bg = (70, 44, 44) if hovered else (42, 30, 30)
                border = (220, 130, 130) if hovered else (120, 80, 80)
            else:
                active = (name == self._category)
                label = dict(CATEGORY_NAMES).get(name, name)
                img = cat_f if (hovered or active) else cat_d
                bg = ((233, 69, 96) if active else
                      (85, 62, 95) if hovered else (45, 45, 70))
                border = ((255, 210, 130) if (active or hovered)
                          else (90, 90, 130))
            if img is not None:
                # 图优先: 九宫格拉伸 (图自带文字时可配 text_visible: false)
                surface.blit(ui.nine_slice(img, rect), rect.topleft)
                if str(self._cfg.get("cat_text", "true")).lower() not in (
                        "false", "0", "no"):
                    ui.text(surface, font_b, label,
                            color=(255, 255, 255), center=rect.center)
            else:
                ui.panel(surface, rect, bg_color=(*bg, 240),
                         border_color=border, border_width=2, radius=8)
                ui.text(surface, font_b, label, color=(255, 255, 255),
                        center=rect.center)
        # 内容
        if self._category == "cg":
            self._draw_cg(surface)
        elif self._category == "bgm":
            self._draw_bgm(surface)
        elif self._category == "character":
            self._draw_characters(surface)
        elif self._category == "scene":
            self._draw_scenes(surface)

    def _build_cat_layout(self, w):
        cats = self._categories() + ["back"]
        bw, bh, gap = 150, 44, 14
        total = len(cats) * bw + (len(cats) - 1) * gap
        x0 = max(8, (w - total) // 2)
        self._cat_rects = []
        self._cat_names = []
        for i, name in enumerate(cats):
            self._cat_rects.append(
                pygame.Rect(x0 + i * (bw + gap), 80, bw, bh))
            self._cat_names.append(name)

    def _draw_cg(self, surface):
        ui = self.engine.ui
        w, h = surface.get_size()
        rt = self.engine.runtime
        entries = self._cg_entries()
        collected = sum(1 for _s, poses, _t, _th in entries if poses)
        ui.text(surface, self.engine.get_font(20),
                f"CG 收集: {collected} / {len(entries)}",
                color=(200, 200, 210), pos=(28, 132))
        self._grid_rects = []
        self._grid_items = []
        if not entries:
            ui.text(surface, self.engine.get_font(20),
                    "暂无 CG 可鉴赏", color=(150, 150, 165),
                    center=(w // 2, h // 2))
            return
        cols = 4
        gap = 16
        cw = min(300, (w - 80 - gap * (cols - 1)) // cols)
        ch = int(cw * 9 / 16)
        x0 = (w - (cols * cw + (cols - 1) * gap)) // 2
        y0 = 158
        font_s = self.engine.get_font(16)
        font_q = self.engine.get_font(44)
        frame_d, _frame_f = self._theme_img("cg_frame")
        placeholder = self._load_img(self._cfg.get("cg_placeholder"))
        for i, (sid, poses, total, thumb) in enumerate(entries):
            r, c = divmod(i, cols)
            rect = pygame.Rect(x0 + c * (cw + gap), y0 + r * (ch + 26),
                               cw, ch)
            self._grid_rects.append(rect)
            self._grid_items.append(("cg", (sid, poses, total)))
            scene = rt.scenes.get(sid, {})
            if thumb:
                # 已解锁: 插画框 + 缩略图 + 形态进度
                if frame_d is not None:
                    surface.blit(ui.nine_slice(frame_d, rect), rect.topleft)
                else:
                    ui.panel(surface, rect, bg_color=(22, 22, 32),
                             border_color=(90, 90, 120), border_width=1)
                img = self._scaled(thumb, cw - 6, ch - 6)
                if img:
                    surface.blit(img, img.get_rect(center=rect.center))
                label = (f"{scene.get('name', sid)} "
                         f"({len(poses)}/{total})")
                color = (230, 230, 235)
            else:
                # 未解锁: 占位图 (或灰色框 + 问号)
                if placeholder is not None:
                    surface.blit(pygame.transform.smoothscale(
                        placeholder, rect.size), rect.topleft)
                else:
                    ui.panel(surface, rect, bg_color=(48, 48, 54),
                             border_color=(90, 90, 98), border_width=1)
                    ui.text(surface, font_q, "？", color=(120, 120, 128),
                            center=rect.center)
                label = f"{scene.get('name', sid)} · 未解锁"
                color = (140, 140, 150)
            ui.text(surface, font_s, label, color=color,
                    center=(rect.centerx, rect.bottom + 13))

    def _draw_bgm(self, surface):
        ui = self.engine.ui
        w, h = surface.get_size()
        songs = self._bgm_entries()
        self._grid_rects = []
        self._grid_items = []
        if not songs:
            ui.text(surface, self.engine.get_font(20), "暂无 BGM 可鉴赏",
                    color=(150, 150, 165), center=(w // 2, h // 2))
            return
        font = self.engine.get_font(20)
        font_f = self.engine.get_font(15)
        cur = self.engine.audio.current_bgm_name
        # 待切换 BGM: 先在页面上显示提示, 稍后再实际切换
        if self._bgm_pending is not None:
            pend = self._bgm_pending
            if pygame.time.get_ticks() - pend["t0"] >= 650:
                self.engine.play_music(pend["name"])   # 注册名试听
                self._bgm_pending = None
                cur = self.engine.audio.current_bgm_name
            else:
                ui.text(surface, self.engine.get_font(18),
                        f"正在切换 BGM：{pend['name']} …",
                        color=(255, 210, 130), pos=(80, 122))
        y = 150
        for name, f in songs:
            rect = pygame.Rect(80, y, w - 160, 48)
            self._grid_rects.append(rect)
            self._grid_items.append(("bgm", name))
            playing = (cur == name)
            ui.panel(surface, rect,
                     bg_color=(*(233, 69, 96), 235) if playing
                     else (38, 38, 56),
                     border_color=(255, 210, 130) if playing
                     else (80, 80, 110),
                     border_width=2, radius=8)
            ui.text(surface, font,
                    ("▶ " if playing else "") + name,
                    color=(255, 255, 255) if playing else (220, 220, 232),
                    pos=(rect.x + 18, rect.y + 10))
            ui.text(surface, font_f, os.path.basename(str(f)),
                    color=(150, 150, 168),
                    pos=(rect.x + 240, rect.y + 16))
            y += 56
        if self._bgm_pending is None:
            ui.text(surface, self.engine.get_font(16),
                    "点击曲目试听（再点另一首切换）", color=(140, 140, 155),
                    pos=(80, y + 4))

    def _draw_characters(self, surface):
        ui = self.engine.ui
        w, h = surface.get_size()
        chars = list(self.engine.runtime.characters.values())
        self._grid_rects = []
        self._grid_items = []
        if not chars:
            ui.text(surface, self.engine.get_font(20), "暂无角色",
                    color=(150, 150, 165), center=(w // 2, h // 2))
            return
        cols = 3
        gap = 28
        cw = min(250, (w - 80 - gap * (cols - 1)) // cols)
        ch = int(cw * 4 / 3)
        x0 = (w - (cols * cw + (cols - 1) * gap)) // 2
        y0 = 140
        font_n = self.engine.get_font(22)
        font_d = self.engine.get_font(16)
        for i, ch_ in enumerate(chars):
            r, c = divmod(i, cols)
            rect = pygame.Rect(x0 + c * (cw + gap), y0 + r * (ch + 86),
                               cw, ch)
            self._grid_rects.append(rect)
            self._grid_items.append(("character", ch_["id"]))
            ui.panel(surface, rect, bg_color=(18, 18, 28),
                     border_color=(70, 70, 95), border_width=1)
            img = self._scaled(ch_.get("default"), cw, ch)
            if img:
                surface.blit(img, img.get_rect(center=rect.center))
            ui.text(surface, font_n, str(ch_.get("name", ch_["id"])),
                    color=(255, 220, 130), center=(rect.centerx,
                                                   rect.bottom + 18))
            desc = ch_.get("meta", {}).get("desc", "")
            if desc:
                lines = ui.wrap_text(font_d, str(desc), cw)
                for k, line in enumerate(lines[:2]):
                    ui.text(surface, font_d, line, color=(185, 185, 200),
                            center=(rect.centerx, rect.bottom + 44 + k * 20))

    def _draw_scenes(self, surface):
        ui = self.engine.ui
        w, h = surface.get_size()
        # 场景鉴赏只展示 normal 场景 (CG 场景归 CG 鉴赏)
        scenes = [sc for sc in self.engine.runtime.scenes.values()
                  if sc.get("type") != "cg"]
        self._grid_rects = []
        self._grid_items = []
        if not scenes:
            ui.text(surface, self.engine.get_font(20), "暂无场景",
                    color=(150, 150, 165), center=(w // 2, h // 2))
            return
        cols = 4
        gap = 16
        cw = min(300, (w - 80 - gap * (cols - 1)) // cols)
        ch = int(cw * 9 / 16)
        x0 = (w - (cols * cw + (cols - 1) * gap)) // 2
        y0 = 140
        font_s = self.engine.get_font(16)
        for i, sc in enumerate(scenes):
            r, c = divmod(i, cols)
            rect = pygame.Rect(x0 + c * (cw + gap), y0 + r * (ch + 26),
                               cw, ch)
            self._grid_rects.append(rect)
            self._grid_items.append(("scene", sc["id"]))
            ui.panel(surface, rect, bg_color=(22, 22, 32),
                     border_color=(70, 70, 95), border_width=1)
            img = self._scaled(sc.get("default"), cw, ch)
            if img:
                surface.blit(img, img.get_rect(center=rect.center))
            label = str(sc.get("name", sc["id"]))
            if sc.get("type") == "cg":
                label += " [CG]"
            ui.text(surface, font_s, label, color=(190, 190, 205),
                    center=(rect.centerx, rect.bottom + 13))

    def _draw_view(self, surface):
        """CG 大图查看: 全屏黑底 + 等比放大图; 点击轮播形态, 播完退出。"""
        ui = self.engine.ui
        w, h = surface.get_size()
        # 确认框/错误弹窗打开时: 完全让出绘制 (确认框自带遮罩)
        if (self.engine.display.confirm_active
                or self.engine.display.error_active):
            return
        v = self._view
        scene = self.engine.runtime.scenes.get(v["scene"], {})
        pose = v["poses"][v["idx"]]
        img_path = (scene["backgrounds"].get(pose)
                    if pose in scene["backgrounds"]
                    else scene.get("default"))
        surface.fill((0, 0, 0))
        img = self._load_img(img_path)
        if img:
            iw, ih = img.get_size()
            scale = min((w - 40) / iw, (h - 110) / ih)
            tw, th = max(1, int(iw * scale)), max(1, int(ih * scale))
            shown = pygame.transform.smoothscale(img, (tw, th))
            surface.blit(shown, shown.get_rect(center=(w // 2, (h - 60) // 2)))
        total = len(v["poses"])
        label = (f"{scene.get('name', v['scene'])} · "
                 f"形态 {v['idx'] + 1} / {total}")
        ui.text(surface, self.engine.get_font(22), label,
                color=(230, 230, 240), center=(w // 2, h - 46))
        if v["idx"] < total - 1:
            hint = "点击切换下一形态 · ESC 退出"
        else:
            hint = "已是最后形态 · 点击退出"
        ui.text(surface, self.engine.get_font(16), hint,
                color=(140, 140, 155), center=(w // 2, h - 20))
