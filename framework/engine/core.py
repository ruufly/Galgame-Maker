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
            self.plugins.discover(self.plugins_dir)
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
            dt = self.clock.tick(self.fps) / 1000.0
            for event in pygame.event.get():
                self.handle_event(event)
            self.update(dt)
            self.draw()

    def handle_event(self, event) -> None:
        if event.type == pygame.QUIT:
            self.request_quit()   # 右上角关闭按钮 -> 退出确认
        elif event.type == pygame.KEYDOWN:
            self._handle_key(event.key)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.on_click(event.pos)

    def _handle_key(self, key) -> None:
        if key in (pygame.K_SPACE, pygame.K_RETURN):
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
        """打开游戏内菜单 (暂停游戏)。"""
        self.paused = True
        items = [
            ("继续游戏", {"continue": True}),
            ("存档", {"save": True}),
            ("读取存档", {"load": True}),
            ("返回标题", {"title": True}),
            ("退出游戏", {"quit": True}),
        ]
        self.display.show_system_menu(items)
        self.emit("menu_open")

    def close_system_menu(self) -> None:
        self.display.system_menu_active = False
        self.paused = False
        self.emit("menu_close")

    def _perform_load(self, slot: int) -> None:
        """执行读档 (确认通过后), 并关闭所有菜单层回到游戏。"""
        self.load_game(slot)
        d = self.display
        d.slot_menu_active = False
        d.system_menu_active = False
        d.title_active = False
        self.paused = False

    def goto_title(self) -> None:
        """结束当前游戏流程, 回到 start 标签 (通常为标题画面)。"""
        d = self.display
        d.clear_text()
        d.clear_sprites()
        d.clear_bg()          # 清掉旧场景, 由 start 块重新布置
        d.clear_fade()        # 清除黑幕/结束画面/未完成过渡
        d.title_active = False
        d.system_menu_active = False
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
        """处理一次点击: 确认框 -> 槽位界面 -> 系统菜单 -> 标题 -> 选择支等。"""
        d = self.display
        # 0) 确认对话框 (最高优先级)
        if d.confirm_active:
            idx = d.hit_confirm(pos)
            if idx < 0:
                return
            d.confirm_active = False
            cb = self._confirm_callback
            self._confirm_callback = None
            self.emit("confirm_choice", index=idx)
            if idx == 0 and cb is not None:
                cb()      # 是 -> 执行确认后的动作
            return
        # 1) 存档槽位选择界面
        if d.slot_menu_active:
            hit = d.hit_slot_menu(pos)
            if hit is None:
                return
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
        # 2) 系统菜单 (ESC)
        if d.system_menu_active:
            idx = d.hit_system_menu(pos)
            if idx < 0:
                return
            label, action = d.system_menu_items[idx]
            self.emit("menu_choice", index=idx, label=label, action=action)
            if "continue" in action:
                self.close_system_menu()
            elif "save" in action:
                d.show_slot_menu(self.save.list_slots(), "save")
            elif "load" in action:
                d.show_slot_menu(self.save.list_slots(), "load")
            elif "title" in action:
                self.goto_title()
            elif "quit" in action:
                self.request_quit()
            return
        # 3) 标题画面菜单
        if d.title_active:
            idx = d.hit_title(pos)
            if idx < 0:
                return
            label, action = d.title_items[idx]
            self.emit("title_choice", index=idx, label=label, action=action)
            if "jump" in action:
                d.title_active = False
                d.title_items = []
                self.runtime.release("title")
                self.runtime._jump_to(action["jump"])
                self.runtime.advance()
            elif "load" in action:
                # 打开槽位选择界面, 标题保留在底层 (可"返回")
                d.show_slot_menu(self.save.list_slots(), "load")
            elif "quit" in action:
                self.request_quit()
            return
        # 1) 选项
        if d.choice_active:
            idx = d.hit_choice(pos)
            if idx < 0:
                return
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
        if self.paused:
            return   # 系统菜单打开时暂停游戏逻辑 (菜单绘制仍进行)
        self.display.update(dt)
        self.runtime.tick(dt)

    def draw(self) -> None:
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
    def apply_config(self, cfg: dict) -> None:
        """应用脚本 window 配置中的运行时选项 (窗口已在构造时创建)。"""
        if "confirm_quit" in cfg:
            self.confirm_quit_enabled = str(cfg["confirm_quit"]).lower() in (
                "true", "1", "yes", "on")
        if "confirm_quit_text" in cfg:
            self.confirm_quit_text = str(cfg["confirm_quit_text"])
        if "confirm_quit_yes" in cfg:
            self.confirm_quit_yes = str(cfg["confirm_quit_yes"])
        if "confirm_quit_no" in cfg:
            self.confirm_quit_no = str(cfg["confirm_quit_no"])
        if "confirm_load" in cfg:
            self.confirm_load_enabled = str(cfg["confirm_load"]).lower() in (
                "true", "1", "yes", "on")
        if "confirm_load_text" in cfg:
            self.confirm_load_text = str(cfg["confirm_load_text"])
        if "confirm_load_yes" in cfg:
            self.confirm_load_yes = str(cfg["confirm_load_yes"])
        if "confirm_load_no" in cfg:
            self.confirm_load_no = str(cfg["confirm_load_no"])
        log.info(f"退出确认: {self.confirm_quit_enabled} "
                 f"({self.confirm_quit_text!r}) | "
                 f"读档确认: {self.confirm_load_enabled} "
                 f"({self.confirm_load_text!r})")

    def ask_confirm(self, text: str, yes_text: str, no_text: str,
                    callback) -> None:
        """弹确认框, 玩家点"是"时执行 callback。"""
        self._confirm_callback = callback
        self.display.show_confirm(text, yes_text, no_text)

    def request_quit(self) -> None:
        """请求退出: 启用确认时弹对话框, 否则直接退出。"""
        if self.confirm_quit_enabled and not self.display.confirm_active:
            self.ask_confirm(self.confirm_quit_text, self.confirm_quit_yes,
                             self.confirm_quit_no, self.quit)
        else:
            self.quit()

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
        # 恢复音乐
        music = data.get("music")
        if music:
            self.audio.play_music(music)
        else:
            self.audio.stop_music()
        self.display.show_notice(f"已读档 (槽位 {slot})")
        self.runtime.advance()
