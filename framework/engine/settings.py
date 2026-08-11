"""设置系统: 设置项注册表 + 设置界面 (核心模块)。

开发者通过 setting.gal 配置界面布局与条目 (settings 块 + setting 子块),
插件通过 ``engine.settings.register()`` 注册自定义设置项。

内置设置项 (key / 类型 / 说明):
    bgm_volume        slider   BGM 音量
    sfx_volume        slider   音效音量
    voice_volume      slider   全局语音音量
    voice:<角色id>    slider   指定角色的语音音量 (动态, 脚本注册角色后可用)
    text_speed        slider   文字速度 (字符/秒)
    fullscreen        checkbox 全屏
    resizable         checkbox 窗口可缩放
    player_name       cycle    主角名字 ($player_name 变量)
    key_up/key_down/key_confirm  keybind  键盘导航键位

设置值保存在 ``save/settings.json`` (跨存档)。
"""

import os

import pygame

from framework.engine import log


class SettingsManager:
    """设置注册表 + 设置界面。"""

    # 内置键名 -> (label, kind, 附加配置) 简表 (用于动态项解析与默认显示)
    _DYNAMIC_PREFIX = "voice:"

    def __init__(self, engine) -> None:
        self.engine = engine
        self.items = {}          # key -> {label, kind, getter, setter, ...}
        self.order = []          # 显示顺序
        self.title = "设置"
        self.columns = 2
        self.bg = None           # 面板背景图 (九宫格, 可选)
        self.active = False      # 设置界面是否打开
        self._current_section = None   # 当前分栏 (None=首个)
        self._back_rect = None   # 返回按钮 rect (点击判定)
        self._tab_rects = []     # [(分栏名, rect)]
        self._binding = None     # keybind 等待捕获的 key
        self._hover = -1         # 当前悬停条目索引
        self._img_cache = {}

        self._register_builtins()
        self.load()

        # 交互钩子
        engine.events.on("draw_overlay", self._draw)
        engine.events.on("engine_click", self._on_click)
        engine.events.on("engine_escape", self._on_escape)
        engine.register_action("settings_open", self._open)

    # ==================================================================
    # 注册表
    # ==================================================================
    def register(self, key, label=None, kind="slider", getter=None,
                 setter=None, min=0.0, max=1.0, step=0.05,
                 options=None, visible=True, on_click=None,
                 section="通用") -> None:
        """插件 API: 注册一个设置项。

        kind: slider (数值滑条) / checkbox (开关) / cycle (枚举循环) /
              keybind (按键绑定) / button (点击按钮, 需 on_click)。
        section: 所属分栏 (设置界面按栏显示, 可自定义)。
        """
        self.items[key] = {
            "key": key, "label": label or key, "kind": kind,
            "getter": getter, "setter": setter,
            "min": float(min), "max": float(max), "step": float(step),
            "options": list(options) if options else None,
            "visible": visible, "on_click": on_click,
            "section": str(section),
        }
        if key not in self.order:
            self.order.append(key)

    def _register_builtins(self) -> None:
        a = self.engine.audio
        d = self.engine.display
        self.register("bgm_volume", "音乐音量", "slider",
                      getter=lambda: a.bgm_volume,
                      setter=lambda v: a.set_bgm_volume(v),
                      min=0, max=1, step=0.05, section="音量")
        self.register("sfx_volume", "音效音量", "slider",
                      getter=lambda: a.sfx_volume,
                      setter=lambda v: a.set_sfx_volume(v),
                      min=0, max=1, step=0.05, section="音量")
        self.register("voice_volume", "语音音量", "slider",
                      getter=lambda: a.voice_volume,
                      setter=lambda v: a.set_voice_volume(v),
                      min=0, max=1, step=0.05, section="语音")
        self.register("text_speed", "文字速度", "slider",
                      getter=lambda: d.type_speed,
                      setter=lambda v: setattr(d, "type_speed", v),
                      min=10, max=120, step=5, section="显示")
        self.register("fullscreen", "全屏", "checkbox",
                      getter=lambda: self.engine.fullscreen,
                      setter=lambda v: self.engine.set_fullscreen(bool(v)),
                      section="显示")
        self.register("resizable", "窗口可缩放", "checkbox",
                      getter=lambda: self.engine.resizable,
                      setter=lambda v: (setattr(self.engine, "resizable",
                                                bool(v)),
                                        self.engine._rebuild_window()),
                      section="显示")
        self.register("player_name", "主角名字", "cycle",
                      options=["阿明", "小明", "未命名"],
                      getter=lambda: self.engine.runtime.vars.get(
                          "player_name", "未命名"),
                      setter=lambda v: self.engine.set_var("player_name", v),
                      section="游戏")
        for key, label in (("key_up", "上移键"),
                           ("key_down", "下移键"),
                           ("key_confirm", "确认键")):
            self.register(key, label, "keybind",
                          getter=lambda k=key: self._keys_to_str(
                              getattr(self.engine, k)),
                          setter=lambda v, k=key: setattr(
                              self.engine, k,
                              self.engine._parse_keys(v)),
                          section="按键")

    def _resolve_item(self, key):
        """动态项: voice:<角色id> 的角色语音音量。"""
        if key.startswith(self._DYNAMIC_PREFIX):
            cid = key[len(self._DYNAMIC_PREFIX):]
            rt = self.engine.runtime

            def getter():
                ch = rt.characters.get(cid, {})
                try:
                    return float(ch.get("voice_volume", 1.0))
                except (TypeError, ValueError):
                    return 1.0

            def setter(v):
                ch = rt.characters.get(cid)
                if ch:
                    ch["voice_volume"] = max(0.0, min(1.0, float(v)))
            return {"key": key, "label": f"{cid} 语音", "kind": "slider",
                    "getter": getter, "setter": setter,
                    "min": 0.0, "max": 1.0, "step": 0.05,
                    "options": None, "visible": True, "on_click": None,
                    "section": "语音"}   # 各角色语音默认归并到"语音"栏
        return None

    def _get_item(self, key):
        return self.items.get(key) or self._resolve_item(key)

    def _sections(self) -> list:
        """分栏列表 (保序去重; 含全部已注册/动态项的分栏)。"""
        out = []
        for key in self.order:
            item = self._get_item(key)
            if item and item.get("section"):
                sec = item["section"]
                if sec not in out:
                    out.append(sec)
        return out

    def visible_keys(self) -> list:
        """当前分栏下显示的设置键 (顺序)。"""
        cur = self._current_section
        if cur is None:
            secs = self._sections()
            cur = secs[0] if secs else None
        out = []
        for key in self.order:
            item = self._get_item(key)
            if not item or not item.get("visible", True):
                continue
            if cur is None or item.get("section") == cur:
                out.append(key)
        return out

    # ==================================================================
    # 存取 (save/settings.json)
    # ==================================================================
    def save(self) -> None:
        data = {}
        for key in self.order:
            item = self._get_item(key)
            if not item or item.get("getter") is None:
                continue
            try:
                data[key] = item["getter"]()
            except Exception:
                pass
        self.engine.save.set_settings(data)

    def load(self) -> None:
        data = self.engine.save.get_settings() or {}
        for key, value in data.items():
            item = self._get_item(key)
            if item and item.get("setter") is not None:
                try:
                    item["setter"](value)
                except Exception:
                    pass

    def get(self, key, default=None):
        """插件 API: 读取设置值。"""
        item = self._get_item(key)
        if not item or item.get("getter") is None:
            return default
        try:
            return item["getter"]()
        except Exception:
            return default

    def set(self, key, value) -> bool:
        """插件 API: 写入设置值 (应用并保存)。"""
        item = self._get_item(key)
        if not item or item.get("setter") is None:
            return False
        try:
            item["setter"](value)
            self.save()
            self.engine.emit("setting_changed", key=key, value=value)
            return True
        except Exception as exc:
            log.warning(f"设置 {key} 写入失败: {exc}")
            return False

    # ==================================================================
    # 配置 (setting.gal: settings 块 + setting 子块)
    # ==================================================================
    def apply_config(self, stmt) -> None:
        """应用 settings 块 (布局属性 + 条目覆盖/顺序)。"""
        cfg = stmt.kwargs
        if "title" in cfg:
            self.title = str(cfg["title"])
        if "columns" in cfg:
            try:
                self.columns = max(1, int(float(cfg["columns"])))
            except (TypeError, ValueError):
                pass
        if "bg" in cfg:
            self.bg = str(cfg["bg"])
        for sub in stmt.block:      # setting <key> 子块
            if sub.op != "setting":
                continue
            key = sub.args[0] if sub.args else ""
            props = dict(sub.kwargs)
            if key not in self.items and not self._resolve_item(key):
                # 未注册项: 尝试按 props 动态注册 (插件项应在插件 on_load 注册,
                # 这里兜底注册一个通用项)
                self.register(key, kind=props.get("type", "slider"),
                              label=props.get("label", key),
                              options=props.get("options"))
            item = self._get_item(key)
            if not item:
                continue
            if "label" in props:
                item["label"] = str(props["label"])
            if "section" in props:
                item["section"] = str(props["section"])
            if "type" in props:
                item["kind"] = str(props["type"])
            if "options" in props:
                item["options"] = [s.strip() for s in
                                   str(props["options"]).split(",")
                                   if s.strip()]
            if "visible" in props:
                item["visible"] = str(props["visible"]).lower() in (
                    "true", "1", "yes", "on")
            # 重新排列: 按子块出现顺序 (动态项也进入 order 以参与保存)
            if key in self.order:
                self.order.remove(key)
            self.order.append(key)
        log.info(f"设置配置已应用: {self.title} 列x{self.columns} "
                 f"{len(self.order)} 项")

    # ==================================================================
    # 打开 / 关闭
    # ==================================================================
    def _open(self, engine, params, source):
        """action settings_open: 打开设置界面。"""
        self.open()
        return True

    def open(self) -> None:
        self.active = True
        self._binding = None
        self._hover = -1
        secs = self._sections()
        self._current_section = secs[0] if secs else None
        self.engine.paused = True
        # 不关闭底层菜单: 从标题/ESC 菜单进入时保留, 返回自然恢复
        self.engine.display.slot_menu_active = False
        self.engine.emit("settings_open")

    def close(self) -> None:
        if not self.active:
            return
        self.active = False
        self._binding = None
        self.save()
        # 从标题/ESC 菜单进入时菜单保留在底层 -> 返回后保持菜单暂停状态;
        # 游戏中进入 -> 恢复游戏
        d = self.engine.display
        self.engine.paused = bool(d.selection_active)
        self.engine.emit("settings_close")

    # ==================================================================
    # 交互
    # ==================================================================
    def _on_click(self, pos, **kw):
        if not self.active:
            return None
        d = self.engine.display
        if d.confirm_active or d.error_active or d.slot_menu_active:
            return None        # 确认框/错误弹窗/槽位界面优先, 不拦截
        # 返回按钮
        if self._back_rect is not None and self._back_rect.collidepoint(pos):
            self.close()
            return False
        self._handle_click(pos)
        return False              # 消费点击

    def _on_escape(self, **kw):
        if self.active:
            self.close()
            return False
        return None

    def handle_key(self, key) -> None:
        """设置界面键盘: keybind 捕获 / 左右调节。"""
        if self._binding is not None:
            if key in (pygame.K_ESCAPE,):
                self._binding = None     # ESC 取消绑定 (由 on_escape 关闭界面)
                return
            try:
                name = pygame.key.name(key)
            except Exception:
                name = str(key)
            item = self._get_item(self._binding)
            if item and item.get("setter"):
                item["setter"](name)
                self.save()
            self.engine.display.show_notice(
                f"{item['label'] if item else ''} -> {name}", 1.2)
            self._binding = None
            return
        if key in (pygame.K_LEFT, pygame.K_RIGHT) and self._hover >= 0:
            keys = self.visible_keys()
            if 0 <= self._hover < len(keys):
                self._step(keys[self._hover],
                           -1 if key == pygame.K_LEFT else 1)

    def _step(self, key, delta: int) -> None:
        """方向键调节 slider/cycle。"""
        item = self._get_item(key)
        if not item:
            return
        if item["kind"] == "slider":
            cur = float(item["getter"]() or 0)
            self.set(key, max(item["min"], min(item["max"],
                                               cur + delta * item["step"])))
        elif item["kind"] == "cycle" and item.get("options"):
            cur = item["getter"]()
            opts = item["options"]
            try:
                idx = opts.index(cur)
            except ValueError:
                idx = 0
            self.set(key, opts[(idx + delta) % len(opts)])

    def _handle_click(self, pos) -> None:
        # 分栏 (tab) 切换
        for sec, rect in getattr(self, "_tab_rects", []):
            if rect.collidepoint(pos):
                self._current_section = sec
                self._hover = -1
                return
        keys = self.visible_keys()
        rects = self._item_rects()
        for i, rect in enumerate(rects):
            if not rect.collidepoint(pos):
                continue
            self._hover = i
            if i >= len(keys):
                return
            key = keys[i]
            item = self._get_item(key)
            if not item:
                return
            kind = item["kind"]
            if kind == "slider":
                self._click_slider(item, pos, rect)
            elif kind == "checkbox":
                self.set(key, not bool(item["getter"]()))
            elif kind == "cycle":
                # 左右半区切换
                if pos[0] < rect.centerx:
                    self._step(key, -1)
                else:
                    self._step(key, 1)
            elif kind == "keybind":
                self._binding = key
                self.engine.display.show_notice(
                    f"按下新按键 (ESC 取消)", 2.0)
            elif kind == "button" and item.get("on_click"):
                try:
                    item["on_click"](self.engine)
                except Exception as exc:
                    log.warning(f"设置按钮 {key} 执行失败: {exc}")
            return

    def _click_slider(self, item, pos, rect) -> None:
        """点击滑条轨道设值 (step 对齐)。"""
        track = self._slider_track(rect)
        if track.w <= 0:
            return
        ratio = (pos[0] - track.x) / track.w
        ratio = max(0.0, min(1.0, ratio))
        value = item["min"] + ratio * (item["max"] - item["min"])
        step = max(0.0001, item["step"])
        value = round(value / step) * step
        self.set(item["key"], max(item["min"], min(item["max"], value)))

    # ==================================================================
    # 布局 / 绘制
    # ==================================================================
    def _panel(self):
        w, h = self.engine.width, self.engine.height
        return pygame.Rect(int(w * 0.06), int(h * 0.08),
                           int(w * 0.88), int(h * 0.84))

    def _item_rects(self) -> list:
        panel = self._panel()
        keys = self.visible_keys()
        cols = max(1, self.columns)
        rows = max(1, (len(keys) + cols - 1) // cols)
        gap_x, gap_y = 18, 10
        cw = (panel.w - 40 - gap_x * (cols - 1)) // cols
        ch = 54
        # 内容区从标题 + 分栏行下方开始
        y0 = panel.y + 104
        rects = []
        for i in range(len(keys)):
            r, c = divmod(i, cols)
            x = panel.x + 20 + c * (cw + gap_x)
            y = y0 + r * (ch + gap_y)
            rects.append(pygame.Rect(x, y, cw, ch))
        return rects

    def _slider_track(self, rect) -> pygame.Rect:
        tw = int(rect.w * 0.42)
        return pygame.Rect(rect.right - tw - 12, rect.centery - 4, tw, 8)

    def _keys_to_str(self, keys) -> str:
        return ", ".join(pygame.key.name(k) for k in keys)

    def _draw(self, surface, **kw):
        if not self.active:
            return
        ui = self.engine.ui
        w, h = surface.get_size()
        # 确认框/错误弹窗打开时: 只画暗化底, 让引擎覆盖层正常显示
        if (self.engine.display.confirm_active
                or self.engine.display.error_active):
            ui.dim_overlay(surface, 120)
            return
        ui.dim_overlay(surface, 150)
        panel = self._panel()
        bg = self._load_img(self.bg)
        self._panel_or_image(surface, panel, bg,
                             (22, 22, 36, 245), (120, 120, 160), 2, 12)
        # 标题 + 返回
        ui.text(surface, self.engine.get_font(34), self.title,
                color=(255, 220, 130), center=(panel.centerx, panel.y + 30))
        back = pygame.Rect(panel.right - 96, panel.y + 12, 76, 34)
        self._back_rect = back
        mouse = self.engine.display.mouse_pos()
        hover_back = back.collidepoint(mouse)
        ui.panel(surface, back,
                 bg_color=(*(80, 50, 50), 235) if hover_back else (50, 40, 40),
                 border_color=(220, 130, 130) if hover_back else (120, 80, 80),
                 border_width=2, radius=8)
        ui.text(surface, self.engine.get_font(18), "返回",
                color=(255, 255, 255), center=back.center)
        # 分栏 (tab) 行
        secs = self._sections()
        cur = self._current_section or (secs[0] if secs else None)
        tab_font = self.engine.get_font(20)
        self._tab_rects = []
        tx = panel.x + 20
        ty = panel.y + 56
        for sec in secs:
            w_sec = tab_font.size(sec)[0] + 32
            rect = pygame.Rect(tx, ty, w_sec, 34)
            self._tab_rects.append((sec, rect))
            active = (sec == cur)
            hovered = rect.collidepoint(mouse)
            ui.panel(surface, rect,
                     bg_color=(*(233, 69, 96), 240) if active
                     else (*(70, 60, 80), 230) if hovered else (45, 45, 66),
                     border_color=(255, 210, 130) if active else (90, 90, 120),
                     border_width=2, radius=8)
            ui.text(surface, tab_font, sec,
                    color=(255, 255, 255), center=rect.center)
            tx += w_sec + 10
        # 条目
        keys = self.visible_keys()
        rects = self._item_rects()
        self._hover = -1
        for i, rect in enumerate(rects):
            if rect.collidepoint(mouse):
                self._hover = i
            if i >= len(keys):
                break
            item = self._get_item(keys[i])
            if not item:
                continue
            hovered = (i == self._hover)
            self._draw_item(surface, item, rect, hovered, mouse)
        # 绑定提示
        if self._binding:
            ui.text(surface, self.engine.get_font(18),
                    "按下新按键 (ESC 取消) …", color=(255, 210, 130),
                    center=(w // 2, h - 28))

    def _draw_item(self, surface, item, rect, hovered, mouse):
        ui = self.engine.ui
        ui.panel(surface, rect,
                 bg_color=(*(60, 60, 82), 230) if hovered else (38, 38, 56),
                 border_color=(255, 210, 130) if hovered else (80, 80, 110),
                 border_width=2, radius=8)
        font = self.engine.get_font(20)
        label = str(item.get("label", item["key"]))
        ui.text(surface, font, label, color=(230, 230, 238),
                pos=(rect.x + 12, rect.y + 8))
        kind = item["kind"]
        try:
            value = item["getter"]()
        except Exception:
            value = None
        if kind == "slider":
            track = self._slider_track(rect)
            ui.panel(surface, track, bg_color=(20, 20, 30),
                     border_color=(100, 100, 130), border_width=1, radius=4)
            try:
                ratio = ((float(value) - item["min"])
                         / max(0.0001, item["max"] - item["min"]))
            except (TypeError, ValueError):
                ratio = 0
            ratio = max(0.0, min(1.0, ratio))
            fill = pygame.Rect(track.x, track.y,
                               max(6, int(track.w * ratio)), track.h)
            ui.panel(surface, fill, bg_color=(233, 69, 96, 240),
                     border_width=0, radius=4)
            ui.text(surface, self.engine.get_font(16),
                    f"{float(value):.2f}", color=(200, 200, 210),
                    center=(track.centerx, track.y + track.h + 12))
        elif kind == "checkbox":
            box = pygame.Rect(rect.right - 48, rect.centery - 14, 28, 28)
            on = bool(value)
            ui.panel(surface, box,
                     bg_color=(*(233, 69, 96), 240) if on else (30, 30, 44),
                     border_color=(255, 210, 130) if on else (120, 120, 150),
                     border_width=2, radius=6)
            if on:
                ui.text(surface, self.engine.get_font(20), "✓",
                        color=(255, 255, 255), center=box.center)
        elif kind == "cycle":
            txt = str(value if value is not None else "")
            ui.text(surface, font, "◀", color=(200, 200, 210),
                    center=(rect.right - 64, rect.centery + 4))
            ui.text(surface, font, txt, color=(255, 230, 170),
                    center=(rect.centerx, rect.centery + 4))
            ui.text(surface, font, "▶", color=(200, 200, 210),
                    center=(rect.right - 20, rect.centery + 4))
        elif kind == "keybind":
            txt = str(value if value is not None else "未设置")
            ui.text(surface, self.engine.get_font(17), txt,
                    color=(255, 210, 130), pos=(rect.right - 150,
                                                rect.centery - 8))
        elif kind == "button":
            pass

    def _panel_or_image(self, surface, rect, img, bg_color, border_color,
                        border_width, radius):
        ui = self.engine.ui
        if img is not None:
            surface.blit(ui.nine_slice(img, rect), rect.topleft)
        else:
            ui.panel(surface, rect, bg_color=bg_color,
                     border_color=border_color,
                     border_width=border_width, radius=radius)

    def _load_img(self, path):
        if not path:
            return None
        if path in self._img_cache:
            return self._img_cache[path]
        real = self.engine.resolve_path(path)
        img = None
        try:
            img = pygame.image.load(real).convert_alpha()
        except Exception:
            img = None
        self._img_cache[path] = img
        return img
