"""流程节点模型 (P2): 对话流节点图 <-> story.gal 标签结构。

映射约定 (v1, 语义等价优先于文本简洁):
- 节点 = story.gal 的一个标签 (label: 块)
- 顺序后继 (dialogue -> next) = 块尾追加 `jump <next>`
- 选择支选项 = choice 块内 `"文本" -> <目标标签>`
- jump 节点 = `jump/call <目标>`; ending = `ending [名称]`
- raw 节点 = 原样保留未知语句 (导入兜底, 不丢内容)

导入: labels -> 节点图 (标签名即节点 id, 保证 jump/choice 目标有效)
导出: 节点图 -> Script (story.gal), 每个节点一个标签
"""

from framework.engine.parser import Script, Statement

DIALOGUE_OPS = {"say", "nar", "text"}
DIALOGUE_LABEL = {"say": "对话", "nar": "旁白", "text": "文本"}


class FlowNode:
    """一个流程节点 (= 一个标签块)。

    extra_stmts: 块内紧随本节点语句之后的顺序语句 (对话链合并用,
    避免每句对话都生成一个标签)。
    """

    def __init__(self, node_id: str, kind: str, x: float = 0.0,
                 y: float = 0.0, next_id: str | None = None,
                 data: dict | None = None,
                 options: list | None = None, raw: Statement | None = None,
                 extra_stmts: list | None = None):
        self.node_id = node_id
        self.kind = kind          # dialogue/choice/jump/ending/label/raw
        self.x, self.y = x, y
        self.next_id = next_id    # 顺序后继节点 id
        self.data = data or {}    # dialogue: op/speaker/text; jump: target/is_call;
                                  # ending: name; label: text
        self.options = options or []   # choice: [[text, target_id], ...]
        self.raw = raw            # raw: 原始语句
        self.extra_stmts = extra_stmts or []

    def summary(self) -> str:
        if self.kind == "dialogue":
            sp = self.data.get("speaker", "")
            tx = self.data.get("text", "")
            return ("%s: %s" % (sp, tx)) if sp else tx
        if self.kind == "choice":
            return "选择支 (%d 项)" % len(self.options)
        if self.kind == "jump":
            return "跳转 → %s" % self.data.get("target", "?")
        if self.kind == "ending":
            return "结局%s" % ("「%s」" % self.data["name"]
                               if self.data.get("name") else "")
        if self.kind == "label":
            return "标签%s" % ("「%s」" % self.data.get("text", "")
                               if self.data.get("text") else "")
        if self.kind == "action":
            return "%s %s" % (self.raw.op, " ".join(self.raw.args)) \
                if self.raw else "动作"
        if self.kind == "stage":
            scene, pose, effect = self.data.get("bg", ["", "", ""])
            head = "场景: %s%s" % (scene or pose or "(直接路径)",
                                   " [%s]" % pose if scene and pose else "")
            sprites = self.data.get("sprites", [])
            if sprites:
                head += "  (%d 个立绘动作)" % len(sprites)
            return head
        if self.kind == "raw":
            return self.raw.op if self.raw else "代码块"
        return self.kind


