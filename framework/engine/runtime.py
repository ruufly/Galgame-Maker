"""运行时: 脚本加载、语句执行、变量与分支、跳转/调用栈、存档恢复。

执行模型::

    Runtime 持有一个"当前语句列表 + 指令指针"(栈式)。
    advance() 不断取下一条语句执行, 直到遇到阻塞语句
    (text / choice / sleep) 或脚本结束。
    阻塞解除后由引擎调用 release() 并继续 advance()。
"""

import os
import re
import time

from framework.engine import log
from framework.engine.parser import Statement, parse_file

BLOCK = "block"


class RuntimeError_(Exception):
    pass


class Runtime:
    def __init__(self, engine) -> None:
        self.engine = engine
        self.vars = {}                # 游戏变量 (main:: 域默认, 键为裸名)
        self.builtin_vars = {}        # 内置变量 (builtin:: 域, 引擎预置)
        self.using_ns = set()         # using 导入的命名空间 (插件名)
        self.labels = {}
        self.statements = []          # 当前执行块
        self.ip = 0
        self.call_stack = []          # [(statements, ip, label)]
        self.current_label = None
        self.blocked = None           # None / "text" / "choice" / "sleep"
        self.sleep_until = None
        self.running = False
        self.ended = False
        self.script_path = None
        self.script_dir = "."
        self.widgets_templates = {}   # name -> {parent, blocks}
        self.pending_create = None    # 等待 `-> id` 完成的对象
        self._created_objects = {}    # weight 创建的背景对象 (id -> obj)
        self.characters = {}          # 角色表: id -> {name, sprites, ...}
        self.scenes = {}              # 场景表: id -> {name, backgrounds, ...}
        self.styles = {}              # 样式表: name -> {属性: 值}
        self.current_style_name = None
        self.menus = {}               # 菜单表: id -> [{name, text, action, cfg}]
        self.sounds = {}              # 声音表: name -> {type, file, volume}
        self.title_bgm = None         # start 块配置的标题 BGM (注册名/路径)
        self.skip_mode = False        # 跳过模式: 直达下一个选择支/结局

        # 内置指令表
        self._builtins = {
            "bg": self._cmd_bg,
            "show": self._cmd_show,
            "hide": self._cmd_hide,
            "withdraw": self._cmd_hide,
            "clear": self._cmd_clear,
            "move": self._cmd_move,
            "rotate": self._cmd_rotate,
            "flip": self._cmd_flip,
            "weight": self._cmd_create,
            "sprite": self._cmd_create,
            "object": self._cmd_create,
            "char": self._cmd_char,
            "character": self._cmd_char,
            "scene": self._cmd_scene,
            "scenery": self._cmd_scene,
            "->": self._cmd_bind,
            "text": self._cmd_text,
            "nar": self._cmd_text,
            "narrate": self._cmd_text,
            "say": self._cmd_say,
            "title": self._cmd_title,
            "choice": self._cmd_choice,
            "confirm": self._cmd_confirm,
            "set": self._cmd_set,
            "if": self._cmd_if,
            "jump": self._cmd_jump,
            "call": self._cmd_call,
            "return": self._cmd_return,
            "sleep": self._cmd_sleep,
            "read_settings": self._cmd_read_settings,
            "music": self._cmd_music,
            "sound": self._cmd_sound,
            "stop": self._cmd_stop,
            "fade": self._cmd_fade,
            "fadeout": self._cmd_fadeout,
            "save": self._cmd_save,
            "load": self._cmd_load,
            "ending": self._cmd_ending,
            "quit": self._cmd_ending,
            "pass": self._cmd_pass,
            "window": self._cmd_window,
            "config": self._cmd_window,
            "language": self._cmd_language,
            "fullscreen": self._cmd_fullscreen,
            "style": self._cmd_style,
            "use": self._cmd_use,
            "selection_style": self._cmd_selection_style,
            "menu_bar": self._cmd_menu_bar,
            "import": self._cmd_pass,
            "ui": self._cmd_ui,
            "menu": self._cmd_menu,
            "typing": self._cmd_typing,
            "sound": self._cmd_sound,
            "sfx": self._cmd_sfx,
            "pause": self._cmd_pause,
            "resume": self._cmd_resume,
            "volume": self._cmd_volume,
            "using": self._cmd_using,
            "plugin": self._cmd_plugin,
            "python": self._cmd_python,
        }

    # ==================================================================
    # 脚本加载
    # ==================================================================
    def load_script(self, path: str) -> None:
        path = os.path.abspath(path)
        self.script_path = path
        self.script_dir = os.path.dirname(path)
        self.engine.project_dir = self.script_dir
        # 递归展开 import 后解析
        from framework.engine.loader import load_script_with_imports
        script = load_script_with_imports(path)
        # 游戏文本多语言: <项目目录>/lang/*.json (存在即启用 {@key})
        self.engine.i18n.load_dir(os.path.join(self.script_dir, "lang"),
                                  ns="game")
        self.labels = script.labels
        self.statements = script.statements
        self.ip = 0
        # 对象注册表: 静态扫描脚本中的 weight/sprite/char 定义,
        # id -> {kind, image, pos, scale, mode, effect}
        # 存档只存 id, 图片路径以脚本为准 (改图片名不影响旧存档)
        self.script_objects = self._scan_objects(script)
        # 角色表 / 场景表 / 样式表 (静态注册, 无需执行到定义语句)
        self._rebuild_characters()
        self._rebuild_scenes()
        # 样式表: 预装内置样式 + 脚本定义 (同名覆盖)
        from framework.engine.styles import BUILTIN_STYLES
        self.styles = dict(BUILTIN_STYLES)
        self.styles.update(self._scan_styles(script))
        # selection 全局样式 / UI 主题素材 / 菜单 / 声音 (静态应用)
        self.engine.display.selection_style_overrides.clear()
        for stmt in self._scan_statements(script):
            if stmt.op == "selection_style":
                self._apply_selection_style_stmt(stmt)
            elif stmt.op == "ui":
                self._cmd_ui(stmt)
            elif stmt.op == "menu":
                self._cmd_menu(stmt)
            elif stmt.op == "sound":
                self._cmd_sound(stmt)
            elif stmt.op == "using":
                # 命名空间声明: 加载即生效 (顶层 using 不依赖执行流程)
                self._cmd_using(stmt)
            elif stmt.op == "menu_bar":
                # 常驻菜单栏样式 (bar 模式系统菜单)
                self._apply_menu_bar_stmt(stmt)
            elif stmt.op == "settings":
                # 设置界面配置 (setting.gal: 布局 + 条目)
                self.engine.settings.apply_config(stmt)
            elif stmt.op == "language":
                # 主文件 language 块: 支持的语言 / 默认语言 / 显示名
                self._cmd_language(stmt)
            elif stmt.kwargs or stmt.block:
                # 其他属性块: 广播给插件处理 (如 gallery 块由 gallery
                # 插件解析; 未装载对应插件时安全忽略)
                self.engine.emit("script_block", op=stmt.op, stmt=stmt)
            # 注: window/config 块不在此静态应用 —— 窗口类配置由启动器
            # 预解析 (extract_window_config), 交互配置由启动器 apply_config;
            # 运行中的 `window config` 命令在执行到该语句时即时生效。
        self.engine.emit("script_load", path=path, name=script.name)
        log.i("log.script_loaded", path=path, labels=len(script.labels),
              objects=len(self.script_objects), chars=len(self.characters),
              scenes=len(self.scenes))
        # 按 menu_mode 构建常驻菜单栏 (bar 模式; menu system 已静态注册)
        self.engine.refresh_menu_bar()
        # widgets 模板
        if script.widgets_dir:
            self.load_widget_templates(
                os.path.join(self.script_dir, script.widgets_dir))

    # ------------------------------------------------------------------
    def _scan_objects(self, script) -> dict:
        """扫描脚本语句, 收集所有 weight/sprite/char 创建的对象定义。"""
        objs = {}

        def scan(stmts):
            pending = None
            for stmt in stmts:
                if stmt.op == "weight":
                    pending = {"kind": "weight", **stmt.kwargs}
                elif stmt.op in ("sprite", "object") and stmt.args:
                    objs[stmt.args[0]] = {"kind": stmt.op, **stmt.kwargs}
                elif stmt.op in ("char", "character") and stmt.args:
                    props = dict(stmt.kwargs)
                    img = props.get("default") or (
                        next(iter(props.values())) if props else None)
                    objs[stmt.args[0]] = {"kind": "char", "image": img,
                                          "props": props}
                elif stmt.op in ("scene", "scenery") and stmt.args:
                    props = dict(stmt.kwargs)
                    img = props.get("default") or (
                        next(iter(props.values())) if props else None)
                    objs[stmt.args[0]] = {"kind": "scene", "image": img,
                                          "props": props}
                elif stmt.op == "->" and pending is not None:
                    if stmt.args:
                        objs[stmt.args[0]] = dict(pending)
                    pending = None
                # 递归扫描子块 (choice/if)
                for cond, body in stmt.kwargs.get("branches", []):
                    scan(body)
                if stmt.kwargs.get("else"):
                    scan(stmt.kwargs["else"])
                if stmt.block:
                    scan(stmt.block)

        scan(script.statements)
        for body in script.labels.values():
            scan(body)
        return objs

    # ------------------------------------------------------------------
    def _rebuild_characters(self) -> None:
        """从对象注册表重建角色表 (静态注册 / 读档时调用)。"""
        self.characters = {}
        for cid, obj in self.script_objects.items():
            if obj.get("kind") != "char":
                continue
            props = dict(obj.get("props", {}))
            name = props.pop("name", cid)
            default = props.pop("default", None)
            pos = props.pop("pos", "center")
            scale = props.pop("scale", None)
            mode = props.pop("mode", None)
            meta = {}
            for key in list(props):
                if key in self._CHAR_META_KEYS:
                    meta[key] = props.pop(key)
            try:
                voice_volume = max(0.0, min(1.0, float(props.pop(
                    "voice_volume", 1.0))))
            except (TypeError, ValueError):
                voice_volume = 1.0
            self.characters[cid] = {
                "id": cid, "name": name, "sprites": props,
                "default": default, "pos": pos, "scale": scale, "mode": mode,
                "voice_volume": voice_volume, "meta": meta,
            }

    # ------------------------------------------------------------------
    def _rebuild_scenes(self) -> None:
        """从对象注册表重建场景表 (静态注册 / 读档时调用)。"""
        self.scenes = {}
        for sid, obj in self.script_objects.items():
            if obj.get("kind") != "scene":
                continue
            props = dict(obj.get("props", {}))
            name = props.pop("name", sid)
            default = props.pop("default", None)
            mode = props.pop("mode", None)
            stype = str(props.pop("type", "normal")).lower()
            if stype not in ("cg", "normal"):
                stype = "normal"
            self.scenes[sid] = {"id": sid, "name": name, "type": stype,
                                "backgrounds": props, "default": default,
                                "mode": mode}

    # ------------------------------------------------------------------
    def _scan_statements(self, script) -> list:
        """收集脚本中所有语句 (顶层 + 各标签), 按出现顺序。"""
        out = list(script.statements)

        def scan(stmts):
            for stmt in stmts:
                for cond, body in stmt.kwargs.get("branches", []):
                    scan(body)
                if stmt.kwargs.get("else"):
                    scan(stmt.kwargs["else"])
                if stmt.block:
                    scan(stmt.block)

        for body in script.labels.values():
            out.extend(body)
        return out

    # ------------------------------------------------------------------
    _SEL_STYLE_COLOR_KEYS = {"button_bg", "button_bg_hover", "button_border",
                             "button_border_hover", "text_color",
                             "text_color_hover", "dialog_text_color"}
    _SEL_STYLE_NUM_KEYS = {"width_ratio", "width", "height", "gap",
                           "caption_y", "caption_size", "dim_alpha",
                           "text_size", "unhover_alpha"}
    _SEL_STYLE_BOOL_KEYS = {"button_stretch", "button_text"}
    _SEL_STYLE_STR_KEYS = {"anchor_x", "caption_x", "anchor_y",
                           "button_image", "button_image_hover",
                           "dialog_image"}

    # menu_bar 常驻菜单栏样式键
    _MENU_BAR_COLOR_KEYS = {"bg", "border", "button_bg", "button_bg_hover",
                            "button_border", "button_border_hover",
                            "text_color", "text_color_hover"}
    _MENU_BAR_NUM_KEYS = {"gap", "padding", "height", "btn_h", "y_offset",
                          "text_size", "button_radius"}
    _MENU_BAR_STR_KEYS = {"align", "bg_image", "button_image",
                          "button_image_hover", "button_image_active",
                          "button_image_disabled"}

    def _apply_menu_bar_stmt(self, stmt) -> None:
        """解析并应用一条 menu_bar 样式语句 (属性块)。"""
        from framework.engine.rich import parse_color
        parsed = {}
        for key, value in stmt.kwargs.items():
            if key in self._MENU_BAR_COLOR_KEYS:
                parsed[key] = parse_color(str(value),
                                          (255, 255, 255, 255))
            elif key in self._MENU_BAR_NUM_KEYS:
                try:
                    parsed[key] = float(value)
                except (TypeError, ValueError):
                    pass
            elif key in self._MENU_BAR_STR_KEYS:
                parsed[key] = str(value)
        self.engine.display.apply_menu_bar_style(parsed)

    def _apply_selection_style_stmt(self, stmt) -> None:
        """解析并应用一条 selection_style 语句 (属性块)。"""
        from framework.engine.rich import parse_color
        parsed = {}
        for key, value in stmt.kwargs.items():
            if key in self._SEL_STYLE_COLOR_KEYS:
                parsed[key] = parse_color(str(value),
                                          (255, 255, 255, 255))
            elif key in self._SEL_STYLE_NUM_KEYS:
                try:
                    parsed[key] = float(value)
                except (TypeError, ValueError):
                    pass
            elif key in self._SEL_STYLE_BOOL_KEYS:
                parsed[key] = str(value).lower() in ("true", "1", "yes",
                                                     "on")
            elif key in self._SEL_STYLE_STR_KEYS:
                parsed[key] = str(value)
        self.engine.display.apply_selection_style(parsed)

    def _cmd_selection_style(self, stmt):
        """设置 selection (标题/系统菜单按钮列表) 全局样式。

        selection_style              # 属性块形式:
            width_ratio: 0.3         #   按钮宽占比
            height: 56 / gap: 14
            anchor_x: center         #   水平锚点 (center/left/right/数字)
            anchor_y: center         #   垂直: center=整体居中 / 数字
            button_bg: "#1a1a2e"     #   按钮配色
            button_bg_hover: ...
            button_border: ...
            button_border_hover: ...
            button_radius: 6
            text_size: 28
            dim_alpha: 120
        selection_style default      # 重置为默认
        """
        if stmt.args and stmt.args[0] == "default":
            self.engine.display.selection_style_overrides.clear()
            return None
        self._apply_selection_style_stmt(stmt)
        return None

    def _cmd_menu_bar(self, stmt):
        """定义常驻菜单栏样式 (bar 模式系统菜单):

        menu_bar
            bg: "#1a1a2e"              # 条背景 (RGBA)
            align: center              # left / center / right
            gap: 12                    # 按钮间距
            padding: 18                # 按钮左右内边距
            height: 56                 # 条高度
            btn_h: 38                  # 按钮高度
            y_offset: 0                # 位置微调
            button_bg / button_bg_hover / button_border / ...
            text_color / text_color_hover / text_size / button_radius
        menu_bar default               # 重置为默认
        """
        if stmt.args and stmt.args[0] == "default":
            from framework.engine.display import DEFAULT_MENU_BAR_STYLE
            self.engine.display.menu_bar_style = dict(DEFAULT_MENU_BAR_STYLE)
            return None
        self._apply_menu_bar_stmt(stmt)
        return None

    def _scan_styles(self, script) -> dict:
        """静态扫描脚本中的 style 定义块。"""
        styles = {}

        def scan(stmts):
            for stmt in stmts:
                if stmt.op == "style" and stmt.args:
                    styles[stmt.args[0]] = dict(stmt.kwargs)
                for cond, body in stmt.kwargs.get("branches", []):
                    scan(body)
                if stmt.kwargs.get("else"):
                    scan(stmt.kwargs["else"])
                if stmt.block:
                    scan(stmt.block)

        scan(script.statements)
        for body in script.labels.values():
            scan(body)
        return styles

    # ------------------------------------------------------------------
    _STYLE_COLOR_KEYS = {
        "textbox_bg", "textbox_border", "text_color", "speaker_color",
        "speaker_bg", "arrow_color", "choice_bg", "choice_bg_hover",
        "choice_border", "choice_border_hover", "choice_text_color",
        "choice_text_color_hover",
    }
    _STYLE_INT_KEYS = {"textbox_alpha", "textbox_border_width",
                       "textbox_radius", "text_size", "choice_text_size",
                       "choice_height"}
    _STYLE_FLOAT_KEYS = {"choice_width_ratio"}
    _STYLE_BOOL_KEYS = {"choice_fit_image"}
    _STYLE_STR_KEYS = {"textbox_image", "speaker_image", "choice_image",
                       "choice_image_hover"}

    def _parse_style_props(self, props: dict) -> dict:
        """把 style 块的字符串属性解析为样式值 (颜色 tuple / 数字)。"""
        from framework.engine.rich import parse_color
        from framework.engine.display import DEFAULT_STYLE
        out = {}
        for key, value in props.items():
            if key in self._STYLE_COLOR_KEYS:
                default = DEFAULT_STYLE.get(key, (255, 255, 255))
                out[key] = parse_color(str(value), default)
            elif key in self._STYLE_INT_KEYS:
                try:
                    out[key] = int(float(value))
                except (TypeError, ValueError):
                    pass
            elif key in self._STYLE_FLOAT_KEYS:
                try:
                    out[key] = float(value)
                except (TypeError, ValueError):
                    pass
            elif key in self._STYLE_BOOL_KEYS:
                out[key] = str(value).lower() in ("true", "1", "yes", "on")
            elif key in self._STYLE_STR_KEYS:
                out[key] = str(value)
        return out

    # ------------------------------------------------------------------
    def load_widget_templates(self, directory: str) -> None:
        if not os.path.isdir(directory):
            log.w("log.runtime.widgets_missing", path=directory)
            return
        for name in sorted(os.listdir(directory)):
            if not name.endswith(".wid"):
                continue
            path = os.path.join(directory, name)
            try:
                with open(path, "r", encoding="utf-8-sig") as f:
                    text = f.read()
                tpl = self._parse_wid(text, name)
                if tpl:
                    self.widgets_templates[tpl["name"]] = tpl
                    log.i("log.runtime.widget_registered", name=tpl["name"])
            except Exception as exc:
                log.w("log.runtime.widget_load_failed", path=path, exc=exc)

    def _parse_wid(self, text: str, filename: str):
        """解析 .wid: 提取 reg class / @parent / 各事件块。

        简化实现: 块内语句交给主解析器解析, 不支持的指令执行时会警告跳过。
        """
        tpl = {"name": None, "parent": None, "blocks": {}}
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        i = 0
        current_block = None
        body = []
        while i < len(lines):
            ln = lines[i]
            m = re.match(r"^reg class (\w+)", ln)
            if m:
                tpl["name"] = m.group(1)
                i += 1
                continue
            m = re.match(r"^@parent (.+)$", ln)
            if m:
                tpl["parent"] = m.group(1).strip()
                i += 1
                continue
            m = re.match(r"^([\w ]+):$", ln)  # 块头
            if m:
                current_block = m.group(1).strip()
                tpl["blocks"][current_block] = []
                body = tpl["blocks"][current_block]
                i += 1
                continue
            if current_block is not None:
                # 逐行解析 (block 结构简单, 用主解析器逐行构造)
                try:
                    from framework.engine.parser import Parser
                    p = Parser()
                    p._preprocess(ln)
                    if p.lines:
                        stmt, _ = p._parse_statement(0, 0)
                        if stmt is not None:
                            body.append(stmt)
                except Exception:
                    pass
            i += 1
        if not tpl["name"]:
            return None
        return tpl

    # ==================================================================
    # 启动 / 推进
    # ==================================================================
    def start(self) -> None:
        self.running = True
        self.ended = False
        self.blocked = None
        if "start" in self.labels:
            self._jump_to("start")
        self.engine.emit("script_start")
        self.advance()

    def advance(self) -> None:
        """执行语句直到阻塞或脚本结束。

        skip_mode 开启时跳过文本/等待/动画类阻塞, 直达下一个选择支、
        标题或结局 (choice/title 仍会停止, ending 自然结束)。
        """
        while self.running and not self.ended:
            if self.blocked and not self.skip_mode:
                return
            if self.ip >= len(self.statements):
                if self.call_stack:
                    self._pop_block()
                    continue
                self._end_script()
                return
            stmt = self.statements[self.ip]
            self.ip += 1
            self.engine.emit("statement", stmt=stmt,
                                    label=self.current_label)
            result = self._dispatch(stmt)
            if result == BLOCK:
                if self.skip_mode and self._skipable(stmt):
                    self.blocked = None     # 跳过阻塞, 继续执行
                    continue
                return

    def _skipable(self, stmt) -> bool:
        """跳过模式下可忽略的阻塞指令 (文本/等待/移动动画)。"""
        return stmt.op in ("text", "nar", "narrate", "say", "sleep",
                           "move")

    def _dispatch(self, stmt: Statement):
        op = stmt.op
        # 显式命名空间: builtin::text / shake::shake
        if "::" in op:
            ns, name = op.split("::", 1)
            if ns == "builtin":
                handler = self._builtins.get(name)
                if handler is not None:
                    return handler(stmt)
            else:
                handler = self.engine.commands.get(name, ns)
                if handler is not None:
                    return handler(self.engine, stmt)
            log.w("log.runtime.cmd_unknown", line=stmt.line, op=op)
            return None
        # 无命名空间: builtin:: 优先
        handler = self._builtins.get(op)
        if handler is not None:
            return handler(stmt)
        # main:: 域 (引擎 API 直接注册)
        handler = self.engine.commands.get(op, "main")
        if handler is not None:
            return handler(self.engine, stmt)
        # 已 using 导入的插件命名空间
        for ns in list(self.using_ns):
            handler = self.engine.commands.get(op, ns)
            if handler is not None:
                return handler(self.engine, stmt)
        # 裸词: 尝试 widgets 模板实例化
        if not stmt.args and not stmt.kwargs and op in self.widgets_templates:
            self._instantiate_widget(op)
            return None
        # 报错: 插件指令需 using 或显式命名空间
        loc = self.engine.commands.find(op)
        if loc:
            hint = "、".join(f"{ns}::{op}" for ns, _ in loc)
            log.w("log.runtime.cmd_ns_hint", line=stmt.line, op=op, ns=hint)
        else:
            log.w("log.runtime.cmd_unknown", line=stmt.line, op=op)
        return None

    def _end_script(self) -> None:
        self.ended = True
        self.running = False
        self.engine.emit("script_end")
        log.i("log.runtime.script_end")

    # ------------------------------------------------------------------
    def _jump_to(self, label: str) -> None:
        if label not in self.labels:
            raise RuntimeError_(f"跳转到不存在的标签: {label!r}")
        self.statements = self.labels[label]
        self.ip = 0
        self.current_label = label
        self.engine.emit("label_enter", label=label)

    def _push_block(self, statements, ip=None, label=None) -> None:
        self.call_stack.append(
            (self.statements, self.ip, self.current_label))
        self.statements = statements
        self.ip = ip or 0
        self.current_label = label

    def _pop_block(self) -> None:
        if not self.call_stack:
            return
        self.statements, self.ip, self.current_label = self.call_stack.pop()

    # ==================================================================
    # 阻塞解除 (由引擎调用)
    # ==================================================================
    def release(self, kind: str) -> None:
        if self.blocked == kind:
            self.blocked = None

    def tick(self, dt: float) -> None:
        """每帧调用: 处理 sleep 计时与动画阻塞。"""
        if self.blocked == "sleep" and self.sleep_until is not None:
            if time.time() >= self.sleep_until:
                self.sleep_until = None
                self.release("sleep")
                self.advance()
            return
        if self.blocked == "anim":
            # 所有立绘动画播放完毕 -> 解除阻塞继续脚本
            if not any(spr.anim_move is not None or spr.anim_rotate is not None
                       for spr in self.engine.display.sprites.values()):
                self.release("anim")
                self.advance()

    # ==================================================================
    # 内置指令
    # ==================================================================
    # -- 场景 -----------------------------------------------------------
    def _cmd_scene(self, stmt):
        """注册场景: scene <id> + 属性块 (name/default/背景名: 路径)。

        type: normal (默认) / cg —— CG 场景展示时记入全局 CG 收集
        (鉴赏插件用)。显示逻辑与 normal 完全一致。
        """
        if not stmt.args:
            return None
        sid = stmt.args[0]
        props = dict(stmt.kwargs)
        name = props.pop("name", sid)
        default = props.pop("default", None)
        stype = str(props.pop("type", "normal")).lower()
        if stype not in ("cg", "normal"):
            stype = "normal"
        self.scenes[sid] = {"id": sid, "name": name, "type": stype,
                            "backgrounds": props, "default": default}
        # 同步到对象注册表 (存档/读档用)
        self.script_objects[sid] = {
            "kind": "scene", "image": default or (
                next(iter(props.values())) if props else None),
            "props": dict(stmt.kwargs),
        }
        self.engine.emit("scene_register", id=sid, name=name, type=stype)
        log.i("log.runtime.scene_registered", sid=sid, name=name,
              stype=stype, count=len(props))
        return None

    def _cmd_bg(self, stmt):
        """切换背景:
            bg <场景id> [背景名] [with 效果] —— 场景绑定背景间切换
            bg "路径" [with 效果]       —— 直接指定图片 (兼容)
        效果: fade / dissolve / blinds / none / 插件注册的过渡
        """
        if not stmt.args:
            return None
        args = list(stmt.args)
        effect = None
        if "with" in args:
            idx = args.index("with")
            if idx + 1 < len(args):
                effect = args[idx + 1]
            args = args[:idx]
        mode = None
        if "mode" in args:
            idx = args.index("mode")
            if idx + 1 < len(args):
                mode = args[idx + 1]
            del args[idx:idx + 2]
        if self.skip_mode:
            # 跳过模式: 背景瞬间切换 (不播放过渡动画)
            effect = None
        if not args:
            return None
        target = self._interp(args[0])
        d = self.engine.display
        if target in self.scenes:
            scene = self.scenes[target]
            pose = self._interp(args[1]) if len(args) > 1 else None
            img = None
            if pose and pose in scene["backgrounds"]:
                img = scene["backgrounds"][pose]
            elif pose:
                log.w("log.runtime.scene_pose_fallback", line=stmt.line,
              sid=target, pose=pose)
                pose = None
            if img is None:
                img = scene.get("default")
            if img:
                d.set_bg(img, effect, mode or scene.get("mode"))
                d.bg_scene = target
                d.bg_pose = pose
                d.bg_id = None
                self.engine.emit("scene_change", id=target,
                                 name=scene["name"], background=img, pose=pose)
                # CG 场景: 展示即记录 (全局 CG 收集, 跨存档)
                if scene.get("type") == "cg":
                    self.engine.record_cg(target, pose)
            return None
        # 直接路径
        d.set_bg(target, effect, mode)
        d.bg_scene = None
        d.bg_pose = None
        d.bg_id = None
        self.engine.emit("bg_change", path=target, effect=effect)
        return None

    # -- 角色 -----------------------------------------------------------
    _CHAR_META_KEYS = {"desc", "description", "bio", "intro", "cv",
                       "birthday", "height", "age"}

    def _cmd_char(self, stmt):
        """注册角色: char <id> + 属性块 (name/default/立绘名: 路径)。

        描述性信息 (不进入立绘表, 供角色鉴赏等使用):
            desc: "角色描述" / cv: "声优" / birthday / height / age
        """
        if not stmt.args:
            return None
        cid = stmt.args[0]
        props = dict(stmt.kwargs)
        name = props.pop("name", cid)
        default = props.pop("default", None)
        pos = props.pop("pos", "center")
        scale = props.pop("scale", None)
        mode = props.pop("mode", None)
        meta = {}
        for key in list(props):
            if key in self._CHAR_META_KEYS:
                meta[key] = props.pop(key)
        try:
            voice_volume = max(0.0, min(1.0, float(props.pop(
                "voice_volume", 1.0))))
        except (TypeError, ValueError):
            voice_volume = 1.0
        self.characters[cid] = {
            "id": cid, "name": name, "sprites": props,
            "default": default, "pos": pos, "scale": scale, "mode": mode,
            "voice_volume": voice_volume, "meta": meta,
        }
        # 同步到对象注册表 (存档/读档用)
        self.script_objects[cid] = {
            "kind": "char", "image": default or (
                next(iter(props.values())) if props else None),
            "props": dict(stmt.kwargs),
        }
        self.engine.emit("character_register", id=cid, name=name)
        log.i("log.runtime.char_registered", cid=cid, name=name,
              count=len(props))
        return None

    def _cmd_show(self, stmt):
        if not stmt.args:
            return None
        sid = stmt.args[0]
        args = stmt.args[1:]
        props = {}
        pos = None
        if "at" in args:
            idx = args.index("at")
            if idx + 1 < len(args):
                pos = args[idx + 1]
        if "with" in args:
            idx = args.index("with")
            if idx + 1 < len(args):
                props["effect"] = args[idx + 1]
        if self.skip_mode:
            # 跳过模式: 立绘瞬间显示 (不播放登场动画)
            props.pop("effect", None)
        # 角色立绘: show <角色id> [立绘名] [at pos] [with effect]
        if sid in self.characters:
            char = self.characters[sid]
            pose = None
            for a in args:
                if a not in ("at", "with") and pos is None and "effect" not in props:
                    pose = a
                    break
            if pose is None:
                pose = char.get("default")
            img = char["sprites"].get(pose) or char.get("default")
            if not img:
                log.w("log.runtime.char_pose_undefined", line=stmt.line,
              cid=sid, pose=pose)
                return None
            self.engine.display.show_sprite(
                sid, img, pos or char.get("pos"), char.get("scale"),
                char.get("mode"), props.get("effect"))
            spr = self.engine.display.sprites.get(sid)
            if spr is not None:
                spr.props["pose"] = pose
                spr.props["image"] = img
            return None
        # 直接 show 已创建对象: 从 pending props 恢复
        if self.pending_create and self.pending_create.get("id") == sid:
            p = self.pending_create
            self.pending_create = None
            self.engine.display.show_sprite(
                sid, p.get("image"), p.get("pos") or pos,
                p.get("scale"), p.get("mode"), p.get("effect"))
            return None
        # 已有立绘: 仅移动/特效
        if self.engine.display.sprites.get(sid):
            self.engine.display.show_sprite(sid, None, pos, effect=props.get("effect"))
            return None
        # 纯对象 id (weight 创建的全屏对象: 按全屏立绘显示, 兼容旧脚本)
        if sid in self._created_objects:
            obj = self._created_objects.pop(sid)
            self._apply_created(obj)
            if obj.get("kind", "weight") == "weight" and obj.get("image"):
                self.engine.display.show_sprite(
                    sid, obj.get("image"), "center", mode="full",
                    effect=obj.get("effect"))
            return None
        log.w("log.runtime.show_unknown", line=stmt.line, sid=sid)
        return None

    def _cmd_hide(self, stmt):
        """hide <id> [with 效果] —— 隐藏立绘 (带效果则播放退场动画)。"""
        if not stmt.args:
            return None
        sid = stmt.args[0]
        effect = None
        if "with" in stmt.args:
            idx = stmt.args.index("with")
            if idx + 1 < len(stmt.args):
                effect = stmt.args[idx + 1]
        if self.skip_mode:
            effect = None        # 跳过模式: 瞬间隐藏 (不播放退场动画)
        if sid in self.engine.display.sprites:
            self.engine.display.hide_sprite(sid, effect)
        else:
            log.w("log.runtime.hide_unknown", line=stmt.line, sid=sid)
        return None

    def _cmd_clear(self, stmt):
        self.engine.display.clear_sprites()
        return None

    # -- 立绘变换 -------------------------------------------------------
    def _extract_coords(self, tokens):
        """从 token 序列开头提取坐标, 返回 (pos或None, 消费的token数)。

        支持: ["640,360"] / ["640,", "360"] / ["640", "360"]。
        非数字 token (如 left) 时返回 (None, 0)。
        """
        nums = []
        consumed = 0
        for tok in tokens:
            s = str(tok).replace("(", "").replace(")", "")
            parts = [p.strip() for p in s.split(",") if p.strip()]
            if not parts:
                break
            got = []
            for p in parts:
                try:
                    got.append(float(p))
                except ValueError:
                    got = None
                    break
            if got is None:
                break
            nums.extend(got)
            consumed += 1
            if len(nums) >= 2:
                break
        if len(nums) >= 2:
            return (nums[0], nums[1]), consumed
        return None, 0

    def _cmd_move(self, stmt):
        """move <id> to <pos> [duration] [ease 缓动]

        pos: center/left/right/top/bottom 或坐标 (支持 640,360 / 640, 360 / 640 360)
        例: move girl to left / move girl to 640,360 / move girl to 400,300 2 ease in_out
        """
        if len(stmt.args) < 2:
            log.w("log.runtime.move_syntax", line=stmt.line)
            return None
        sid = stmt.args[0]
        tokens = stmt.args[2:] if stmt.args[1] == "to" else stmt.args[1:]
        if not tokens:
            return None
        pos, consumed = self._extract_coords(tokens)
        if pos is None:
            pos = tokens[0]
            consumed = 1
        rest = tokens[consumed:]
        duration = 0.0
        ease = "linear"
        if rest:
            try:
                duration = float(rest[0])
            except ValueError:
                pass
        if self.skip_mode:
            duration = 0.0        # 跳过模式: 瞬间移动 (无动画)
        if "ease" in rest:
            idx = rest.index("ease")
            if idx + 1 < len(rest):
                ease = rest[idx + 1]
        self.engine.display.move_sprite(sid, pos, duration, ease)
        if duration and duration > 0:
            # 动画播放期间阻塞脚本, 完成后自动继续
            self.blocked = "anim"
            return BLOCK
        return None

    def _cmd_rotate(self, stmt):
        """rotate <id> <角度> [duration] [ease 缓动] (逆时针为正)"""
        if len(stmt.args) < 2:
            log.w("log.runtime.rotate_syntax", line=stmt.line)
            return None
        sid = stmt.args[0]
        try:
            angle = float(stmt.args[1])
        except ValueError:
            log.w("log.runtime.rotate_invalid", line=stmt.line,
              value=stmt.args[1])
            return None
        duration = 0.0
        ease = "linear"
        rest = stmt.args[2:]
        if rest:
            try:
                duration = float(rest[0])
            except ValueError:
                pass
        if self.skip_mode:
            duration = 0.0        # 跳过模式: 瞬间旋转 (无动画)
        if "ease" in rest:
            idx = rest.index("ease")
            if idx + 1 < len(rest):
                ease = rest[idx + 1]
        self.engine.display.rotate_sprite(sid, angle, duration, ease)
        if duration and duration > 0:
            # 动画播放期间阻塞脚本, 完成后自动继续
            self.blocked = "anim"
            return BLOCK
        return None

    def _cmd_flip(self, stmt):
        """flip <id> [horizontal|vertical] (默认水平翻转, 再次调用恢复)"""
        if not stmt.args:
            return None
        sid = stmt.args[0]
        axis = stmt.args[1] if len(stmt.args) > 1 else "horizontal"
        if axis == "vertical":
            self.engine.display.flip_sprite(sid, horizontal=False, vertical=True)
        else:
            self.engine.display.flip_sprite(sid, horizontal=True)
        return None

    # -- 对象创建 -------------------------------------------------------
    def _cmd_create(self, stmt):
        ident = stmt.args[0] if stmt.args else None
        props = dict(stmt.kwargs)
        if ident:
            # 立即创建: sprite girl (属性块在 kwargs 中)
            if stmt.op == "weight":
                self._apply_created({"kind": "weight", "id": ident, **props})
            else:
                self.engine.display.show_sprite(
                    ident, props.get("image"), props.get("pos"),
                    props.get("scale"), props.get("mode"), props.get("effect"))
        else:
            # 等待 `-> id` 绑定 (weight 块)
            self.pending_create = {"kind": stmt.op, **props}
        return None

    def _cmd_bind(self, stmt):
        if not stmt.args:
            self.pending_create = None
            return None
        ident = stmt.args[0]
        if self.pending_create is None:
            log.w("log.runtime.arrow_no_target", line=stmt.line, ident=ident)
            return None
        p = self.pending_create
        self.pending_create = None
        self._apply_created({"kind": p.get("kind", "weight"), "id": ident, **p})

    def _apply_created(self, obj):
        """应用对象创建结果。背景一律走 scene/bg 指令;
        weight 仅保留为"全屏图层对象" (兼容旧脚本, 不再设置背景)。"""
        kind = obj.get("kind", "weight")
        ident = obj.get("id")
        if not ident:
            return
        if kind == "weight":
            self._created_objects[ident] = obj
            log.w("log.runtime.weight_deprecated", ident=ident)
        else:
            self.engine.display.show_sprite(
                ident, obj.get("image"), obj.get("pos"),
                obj.get("scale"), obj.get("mode"), obj.get("effect"))

    # -- 文本 -----------------------------------------------------------
    def _cmd_text(self, stmt):
        """nar/text 旁白: [voice 语音名]"""
        args = list(stmt.args)
        voice = None
        if "voice" in args:
            vi = args.index("voice")
            if vi + 1 < len(args):
                voice = args[vi + 1]
            del args[vi:vi + 2]
        text = self._interp(" ".join(args)) if args else ""
        # 游戏文本多语言 {@key} 解析 (key 文本内的 $var 再插值一次)
        text = self.engine.i18n.resolve(text)
        text = self._interp(text) if text else text
        if not text:
            log.w("log.runtime.text_empty", line=stmt.line)
            return None
        self._play_voice(voice)
        self.engine.display.show_text(text)
        self.blocked = "text"
        return BLOCK

    def _cmd_say(self, stmt):
        """say <角色> "台词" [voice 语音名]"""
        if not stmt.args:
            return None
        args = list(stmt.args)
        voice = None
        if "voice" in args:
            vi = args.index("voice")
            if vi + 1 < len(args):
                voice = args[vi + 1]
            del args[vi:vi + 2]
        speaker = self._interp(args[0])
        text = self._interp(" ".join(args[1:])) if len(args) > 1 else ""
        # 游戏文本多语言 {@key} 解析 (key 文本内的 $var 再插值一次)
        text = self.engine.i18n.resolve(text)
        text = self._interp(text) if text else text
        if not text:
            log.w("log.runtime.say_empty", line=stmt.line)
            return None
        # 台词分类: 角色 id -> 显示角色名 (支持 {@key}, 显示层按当前语言解析);
        # 旁白 -> 无名字框; 其他 -> 原样
        display_speaker = None
        if speaker in self.characters:
            display_speaker = self.characters[speaker]["name"]
        elif speaker and speaker != "旁白" and speaker != "narrator":
            display_speaker = speaker
        self._play_voice(voice, speaker)
        self.engine.display.show_text(text, display_speaker)
        self.blocked = "text"
        return BLOCK

    def _play_voice(self, voice_name, speaker=None) -> None:
        """播放/停止语音 (voice 参数; 无语音时停止上一个)。

        语音音量 = 全局(sfx×voice) × 声音块 volume × 角色 voice_volume。
        跳过模式 (skip_mode) 下不播放语音, 只停止 (快进静音)。
        """
        if self.skip_mode:
            self.engine.audio.stop_voice()
            return
        if not voice_name:
            self.engine.audio.stop_voice()
            return
        path = self.resolve_sound(voice_name)
        if path:
            self.engine.audio.play_voice(
                path, volume=self._voice_volume(voice_name, speaker))
        else:
            log.w("log.runtime.voice_unregistered", name=voice_name)

    def _voice_volume(self, voice_name, speaker=None) -> float:
        """计算语音音量系数: 声音块 volume × 角色 voice_volume。

        未配置的层为 1.0 (不衰减); 结果钳制在 [0, 1]。
        """
        vol = 1.0
        s = self.sounds.get(voice_name)
        if s:
            try:
                vol *= max(0.0, min(1.0, float(s.get("volume", 1.0))))
            except (TypeError, ValueError):
                pass
        if speaker:
            ch = self.characters.get(speaker)
            if ch:
                try:
                    vol *= max(0.0, min(1.0, float(
                        ch.get("voice_volume", 1.0))))
                except (TypeError, ValueError):
                    pass
        return max(0.0, min(1.0, vol))

    # -- 选项 -----------------------------------------------------------
    # -- 样式 -----------------------------------------------------------
    def _cmd_style(self, stmt):
        """注册样式: style <name> + 属性块 (文本框/文字/名字框/选项等)。"""
        if not stmt.args:
            return None
        name = stmt.args[0]
        self.styles[name] = dict(stmt.kwargs)
        self.engine.emit("style_register", name=name)
        log.i("log.runtime.style_registered", name=name,
              count=len(stmt.kwargs))
        return None

    def _cmd_use(self, stmt):
        """切换样式: use style <name> 或 use <name>"""
        if not stmt.args:
            return None
        if stmt.args[0] == "style" and len(stmt.args) > 1:
            name = self._interp(stmt.args[1])
        else:
            name = self._interp(stmt.args[0])
        if name == "default":
            self.current_style_name = None
            self.engine.display.reset_style()
            self.engine.emit("style_change", name="default")
            return None
        if name not in self.styles:
            log.w("log.runtime.style_undefined", line=stmt.line, name=name)
            return None
        self.current_style_name = name
        # 先回默认再应用: style 未定义的键用默认值, 不残留上一套样式
        self.engine.display.reset_style()
        parsed = self._parse_style_props(self.styles[name])
        self.engine.display.apply_style(parsed)
        # 正在显示的文本按新样式重新解析 (字号/颜色变化即时生效)
        d = self.engine.display
        if d.text_active:
            d._runs = d._rich.parse(
                d.full_text, base_size=d.style["text_size"],
                base_color=d.style["text_color"])
        self.engine.emit("style_change", name=name)
        return None

    def _cmd_ui(self, stmt):
        """配置 UI 主题素材图 (直接相对路径)。

        ui
            textbox: "materials/image/素材切片/对话/对话_adv对话框_llf.png"
            title_buttons: "图1_默认.png, 图1_焦点.png; 图2_默认.png, 图2_焦点.png"
            slot_panel: "path_llf.png"

        值 = 相对脚本目录的图片路径; 单组用逗号分隔 默认,焦点 (单个即无状态);
        分号分隔多组时按按钮索引依次取图 (不同按键不同图)。
        """
        if not stmt.kwargs:
            return None
        for comp, value in stmt.kwargs.items():
            groups = [g.strip() for g in str(value).split(";") if g.strip()]
            if len(groups) <= 1:
                parts = [p.strip() for p in groups[0].split(",")
                         if p.strip()] if groups else []
                if not parts:
                    continue
                paths = {"default": os.path.join(self.script_dir, parts[0])}
                if len(parts) > 1:
                    paths["focus"] = os.path.join(self.script_dir, parts[1])
                self.engine.display.set_theme_image(comp, paths)
            else:
                items = []
                for g in groups:
                    parts = [p.strip() for p in g.split(",") if p.strip()]
                    if not parts:
                        continue
                    item = {"default": os.path.join(self.script_dir, parts[0])}
                    if len(parts) > 1:
                        item["focus"] = os.path.join(self.script_dir, parts[1])
                    items.append(item)
                self.engine.display.set_theme_image(comp, items)
        return None

    def _parse_action(self, s: str) -> dict:
        """解析动作字符串: "type [参数...] [k=v ...]"。

        无名参数按动作类型的位置参数名填充:
            "start game_start" -> label=game_start
            "slot_menu load"   -> mode=load
            "save 0"           -> slot=0
            未知类型默认参数名为 label。
        """
        parts = str(s).split()
        if not parts:
            return None
        atype = parts[0]
        names = {"start": ("label",), "jump": ("label",), "call": ("label",),
                 "slot_menu": ("mode",), "save": ("slot",),
                 "load": ("slot",)}.get(atype, ("label",))
        params = {}
        pos = 0
        for p in parts[1:]:
            if "=" in p:
                k, v = p.split("=", 1)
                params[k] = v
            else:
                name = names[pos] if pos < len(names) else f"arg{pos}"
                params[name] = p
                pos += 1
        return {"type": atype, **params}

    def _cmd_menu(self, stmt):
        """定义命名菜单: menu <id> + 按键子块 (可精细化配置)。

        menu title
            start_button
                text: "开始游戏"
                image: "a_默认.png, a_焦点.png"   # 相对脚本目录 (逗号=默认,焦点)
                width: 262
                height: 98
                stretch: false            # 不拉伸 (原尺寸居中)
                text_visible: false       # 图自带文字时不渲染文案
                action: start game_start  # 动作: 类型 [参数] (可自定义插件动作)

        标题画面: title 块加 menu: <id> 使用; 系统菜单: 定义 menu system 覆盖内置。
        """
        if not stmt.args:
            return None
        mid = stmt.args[0]
        ui_cfg = {}
        for key in ("ui_click_sound", "ui_hover_sound"):
            if key in stmt.kwargs:
                ui_cfg[key] = str(stmt.kwargs[key])
        items = []
        for sub in stmt.block:
            props = dict(sub.kwargs)
            text = props.pop("text", sub.op)
            action = self._parse_action(props.pop("action", ""))
            cfg = {}
            for key in ("image", "image_focus", "image_disabled",
                        "image_active", "width", "height",
                        "stretch", "text_visible"):
                if key in props:
                    val = props[key]
                    if key in ("width", "height"):
                        try:
                            cfg[key] = int(float(val))
                        except (TypeError, ValueError):
                            pass
                    elif key in ("stretch", "text_visible"):
                        cfg[key] = str(val).lower() in ("true", "1", "yes",
                                                        "on")
                    elif key == "image":
                        # "默认图, 焦点图" -> image / image_focus
                        parts = [p.strip() for p in str(val).split(",")
                                 if p.strip()]
                        if parts:
                            cfg["image"] = parts[0]
                            if len(parts) > 1:
                                cfg["image_focus"] = parts[1]
                    else:
                        cfg[key] = str(val)
            items.append({"name": sub.op, "text": str(text),
                          "action": action, "cfg": cfg})
        if ui_cfg:
            self.menus[mid] = {"ui": ui_cfg, "items": items}
        else:
            self.menus[mid] = items
        self.engine.emit("menu_register", name=mid, items=len(items))
        log.i("log.runtime.menu_registered", mid=mid, count=len(items))
        return None

    def add_menu_button(self, mid: str, text: str, action,
                        cfg: dict = None, index: int = None) -> dict:
        """插件 API: 向命名菜单 (title/system/自定义) 追加/插入按钮。

        action: 动作 dict ({"type": ...}) 或动作字符串
        ("slot_menu save" / "start game_start" / 插件自定义动作)。
        cfg: {width, height, image, image_focus, stretch, text_visible,
              enabled(False=禁用态, 点击无效), name(按钮标识)}。
        """
        menu = self.menus.get(mid)
        if isinstance(menu, dict) and "items" in menu:
            items = menu["items"]
            ui = menu.get("ui", {})
        elif isinstance(menu, list):
            items = menu
            ui = {}
        else:
            items, ui = [], {}
            self.menus[mid] = {"ui": ui, "items": items}
        if isinstance(action, str):
            action = self._parse_action(action) or {"type": "close"}
        if not isinstance(action, dict):
            action = {"type": "close"}
        cfg = dict(cfg or {})
        if "enabled" in cfg:
            cfg["enabled"] = str(cfg["enabled"]).lower() in (
                "true", "1", "yes", "on")
        item = {
            "name": str(cfg.get("name") or text),
            "text": str(text), "action": dict(action), "cfg": cfg,
        }
        if index is None:
            items.append(item)
        else:
            items.insert(max(0, min(index, len(items))), item)
        # 统一为 dict 格式
        if not (isinstance(self.menus.get(mid), dict)
                and "items" in self.menus[mid]):
            self.menus[mid] = {"ui": ui, "items": items}
        self.engine.emit("menu_button_added", name=mid, text=str(text))
        log.i("log.runtime.menu_button_added", mid=mid, name=item["name"])
        return item

    def set_menu_button_state(self, mid: str, key, enabled: bool) -> bool:
        """设置菜单按钮启用/禁用状态。

        key: 按钮名 (子块名/添加时 cfg.name) / 按钮文本 / 整数索引。
        """
        menu = self.menus.get(mid)
        if isinstance(menu, dict):
            items = menu.get("items", [])
        elif isinstance(menu, list):
            items = menu
        else:
            return False
        idx = None
        if isinstance(key, int):
            idx = key
        else:
            key_s = str(key)
            for i, it in enumerate(items):
                if it.get("name") == key_s or str(it.get("text")) == key_s:
                    idx = i
                    break
            # 兼容: 外部传 {@key} 解析后的文本 (如 "Gallery"/"鉴赏")
            if idx is None:
                for i, it in enumerate(items):
                    if (self.engine.i18n.resolve(str(it.get("text")))
                            == key_s):
                        idx = i
                        break
        if idx is None or not (0 <= idx < len(items)):
            return False
        items[idx].setdefault("cfg", {})["enabled"] = bool(enabled)
        self.engine.emit("menu_button_state", name=mid,
                         button=items[idx]["name"], enabled=bool(enabled))
        return True

    def set_menu_button_cfg(self, mid: str, key, cfg_update: dict) -> bool:
        """插件 API: 更新菜单按钮的 cfg (如动态切换按钮图/文本)。

        自动模式等按钮的"激活/未激活"外观切换用。
        """
        menu = self.menus.get(mid)
        if isinstance(menu, dict):
            items = menu.get("items", [])
        elif isinstance(menu, list):
            items = menu
        else:
            return False
        idx = None
        if isinstance(key, int):
            idx = key
        else:
            key_s = str(key)
            for i, it in enumerate(items):
                if it.get("name") == key_s or str(it.get("text")) == key_s:
                    idx = i
                    break
            # 兼容: 外部传 {@key} 解析后的文本
            if idx is None:
                for i, it in enumerate(items):
                    if (self.engine.i18n.resolve(str(it.get("text")))
                            == key_s):
                        idx = i
                        break
        if idx is None or not (0 <= idx < len(items)):
            return False
        items[idx].setdefault("cfg", {}).update(dict(cfg_update))
        self.engine.emit("menu_button_cfg", name=mid,
                         button=items[idx]["name"])
        return True

    def _menu_items(self, mid: str) -> list:
        """把命名菜单转成 selection items: [(text, action, cfg), ...]。"""
        menu = self.menus.get(mid)
        if not menu:
            return None
        if isinstance(menu, dict):
            menu = menu["items"]
        out = []
        for it in menu:
            action = it["action"]
            if action is None:
                action = {"type": "close"}
            # 按钮文本支持游戏文本多语言 {@key}
            out.append((self.engine.i18n.resolve(it["text"]),
                        action, it["cfg"]))
        return out

    def _cmd_typing(self, stmt):
        """切换对话框文字显示模式: typing <模式名>

        预设: typewriter (默认打字机) / instant (直接出现) / terminal (终端)
        插件可注册自定义模式 (display.register_text_mode)。
        """
        if not stmt.args:
            return None
        self.engine.display.set_text_mode(self._interp(stmt.args[0]))
        return None

    # -- 声音系统 -------------------------------------------------------
    def resolve_sound(self, name: str) -> str:
        """把声音注册名解析为绝对路径 (未注册时返回 None)。"""
        s = self.sounds.get(name)
        if s and s.get("file"):
            return os.path.join(self.script_dir, str(s["file"]))
        return None

    def _cmd_sound(self, stmt):
        """注册声音: sound <名称> + 属性块。

        sound sfx_click
            type: sfx_ui        # music / sfx_ui / sfx_story / voice
            file: "sfx/click.wav"
            volume: 0.8         # 可选
        """
        if not stmt.args:
            return None
        name = stmt.args[0]
        props = dict(stmt.kwargs)
        stype = props.pop("type", "sfx_story")
        f = props.pop("file", "")
        self.sounds[name] = {"type": str(stype), "file": str(f), **props}
        self.engine.emit("sound_register", name=name, type=stype)
        log.i("log.runtime.sound_registered", name=name, stype=stype)
        return None

    def _cmd_sfx(self, stmt):
        """播放剧情音效: sfx <声音名>"""
        if not stmt.args:
            return None
        name = self._interp(stmt.args[0])
        path = self.resolve_sound(name)
        if path:
            self.engine.audio.play_sound(path)
        else:
            log.w("log.runtime.sfx_unregistered", line=stmt.line, name=name)
        return None

    def _cmd_music(self, stmt):
        """播放音乐: music <注册名或路径> [loop 1/0] [fade 秒|表达式]

        loop 1=循环 (播完自动重播), 0=单次; fade 0 无淡入淡出;
        切换曲目自动旧曲淡出新曲淡入。fade/loop 值支持变量/表达式。
        """
        if not stmt.args:
            return None
        args = list(stmt.args)
        fade = None
        if "fade" in args:
            fi = args.index("fade")
            if fi + 1 < len(args):
                try:
                    fade = float(self.evaluate(args[fi + 1]))
                except (ValueError, RuntimeError_):
                    fade = None
            del args[fi:fi + 2]
        target = self._interp(args[0])
        loop = True
        if "loop" in args:
            idx = args.index("loop")
            if idx + 1 < len(args):
                try:
                    loop = bool(self.evaluate(args[idx + 1]))
                except RuntimeError_:
                    loop = True
        # 注册名优先, 否则按路径
        is_reg = target in self.sounds
        path = self.resolve_sound(target)
        if path is None:
            path = target
        self.engine.audio.play_music(path, loop, fade,
                                     name=(target if is_reg else None))
        # 记录标题 BGM (start 块配置, 鉴赏/回标题恢复用)
        if self.current_label == "start":
            self.title_bgm = target if is_reg else path
        return None

    def _cmd_pause(self, stmt):
        """暂停: pause music [fade 秒] / pause all (全局暂停, 淡出配置沿用)"""
        if not stmt.args:
            return None
        target = stmt.args[0]
        fade = None
        if len(stmt.args) > 2 and stmt.args[1] == "fade":
            try:
                fade = float(self.evaluate(stmt.args[2]))
            except (ValueError, RuntimeError_):
                fade = None
        if target in ("music", "bgm"):
            self.engine.audio.pause_music(fade)
        elif target in ("all", "everything"):
            self.engine.audio.pause_all(fade)
        return None

    def _cmd_resume(self, stmt):
        """恢复音乐: resume music [fade 秒]"""
        if not stmt.args or stmt.args[0] not in ("music", "bgm"):
            return None
        fade = None
        if len(stmt.args) > 2 and stmt.args[1] == "fade":
            try:
                fade = float(stmt.args[2])
            except ValueError:
                fade = None
        self.engine.audio.resume_music(fade)
        return None

    def _cmd_volume(self, stmt):
        """音量调整:

        volume music <0-1>          BGM 音量
        volume sfx <0-1>            音效音量 (同时影响语音 master)
        volume voice <0-1>          全局语音音量
        volume voice <角色> <0-1>    某个角色的语音音量 (char voice_volume)
        """
        if len(stmt.args) < 2:
            return None
        target = stmt.args[0]
        if target in ("music", "bgm"):
            try:
                vol = max(0.0, min(1.0, float(self._interp(stmt.args[1]))))
            except ValueError:
                return None
            self.engine.audio.set_bgm_volume(vol)
        elif target in ("sfx", "sound"):
            try:
                vol = max(0.0, min(1.0, float(self._interp(stmt.args[1]))))
            except ValueError:
                return None
            self.engine.audio.set_sfx_volume(vol)
        elif target == "voice":
            if len(stmt.args) >= 3:
                # volume voice <角色> <音量>: 按角色独立调控
                cid = self._interp(stmt.args[1])
                try:
                    vol = max(0.0, min(1.0, float(self._interp(stmt.args[2]))))
                except ValueError:
                    return None
                if cid in self.characters:
                    self.characters[cid]["voice_volume"] = vol
                    log.i("log.runtime.voice_volume_set", cid=cid, vol=vol)
                else:
                    log.w("log.runtime.voice_volume_char_missing", line=stmt.line,
              cid=cid)
            else:
                # volume voice <音量>: 全局语音音量
                try:
                    vol = max(0.0, min(1.0, float(self._interp(stmt.args[1]))))
                except ValueError:
                    return None
                self.engine.audio.set_voice_volume(vol)
        return None

    def _menu_ui(self, mid: str) -> dict:
        """取命名菜单的 UI 音效配置 (无则空)。"""
        menu = self.menus.get(mid)
        if isinstance(menu, dict) and menu.get("ui"):
            return menu["ui"]
        return {}

    def _cmd_title(self, stmt):
        """显示标题画面 (阻塞直到玩家选择)。

        title
            caption: "游戏标题"         # 标题文字 (支持富文本, 可留空)
            image: "materials/title.png"  # 可选: 标题图片 (显示在文字上方)
            title_x: center            # 标题水平位置: center/left/right/数字
            title_y: 200               # 标题垂直中心 (像素)
            start: game_start          # "开始游戏" -> 跳转标签 (必填)
            start_text: "开始游戏"     # 可选: 自定义按钮文本
            load: 0                    # 可选: 读取存档槽位
            load_text: "读取存档"
            quit: true                 # 可选: 退出按钮
            quit_text: "退出游戏"
            button_x: center           # 按钮区水平锚点
            button_y: 400              # 按钮区垂直锚点 (第一个按钮中心)
        """
        props = dict(stmt.kwargs)
        caption = str(props.get("caption") or props.get("title") or "")
        image = props.get("image")
        pos = {
            "title_x": props.get("title_x", "center"),
            "title_y": props.get("title_y"),
            "button_x": props.get("button_x", "center"),
            "button_y": props.get("button_y"),
        }
        if "button_columns" in props:
            try:
                pos["columns"] = max(1, int(float(props["button_columns"])))
            except (TypeError, ValueError):
                pass
        for bool_key in ("button_stretch", "button_text"):
            if bool_key in props:
                pos[bool_key] = str(props[bool_key]).lower() in (
                    "true", "1", "yes", "on")
        items = None
        menu_id = props.get("menu")
        if menu_id:
            self.engine._set_ui_sounds(self._menu_ui(str(menu_id)))
            items = self._menu_items(str(menu_id))
            if items is None:
                log.w("log.runtime.menu_undefined", line=stmt.line, mid=menu_id)
                items = []
        if items is None:
            items = []
            start_label = props.get("start")
            if start_label:
                text = str(props.get("start_text")
                           or self.engine.i18n.t("menu.start"))
                items.append((text, {"type": "start", "label": str(start_label)}, {}))
            if "load" in props:
                try:
                    slot = int(props["load"])
                except (TypeError, ValueError):
                    slot = 0
                    log.w("log.runtime.title_load_invalid", line=stmt.line)
                text = str(props.get("load_text")
                           or self.engine.i18n.t("menu.load"))
                items.append((text, {"type": "slot_menu", "mode": "load"}, {}))
            if str(props.get("quit", "false")).lower() in ("true", "1", "yes", "on"):
                text = str(props.get("quit_text")
                           or self.engine.i18n.t("menu.quit"))
                items.append((text, {"type": "quit"}, {}))
        if not items:
            log.w("log.runtime.title_no_items", line=stmt.line)
            return None
        self.engine.display.show_title(caption, items, image, pos)
        self.blocked = "title"
        return BLOCK

    def _cmd_choice(self, stmt):
        # choice [ui_click 名] [ui_hover 名]
        ui_cfg = {}
        args = list(stmt.args)
        if "ui_click" in args:
            ai = args.index("ui_click")
            if ai + 1 < len(args):
                ui_cfg["ui_click_sound"] = args[ai + 1]
        if "ui_hover" in args:
            ai = args.index("ui_hover")
            if ai + 1 < len(args):
                ui_cfg["ui_hover_sound"] = args[ai + 1]
        self.engine._set_ui_sounds(ui_cfg)
        options = stmt.kwargs.get("options", [])
        # 选项文本支持变量插值 + 游戏文本多语言 {@key}
        rendered = []
        for t, lbl in options:
            t = self._interp(t)
            t = self.engine.i18n.resolve(t)
            t = self._interp(t) if t else t
            rendered.append((t, lbl))
        # choice_prepare: 显示前广播 (插件可原地修改 options 列表,
        # 用于动态选项/直播互动/外部注入)
        self.engine.emit("choice_prepare", options=rendered)
        self.engine.display.show_choices(rendered)
        self.blocked = "choice"
        return BLOCK

    def choose(self, index: int, label: str) -> None:
        """选项被点击后由引擎调用。"""
        self.release("choice")
        self.engine.display.clear_text()
        # 选择支结束, 恢复默认 UI 音效
        self.engine._set_ui_sounds({})
        if label:
            # 跳转失败抛 RuntimeError_, 由引擎按 error 处理 (弹窗)
            self._jump_to(label)
        self.advance()

    # -- 询问对话框 -----------------------------------------------------
    def _cmd_confirm(self, stmt):
        """询问对话框: confirm <文本> [yes 文本] [no 文本] [-> 变量]

        阻塞直到玩家选择; 结果 ("yes"/"no") 存入 -> 指定的变量
        (也可用 if $var == "yes" 分支)。未指定变量时仅阻塞。
        """
        args = list(stmt.args)
        var = None
        if "->" in args:
            vi = args.index("->")
            if vi + 1 < len(args):
                var = args[vi + 1]
            del args[vi:vi + 2]
        text = self._interp(args[0]) if args else ""
        yes, no = (self.engine.i18n.t("confirm.yes"),
                   self.engine.i18n.t("confirm.no"))
        if "yes" in args:
            yi = args.index("yes")
            if yi + 1 < len(args):
                yes = self._interp(args[yi + 1])
            del args[yi:yi + 2]
        if "no" in args:
            ni = args.index("no")
            if ni + 1 < len(args):
                no = self._interp(args[ni + 1])
            del args[ni:ni + 2]
        if not text:
            log.w("log.runtime.confirm_empty", line=stmt.line)
            return None

        def _done(choice):
            if var:
                self.engine.set_var(var, choice)
            self.release("confirm")
            self.advance()

        self.engine.ask_confirm(text, yes, no,
                                lambda: _done("yes"),
                                on_no=lambda: _done("no"))
        self.blocked = "confirm"
        return BLOCK

    # -- 变量与条件 -----------------------------------------------------
    # ==================================================================
    # 命名空间系统
    # ==================================================================
    _NS_RE = r"[A-Za-z_\u4e00-\u9fff][\w\u4e00-\u9fff]*(?:::[A-Za-z_\u4e00-\u9fff][\w\u4e00-\u9fff]*)?"

    def _cmd_using(self, stmt):
        """using <命名空间> [...] —— 导入命名空间 (类似 C++ using)。

        之后该命名空间的指令可省略前缀直接调用。示例: ``using shake``
        """
        for arg in stmt.args:
            ns = str(arg).strip()
            if ns:
                self.using_ns.add(ns)
        self.engine.emit("using", namespaces=list(self.using_ns))
        return None

    def _cmd_plugin(self, stmt):
        """运行时插件管理: plugin load <插件名...> / plugin unload <插件名...>
        / plugin list

        装载后自动加入 using 命名空间; 卸载时清指令/事件/订阅。
        """
        if not stmt.args:
            return None
        action = stmt.args[0]
        names = [str(a) for a in stmt.args[1:]]
        pm = self.engine.plugins
        if action in ("load", "enable"):
            directory = pm.directory
            if not directory:
                log.w("log.runtime.plugin_no_dir", line=stmt.line)
                return None
            for name in names:
                path = os.path.join(directory, name + ".py")
                if not os.path.isfile(path):
                    log.w("log.runtime.plugin_file_missing", line=stmt.line, name=path)
                    continue
                mod_name = "gm_plugin_" + name
                if mod_name in pm._modules:
                    log.i("log.runtime.plugin_already_loaded", name=name)
                    continue
                if pm.load_module_from_path(mod_name, path):
                    self.using_ns.add(name)
                    log.i("log.runtime.plugin_loaded", name=name)
            return None
        if action in ("unload", "disable"):
            for name in names:
                mod_name = "gm_plugin_" + name
                if mod_name in pm._modules:
                    pm.unload_module(mod_name)
                    self.using_ns.discard(name)
                    log.i("log.runtime.plugin_unloaded", name=name)
                else:
                    log.w("log.runtime.plugin_not_loaded", line=stmt.line, name=name)
            return None
        if action == "list":
            loaded = sorted(m.replace("gm_plugin_", "")
                            for m in pm._modules)
            log.i("log.runtime.plugin_list",
              names=", ".join(loaded) or self.engine.i18n.t("log.runtime.none"))
            return None
        log.w("log.runtime.plugin_op_unknown", line=stmt.line, op=action)
        return None

    def _norm_var_name(self, name: str) -> str:
        """变量名规范化: main::x -> x (main 域键为裸名); 其余保留。"""
        if name.startswith("main::"):
            return name[len("main::"):]
        return name

    def _resolve_var(self, name: str, default=None):
        """变量解析: 显式命名空间按域查; 无命名空间先 main:: 再 builtin::。"""
        if "::" in name:
            return self.vars.get(self._norm_var_name(name), default)
        if name in self.vars:
            return self.vars[name]
        if name in self.builtin_vars:
            return self.builtin_vars[name]
        return default

    def _cmd_set(self, stmt):
        if len(stmt.args) < 2:
            log.w("log.runtime.set_syntax", line=stmt.line)
            return None
        name = self._norm_var_name(stmt.args[0])
        expr = " ".join(stmt.args[1:])
        expr = expr.lstrip("=").strip()
        self.vars[name] = self.evaluate(expr)
        self.engine.emit("var_set", name=name, value=self.vars[name])
        return None

    def _cmd_if(self, stmt):
        branches = stmt.kwargs.get("branches", [])
        else_body = stmt.kwargs.get("else")
        for cond_expr, body in branches:
            # 条件求值失败抛 RuntimeError_, 由引擎按 error 处理 (弹窗)
            if self.evaluate(cond_expr):
                self._push_block(body)
                return None
        if else_body:
            self._push_block(else_body)
        return None

    def evaluate(self, expr: str):
        """安全求值 DSL 表达式。支持 $var 与裸变量名引用, 以及算术/比较/逻辑运算。

        安全性: eval 使用空 __builtins__, 变量表只含游戏变量与常量,
        无法调用任何函数或访问模块。
        """
        expr = expr.strip()
        if not expr:
            return None
        # 字面量快捷路径
        if expr in ("true", "True"):
            return True
        if expr in ("false", "False"):
            return False
        # 翻译 $var -> __vars__['var'] (支持命名空间: $main::x / $plugin::x)
        translated = re.sub(
            r"\$(" + self._NS_RE + r")",
            r"__vars__['\1']", expr)
        # 安全检查: 禁止函数调用与魔法属性 (__vars__ 为内部合法名)
        if re.search(r"[A-Za-z_\u4e00-\u9fff]\s*\(", translated):
            raise RuntimeError_(f"表达式不允许函数调用: {expr!r}")
        if re.search(r"\b__(?!vars__)\w+__\b", translated):
            raise RuntimeError_(f"表达式包含非法符号: {expr!r}")
        ns = dict(self.vars)
        # 命名空间别名: main::x -> x; builtin:: 域合并
        for k in list(self.vars):
            if "::" not in k and f"main::{k}" not in ns:
                ns[f"main::{k}"] = self.vars[k]
        for k, v in self.builtin_vars.items():
            ns.setdefault(k, v)
            ns.setdefault(f"builtin::{k}", v)
        ns["__vars__"] = ns
        ns["true"] = ns["True"] = True
        ns["false"] = ns["False"] = False
        ns["None"] = None
        try:
            return eval(translated, {"__builtins__": {}}, ns)
        except Exception as exc:
            raise RuntimeError_(f"表达式求值失败 {expr!r}: {exc}")

    # -- 流程控制 -------------------------------------------------------
    def _cmd_jump(self, stmt):
        if not stmt.args:
            return None
        label = self._interp(stmt.args[0])
        self._jump_to(label)
        return None

    def _cmd_call(self, stmt):
        if not stmt.args:
            return None
        label = self._interp(stmt.args[0])
        if label not in self.labels:
            raise RuntimeError_(f"call 到不存在的标签: {label!r}")
        self._push_block(self.labels[label], 0, label)
        self.engine.emit("label_enter", label=label)
        return None

    def _cmd_return(self, stmt):
        self._pop_block()
        return None

    # -- 时间 / 音频 ----------------------------------------------------
    def _cmd_sleep(self, stmt):
        try:
            sec = float(self._interp(stmt.args[0])) if stmt.args else 1.0
        except (ValueError, IndexError):
            sec = 1.0
        self.sleep_until = time.time() + sec
        self.blocked = "sleep"
        return BLOCK

    def _cmd_stop(self, stmt):
        """停止: stop music [fade 秒] / stop all (全局停止, 淡出配置沿用)"""
        if not stmt.args:
            return None
        target = stmt.args[0]
        fade = None
        if "fade" in stmt.args:
            fi = stmt.args.index("fade")
            if fi + 1 < len(stmt.args):
                try:
                    fade = float(self.evaluate(stmt.args[fi + 1]))
                except (ValueError, RuntimeError_):
                    fade = None
        if target in ("all", "everything"):
            self.engine.audio.stop_all(fade)
        elif target in ("music", "bgm"):
            self.engine.audio.stop_music(fade)
        return None

    # -- 转场 -----------------------------------------------------------
    def _cmd_fade(self, stmt):
        self.engine.display.start_fadein()
        return None

    def _cmd_fadeout(self, stmt):
        self.engine.display.start_fadeout()
        return None

    # -- 存档 -----------------------------------------------------------
    def _cmd_save(self, stmt):
        slot = 0
        if stmt.args:
            try:
                slot = int(stmt.args[0])
            except ValueError:
                slot = 0
        self.engine.save_game(slot, silent=False)
        return None

    def _cmd_load(self, stmt):
        slot = 0
        if stmt.args:
            try:
                slot = int(stmt.args[0])
            except ValueError:
                slot = 0
        self.engine.load_game(slot)
        return None

    # -- 结束 -----------------------------------------------------------
    def _cmd_ending(self, stmt):
        """结束游戏: ending [结局名]

        显示结束画面 (结局名), 淡出停止 BGM, 结局名记入全局进度
        (save/global.json, 跨存档; 鉴赏插件等可监听 ending_recorded)。
        """
        name = self._interp(stmt.args[0]) if stmt.args else None
        self.engine.record_ending(name)
        self.engine.display.show_ending(name)
        self.engine.audio.stop_music()   # 淡出 (沿用 music_fade)
        self.ended = True
        self.running = False
        self.engine.emit("script_end", ending=name)
        return None

    def _cmd_pass(self, stmt):
        return None

    def _cmd_python(self, stmt):
        """python:: 原始代码块: 在脚本中直接执行嵌入的 Python 代码。

        语法 (双冒号, 块内行原样保留, 不按 DSL 解析)::

            python::
                import random
                engine.set_var("luck", random.randint(1, 100))
                runtime.vars["note"] = "来自 python 块"

        命名空间提供 engine / runtime / display / audio / save / i18n /
        ui / pygame / os / math 等常用对象; 代码拥有完整解释器权限
        (如同插件, 仅在可信脚本中使用); 异常记录日志不中断游戏。
        """
        code = str(stmt.kwargs.get("code") or "")
        if not code.strip():
            return None
        # 块内行保留原缩进, 执行前去除公共前导空白
        import textwrap
        code = textwrap.dedent(code)
        ns = {
            "engine": self.engine,
            "runtime": self,
            "display": self.engine.display,
            "audio": self.engine.audio,
            "save": self.engine.save,
            "i18n": self.engine.i18n,
            "ui": self.engine.ui,
            "pygame": __import__("pygame"),
            "os": __import__("os"),
            "math": __import__("math"),
        }
        try:
            exec(code, ns)
        except Exception as exc:
            log.w("log.runtime.python_exec_failed", exc=exc)
        return None

    def _cmd_window(self, stmt):
        """运行时窗口配置命令:

        window config
            title: "新标题"            # 窗口名
            width: 1600               # 窗口大小 (内容等比缩放, 比例不变)
            height: 900
            icon: "materials/x.png"   # 图标 (相对脚本目录)
            fullscreen: true          # 全屏开关
            resizable: true           # 是否允许拖拽缩放窗口
            fps: 60                   # 帧率
        """
        if stmt.args and stmt.args[0] != "config":
            return None
        cfg = dict(stmt.kwargs)
        if not cfg:
            return None
        # 运行时选项 (确认框/键位/UI 音效/文案) + 窗口配置 (标题/尺寸/图标/全屏)
        self.engine.apply_config(cfg)
        self.engine.apply_window_config(cfg)
        self.engine.emit("window_config", config=cfg)
        log.i("log.runtime.window_config_applied", cfg=cfg)
        return None

    def _cmd_language(self, stmt):
        """language 块: 声明项目支持的语言、默认语言与显示名。

        language:
            default: en            # 默认语言 (当前语言缺翻译时回退)
            en: "English"          # 语言码 -> 设置中显示的名字
            zh-CN: "简体中文"
        """
        cfg = dict(stmt.kwargs)
        if not cfg:
            return None
        self.engine.i18n.configure_language(
            cfg, lang_dir=os.path.join(self.script_dir, "lang"))
        return None

    def _cmd_fullscreen(self, stmt):
        """切换全屏: fullscreen true / fullscreen false"""
        if not stmt.args:
            return None
        val = str(self._interp(stmt.args[0])).lower() in (
            "true", "1", "yes", "on")
        self.engine.set_fullscreen(val)
        self.engine.emit("window_config", config={"fullscreen": val})
        return None

    # -- widgets 模板实例化 ---------------------------------------------
    def _instantiate_widget(self, name: str) -> None:
        tpl = self.widgets_templates.get(name)
        if not tpl:
            return
        body = tpl["blocks"].get("when run") or []
        if body:
            self._push_block(body)
        else:
            log.i("log.runtime.widget_no_run", name=name)

    def _cmd_read_settings(self, stmt):
        """从设置文件读取设置并赋值到对应变量 (read_settings)。

        读取 save/settings.json, 值写入 setting.gal 绑定的变量
        (文件里读不到的项用默认值); 随后按变量重新应用 window 配置
        (window 块声明支持 $变量, 如 width: "$res_w")。
        应在脚本开头 (start 标签首行) 调用。
        """
        self.engine.settings.load(apply_defaults=True)
        self._reapply_window_config()
        return None

    def _reapply_window_config(self) -> None:
        """插值 window/config 块的 $变量后重新应用 (声明支持变量)。

        只应用窗口类配置 (标题/尺寸/图标/全屏等); 确认框/键位/音效等
        交互配置由启动器 apply_config 负责, 这里不重复 (避免测试/直接
        使用引擎时意外开启确认框)。
        """
        try:
            from framework.engine.loader import load_script_with_imports
            script = load_script_with_imports(self.script_path)
            for stmt in script.statements:
                if stmt.op in ("window", "config") and not stmt.args:
                    cfg = {k: self._interp(str(v))
                           for k, v in stmt.kwargs.items()}
                    self.engine.apply_window_config(cfg)
        except Exception as exc:
            log.w("log.runtime.window_reapply_failed", exc=exc)

    # ==================================================================
    # 文本插值
    # ==================================================================
    def _interp(self, text: str) -> str:
        """替换 $var 变量 (支持 $ns::name); $$ 转义为字面 $。"""
        def repl(m):
            return str(self._resolve_var(m.group(1), ""))
        text = text.replace("$$", "\x00")
        text = re.sub(r"\$(" + self._NS_RE + r")", repl, text)
        return text.replace("\x00", "$")

    # ==================================================================
    # 存档快照
    # ==================================================================
    def snapshot(self) -> dict:
        """导出运行时状态供存档。

        对象以脚本 id 存储 (不存图片路径), 图片路径以脚本为准。
        """
        d = self.engine.display
        return {
            "vars": dict(self.vars),
            "label": self.current_label,
            "ip": self.ip,
            "script": os.path.basename(self.script_path) if self.script_path else None,
            # 调用栈: 每帧 (标签, 栈内 ip), 标签名可序列化
            "call_stack": [(lbl, stk_ip)
                           for (_stmts, stk_ip, lbl) in self.call_stack if lbl],
            # 阻塞状态 (读档后恢复, 支持在文本/选择支处继续)
            "blocked": self.blocked,
            "text": d.full_text if self.blocked == "text" else None,
            "speaker": d.speaker if self.blocked == "text" else None,
            "choices": d.choices if self.blocked == "choice" else None,
            # 视觉与音频 (背景/立绘存脚本 id, 路径以脚本为准)
            "bg_id": d.bg_id,
            "bg_scene": d.bg_scene,
            "bg_pose": d.bg_pose,
            "bg": d.bg_path if d.bg_id is None and d.bg_scene is None else None,
            "sprites": d.sprite_state(),
            "music": (self.engine.audio.current_bgm_name
                      or self.engine.audio.current_bgm),
            "style": self.current_style_name,
        }

    def restore(self, data: dict) -> None:
        """从存档恢复运行时状态。"""
        self.vars = dict(data.get("vars", {}))
        label = data.get("label")
        ip = data.get("ip", 0)
        # 恢复调用栈
        self.call_stack = []
        for lbl, stk_ip in data.get("call_stack", []):
            if lbl in self.labels:
                self.call_stack.append((self.labels[lbl], stk_ip, lbl))
        if label and label in self.labels:
            self.statements = self.labels[label]
            self.ip = int(ip)
            self.current_label = label
        else:
            self.statements = self.labels.get("start", [])
            self.ip = 0
            self.current_label = "start"
        self.running = True
        self.ended = False
        self.sleep_until = None
        # 重建角色表/场景表 (定义可能位于存档点之前)
        self._rebuild_characters()
        self._rebuild_scenes()
        # 恢复样式
        style_name = data.get("style")
        if style_name:
            self._cmd_use(Statement(op="use", args=[style_name], line=0))
        elif self.current_style_name is not None:
            self.current_style_name = None
            self.engine.display.reset_style()
        # 阻塞状态: text / choice 恢复 (由 display.restore_state 配合显示),
        # sleep 不恢复 (剩余等待时间无意义)
        blocked = data.get("blocked")
        self.blocked = blocked if blocked in ("text", "choice") else None
