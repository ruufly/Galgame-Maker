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
        self.vars = {}
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
            "set": self._cmd_set,
            "if": self._cmd_if,
            "jump": self._cmd_jump,
            "call": self._cmd_call,
            "return": self._cmd_return,
            "sleep": self._cmd_sleep,
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
            "window": self._cmd_pass,
            "config": self._cmd_pass,
            "style": self._cmd_style,
            "use": self._cmd_use,
            "selection_style": self._cmd_selection_style,
        }

    # ==================================================================
    # 脚本加载
    # ==================================================================
    def load_script(self, path: str) -> None:
        path = os.path.abspath(path)
        self.script_path = path
        self.script_dir = os.path.dirname(path)
        self.engine.project_dir = self.script_dir
        script = parse_file(path)
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
        # selection 全局样式 (静态应用, 读档后仍生效)
        self.engine.display.selection_style_overrides.clear()
        for stmt in self._scan_statements(script):
            if stmt.op == "selection_style":
                self._apply_selection_style_stmt(stmt)
        self.engine.emit("script_load", path=path, name=script.name)
        log.info(f"脚本已加载: {path} (标签 {len(script.labels)} 个, "
                 f"对象 {len(self.script_objects)} 个, "
                 f"角色 {len(self.characters)} 个, "
                 f"场景 {len(self.scenes)} 个)")
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
            self.characters[cid] = {
                "id": cid, "name": name, "sprites": props,
                "default": default, "pos": pos, "scale": scale, "mode": mode,
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
            self.scenes[sid] = {"id": sid, "name": name,
                                "backgrounds": props, "default": default}

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
                             "button_border_hover"}
    _SEL_STYLE_NUM_KEYS = {"width_ratio", "height", "gap", "caption_y",
                           "caption_size", "dim_alpha", "text_size",
                           "unhover_alpha"}
    _SEL_STYLE_STR_KEYS = {"anchor_x", "caption_x", "anchor_y"}

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
        "choice_border", "choice_border_hover",
    }
    _STYLE_INT_KEYS = {"textbox_alpha", "textbox_border_width",
                       "textbox_radius", "text_size"}

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
        return out

    # ------------------------------------------------------------------
    def load_widget_templates(self, directory: str) -> None:
        if not os.path.isdir(directory):
            log.warning(f"widgets 目录不存在: {directory}")
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
                    log.info(f"widget 模板已注册: {tpl['name']}")
            except Exception as exc:
                log.warning(f"widget 模板加载失败 {path}: {exc}")

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
        """执行语句直到阻塞或脚本结束。"""
        while self.running and not self.ended:
            if self.blocked:
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
                return

    def _dispatch(self, stmt: Statement):
        handler = self._builtins.get(stmt.op)
        if handler is not None:
            return handler(stmt)
        # 插件自定义指令
        if self.engine.commands.has(stmt.op):
            result = self.engine.commands.call(stmt.op, stmt)
            return result if result == BLOCK else None
        # 裸词: 尝试 widgets 模板实例化
        if not stmt.args and not stmt.kwargs and stmt.op in self.widgets_templates:
            self._instantiate_widget(stmt.op)
            return None
        log.warning(f"第{stmt.line}行: 未知指令 {stmt.op!r}, 已跳过")
        return None

    def _end_script(self) -> None:
        self.ended = True
        self.running = False
        self.engine.emit("script_end")
        log.info("脚本执行结束")

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
        """注册场景: scene <id> + 属性块 (name/default/背景名: 路径)。"""
        if not stmt.args:
            return None
        sid = stmt.args[0]
        props = dict(stmt.kwargs)
        name = props.pop("name", sid)
        default = props.pop("default", None)
        self.scenes[sid] = {"id": sid, "name": name,
                            "backgrounds": props, "default": default}
        # 同步到对象注册表 (存档/读档用)
        self.script_objects[sid] = {
            "kind": "scene", "image": default or (
                next(iter(props.values())) if props else None),
            "props": dict(stmt.kwargs),
        }
        self.engine.emit("scene_register", id=sid, name=name)
        log.info(f"场景已注册: {sid} ({name}), 背景 {len(props)} 张")
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
                log.warning(f"第{stmt.line}行: 场景 {target} 无背景 {pose!r}, "
                            f"改用默认背景")
                pose = None
            if img is None:
                img = scene.get("default")
            if img:
                d.set_bg(img, effect)
                d.bg_scene = target
                d.bg_pose = pose
                d.bg_id = None
                self.engine.emit("scene_change", id=target,
                                 name=scene["name"], background=img, pose=pose)
            return None
        # 直接路径
        d.set_bg(target, effect)
        d.bg_scene = None
        d.bg_pose = None
        d.bg_id = None
        self.engine.emit("bg_change", path=target, effect=effect)
        return None

    # -- 角色 -----------------------------------------------------------
    def _cmd_char(self, stmt):
        """注册角色: char <id> + 属性块 (name/default/立绘名: 路径)。"""
        if not stmt.args:
            return None
        cid = stmt.args[0]
        props = dict(stmt.kwargs)
        name = props.pop("name", cid)
        default = props.pop("default", None)
        pos = props.pop("pos", "center")
        scale = props.pop("scale", None)
        mode = props.pop("mode", None)
        self.characters[cid] = {
            "id": cid, "name": name, "sprites": props,
            "default": default, "pos": pos, "scale": scale, "mode": mode,
        }
        # 同步到对象注册表 (存档/读档用)
        self.script_objects[cid] = {
            "kind": "char", "image": default or (
                next(iter(props.values())) if props else None),
            "props": dict(stmt.kwargs),
        }
        self.engine.emit("character_register", id=cid, name=name)
        log.info(f"角色已注册: {cid} ({name}), 立绘 {len(props)} 张")
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
                log.warning(f"第{stmt.line}行: 角色 {sid} 的立绘 {pose!r} 未定义")
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
        log.warning(f"第{stmt.line}行: show 的对象 {sid!r} 不存在")
        return None

    def _cmd_hide(self, stmt):
        if not stmt.args:
            return None
        sid = stmt.args[0]
        if sid in self.engine.display.sprites:
            self.engine.display.hide_sprite(sid)
        else:
            log.warning(f"第{stmt.line}行: hide 的对象 {sid!r} 不存在")
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
            log.warning(f"第{stmt.line}行: move 需要 move <id> to <位置>")
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
            log.warning(f"第{stmt.line}行: rotate 需要 rotate <id> <角度>")
            return None
        sid = stmt.args[0]
        try:
            angle = float(stmt.args[1])
        except ValueError:
            log.warning(f"第{stmt.line}行: rotate 角度无效: {stmt.args[1]!r}")
            return None
        duration = 0.0
        ease = "linear"
        rest = stmt.args[2:]
        if rest:
            try:
                duration = float(rest[0])
            except ValueError:
                pass
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
            log.warning(f"第{stmt.line}行: -> {ident} 没有待绑定的对象")
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
            log.warning(f"对象 {ident}: weight 已不承担背景职责, "
                        f"背景请改用 scene/bg 指令")
        else:
            self.engine.display.show_sprite(
                ident, obj.get("image"), obj.get("pos"),
                obj.get("scale"), obj.get("mode"), obj.get("effect"))

    # -- 文本 -----------------------------------------------------------
    def _cmd_text(self, stmt):
        text = self._interp(" ".join(stmt.args)) if stmt.args else ""
        if not text:
            log.warning(f"第{stmt.line}行: text 内容为空")
            return None
        self.engine.display.show_text(text)
        self.blocked = "text"
        return BLOCK

    def _cmd_say(self, stmt):
        if not stmt.args:
            return None
        speaker = self._interp(stmt.args[0])
        text = self._interp(" ".join(stmt.args[1:])) if len(stmt.args) > 1 else ""
        if not text:
            log.warning(f"第{stmt.line}行: say 内容为空")
            return None
        # 台词分类: 角色 id -> 显示角色名; 旁白 -> 无名字框; 其他 -> 原样
        display_speaker = None
        if speaker in self.characters:
            display_speaker = self.characters[speaker]["name"]
        elif speaker and speaker != "旁白":
            display_speaker = speaker
        self.engine.display.show_text(text, display_speaker)
        self.blocked = "text"
        return BLOCK

    # -- 选项 -----------------------------------------------------------
    # -- 样式 -----------------------------------------------------------
    def _cmd_style(self, stmt):
        """注册样式: style <name> + 属性块 (文本框/文字/名字框/选项等)。"""
        if not stmt.args:
            return None
        name = stmt.args[0]
        self.styles[name] = dict(stmt.kwargs)
        self.engine.emit("style_register", name=name)
        log.info(f"样式已注册: {name} ({len(stmt.kwargs)} 项)")
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
            log.warning(f"第{stmt.line}行: 样式 {name!r} 未定义")
            return None
        self.current_style_name = name
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
        items = []
        start_label = props.get("start")
        if start_label:
            text = str(props.get("start_text") or "开始游戏")
            items.append((text, {"type": "start", "label": str(start_label)}))
        if "load" in props:
            try:
                slot = int(props["load"])
            except (TypeError, ValueError):
                slot = 0
                log.warning(f"第{stmt.line}行: title 的 load 槽位无效")
            text = str(props.get("load_text") or "读取存档")
            items.append((text, {"type": "slot_menu", "mode": "load"}))
        if str(props.get("quit", "false")).lower() in ("true", "1", "yes", "on"):
            text = str(props.get("quit_text") or "退出游戏")
            items.append((text, {"type": "quit"}))
        if not items:
            log.warning(f"第{stmt.line}行: title 没有菜单项")
            return None
        self.engine.display.show_title(caption, items, image, pos)
        self.blocked = "title"
        return BLOCK

    def _cmd_choice(self, stmt):
        options = stmt.kwargs.get("options", [])
        # 选项文本支持变量插值
        rendered = [(self._interp(t), lbl) for t, lbl in options]
        self.engine.display.show_choices(rendered)
        self.blocked = "choice"
        return BLOCK

    def choose(self, index: int, label: str) -> None:
        """选项被点击后由引擎调用。"""
        self.release("choice")
        self.engine.display.clear_text()
        if label:
            try:
                self._jump_to(label)
            except RuntimeError_ as exc:
                log.warning(str(exc))
        self.advance()

    # -- 变量与条件 -----------------------------------------------------
    def _cmd_set(self, stmt):
        if len(stmt.args) < 2:
            log.warning(f"第{stmt.line}行: set 需要 变量 = 值")
            return None
        name = stmt.args[0]
        expr = " ".join(stmt.args[1:])
        expr = expr.lstrip("=").strip()
        self.vars[name] = self.evaluate(expr)
        self.engine.emit("var_set", name=name, value=self.vars[name])
        return None

    def _cmd_if(self, stmt):
        branches = stmt.kwargs.get("branches", [])
        else_body = stmt.kwargs.get("else")
        for cond_expr, body in branches:
            try:
                if self.evaluate(cond_expr):
                    self._push_block(body)
                    return None
            except RuntimeError_ as exc:
                log.warning(f"第{stmt.line}行: 条件求值失败 {cond_expr!r}: {exc}")
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
        # 翻译 $var -> __vars__['var'] (裸变量名直接由命名空间解析)
        translated = re.sub(
            r"\$([A-Za-z_\u4e00-\u9fff][\w\u4e00-\u9fff]*)",
            r"__vars__['\1']", expr)
        # 安全检查: 禁止函数调用与魔法属性
        if re.search(r"[A-Za-z_\u4e00-\u9fff]\s*\(", translated):
            raise RuntimeError_(f"表达式不允许函数调用: {expr!r}")
        if re.search(r"\b__\w+__\b", translated):
            raise RuntimeError_(f"表达式包含非法符号: {expr!r}")
        ns = dict(self.vars)
        ns["__vars__"] = self.vars
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

    def _cmd_music(self, stmt):
        if not stmt.args:
            return None
        path = self._interp(stmt.args[0])
        loop = True
        if "loop" in stmt.args:
            loop = self._interp(stmt.args[stmt.args.index("loop") + 1]) != "0" \
                if stmt.args.index("loop") + 1 < len(stmt.args) else True
        self.engine.audio.play_music(path, loop)
        return None

    def _cmd_sound(self, stmt):
        if not stmt.args:
            return None
        self.engine.audio.play_sound(self._interp(stmt.args[0]))
        return None

    def _cmd_stop(self, stmt):
        self.engine.audio.stop_music()
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
        self.engine.display.show_ending()
        self.ended = True
        self.running = False
        self.engine.emit("script_end")
        return None

    def _cmd_pass(self, stmt):
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
            log.info(f"widget {name} 无 when run 块, 实例化空操作")

    # ==================================================================
    # 文本插值
    # ==================================================================
    def _interp(self, text: str) -> str:
        """替换 $var 变量; $$ 转义为字面 $。"""
        def repl(m):
            return str(self.vars.get(m.group(1), ""))
        text = text.replace("$$", "\x00")
        text = re.sub(r"\$([A-Za-z_\u4e00-\u9fff][\w\u4e00-\u9fff]*)", repl, text)
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
            "music": self.engine.audio.current_bgm,
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