class FlowGraph:
    """节点图 (编辑 story.gal 的标签)。"""

    def __init__(self, script_name: str = "story.gal"):
        self.script_name = script_name
        self.nodes: dict[str, FlowNode] = {}
        self.order: list[str] = []     # 标签/节点顺序
        self._counter = 0

    # ---- 节点操作 -----------------------------------------------------
    def add_node(self, kind: str, x: float = 0.0, y: float = 0.0,
                 node_id: str | None = None, **kw) -> FlowNode:
        if node_id is None:
            while True:
                self._counter += 1
                node_id = "n%d" % self._counter
                if node_id not in self.nodes:
                    break
        if node_id in self.nodes:
            raise ValueError("节点 id 已存在: %s" % node_id)
        node = FlowNode(node_id, kind, x, y, **kw)
        self.nodes[node_id] = node
        self.order.append(node_id)
        return node

    def remove_node(self, node_id: str) -> None:
        if node_id not in self.nodes:
            return
        del self.nodes[node_id]
        if node_id in self.order:
            self.order.remove(node_id)
        # 清理引用
        for n in self.nodes.values():
            if n.next_id == node_id:
                n.next_id = None
            for opt in n.options:
                if opt[1] == node_id:
                    opt[1] = None

    def copy(self) -> "FlowGraph":
        """深拷贝 (撤销快照用; Statement 为 dataclass 可 deepcopy)。"""
        import copy
        g = FlowGraph(self.script_name)
        g.nodes = copy.deepcopy(self.nodes)
        g.order = list(self.order)
        g._counter = self._counter
        return g

    def connect(self, src_id: str, dst_id: str | None, port: int = 0) -> None:
        """连线: dialogue 顺序后继 / jump 目标 / choice 选项目标 (port=选项序号)。"""
        src = self.nodes.get(src_id)
        if src is None:
            return
        if src.kind == "choice":
            if 0 <= port < len(src.options):
                src.options[port][1] = dst_id
        elif src.kind == "jump":
            src.data["target"] = dst_id
        else:
            src.next_id = dst_id

    def set_option(self, choice_id: str, idx: int, text: str,
                   target: str | None) -> None:
        node = self.nodes.get(choice_id)
        if node is None or node.kind != "choice":
            return
        while len(node.options) <= idx:
            node.options.append(["", None])
        node.options[idx] = [text, target]

    # ---- 导入: Script(story.gal) -> 节点图 ---------------------------
    @classmethod
    def from_script(cls, script: Script, script_name: str = "story.gal",
                    layout: bool = True) -> "FlowGraph":
        g = cls(script_name)
        # 第一遍: 注册全部标签节点 (保证自动 id 不与标签名冲突)
        for label in script.labels:
            g.add_node("label", x=0, y=0, node_id=label,
                       data={"text": label})
        # 第二遍: 填充标签内容; 顺序语句 (对话/动作/代码) 合并进
        # extra_stmts, 分支语句 (choice/jump/ending) 新建节点
        y = 0
        for label, body in script.labels.items():
            g.nodes[label].y = y
            y += 1
            prev = label
            first = True
            n = len(body)
            for idx, stmt in enumerate(body):
                # 块尾 jump (目标标签已存在, 且 prev 非 choice) 折叠为
                # next 连线, 不建节点 —— 保证 导入->导出->导入 幂等
                if (idx == n - 1 and not first and stmt.op == "jump"
                        and stmt.args and stmt.args[0] in g.nodes
                        and g.nodes[prev].kind != "choice"):
                    g.connect(prev, stmt.args[0])
                    continue
                kind, data, options, raw = _stmt_to_node(stmt)
                if first:
                    node = g.nodes[label]
                    node.kind = kind
                    node.data = data
                    node.options = options
                    node.raw = raw
                    first = False
                    prev = label
                    continue
                mergeable = kind in ("dialogue", "action", "raw")
                prev_mergeable = g.nodes[prev].kind in (
                    "dialogue", "action", "raw", "label")
                # 紧跟 stage 的 show/hide/clear 并入该 stage 的立绘列表
                if g.nodes[prev].kind == "stage" and stmt.op in (
                        "show", "hide", "clear"):
                    g.nodes[prev].data["sprites"].append(
                        _sprite_from_stmt(stmt))
                elif g.nodes[prev].kind == "stage" and stmt.op == "move":
                    g.nodes[prev].data.setdefault("moves", []).append(
                        _move_from_stmt(stmt))
                elif g.nodes[prev].kind == "stage" and stmt.op in (
                        "music", "sfx", "volume", "pause", "resume", "stop"):
                    row = _audio_from_stmt(stmt)
                    if row is not None:
                        g.nodes[prev].data.setdefault("audio", []).append(row)
                elif mergeable and prev_mergeable:
                    g.nodes[prev].extra_stmts.append(stmt)
                else:
                    node = g.add_node(kind, x=0, y=y, data=data,
                                      options=options, raw=raw)
                    y += 1
                    g.connect(prev, node.node_id)
                    prev = node.node_id
        if layout:
            g.auto_layout()
        return g

    # ---- 导出: 节点图 -> Script(story.gal) ---------------------------
    def to_script(self) -> Script:
        script = Script(path=self.script_name)
        for nid in self.order:
            node = self.nodes[nid]
            body = _node_to_statements(node)
            script.labels[nid] = body
        return script

    # ---- 布局 ---------------------------------------------------------
    def auto_layout(self, x_gap: float = 260.0, y_gap: float = 120.0) -> None:
        """简单分层布局 (BFS 分层)。"""
        indeg = {nid: 0 for nid in self.order}
        for n in self.nodes.values():
            targets = []
            if n.next_id:
                targets.append(n.next_id)
            if n.kind == "jump" and n.data.get("target"):
                targets.append(n.data["target"])
            for _t, tg in n.options:
                if tg:
                    targets.append(tg)
            for t in targets:
                if t in indeg:
                    indeg[t] += 1
        # 起点: 入度 0 (或 game_start 优先)
        import heapq
        ready = [nid for nid in self.order if indeg[nid] == 0]
        # game_start 优先
        if "game_start" in ready:
            ready.remove("game_start")
            ready.insert(0, "game_start")
        heap = []
        for i, nid in enumerate(ready):
            heapq.heappush(heap, (0, i, nid))
        layers = {}
        seq = 0
        while heap:
            _l, _s, nid = heapq.heappop(heap)
            if nid in layers:
                continue
            layers[nid] = _l
            node = self.nodes[nid]
            seq += 1
            targets = []
            if node.next_id:
                targets.append(node.next_id)
            if node.kind == "jump" and node.data.get("target"):
                targets.append(node.data["target"])
            for _t, tg in node.options:
                if tg:
                    targets.append(tg)
            for t in targets:
                if t in indeg and t not in layers:
                    indeg[t] -= 1
                    heapq.heappush(heap, (_l + 1, seq, t))
        # 孤立节点补层
        for nid in self.order:
            if nid not in layers:
                layers[nid] = 0
        # 按层计算坐标 (每层横向错开)
        per_layer = {}
        for nid, l in layers.items():
            per_layer.setdefault(l, []).append(nid)
        for l, ids in per_layer.items():
            for i, nid in enumerate(ids):
                node = self.nodes[nid]
                node.x = l * x_gap
                node.y = i * y_gap - (len(ids) - 1) * y_gap / 2


