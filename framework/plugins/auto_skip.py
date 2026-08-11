"""自动模式 / 跳过剧情 插件 (auto_skip)。

在系统菜单 (ESC 弹窗 popup / bar 常驻栏共用 menu system) 提供:

* **自动模式**: 文本显示完毕后自动推进下一句; 选择支/标题暂停;
  标题/鉴赏/菜单等非正式游戏界面时自动关闭, 回到正式界面自动恢复。
  开启/关闭时菜单按钮切换激活样式 (脚本可配置 image_active 图)。
* **跳过剧情**: 快进到下一个**选择支/标题/结局**之前 (跳过文本/等待/
  移动动画; 背景等场景指令正常执行到位); 再次点击可取消。

按钮样式在 ui.gal 的 ``menu system`` 中配置 (action: auto_toggle /
skip_once, 支持 image/image_focus/image_active/image_disabled 等),
插件只负责挂接 action 与状态切换; 未在脚本中定义时自动追加默认按钮。

依赖引擎扩展: register_menu_button / set_menu_button_cfg /
runtime.skip_mode (advance 快进) / draw_overlay。
"""

import pygame

from framework.api import Plugin


class AutoSkipPlugin(Plugin):
    name = "auto_skip"
    version = "1.0"

    AUTO_DELAY = 1.2          # 自动模式: 文本完成后等待秒数
    AUTO_BUTTON = "自动模式"
    SKIP_BUTTON = "跳过剧情"

    def on_load(self):
        self.auto_on = False
        self._auto_wanted = False     # 用户意图 (非正式界面时临时关闭)
        self._auto_t = 0
        self._skip_running = False
        self._btn_styles = {}         # 按钮名 -> 原始 cfg (恢复样式用)

        self.engine.register_action("auto_toggle", self._toggle_auto)
        self.engine.register_action("skip_once", self._do_skip)

        @self.listen("script_load")
        def _on_script_load(**kw):
            # 菜单定义就绪 (popup/bar 共用 menu system): 挂接/添加按钮
            self._ensure_menu()

        @self.listen("draw_overlay")
        def _on_draw(surface, **kw):
            self._sync_auto_state()
            self._auto_tick()
            if self.auto_on:
                self._draw_indicator(surface, "自动", (120, 220, 255))
            elif self._skip_running:
                self._draw_indicator(surface, "跳过", (255, 200, 120))

    def on_unload(self):
        self.engine.actions.pop("auto_toggle", None)
        self.engine.actions.pop("skip_once", None)
        self.engine.runtime.skip_mode = False
        print("[插件] auto_skip 已卸载")

    # ------------------------------------------------------------------
    # 菜单按钮: 挂接 / 样式
    # ------------------------------------------------------------------
    def _ensure_menu(self):
        """挂接系统菜单按钮。

        脚本 menu system 已定义 (action: auto_toggle / skip_once) 时
        只挂接 action; 未定义时自动追加默认按钮 (无 menu system 时
        先补引擎内置五项)。
        """
        rt = self.engine.runtime
        if rt._menu_items("system") is None:
            # 无 menu system 定义: 先补引擎默认菜单 (含设置), 再追加
            for text, action, _cfg in self.engine.default_system_items():
                rt.add_menu_button("system", text, action)
        items = rt._menu_items("system") or []
        types = {a.get("type") for _t, a, _c in items
                 if isinstance(a, dict)}
        if "auto_toggle" not in types:
            rt.add_menu_button("system", self.AUTO_BUTTON,
                               {"type": "auto_toggle"})
        if "skip_once" not in types:
            rt.add_menu_button("system", self.SKIP_BUTTON,
                               {"type": "skip_once"})
        # 记住按钮原始样式 (激活状态切换用)
        for text, _a, cfg in (rt._menu_items("system") or []):
            if text in (self.AUTO_BUTTON, self.SKIP_BUTTON):
                self._btn_styles.setdefault(text, dict(cfg))

    def _close_system_menu(self, engine):
        """popup 模式: 点击后退出 ESC 菜单; bar 模式常驻无需关闭。"""
        if engine.display.system_menu_active:
            engine.close_system_menu()

    def _update_auto_button(self):
        """自动模式按钮激活样式: 切换 image_active 图 (脚本可配置)。"""
        orig = self._btn_styles.get(self.AUTO_BUTTON)
        if not orig or not orig.get("image_active"):
            return
        rt = self.engine.runtime
        if self.auto_on:
            img = orig["image_active"]
            rt.set_menu_button_cfg("system", self.AUTO_BUTTON,
                                   {"image": img, "image_focus": img})
        else:
            rt.set_menu_button_cfg("system", self.AUTO_BUTTON,
                                   {"image": orig.get("image"),
                                    "image_focus": orig.get("image_focus")})
        if self.engine.display.system_menu_active:
            self.engine.display.sync_selection_cfg("system")

    # ------------------------------------------------------------------
    # 自动模式
    # ------------------------------------------------------------------
    def _toggle_auto(self, engine, params, source):
        """action auto_toggle: 切换自动模式 (点击后退出 ESC 菜单)。

        翻转基于用户意图 _auto_wanted (而非显示状态 auto_on:
        菜单等非正式界面时 auto_on 会被临时置 False, 用显示值
        翻转会导致无法关闭)。
        """
        self._auto_wanted = not self._auto_wanted
        self.auto_on = self._auto_wanted
        self._auto_t = 0
        if self.auto_on:
            self._skip_running = False
            engine.runtime.skip_mode = False
        self._update_auto_button()
        engine.display.show_notice(
            "自动模式：开" if self.auto_on else "自动模式：关", 1.2)
        self._close_system_menu(engine)
        return False

    def _sync_auto_state(self):
        """非正式游戏界面 (标题/鉴赏/菜单/确认框等) 时自动关闭自动模式,
        回到正式游戏界面自动恢复 (按用户意图)。"""
        d = self.engine.display
        in_game = not (d.title_active or d.selection_active
                       or d.slot_menu_active or d.confirm_active
                       or d.error_active or self.engine.paused)
        self.auto_on = bool(self._auto_wanted and in_game)
        if not in_game:
            self._auto_t = 0

    def _auto_tick(self):
        """自动推进: 文本显示完毕后等待 AUTO_DELAY 秒自动下一句。"""
        if not self.auto_on:
            self._auto_t = 0
            return
        d = self.engine.display
        if not d.text_active or not d.text_done():
            self._auto_t = 0
            return
        now = pygame.time.get_ticks()
        if self._auto_t == 0:
            self._auto_t = now
        elif now - self._auto_t >= self.AUTO_DELAY * 1000:
            self._auto_t = 0
            # 与键盘推进同路径 (走完整 on_click: 停语音/播UI音效/advance)
            self.engine.on_click((self.engine.width // 2,
                                  self.engine.height // 2))

    # ------------------------------------------------------------------
    # 跳过剧情
    # ------------------------------------------------------------------
    def _do_skip(self, engine, params, source):
        """action skip_once: 快进到下一个选择支/标题/结局之前
        (点击后退出 ESC 菜单; 再次点击可取消)。"""
        rt = engine.runtime
        if rt.skip_mode:
            rt.skip_mode = False
            self._skip_running = False
            engine.display.show_notice("已取消跳过", 1.0)
            self._close_system_menu(engine)
            return False
        self.auto_on = False
        self._auto_wanted = False
        self._auto_t = 0
        rt.skip_mode = True
        self._skip_running = True
        try:
            rt.blocked = None          # 跳过当前文本/等待阻塞
            rt.advance()               # 直达 choice/title/ending
        finally:
            rt.skip_mode = False
            self._skip_running = False
            # 清理跳过期间可能残留的动画状态 (背景过渡/立绘效果),
            # 避免画面鬼畜/卡死
            dd = self.engine.display
            dd._transition = None
            dd.bg_fading = False
            for spr in dd.sprites.values():
                spr.effect = None
        d = engine.display
        if d.choice_active:
            engine.display.show_notice("已跳转到选择支", 1.2)
        elif d.title_active:
            engine.display.show_notice("已跳转到标题", 1.2)
        elif rt.ended:
            engine.display.show_notice("已跳转到结局", 1.2)
        else:
            engine.display.show_notice("跳过完成", 1.0)
        self._close_system_menu(engine)
        return False

    # ------------------------------------------------------------------
    def _draw_indicator(self, surface, label, color):
        """右上角状态指示 (自动/跳过)。"""
        font = self.engine.get_font(18)
        surf = font.render(f"[{label}]", True, color)
        x = surface.get_width() - surf.get_width() - 12
        y = 10
        pygame.draw.rect(surface, (0, 0, 0, 150),
                         (x - 6, y - 3, surf.get_width() + 12,
                          surf.get_height() + 6))
        surface.blit(surf, (x, y))
