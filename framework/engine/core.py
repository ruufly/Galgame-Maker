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

from framework.engine import log
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
                 plugins_dir: str = None, autoload_plugins: bool = True) -> None:
        self.width = width
        self.height = height
        self.title = title
        self.fps = fps
        self.project_dir = os.getcwd()
        self.script_dir = None

        pygame.init()
        try:
            self.screen = pygame.display.set_mode((width, height))
        except pygame.error as exc:
            log.error(f"无法创建窗口: {exc}")
            raise
        pygame.display.set_caption(title)

        self.clock = pygame.time.Clock()
        self.running = False

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

    def get_font(self, size: int):
        """按字号获取 pygame 字体 (带缓存)。"""
        if size in self._font_cache:
            return self._font_cache[size]
        font = None
        if self._font_path:
            try:
                font = pygame.font.Font(self._font_path, size)
            except Exception:
                font = None
        if font is None:
            font = pygame.font.SysFont("microsoftyahei,simhei,arial", size)
        self._font_cache[size] = font
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
            self.running = False
        elif event.type == pygame.KEYDOWN:
            self._handle_key(event.key)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.on_click(event.pos)

    def _handle_key(self, key) -> None:
        if key in (pygame.K_SPACE, pygame.K_RETURN):
            self.on_click((self.width // 2, self.height // 2))
        elif key == pygame.K_F5:
            self.save_game(0, silent=False)
        elif key == pygame.K_F9:
            self.load_game(0)
        elif key == pygame.K_ESCAPE:
            self.running = False

    # ==================================================================
    # 点击推进逻辑
    # ==================================================================
    def on_click(self, pos) -> None:
        """处理一次点击: 选项命中 -> 选择; 文本 -> 推进; 否则推进脚本。"""
        d = self.display
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
    # 存档快捷方式
    # ==================================================================
    def save_game(self, slot: int = 0, silent: bool = False) -> None:
        data = self.runtime.snapshot()
        data["bg"] = None
        path = self.save.save(slot, data)
        if not silent:
            self.display.show_notice(f"已存档 (槽位 {slot})  按 F9 读档")

    def load_game(self, slot: int = 0) -> None:
        data = self.save.load(slot)
        if data is None:
            self.display.show_notice(f"槽位 {slot} 没有存档")
            return
        self.runtime.restore(data)
        self.display.restore_sprites(data.get("sprites", []))
        self.display.clear_text()
        self.display.choice_active = False
        self.display.show_notice(f"已读档 (槽位 {slot})")
        self.runtime.advance()