# ----------------------------------------------------------------------
# 语句 <-> 节点 转换
# ----------------------------------------------------------------------
def _stmt_to_node(stmt: Statement):
    """语句 -> (kind, data, options, raw)。"""
    op = stmt.op
    if op in DIALOGUE_OPS:
        return ("dialogue",
                {"op": op, "speaker": stmt.args[0] if op == "say"
                 and stmt.args else "",
                 "text": stmt.args[-1] if stmt.args else ""},
                [], None)
    if op == "choice":
        options = [[t, tg] for t, tg in stmt.kwargs.get("options", [])]
        return ("choice", {}, options, None)
    if op in ("jump", "call"):
        return ("jump",
                {"target": stmt.args[0] if stmt.args else None,
                 "is_call": op == "call"},
                [], None)
    if op == "ending":
        return ("ending", {"name": stmt.args[0] if stmt.args else ""},
                [], None)
    if op == "bg":
        # 场景节点: bg 参数解析 (scene [pose] [with effect] / 直接路径)
        scene, pose, effect = _parse_bg(stmt)
        return ("stage", {"bg": [scene, pose, effect], "sprites": []},
                [], stmt)
    # 其他普通语句 (show/music/set/save/fade/...): 动作节点, 原样保留
    if op not in ("->",) and stmt.op:
        return ("action", {}, [], stmt)
    return ("raw", {}, [], stmt)


def _parse_bg(stmt: Statement):
    """bg 语句 -> (scene, pose, effect)。"""
    args = list(stmt.args)
    effect = ""
    if "with" in args:
        i = args.index("with")
        effect = args[i + 1] if i + 1 < len(args) else ""
        args = args[:i]
    if not args:
        return ("", "", effect)
    if len(args) == 1:
        return (args[0], "", effect)
    return (args[0], args[1], effect)


def _move_from_stmt(stmt: Statement):
    """move 语句 -> [角色, xy, 秒, 效果, 缓动] (紧跟 stage 的立绘定位)。

    语法: move <char> [to] <xy> [秒] [ease <名>] [with 效果]
    """
    args = list(stmt.args)
    char = args[0] if args else ""
    rest = args[1:]
    eff = ease = ""
    if "with" in rest:
        i = rest.index("with")
        eff = rest[i + 1] if i + 1 < len(rest) else ""
        rest = rest[:i]
    if "ease" in rest:
        i = rest.index("ease")
        ease = rest[i + 1] if i + 1 < len(rest) else ""
        rest = rest[:i]
    if rest and rest[0] == "to":
        rest = rest[1:]
    xy = rest[0] if rest else ""
    dur = rest[1] if len(rest) > 1 else "0"
    return [char, xy, dur, eff, ease]


