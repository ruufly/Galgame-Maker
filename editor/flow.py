"""流程节点模型 (P4 重构): 对话流节点图 <-> story.gal 标签结构。

映射约定 (v2, 每行代码都有节点):
- **每个标签 = 独立的剧情树入口** (label 节点, 节点 id = 标签名)
- 标签体内**每条语句 = 一个节点**, 顺序连线 (不再合并对话链)
- choice / if / python:: 为块语句 -> 单节点 (选项/分支/代码保留在节点内)
- jump/call 单独呈现为 jump 节点 (不再折叠为块尾连线)
- 声音/立绘/插件等任意指令 -> action 节点 (原语句保留, 参数表单编辑)
- bg -> stage 节点 (场景缩略图)

导出: 从每个 label 入口沿 next 链收集语句 (遇 jump/ending/label 终止),
选择支/跳转目标均为标签名 (节点 id), 语义与导入完全一致, 天然幂等。
"""

from framework.engine.parser import Script, Statement

DIALOGUE_OPS = {"say", "nar", "text"}
DIALOGUE_LABEL = {"say": "对话", "nar": "旁白", "text": "文本"}


class FlowNode:
    """一个流程节点。

    v2 简化: 每节点对应一条语句 (或一个块); extra_stmts 保留字段
    兼容旧数据, 新导入不再填充。
    """

    def __init__(self, node_id: str, kind: str, x: float = 0.0,
                 y: float = 0.0, next_id: str | None = None,
                 data: dict | None = None,
                 options: list | None = None, raw: Statement | None = None,
                 extra_stmts: list | None = None):
        self.node_id = node_id
        self.kind = kind          # label/dialogue/choice/jump/ending/stage/
                                  # action/raw/if
        self.x, self.y = x, y
        self.next_id = next_id    # 顺序后继节点 id
        self.data = data or {}    # dialogue: op/speaker/text; jump: target/is_call;
                                  # ending: name; label: text; if: raw
        self.options = options or []   # choice: [[text, target_id], ...]
        self.raw = raw            # action/raw/if: 原始语句
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
        if self.kind == "if":
            return "如果 %s" % self.data.get("cond", "?")
        if self.kind == "action":
            return "%s %s" % (self.raw.op, " ".join(self.raw.args)) \
                if self.raw else "动作"
        if self.kind == "stage":
            scene, pose, effect = self.data.get("bg", ["", "", ""])
            head = "场景: %s%s" % (scene or pose or "(直接路径)",
                                   " [%s]" % pose if scene and pose else "")
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

    # ---- 导入: Script(story.gal) -> 节点图 (每行一个节点) -------------
    @classmethod
    def from_script(cls, script: Script, script_name: str = "story.gal",
                    layout: bool = True) -> "FlowGraph":
        g = cls(script_name)
        # 第一遍: 注册全部标签入口节点 (自动 id 不与标签名冲突)
        for label in script.labels:
            g.add_node("label", x=0, y=0, node_id=label,
                       data={"text": label})
        # 第二遍: 标签体内每条语句一个节点, 顺序连线
        # (if 块特殊处理: 分支体每行一个节点, elif/else 为边界节点)
        y = 0
        for label, body in script.labels.items():
            prev = label
            for stmt in body:
                if stmt.op == "if":
                    prev, y = g._import_if(stmt, prev, y)
                    continue
                kind, data, options, raw = _stmt_to_node(stmt)
                node = g.add_node(kind, x=0, y=y, data=data,
                                  options=options, raw=raw)
                y += 1
                g.connect(prev, node.node_id)
                prev = node.node_id
        if layout:
            g.auto_layout()
        return g

    def _import_if(self, stmt: Statement, prev: str, y: int):
        """if 块 -> 条件边界节点 + 分支体每行一个节点。

        返回 (最后一个节点 id, 下一个 y)。分支体节点 data["branch"]=
        分支索引 (0=if 体, 1=第一个 elif...); else 分支 = len(branches)。
        elif/else 为 role 标记的 if 节点 (data["role"]="elif"/"else")。
        """
        branches = stmt.kwargs.get("branches", [])
        else_body = stmt.kwargs.get("else")
        # 主 if 条件节点
        cond0 = str(branches[0][0]) if branches else \
            str(stmt.kwargs.get("cond", ""))
        node = self.add_node("if", x=0, y=y,
                             data={"cond": cond0, "role": "if"}, raw=stmt)
        y += 1
        self.connect(prev, node.node_id)
        prev = node.node_id
        # 各分支体平铺 (elif 前插入边界节点)
        for idx, (cond, body) in enumerate(branches):
            if idx > 0:
                bnode = self.add_node("if", x=0, y=y,
                                      data={"cond": str(cond),
                                            "role": "elif"}, raw=stmt)
                y += 1
                self.connect(prev, bnode.node_id)
                prev = bnode.node_id
            for bstmt in body:
                kind, data, options, raw = _stmt_to_node(bstmt)
                n = self.add_node(kind, x=0, y=y, data=data,
                                  options=options, raw=raw)
                n.data["branch"] = idx
                y += 1
                self.connect(prev, n.node_id)
                prev = n.node_id
        # else 边界
        if else_body is not None:
            enode = self.add_node("if", x=0, y=y,
                                  data={"cond": "", "role": "else"},
                                  raw=stmt)
            y += 1
            self.connect(prev, enode.node_id)
            prev = enode.node_id
            for bstmt in else_body:
                kind, data, options, raw = _stmt_to_node(bstmt)
                n = self.add_node(kind, x=0, y=y, data=data,
                                  options=options, raw=raw)
                n.data["branch"] = len(branches)
                y += 1
                self.connect(prev, n.node_id)
                prev = n.node_id
        return prev, y

    # ---- 导出: 节点图 -> Script(story.gal) ----------------------------
    def to_script(self) -> Script:
        """从每个 label 入口沿 next 链收集语句; 遇 jump/ending/其它
        label 终止 (标签边界)。jump/选择支目标即标签名。

        gal 语义: jump/选择支目标必须是标签 -> 被引用但不是 label 的
        节点自动**提升为宿主标签** (以节点 id 为标签名), 保证任意
        连线都能导出且往返稳定。
        """
        script = Script(path=self.script_name)
        referenced: set = set()
        for n in self.nodes.values():
            if n.kind == "jump" and n.data.get("target"):
                referenced.add(n.data["target"])
            for _t, tg in n.options:
                if tg:
                    referenced.add(tg)
        hosts = [nid for nid in self.order
                 if self.nodes[nid].kind == "label"]
        promoted = [rid for rid in self.order
                    if rid in referenced and rid not in hosts
                    and self.nodes[rid].kind != "label"]

        def collect(start_id: str | None, label_name: str) -> None:
            body: list = []
            nxt = start_id
            visited = set()
            while nxt and nxt not in visited and nxt in self.nodes:
                visited.add(nxt)
                n = self.nodes[nxt]
                if n.kind == "label":
                    break
                if n.kind == "if" and n.data.get("role") == "if":
                    # 条件块: 分支体节点重建为 if 语句, 跳到主线恢复点
                    stmt, nxt = self._collect_if_block(n)
                    body.append(stmt)
                    continue
                body.extend(_node_to_statements(n))
                if n.kind in ("jump", "ending"):
                    break
                nxt = n.next_id
            script.labels[label_name] = body

        for nid in hosts:
            collect(self.nodes[nid].next_id, nid)
        for rid in promoted:
            collect(rid, rid)
        return script

    def _collect_if_block(self, if_node: FlowNode):
        """从条件节点沿链收集分支体, 重建 if 语句。

        返回 (if Statement, 主线恢复点节点 id)。分支体节点
        data["branch"] 标记归属; elif/else 为边界节点。
        """
        branches: list = []
        else_body = None
        cur_cond = if_node.data.get("cond", "")
        cur_body: list = []
        in_else = False
        nxt = if_node.next_id
        visited = set()
        while nxt and nxt not in visited and nxt in self.nodes:
            visited.add(nxt)
            n = self.nodes[nxt]
            if n.kind == "label":
                break
            role = n.data.get("role") if n.kind == "if" else None
            if role == "elif":
                branches.append([cur_cond, cur_body])
                cur_cond = n.data.get("cond", "")
                cur_body = []
                in_else = False
                nxt = n.next_id
                continue
            if role == "else":
                branches.append([cur_cond, cur_body])
                cur_cond = ""
                cur_body = []
                in_else = True
                nxt = n.next_id
                continue
            if role == "if":
                sub_stmt, nxt = self._collect_if_block(n)
                cur_body.append(sub_stmt)
                continue
            if n.data.get("branch") is None:
                break          # 主线恢复 (endif 后)
            cur_body.extend(_node_to_statements(n))
            if n.kind in ("jump", "ending"):
                break
            nxt = n.next_id
        if in_else:
            else_body = cur_body
        elif cur_body or not branches:
            branches.append([cur_cond, cur_body])
        stmt = Statement(op="if", kwargs={"branches": branches})
        if else_body is not None:
            stmt.kwargs["else"] = else_body
        return stmt, nxt

    # ---- 布局 ---------------------------------------------------------
    def auto_layout(self, x_gap: float = 260.0, y_gap: float = 120.0) -> None:
        """竖向分层布局 (BFS): 主链从上到下, 分支左右展开。"""
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
        import heapq
        ready = [nid for nid in self.order if indeg[nid] == 0]
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
        for nid in self.order:
            if nid not in layers:
                layers[nid] = 0
        per_layer = {}
        for nid, l in layers.items():
            per_layer.setdefault(l, []).append(nid)
        for l, ids in per_layer.items():
            for i, nid in enumerate(ids):
                node = self.nodes[nid]
                node.x = i * x_gap - (len(ids) - 1) * x_gap / 2
                node.y = l * y_gap


