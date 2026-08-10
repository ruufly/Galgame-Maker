"""GameEngine: 引擎主类。组装渲染/音频/存档/运行时/插件, 驱动主循环。

插件与游戏代码通过引擎实例访问全部功能::

    engine.display    渲染层 (背景/立绘/文本/选项)
    engine.audio      音频
    engine.save       存档
    engine.runtime    脚本运行时 (vars / evaluate / jump ...)
    engine.events     事件总线 (订阅插件事件)
    engine.commands   指令注册表 (注册自定义 DSL 指令)
    engine.plugins    插件管理器
"""

import os

import pygame

from framework.engine import log, ui as ui_module
from framework.engine.audio import Audio
from framework.engine.display import Display
from framework.engine.runtime import Runtime
from framework.engine.save import SaveManager
from framework.api.events import EventBus
from framework.api.commands import CommandRegistry
from framework.api.plugin import PluginManager


class GameEngine:
    """视觉小说游戏引擎。"""

    def __init__(self, width: int = 1280, height: int = 720,
                 title: str = "Galgame Maker Engine", fps: int = 60,
                 plugins_dir: str = None, autoload_plugins: bool = True,
                 fullscreen: bool = False) -> None:
        self.width = width
        self.height = height
        self.title = title
        self.fps = fps
        self.fullscreen = fullscreen
        self.project_dir = os.getcwd()
        self.script_dir = None

        pygame.init()
        try:
            flags = pygame.FULLSCREEN if fullscreen else 0
            self.screen = pygame.display.set_mode((width, height), flags)
        except pygame.error as exc:
            log.error(f"无法创建窗口: {exc}")
            raise
        pygame.display.set_caption(title)

        self.clock = pygame.time.Clock()
        self.running = False

        # UI 绘制原语 (panel/text/wrap_text/multiline_text/dim_overlay)
        self.ui = ui_module

        # 字体缓存 (需在 Display 之前初始化, Display 构造会取字体)
        self._font_cache = {}
        self._font_path = self._find_font()
        if self._font_path:
            log.info(f"使用字体: {self._font_path}")

        # 模块组装
        self.events = EventBus()
        self.commands = CommandRegistry(self)
        self.plugins = PluginManager(self)
        self.audio = Audio(self)

        # 富文本渲染器 (标记解析 + 行内样式 + LaTeX 公式), 需在 Display 之前
        from framework.engine.rich import RichTextRenderer
        self.rich = RichTextRenderer(self)

        self.display = Display(self, width, height)
        self.save = SaveManager(self)
        self.runtime = Runtime(self)

        # 插件目录
        if plugins_dir is None:
            plugins_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "plugins")
        self.plugins_dir = plugins_dir
        self.autoload_plugins = autoload_plugins

        # 退出确认 (window 配置, 脚本可自定义)
        self.confirm_quit_enabled = False
        self.confirm_quit_text = "确定要退出游戏吗？"
        self.confirm_quit_yes = "退出"
        self.confirm_quit_no = "继续游戏"
        self.confirm_load_enabled = False
        self.confirm_load_text = "确定要读取这个存档吗？"
        self.confirm_load_yes = "读档"
        self.confirm_load_no = "取消"
        self._confirm_callback = None
        self.paused = False          # 系统菜单打开时暂停游戏

        # 键盘导航键位 (window 配置可自定义: key_up/key_down/key_confirm)
        self.key_up = [pygame.K_UP]
        self.key_down = [pygame.K_DOWN]
        self.key_confirm = [pygame.K_RETURN, pygame.K_SPACE]

        # UI 交互音效 (window 配置 ui_click_sound, 按钮确认时播放)
        self.ui_click_sound = None
        self.ui_hover_sound = None      # 活动选项变化时播放 (菜单/choice 配置)
        self._default_ui_click = None   # window 默认点击音 (临时覆盖后恢复用)
        self._last_active_index = -1
        self._last_game_frame = None   # 最近一次纯游戏画面 (存档快照用)

        # 错误处理: 记录日志 + 游戏内弹窗
        from framework.engine.error import ErrorHandler
        self.error_handler = ErrorHandler(self)

        # 对话框 (dialog) 配置: 退出/读档/返回标题等确认框统一归并
        self.dialogs = {
            "quit": {"enabled": self.confirm_quit_enabled,
                     "text": self.confirm_quit_text,
                     "yes": self.confirm_quit_yes,
                     "no": self.confirm_quit_no},
            "load": {"enabled": self.confirm_load_enabled,
                     "text": self.confirm_load_text,
                     "yes": self.confirm_load_yes,
                     "no": self.confirm_load_no},
            "title": {"enabled": False, "text": "确定要返回标题画面吗？",
                      "yes": "返回标题", "no": "取消"},
        }
        # ESC 系统菜单文案 (window 配置可自定义)
        self.menu_texts = {
            "continue": "继续游戏", "save": "存档", "load": "读取存档",
            "title": "返回标题", "quit": "退出游戏",
        }

        # 动作注册表 (selection 按钮/插件触发的事件)
        self.actions = {
            "start": self._act_start,        # 启动游戏 (跳转标签)
            "quit": self._act_quit,          # 关闭游戏 (退出确认)
            "title": self._act_title,        # 回到标题
            "continue": self._act_continue,  # 关闭菜单继续
            "slot_menu": self._act_slot_menu,  # 打开存档/读档页面
            "save": self._act_save,          # 直接存档
            "load": self._act_load,          # 直接读档
            "close": self._act_close,        # 关闭当前选择列表
        }

    # ==================================================================
    # 字体
    # ==================================================================
    def _find_font(self) -> str:
        """在候选位置寻找字体文件 (思源黑体 / Ubuntu)。"""
        candidates = []
        for base in (self.project_dir,
                     os.path.dirname(os.path.abspath(__file__)),
                     os.getcwd()):
            for rel in ("fonts/SourceHanSansSC.otf", "fonts/Ubuntu-R.ttf",
                        "SourceHanSansSC.otf", "Ubuntu-R.ttf"):
                candidates.append(os.path.join(base, rel))
        for path in candidates:
            if os.path.isfile(path):
                return path
        return None

    def get_font(self, size: int, family: str = "default",
                 bold: bool = False, italic: bool = False):
        """按 (字号, 字体族, 粗体, 斜体) 获取 pygame 字体 (带缓存)。

        同一字号的不同样式使用独立 Font 对象, 避免样式状态互相污染。
        """
        key = (family, size, bold, italic)
        if key in self._font_cache:
            return self._font_cache[key]
        font = None
        if self._font_path:
            try:
                font = pygame.font.Font(self._font_path, size)
            except Exception:
                font = None
        if font is None:
            font = pygame.font.SysFont("microsoftyahei,simhei,arial", size)
        if bold:
            font.set_bold(True)
        if italic:
            font.set_italic(True)
        self._font_cache[key] = font
        return font

    # ==================================================================
    # 资源路径
    # ==================================================================
    def resolve_path(self, path: str) -> str:
        """把脚本里的相对路径解析为绝对路径 (相对脚本所在目录)。"""
        if os.path.isabs(path):
            return path
        base = self.script_dir or self.project_dir
        return os.path.normpath(os.path.join(base, path))

    def set_icon(self, path: str) -> None:
        """设置窗口图标 (路径相对脚本所在目录)。"""
        try:
            real = self.resolve_path(path)
            icon = pygame.image.load(real)
            pygame.display.set_icon(icon)
            log.info(f"窗口图标已设置: {real}")
        except Exception as exc:
            log.warning(f"设置窗口图标失败 {path}: {exc}")

    # ==================================================================
    # 事件 (统一在事件上下文里附带 engine 引用, 方便插件取用)
    # ==================================================================
    def emit(self, event_name: str, **kwargs):
        """发布引擎事件。自动附带 engine=self, 插件处理器可
        ``def handler(engine, **kw)`` 或 ``def handler(**kw)``。"""
        kwargs.setdefault("engine", self)
        return self.events.emit(event_name, **kwargs)

    # ==================================================================
    # 主入口
    # ==================================================================
    def run(self, script_path: str) -> None:
        """加载脚本、启动插件、进入主循环。"""
        script_path = os.path.abspath(script_path)
        self.script_dir = os.path.dirname(script_path)
        self.project_dir = self.script_dir

        if self.autoload_plugins:
            # 脚本顶层的 plugins 块可指定装载哪些插件
            plugins_cfg = self._extract_plugins_config(script_path)
            self.plugins.discover(self.plugins_dir, plugins_cfg)
        self.emit("engine_start", engine=self)

        try:
            self.runtime.load_script(script_path)
            self.runtime.start()
        except Exception as exc:
            log.error(f"脚本加载/启动失败: {exc}")
            import traceback
            traceback.print_exc()
            self.running = False
        else:
            self.running = True

        self.main_loop()

        self.emit("engine_quit", engine=self)
        self.plugins.unload_all()
        pygame.quit()

    # ==================================================================
    # 主循环
    # ==================================================================
    def main_loop(self) -> None:
        while self.running:
            try:
                dt = self.clock.tick(self.fps) / 1000.0
                for event in pygame.event.get():
                    self.handle_event(event)
                self.update(dt)
                self.draw()
            except Exception as exc:
                self.handle_error(exc)   # 记录 + 弹窗, 不崩溃

    def handle_event(self, event) -> None:
        if event.type == pygame.QUIT:
            self.request_quit()   # 右上角关闭按钮 -> 退出确认
        elif event.type == pygame.KEYDOWN:
            self._handle_key(event.key)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.on_click(event.pos)

    def _handle_key(self, key) -> None:
        if key in self.key_up:
            self.display.move_active(-1)
        elif key in self.key_down:
            self.display.move_active(1)
        elif key in self.key_confirm:
            d = self.display
            if d.selection_active:
                # 确认活动选项 (无活动项时忽略)
                if d.active_index >= 0 and d.selection_rects:
                    self.on_click(d.selection_rects[d.active_index].center)
                return
            elif d.choice_active:
                if d.active_index >= 0 and d.choice_rects:
                    self.on_click(d.choice_rects[d.active_index].center)
                return
            else:
                # 无活动界面: 推进文本
                self.on_click((self.width // 2, self.height // 2))
        elif key == pygame.K_ESCAPE:
            self.on_escape()

    def on_escape(self) -> None:
        """ESC: 逐层关闭/打开菜单。"""
        d = self.display
        if d.confirm_active:
            return                       # 确认框优先, ESC 不干预
        if d.slot_menu_active:
            d.slot_menu_active = False   # 槽位界面 -> 返回上一层
            return
        if d.system_menu_active:
            self.close_system_menu()     # 系统菜单 -> 继续游戏
            return
        if d.title_active:
            self.request_quit()          # 标题画面 -> 退出确认
            return
        self.open_system_menu()          # 游戏中 -> 打开系统菜单

    # ==================================================================
    # 系统菜单 / 存档选择 / 回标题
    # ==================================================================
    def open_system_menu(self) -> None:
        """打开游戏内菜单 (暂停游戏), 文案由 menu_texts 配置;
        脚本定义 menu system 可整体覆盖。"""
        self.paused = True
        items = self.runtime._menu_items("system")
        if items is None:
            items = [
                (self.menu_texts["continue"], {"type": "continue"}, {}),
                (self.menu_texts["save"], {"type": "slot_menu", "mode": "save"}, {}),
                (self.menu_texts["load"], {"type": "slot_menu", "mode": "load"}, {}),
                (self.menu_texts["title"], {"type": "title"}, {}),
                (self.menu_texts["quit"], {"type": "quit"}, {}),
            ]
        else:
            self._set_ui_sounds(self.runtime._menu_ui("system"))
        self.display.show_system_menu(items)
        self.emit("menu_open")

    def close_system_menu(self) -> None:
        self.display.close_selection()
        self.paused = False
        self.emit("menu_close")

    def _perform_load(self, slot: int) -> None:
        """执行读档 (确认通过后), 并关闭所有菜单层回到游戏。"""
        self.load_game(slot)
        d = self.display
        d.close_selection()       # 关闭 selection / 标题 / 系统菜单
        d.slot_menu_active = False
        d.confirm_active = False
        self.paused = False

    def goto_title(self) -> None:
        """结束当前游戏流程, 回到 start 标签 (通常为标题画面)。"""
        d = self.display
        d.clear_text()
        d.clear_sprites()
        d.clear_bg()          # 清掉旧场景, 由 start 块重新布置
        d.clear_fade()        # 清除黑幕/结束画面/未完成过渡
        self.audio.stop_voice()
        d.close_selection()
        d.slot_menu_active = False
        d.confirm_active = False
        d.choice_active = False
        self.paused = False
        rt = self.runtime
        if "start" in rt.labels:
            rt.call_stack = []
            rt.blocked = None
            rt.sleep_until = None
            rt.running = True
            rt.ended = False
            rt._jump_to("start")
            rt.advance()
        else:
            self.quit()
        self.emit("goto_title")

    # ==================================================================
    # 点击推进逻辑
    # ==================================================================
    def on_click(self, pos) -> None:
        """处理一次点击: 错误弹窗 -> 确认框 -> 槽位界面 -> 选择列表..."""
        d = self.display
        # 0) 错误弹窗 (最高优先级)
        if d.error_active:
            idx = d.hit_error(pos)
            if idx < 0:
                return
            if idx == 0:      # 继续游戏
                d.error_active = False
                d.error_info = None
                self.paused = False
            elif idx == 1:    # 复制完整报错
                text = d.error_info.get("traceback") \
                    if d.error_info else ""
                if self.copy_to_clipboard(text):
                    d.show_notice("完整报错已复制到剪贴板", 2.0)
                else:
                    d.show_notice("复制失败, 请从日志文件复制", 2.0)
            elif idx == 2:    # 退出游戏
                self.quit()
            return
        # 1) 确认对话框 (最高优先级)
        if d.confirm_active:
            idx = d.hit_confirm(pos)
            if idx < 0:
                return
            d.confirm_active = False
            cb = self._confirm_callback
            self._confirm_callback = None
            if idx == 0:
                self._play_ui_sound()
            self.emit("confirm_choice", index=idx)
            if idx == 0 and cb is not None:
                cb()      # 是 -> 执行确认后的动作
            return
        # 1) 存档槽位选择界面
        if d.slot_menu_active:
            hit = d.hit_slot_menu(pos)
            if hit is None:
                return
            if hit != "back":
                self._play_ui_sound()
            if hit == "back":
                d.slot_menu_active = False   # 返回上一层 (菜单/标题)
                return
            info = d.slot_menu_slots[hit]
            if d.slot_menu_mode == "save":
                self.save_game(info["slot"], silent=False)
                d.slot_menu_active = False
                d.system_menu_active = False
                self.paused = False
                d.show_notice(f"已保存到槽位 {info['slot'] + 1}", 1.5)
            else:
                if info.get("empty"):
                    d.show_notice("该槽位没有存档", 1.5)
                    return
                if self.confirm_load_enabled:
                    self.ask_confirm(
                        self.confirm_load_text, self.confirm_load_yes,
                        self.confirm_load_no,
                        lambda slot=info["slot"]: self._perform_load(slot))
                    return
                self._perform_load(info["slot"])
            return
        # 2) 选择列表 (标题画面 / 系统菜单)
        if d.selection_active:
            idx = d.hit_selection(pos)
            if idx < 0:
                return
            text, action, _item_cfg = d.selection_items[idx]
            d.active_index = idx
            self._play_ui_sound()
            source = "title" if d.title_active else "menu"
            self.emit("selection_choice", index=idx, text=text,
                      action=action, source=source)
            self.run_action(action, source=source)
            return
        # 1) 选项
        if d.choice_active:
            idx = d.hit_choice(pos)
            if idx < 0:
                return
            d.active_index = idx
            self._play_ui_sound()
            text, label = d.choices[idx]
            self.emit("choice_made", index=idx, label=label, text=text)
            d.choice_active = False
            d.choices = []
            self.runtime.choose(idx, label)
            return
        # 2) 文本推进
        if d.text_active:
            if not d.text_done():
                d.finish_text()
                return
            self.audio.stop_voice()   # 先停语音 (避免与 UI 音效抢语音通道)
            self.emit("text_advance", text=d.full_text, speaker=d.speaker)
            d.clear_text()
            self.runtime.release("text")
            self.runtime.advance()
            return
        # 3) 无阻塞: 尝试推进脚本
        self.runtime.advance()

    # ==================================================================
    # 帧更新与绘制
    # ==================================================================
    def update(self, dt: float) -> None:
        # BGM 淡入淡出持续推进 (暂停菜单时音乐渐变不中断)
        self.audio.update(dt)
        if self.paused:
            # 暂停期间仍同步鼠标活动项 (ESC 菜单键盘/鼠标一致)
            self.display.sync_mouse_active()
            self._sync_hover_sound()
            return   # 系统菜单打开时暂停游戏逻辑 (菜单绘制仍进行)
        self.display.update(dt)
        self._sync_hover_sound()
        self.runtime.tick(dt)

    def _sync_hover_sound(self) -> None:
        """活动选项变化时播放 UI 悬停音效。"""
        d = self.display
        if d.selection_active or d.choice_active:
            ai = d.active_index
            if ai != self._last_active_index:
                self._last_active_index = ai
                if ai >= 0:
                    self._play_ui_sound("hover")
        else:
            self._last_active_index = -1

    def draw(self) -> None:
        # 记录最近一次纯游戏画面 (无覆盖层时; 供存档快照插件截图)
        d = self.display
        if not (d.slot_menu_active or d.title_active or d.selection_active
                or d.confirm_active or d.choice_active or d.error_active):
            self._last_game_frame = self.screen.copy()
        self.display.draw(self.screen)
        # 插件渲染钩子
        self.emit("draw_overlay", surface=self.screen, dt=0)
        pygame.display.flip()

    # ==================================================================
    # 供脚本/插件调用的高层 API
    # ==================================================================
    def say(self, speaker: str, text: str) -> None:
        """直接显示一条对话 (供插件调用)。"""
        self.display.show_text(text, speaker)
        self.runtime.blocked = "text"

    def show_text(self, text: str) -> None:
        self.say(None, text)

    def set_var(self, name: str, value) -> None:
        self.runtime.vars[name] = value

    def get_var(self, name: str, default=None):
        return self.runtime.vars.get(name, default)

    def jump(self, label: str) -> None:
        self.runtime._jump_to(label)
        self.runtime.advance()

    def change_bg(self, path: str, effect: str = None) -> None:
        self.display.set_bg(self.resolve_path(path), effect)

    def show_sprite(self, sid: str, path: str, pos="center", effect=None) -> None:
        self.display.show_sprite(sid, self.resolve_path(path), pos, effect=effect)

    def hide_sprite(self, sid: str) -> None:
        self.display.hide_sprite(sid)

    def quit(self) -> None:
        self.running = False

    def show_notice(self, text: str, seconds: float = 1.5) -> None:
        """在屏幕顶部显示一条通知 (供插件调用)。"""
        self.display.show_notice(text, seconds)

    # ==================================================================
    # 退出确认
    # ==================================================================
    def _extract_plugins_config(self, script_path: str) -> dict:
        """预解析脚本顶层的 plugins 块 (插件装载配置)。

        plugins
            only: "shake, fps_overlay"    # 只装载列出的插件 (文件名)
            # 或
            except: "fps_overlay"         # 排除列出的插件
        """
        try:
            from framework.engine.loader import load_script_with_imports
            script = load_script_with_imports(script_path)
            for stmt in script.statements:
                if stmt.op == "plugins":
                    cfg = {}
                    only = stmt.kwargs.get("only")
                    ex = stmt.kwargs.get("except")
                    if only:
                        cfg["only"] = [s.strip() for s in str(only).split(",")
                                       if s.strip()]
                    if ex:
                        cfg["except"] = [s.strip() for s in str(ex).split(",")
                                         if s.strip()]
                    log.info(f"插件装载配置: {cfg}")
                    return cfg
        except Exception as exc:
            log.warning(f"解析插件配置失败: {exc}")
        return {}

    _KEY_NAMES = {
        "up": pygame.K_UP, "down": pygame.K_DOWN, "left": pygame.K_LEFT,
        "right": pygame.K_RIGHT, "return": pygame.K_RETURN,
        "enter": pygame.K_RETURN, "space": pygame.K_SPACE,
        "esc": pygame.K_ESCAPE, "escape": pygame.K_ESCAPE,
        "tab": pygame.K_TAB, "backspace": pygame.K_BACKSPACE,
        "delete": pygame.K_DELETE, "home": pygame.K_HOME, "end": pygame.K_END,
    }

    def _parse_keys(self, value) -> list:
        """解析键位配置字符串: "up, w" / "return, space" -> [K_UP, K_w]"""
        out = []
        for part in str(value).split(","):
            name = part.strip().lower()
            if not name:
                continue
            k = self._KEY_NAMES.get(name)
            if k is None and len(name) == 1 and name.isalnum():
                k = getattr(pygame, f"K_{name}", None)
            if k is not None and k not in out:
                out.append(k)
        return out

    def apply_config(self, cfg: dict) -> None:
        """应用脚本 window 配置中的运行时选项 (窗口已在构造时创建)。

        确认框统一归并到 dialogs 表: confirm_quit -> quit,
        confirm_load -> load, confirm_title -> title。
        """
        for cfg_key, dlg_name in (("confirm_quit", "quit"),
                                  ("confirm_load", "load"),
                                  ("confirm_title", "title")):
            dlg = self.dialogs[dlg_name]
            if cfg_key in cfg:
                dlg["enabled"] = str(cfg[cfg_key]).lower() in (
                    "true", "1", "yes", "on")
            if f"{cfg_key}_text" in cfg:
                dlg["text"] = str(cfg[f"{cfg_key}_text"])
            if f"{cfg_key}_yes" in cfg:
                dlg["yes"] = str(cfg[f"{cfg_key}_yes"])
            if f"{cfg_key}_no" in cfg:
                dlg["no"] = str(cfg[f"{cfg_key}_no"])
        # 兼容旧字段
        self.confirm_quit_enabled = self.dialogs["quit"]["enabled"]
        self.confirm_quit_text = self.dialogs["quit"]["text"]
        self.confirm_quit_yes = self.dialogs["quit"]["yes"]
        self.confirm_quit_no = self.dialogs["quit"]["no"]
        self.confirm_load_enabled = self.dialogs["load"]["enabled"]
        self.confirm_load_text = self.dialogs["load"]["text"]
        self.confirm_load_yes = self.dialogs["load"]["yes"]
        self.confirm_load_no = self.dialogs["load"]["no"]
        # 键盘导航键位 (key_up/key_down/key_confirm, 逗号分隔多键)
        for attr, cfg_key in (("key_up", "key_up"), ("key_down", "key_down"),
                              ("key_confirm", "key_confirm")):
            if cfg_key in cfg:
                parsed = self._parse_keys(cfg[cfg_key])
                if parsed:
                    setattr(self, attr, parsed)
        if "ui_click_sound" in cfg:
            self._default_ui_click = str(cfg["ui_click_sound"])
            self.ui_click_sound = self._default_ui_click
        if "music_fade" in cfg:
            try:
                self.audio.fade_duration = max(
                    0.0, float(cfg["music_fade"]))
            except (TypeError, ValueError):
                pass
        # ESC 菜单文案
        for key in self.menu_texts:
            if f"menu_{key}" in cfg:
                self.menu_texts[key] = str(cfg[f"menu_{key}"])
        log.info(f"对话框: " + ", ".join(
            f"{k}={'开' if v['enabled'] else '关'}"
            for k, v in self.dialogs.items()))

    def ask_dialog(self, name: str, callback) -> None:
        """按 dialog 配置弹确认框; 未启用时直接执行 callback。"""
        dlg = self.dialogs.get(name)
        if dlg and dlg.get("enabled") and not self.display.confirm_active:
            self.ask_confirm(dlg["text"], dlg["yes"], dlg["no"], callback)
        else:
            callback()

    def ask_confirm(self, text: str, yes_text: str, no_text: str,
                    callback) -> None:
        """弹确认框, 玩家点"是"时执行 callback。"""
        self._confirm_callback = callback
        self.display.show_confirm(text, yes_text, no_text)

    # ==================================================================
    # 动作系统 (selection 按钮与插件共用)
    # ==================================================================
    def register_action(self, name: str, handler) -> None:
        """注册自定义动作 (插件 API)。

        handler(engine, params, source) -> bool (True=执行后关闭选择列表)
        """
        self.actions[name] = handler
        log.info(f"动作已注册: {name}")

    def run_action(self, action, source: str = None) -> bool:
        """执行一个动作 dict {"type": ..., 其他参数}, 返回是否已处理。"""
        if not isinstance(action, dict) or not action.get("type"):
            return False
        atype = action["type"]
        params = {k: v for k, v in action.items() if k != "type"}
        self.emit("action", type=atype, params=params, source=source)
        handler = self.actions.get(atype)
        if handler is None:
            log.warning(f"未知动作类型: {atype}")
            return False
        try:
            return bool(handler(self, params, source))
        except Exception as exc:
            log.warning(f"动作 {atype} 执行失败: {exc}")
            return False

    def _act_start(self, engine, params, source):
        """启动游戏: 关闭所有菜单, 停止标题残留 BGM (淡出), 跳转。"""
        label = params.get("label") or params.get("jump") or "start"
        self.audio.stop_music()   # 淡出停止 (不全局静音)
        d = self.display
        d.close_selection()
        d.slot_menu_active = False
        d.confirm_active = False
        self.paused = False
        rt = self.runtime
        if label in rt.labels:
            rt.release("title")
            rt._jump_to(label)
            rt.advance()
        return True

    def _act_quit(self, engine, params, source):
        self.request_quit()
        return False    # 确认框接管, 选择列表保持

    def _act_title(self, engine, params, source):
        self.ask_dialog("title", self.goto_title)
        return False    # 确认框启用时菜单保持; 未启用时 goto_title 已关闭

    def _act_continue(self, engine, params, source):
        self.close_system_menu()
        return True

    def _act_slot_menu(self, engine, params, source):
        mode = params.get("mode", "load")
        self.display.show_slot_menu(self.save.list_slots(), mode)
        return False    # 槽位界面浮在选择列表之上

    def _act_save(self, engine, params, source):
        try:
            slot = int(params.get("slot", 0))
        except (TypeError, ValueError):
            slot = 0
        self.save_game(slot, silent=False)
        d = self.display
        d.close_selection()
        d.slot_menu_active = False
        self.paused = False
        d.show_notice(f"已保存到槽位 {slot + 1}", 1.5)
        return True

    def _act_load(self, engine, params, source):
        try:
            slot = int(params.get("slot", 0))
        except (TypeError, ValueError):
            slot = 0
        self.ask_dialog("load", lambda: self._perform_load(slot))
        return False    # 确认框启用时菜单保持; 未启用时 _perform_load 直接进游戏

    def _act_close(self, engine, params, source):
        self.display.close_selection()
        self.paused = False
        return True

    def request_quit(self) -> None:
        """请求退出: 按 quit 对话框配置弹确认, 否则直接退出。"""
        self.ask_dialog("quit", self.quit)

    # ==================================================================
    # 错误处理
    # ==================================================================
    def handle_error(self, error, level: str = "error") -> None:
        """记录错误到日志并弹出温和提示 (不崩溃)。

        level: "error" 弹窗提示; "warn" 仅记录日志。
        """
        try:
            info = self.error_handler.record(error, level)
            if level != "warn":
                self.display.show_error(info)
                self.paused = True   # 弹窗期间暂停游戏
        except Exception as exc:
            log.error(f"错误处理失败: {exc}")

    # ==================================================================
    # 音频 API (供插件/游戏代码调用; 名称可为注册名或路径)
    # ==================================================================
    def play_music(self, name_or_path: str, loop: bool = True,
                   fade: float = None) -> bool:
        """播放/切换 BGM (注册名或路径)。fade None=默认时长。

        loop=True 循环 (播完自动重播); False 单次。注册名会记入存档/事件。
        """
        is_reg = name_or_path in self.runtime.sounds
        path = self.runtime.resolve_sound(name_or_path)
        if path is None:
            path = name_or_path
        return self.audio.play_music(
            path, loop, fade, name=(name_or_path if is_reg else None))

    def stop_music(self, fade: float = None) -> None:
        self.audio.stop_music(fade)

    def pause_music(self, fade: float = None) -> None:
        self.audio.pause_music(fade)

    def resume_music(self, fade: float = None) -> None:
        self.audio.resume_music(fade)

    def play_sfx(self, name: str) -> bool:
        """播放剧情音效 (注册名)。"""
        path = self.runtime.resolve_sound(name)
        if path is None:
            return False
        return self.audio.play_sound(path)

    def play_voice(self, name: str) -> bool:
        path = self.runtime.resolve_sound(name)
        if path is None:
            return False
        return self.audio.play_voice(path)

    def stop_voice(self) -> None:
        self.audio.stop_voice()

    def set_music_volume(self, vol: float) -> None:
        self.audio.set_bgm_volume(vol)

    def set_sfx_volume(self, vol: float) -> None:
        self.audio.set_sfx_volume(vol)

    def stop_all_sounds(self, fade: float = None) -> None:
        """全局停止所有声音 (BGM 淡出 + 音效/语音)。"""
        self.audio.stop_all(fade)

    def pause_all_sounds(self, fade: float = None) -> None:
        """全局暂停所有声音。"""
        self.audio.pause_all(fade)

    def get_last_game_frame(self):
        """最近一次纯游戏画面 Surface (覆盖层弹出前的帧, 存档快照用)。"""
        return self._last_game_frame

    def _play_ui_sound(self, kind: str = "click") -> None:
        """播放 UI 交互音效 (click=按下 / hover=活动项变化)。"""
        name = self.ui_hover_sound if kind == "hover" else self.ui_click_sound
        if not name:
            return
        path = self.runtime.resolve_sound(name)
        if path:
            self.audio.play_sound(path)

    def _set_ui_sounds(self, ui_cfg: dict = None) -> None:
        """应用菜单/选择支的 UI 音效配置 (临时覆盖 window 默认)。

        ui_cfg: {"ui_click_sound": 名, "ui_hover_sound": 名}; 空则恢复默认。
        """
        ui_cfg = ui_cfg or {}
        self.ui_click_sound = ui_cfg.get(
            "ui_click_sound") or self._default_ui_click
        self.ui_hover_sound = ui_cfg.get("ui_hover_sound")

    def copy_to_clipboard(self, text: str) -> bool:
        """把文本复制到系统剪贴板 (pygame.scrap)。"""
        if not text:
            return False
        try:
            if not pygame.scrap.get_init():
                pygame.scrap.init()
            pygame.scrap.put(pygame.SCRAP_TEXT, text.encode("utf-8"))
            return True
        except Exception as exc:
            log.warning(f"复制到剪贴板失败: {exc}")
            return False

    # ==================================================================
    # 存档快捷方式
    # ==================================================================
    def save_game(self, slot: int = 0, silent: bool = False) -> None:
        data = self.runtime.snapshot()
        path = self.save.save(slot, data)
        if not silent:
            self.display.show_notice(f"已存档 (槽位 {slot})  按 F9 读档")

    def load_game(self, slot: int = 0) -> None:
        data = self.save.load(slot)
        if data is None:
            self.display.show_notice(f"槽位 {slot} 没有存档")
            return
        # 恢复运行时 (变量/剧情位置/调用栈/阻塞状态)
        self.runtime.restore(data)
        # 恢复视觉 (背景/立绘/正在显示的文本或选择支)
        self.display.restore_state(data)
        # 恢复音乐 (注册名或路径均可)
        music = data.get("music")
        if music:
            self.play_music(music)
        else:
            self.audio.stop_music()
        self.display.show_notice(f"已读档 (槽位 {slot})")
        self.runtime.advance()