def _audio_from_stmt(stmt: Statement):
    """音乐/音效语句 -> [op, a, b, c] (stage 音频轨条目)。

    music: [music, 名, loop, fade]   sfx: [sfx, 名, "", ""]
    volume: [volume, 目标, 角色(voice), 值]
    pause/resume/stop: [op, 目标, "", fade]
    """
    args = list(stmt.args)
    op = stmt.op
    if op == "music":
        name = args[0] if args else ""
        loop, fade = "1", ""
        for i, a in enumerate(args):
            if a == "loop" and i + 1 < len(args):
                loop = args[i + 1]
            elif a == "fade" and i + 1 < len(args):
                fade = args[i + 1]
        return ["music", name, loop, fade]
    if op == "sfx":
        return ["sfx", args[0] if args else "", "", ""]
    if op == "volume":
        if len(args) >= 2:
            target = args[0]
            if target == "voice" and len(args) >= 3:
                return ["volume", "voice", args[1], args[2]]
            return ["volume", target, "", args[-1]]
        return ["volume", "", "", ""]
    if op in ("pause", "resume", "stop"):
        fade = ""
        if "fade" in args:
            i = args.index("fade")
            fade = args[i + 1] if i + 1 < len(args) else ""
        target = args[0] if args else "music"
        return [op, target, "", fade]
    return None


def _sprite_from_stmt(stmt: Statement):
    """show/hide/clear 语句 -> [动作, 角色, 表情, 效果]。"""
    args = list(stmt.args)
    effect = ""
    if "with" in args:
        i = args.index("with")
        effect = args[i + 1] if i + 1 < len(args) else ""
        args = args[:i]
    op = stmt.op
    if op == "clear":
        return ["clear", "", "", ""]
    char = args[0] if args else ""
    expr = args[1] if op == "show" and len(args) > 1 else ""
    return [op, char, expr, effect]


def _node_to_statements(node: FlowNode) -> list:
    out = []
    k = node.kind
    if k == "dialogue":
        op = node.data.get("op", "text")
        if op == "say":
            out.append(Statement(op="say",
                                 args=[node.data.get("speaker", ""),
                                       node.data.get("text", "")]))
        else:
            out.append(Statement(op=op, args=[node.data.get("text", "")]))
    elif k == "choice":
        options = [[t or "", tg or ""] for t, tg in node.options]
        out.append(Statement(op="choice", kwargs={"options": options}))
    elif k == "jump":
        op = "call" if node.data.get("is_call") else "jump"
        target = node.data.get("target")
        out.append(Statement(op=op, args=[target] if target else []))
    elif k == "ending":
        name = node.data.get("name")
        out.append(Statement(op="ending", args=[name] if name else []))
    elif k == "action" and node.raw is not None:
        out.append(node.raw)
    elif k == "stage":
        scene, pose, effect = node.data.get("bg", ["", "", ""])
        args = []
        if scene:
            args.append(scene)
            if pose:
                args.append(pose)
        elif pose:
            args.append(pose)
        if effect:
            args += ["with", effect]
        out.append(Statement(op="bg", args=args))
        for act, char, expr, eff in node.data.get("sprites", []):
            if act == "clear":
                out.append(Statement(op="clear", args=[]))
                continue
            sargs = [char]
            if act == "show" and expr:
                sargs.append(expr)
            if eff:
                sargs += ["with", eff]
            out.append(Statement(op=act, args=sargs))
        for row in node.data.get("audio", []):
            op, a, b, c = (list(row) + ["", "", "", ""])[:4]
            if op == "music":
                margs = [a]
                if b and b != "1":
                    margs += ["loop", b]
                if c:
                    margs += ["fade", c]
                out.append(Statement(op="music", args=margs))
            elif op == "sfx":
                out.append(Statement(op="sfx", args=[a]))
            elif op == "volume":
                if a == "voice" and b:
                    out.append(Statement(op="volume", args=[a, b, c]))
                else:
                    out.append(Statement(op="volume", args=[a, c]))
            elif op in ("pause", "resume", "stop"):
                margs = [a] if a and a != "music" else []
                if c:
                    margs += ["fade", c]
                out.append(Statement(op=op, args=margs))
        for char, xy, dur, eff, ease in node.data.get("moves", []):
            margs = [char]
            if xy:
                margs += ["to", xy]
            if dur and dur != "0":
                margs.append(dur)
            if ease:
                margs += ["ease", ease]
            if eff:
                margs += ["with", eff]
            out.append(Statement(op="move", args=margs))
    elif k == "raw" and node.raw is not None:
        out.append(node.raw)
    # label: 无主语句 (纯汇合点)
    # 合并的顺序语句
    out.extend(node.extra_stmts)
    # 顺序后继 (块尾 jump)
    if k in ("dialogue", "action", "raw", "label", "stage") and node.next_id:
        out.append(Statement(op="jump", args=[node.next_id]))
    return out