# ----------------------------------------------------------------------
# 语句 <-> 节点 转换
# ----------------------------------------------------------------------
def _stmt_to_node(stmt: Statement):
    """语句 -> (kind, data, options, raw)。"""
    op = stmt.op
    if op in DIALOGUE_OPS:
        args = list(stmt.args)
        voice = ""
        if "voice" in args:
            i = args.index("voice")
            voice = args[i + 1] if i + 1 < len(args) else ""
            args = args[:i]
        speaker = args[0] if op == "say" and args else ""
        data = {"op": op, "speaker": speaker,
                "text": args[-1] if args else ""}
        if voice:
            data["voice"] = voice
        return ("dialogue", data, [], None)
    if op == "choice":
        options = [[t, tg] for t, tg in stmt.kwargs.get("options", [])]
        return ("choice", {}, options, stmt)
    if op in ("jump", "call"):
        return ("jump",
                {"target": stmt.args[0] if stmt.args else None,
                 "is_call": op == "call"},
                [], stmt)
    if op == "ending":
        return ("ending", {"name": stmt.args[0] if stmt.args else ""},
                [], stmt)
    if op == "bg":
        scene, pose, effect = _parse_bg(stmt)
        return ("stage", {"bg": [scene, pose, effect], "sprites": []},
                [], stmt)
    if op == "if":
        # 顶层 if 由 from_script 特殊展开; 分支体内嵌套 if 保留为 raw
        return ("raw", {}, [], stmt)
    # 其它普通语句 (show/music/set/sleep/typing/插件指令...): 动作节点
    if stmt.op:
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


def _node_to_statements(node: FlowNode) -> list:
    out = []
    k = node.kind
    if k == "dialogue":
        op = node.data.get("op", "text")
        voice = node.data.get("voice", "")
        if op == "say":
            args = [node.data.get("speaker", ""),
                    node.data.get("text", "")]
        else:
            args = [node.data.get("text", "")]
        if voice:
            args += ["voice", voice]
        out.append(Statement(op=op, args=args))
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
    elif k == "if":
        # 原样保留 if 块 (编辑时改 data.cond 已写回 raw)
        if node.raw is not None:
            out.append(node.raw)
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
    # label: 无主语句 (纯剧情树入口)
    # 兼容: 手动附加语句 (旧数据)
    out.extend(node.extra_stmts)
    return out
