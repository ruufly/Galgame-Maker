"""流程节点画布 (P2): QGraphicsView 可视化编辑对话流。

组件:
- FlowEditor: 工具栏 + 画布 (导入/生成/自动布局/添加节点)
- FlowScene: 节点/连线同步 + 端口拖线交互
- NodeItem: 类型着色卡片 (输入端口上, 输出端口下; choice 每选项一个端口)
- EdgeItem: 贝塞尔连线 + 箭头

交互:
- 左键拖动节点; 从输出端口拖到目标节点 = 连线
- 双击节点 = 编辑 (对话/选择支/跳转/结局/标签)
- Delete 删除选中节点 (清理引用); 滚轮缩放, 中键平移
"""

import os

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (QBrush, QColor, QFont, QPainter, QPainterPath,
                           QPen, QPixmap, QPolygonF)
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFormLayout,
                               QGraphicsItem,
                               QGraphicsPathItem, QGraphicsScene,
                               QGraphicsView, QHBoxLayout, QInputDialog,
                               QLabel, QLineEdit, QMessageBox, QPushButton,
                               QTableWidget, QTableWidgetItem, QVBoxLayout,
                               QWidget)

from editor.flow import FlowGraph, DIALOGUE_LABEL
from editor.project_settings import save_script
from editor.i18n import t
from editor.plugins_api import registry
from editor.audio_timeline import AudioTimeline

KIND_COLORS = {
    "dialogue": "#2d6cdf",
    "choice": "#e8890c",
    "jump": "#2e9e5b",
    "ending": "#d64550",
    "label": "#7a7a8a",
    "raw": "#8e44ad",
    "action": "#3a86a8",
    "stage": "#4e937a",
    "if": "#c05ac0",
}
KIND_NAMES = {"dialogue": "对话", "choice": "选择支", "jump": "跳转",
              "ending": "结局", "label": "标签", "raw": "代码",
              "action": "动作", "stage": "场景", "if": "条件"}

# 常用指令 (动作节点候选; 插件注册指令自动并入)
KERNEL_OPS = ["say", "nar", "text", "bg", "show", "hide", "clear", "move",
              "rotate", "flip", "music", "sfx", "volume", "pause", "resume",
              "stop", "set", "sleep", "typing", "use", "fade", "fadeout",
              "save", "load", "fullscreen", "do_action", "using", "plugin",
              "confirm", "read_settings", "ending", "jump", "call", "window"]


def _to_int(v, default=0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


# 立绘登场/退场/变换效果候选 (内核 + 插件注册)
KERNEL_SPRITE_EFFECTS = ["", "slide_right", "slide_left", "fade", "bounce",
                         "pop", "zoom_in", "zoom_out", "wobble", "sway",
                         "zoom_bounce", "fade_rotate", "float", "squash"]


def _sprite_effect_cands() -> list:
    out = list(KERNEL_SPRITE_EFFECTS)
    try:
        from editor.plugins_api import registry
        for e in registry.sprite_effects():
            if e and e not in out:
                out.append(e)
    except Exception:
        pass
    return out


def _char_ids_of(project) -> list:
    """项目 cast.gal 的角色 id 列表 (下拉候选)。"""
    if project is None:
        return []
    cast = project.scripts.get("cast.gal")
    if cast is None:
        return []
    try:
        from editor.definitions import iter_defs
        return [s.args[0] for s in iter_defs(cast, "char")]
    except Exception:
        return []

NODE_W = 200


class NodeItem(QGraphicsItem):
    """流程节点卡片。"""

    def __init__(self, node, scene: "FlowScene"):
        super().__init__()
        self.node = node
        self.flow_scene = scene
        self.setFlags(QGraphicsItem.ItemIsMovable
                      | QGraphicsItem.ItemIsSelectable)
        self.setPos(node.x, node.y)
        self.setZValue(1)
        self._rect = self._calc_rect()

    # ---- 尺寸 ---------------------------------------------------------
    def _calc_rect(self) -> QRectF:
        lines = _summary_lines(self.node, self.flow_scene.lang)
        h = 34 + max(1, len(lines)) * 17 + 10
        if self.node.kind == "choice":
            h += len(self.node.options) * 16
        if self.node.kind == "stage" and self._thumb() is not None:
            h += 66
        return QRectF(0, 0, NODE_W, h)

    def _thumb(self):
        """stage 背景缩略图 (缓存), 无图返回 None。"""
        if self.node.kind != "stage":
            return None
        path = resolve_bg_image(self.flow_scene.project, self.node)
        if path is None:
            return None
        return _thumb_pixmap(path, NODE_W - 16, 58)

    def boundingRect(self) -> QRectF:
        return self._rect.adjusted(-6, -6, 6, 6)

    # ---- 绘制 ---------------------------------------------------------
    def paint(self, painter: QPainter, _opt, _w=None):
        r = self._rect
        color = QColor(KIND_COLORS.get(self.node.kind, "#666"))
        painter.setRenderHint(QPainter.Antialiasing)
        # 卡片
        painter.setPen(QPen(color, 2) if self.isSelected()
                      else QPen(QColor("#000000"), 1))
        painter.setBrush(QBrush(QColor("#26263a")))
        painter.drawRoundedRect(r, 8, 8)
        # 标题条 (所属标签树前缀 + 树色块)
        label = self.flow_scene._label_map.get(self.node.node_id, "")
        tree_color = self.flow_scene._label_color(label) if label \
            else QColor("#555")
        painter.fillRect(QRectF(8, 6, 5, 20), tree_color)
        title = ("[%s] " % label if label else "") \
            + "%s  [%s]" % (KIND_NAMES.get(self.node.kind, self.node.kind),
                            self.node.node_id)
        painter.setPen(Qt.white)
        f = painter.font()
        f.setBold(True)
        painter.setFont(f)
        painter.drawText(QRectF(17, 6, NODE_W - 24, 22), Qt.AlignLeft, title)
        # 类型色条
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(color))
        painter.drawRoundedRect(QRectF(8, 30, NODE_W - 16, 4), 2, 2)
        # 摘要
        f.setBold(False)
        f.setPointSize(9)
        painter.setFont(f)
        painter.setPen(QColor("#d8d8e0"))
        y = 40
        thumb = self._thumb()
        if thumb is not None:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(QColor("#000000")))
            painter.drawRoundedRect(QRectF(8, 38, NODE_W - 16, 58), 4, 4)
            painter.drawPixmap(QRectF(8, 38, NODE_W - 16, 58).toRect(),
                               thumb)
            y = 38 + 58 + 6
        for line in _summary_lines(self.node, self.flow_scene.lang):
            painter.drawText(QRectF(8, y, NODE_W - 16, 16),
                             Qt.AlignLeft, line)
            y += 17
        # 端口
        self._paint_ports(painter)

    def _paint_ports(self, painter: QPainter):
        r = self._rect
        in_pos = QPointF(r.center().x(), 0)
        outs = self._output_positions()
        painter.setBrush(QBrush(QColor("#e8e8f0")))
        painter.setPen(QPen(QColor("#000"), 1))
        painter.drawEllipse(in_pos, 5, 5)
        for pos in outs:
            painter.drawEllipse(pos, 5, 5)

    # ---- 端口 ---------------------------------------------------------
    def input_pos(self) -> QPointF:
        return QPointF(self._rect.center().x(), 0)

    def _output_positions(self) -> list:
        r = self._rect
        if self.node.kind == "choice" and self.node.options:
            n = len(self.node.options)
            return [QPointF(r.width() * (i + 1) / (n + 1), r.height())
                    for i in range(n)]
        return [QPointF(r.center().x(), r.height())]

    def output_port_at(self, scene_pos: QPointF):
        """命中的输出端口序号 (choice 为选项序号, 其余为 0), 未命中返回 None。"""
        local = self.mapFromScene(scene_pos)
        outs = self._output_positions()
        for i, pos in enumerate(outs):
            if (local - pos).manhattanLength() <= 10:
                return i
        return None

    def input_hit(self, scene_pos: QPointF) -> bool:
        local = self.mapFromScene(scene_pos)
        return (local.x() >= 0 and local.x() <= self._rect.width()
                and local.y() >= 0 and local.y() <= 20)

    # ---- 移动回写 -----------------------------------------------------
    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange:
            self.node.x = value.x()
            self.node.y = value.y()
        if change == QGraphicsItem.ItemPositionHasChanged:
            self.flow_scene.edges_changed()
        return super().itemChange(change, value)

    def mouseDoubleClickEvent(self, event):
        self.flow_scene.edit_node(self.node)
        super().mouseDoubleClickEvent(event)


class EdgeItem:
    """节点间连线 (纯数据, 由 FlowScene.drawForeground 绘制)。

    兼容性决策 (PySide6 6.11): 不创建 QGraphicsItem 子类 ——
    该环境对自定义 QGraphicsItem 的渲染存在崩溃问题 (多次二分定位
    均指向 item 渲染链)。连线统一在场景前景绘制。
    """

    def __init__(self, src: "NodeItem", dst: "NodeItem", port: int, scene):
        self.src, self.dst, self.port = src, dst, port
        self.flow_scene = scene
        self.hover = False

    # ---- 几何 (由 scene 绘制/命中复用) --------------------------------
    def build_path(self) -> QPainterPath:
        outs = self.src._output_positions()
        p1 = self.src.mapToScene(outs[min(self.port, len(outs) - 1)])
        p2 = self.dst.mapToScene(self.dst.input_pos())
        dx = max(30, abs(p2.x() - p1.x()) * 0.5)
        path = QPainterPath(p1)
        path.cubicTo(p1.x() + dx, p1.y(), p2.x() - dx, p2.y(), p2.x(), p2.y())
        return path

    def hit_test(self, scene_pos, tol: float = 10.0) -> bool:
        path = self.build_path()
        if path.length() < 1:
            return False
        n = 16
        for i in range(0, n + 1):
            pt = path.pointAtPercent(i / n)
            if (abs(pt.x() - scene_pos.x()) < tol
                    and abs(pt.y() - scene_pos.y()) < tol):
                return True
        return False





# ----------------------------------------------------------------------
# 模块级辅助: 缩略图缓存 / 背景图解析 / 节点摘要 (FlowScene 之前)
# ----------------------------------------------------------------------
_THUMB_CACHE = {}


def _choice_insert_row(tbl, row: int = -1) -> None:
    """选择支编辑表: 插入一行 (可指定位置)。"""
    if row < 0 or row > tbl.rowCount():
        row = tbl.rowCount()
    tbl.insertRow(row)
    tbl.setItem(row, 0, QTableWidgetItem(""))


def _choice_remove_row(tbl, row: int) -> None:
    if 0 <= row < tbl.rowCount():
        tbl.removeRow(row)


def _clear_thumb_cache():
    _THUMB_CACHE.clear()


def resolve_bg_image(project, node):
    """stage 节点背景图的绝对路径; 解析失败返回 None。"""
    if project is None or node.kind != "stage":
        return None
    scene, pose, _effect = node.data.get("bg", ["", "", ""])
    path = ""
    if scene:
        cast = project.scripts.get("cast.gal")
        if cast is not None:
            from editor.definitions import iter_defs
            for s in iter_defs(cast, "scene"):
                if s.args[0] == scene:
                    path = s.kwargs.get(pose) or s.kwargs.get("default", "")
                    break
    else:
        path = pose
    if not path:
        return None
    full = os.path.join(project.root, path)
    return full if os.path.isfile(full) else None


def _thumb_pixmap(path: str, w: int, h: int):
    """带缓存的背景缩略图 (失败返回 None)。"""
    key = (path, w, h)
    if key in _THUMB_CACHE:
        return _THUMB_CACHE[key]
    pix = QPixmap(path)
    if pix.isNull():
        _THUMB_CACHE[key] = None
        return None
    pix = pix.scaled(w, h, Qt.KeepAspectRatioByExpanding,
                     Qt.SmoothTransformation)
    if pix.width() > w or pix.height() > h:
        x = (pix.width() - w) // 2
        y = (pix.height() - h) // 2
        pix = pix.copy(x, y, w, h)
    _THUMB_CACHE[key] = pix
    return pix


def _summary_lines(node, lang=None) -> list:
    """节点摘要行; lang 提供时把 {@key} 解析为当前语言文本。"""
    s = node.summary()
    lines = []
    if node.kind == "dialogue":
        sp = node.data.get("speaker", "")
        tx = node.data.get("text", "")
        resolved = lang.resolve(tx) if (lang and tx) else tx
        lines.append(("%s: %s" % (sp, resolved)) if sp else resolved)
        # 对话链合并的语句可视化 (让"被吞"的语句可见)
        extra = node.extra_stmts
        if extra:
            lines.append("  [合并 %d 句]" % len(extra))
            for stmt in extra[:3]:
                if stmt.op in ("say", "nar", "text"):
                    sp2 = stmt.args[0] if stmt.op == "say" and stmt.args \
                        else ""
                    tx2 = stmt.args[-1] if stmt.args else ""
                    r2 = lang.resolve(tx2) if (lang and tx2) else tx2
                    lines.append("  %s" % (("%s: %s" % (sp2, r2))
                                           if sp2 else r2))
                else:
                    lines.append("  [%s %s]" % (stmt.op,
                                                " ".join(stmt.args)[:18]))
            if len(extra) > 3:
                lines.append("  …")
    elif node.kind == "choice":
        lines.append("选择支 (%d 项):" % len(node.options))
        for i, (text, _tg) in enumerate(node.options[:4]):
            resolved = lang.resolve(text) if lang and text else text
            lines.append("  %d. %s" % (i + 1, (resolved or "")[:24]))
        if len(node.options) > 4:
            lines.append("  …")
    elif node.kind == "if":
        role = node.data.get("role", "if")
        cond = node.data.get("cond", "")
        if role == "elif":
            lines.append("否则如果 %s:" % cond)
        elif role == "else":
            lines.append("否则:")
        else:
            lines.append("如果 %s:" % cond)
        if node.raw is not None:
            branches = node.raw.kwargs.get("branches", [])
            else_body = node.raw.kwargs.get("else")
            total = sum(len(b) for _c, b in branches)
            if else_body is not None:
                total += len(else_body)
            lines.append("  [分支体 %d 条语句 → 画布独立节点]" % total)
    elif node.kind == "stage":
        scene, pose, effect = node.data.get("bg", ["", "", ""])
        lines.append("背景: %s%s%s" % (scene or pose or "(路径)",
                                       " / %s" % pose if scene and pose else "",
                                       "  [%s]" % effect if effect else ""))
        for act, char, expr, eff in node.data.get("sprites", [])[:4]:
            if act == "clear":
                lines.append("  ✕ 清除全部立绘")
            else:
                lines.append("  %s %s%s%s" % (
                    "▲" if act == "show" else "▼", char,
                    " (%s)" % expr if expr else "",
                    " [%s]" % eff if eff else ""))
        if len(node.data.get("sprites", [])) > 4:
            lines.append("  …")
    else:
        for ln in s.split("\n")[:4]:
            resolved = lang.resolve(ln) if lang else ln
            lines.append(resolved[:36])
    return lines


# ----------------------------------------------------------------------
# action 节点参数提示 (P3): 按插件能力给出候选 (可测试纯逻辑)
# ----------------------------------------------------------------------
KERNEL_ACTIONS_HINT = ["start", "quit", "title", "continue", "slot_menu",
                       "save", "load", "close"]
KERNEL_TEXT_MODES = ["typewriter", "instant", "terminal", "lines"]


def _dedup(items):
    seen, out = set(), []
    for it in items:
        if it not in seen:
            seen.add(it)
            out.append(it)
    return out


def collect_plugin_caps(project=None) -> dict:
    """插件能力 (从注册中心构建; 插件主动注册, 编辑器不分析源码)。

    project 保留兼容参数 (项目级插件由导入器安装进 editor/plugins)。
    """
    caps = {}
    for name, p in registry.plugins().items():
        caps[name] = {
            "commands": list(p.commands),
            "actions": list(p.actions),
            "text_modes": list(p.text_modes),
            "transitions": list(p.transitions),
            "command_params": {k: v for k, v in p.commands.items() if v},
        }
    return caps


def action_edit_spec(op: str, caps: dict):
    """action 指令 -> (form_key, (标签, 候选)) 或 None (只读)。

    form_key: combo (单选) / multicombo (逗号分隔多选) / plugin
    """
    if op == "do_action":
        cands = _dedup(list(KERNEL_ACTIONS_HINT) +
                       [a for c in caps.values()
                        for a in c.get("actions", [])])
        return ("combo", ("动作名", cands))
    if op == "typing":
        cands = _dedup(list(KERNEL_TEXT_MODES) +
                       [m for c in caps.values()
                        for m in c.get("text_modes", [])])
        return ("combo", ("文字模式", cands))
    if op == "using":
        cands = [n for n in sorted(caps) if caps[n].get("commands")]
        return ("multicombo", ("插件命名空间", cands))
    if op == "plugin":
        return ("plugin", ("插件名", sorted(caps)))
    if op == "sleep":
        return ("combo", ("等待秒数 (数字)", ["1", "2", "3", "0.5", "5"]))
    if op == "fullscreen":
        return ("combo", ("全屏", ["true", "false"]))
    if op == "fade" or op == "fadeout":
        return ("none", ("黑幕过渡", []))
    if op == "volume":
        return ("volume", ("音量", ["music", "sfx", "voice"]))
    if op == "window":
        return ("window", ("窗口配置", []))
    if op == "confirm":
        return ("confirm", ("确认框", []))
    # 插件指令参数表单 (插件经 editor/plugins/<名>.py 主动注册)
    for c in caps.values():
        fields = c.get("command_params", {}).get(op)
        if fields is not None:
            return ("params", ("参数", fields)) if fields else None
    return None


class FlowScene(QGraphicsScene):
    """节点图场景: 数据 (FlowGraph) 与显示同步。

    连线 (EdgeItem) 为纯数据对象, 统一在 drawForeground 绘制 ——
    规避 PySide6 6.11 自定义 QGraphicsItem 渲染崩溃。
    """

    graph_changed = Signal()   # undo 等替换 graph 后通知 FlowEditor

    def __init__(self, parent=None):
        super().__init__(parent)
        self.graph: FlowGraph | None = None
        self.project = None        # 用于 stage 缩略图路径解析
        self.lang = None           # GameLang | None (项目多语言表)
        self.items_by_id: dict = {}
        self.edges: list = []
        self._label_map: dict = {}   # node_id -> 所属标签树 (视觉分组)
        self._drag = None          # (src_id, port, temp_line)
        self.log = lambda msg: None
        self._undo_stack: list = []
        self._redo_stack: list = []
        self.setBackgroundBrush(QColor("#1c1c28"))
        # PySide6 6.11 不触发 ItemPositionChange/ItemPositionHasChanged
        # (setPos/moveBy 静默), 节点拖动回写与 sceneRect 跟随改由
        # 视图层 mouseMove/Release 后显式 _sync_positions() 完成;
        # scene.changed 仅在真实渲染时发射, 作为 GUI 兜底。
        self.changed.connect(self._on_scene_changed)

    def _on_scene_changed(self, _changes=None) -> None:
        """场景内容变化 (真实渲染时 Qt 才发此信号) 后同步。"""
        self._sync_positions()

    def _sync_positions(self, update_rect: bool = True) -> None:
        """把节点 item 当前位置回写模型坐标。

        update_rect=True 时同时扩展 sceneRect (松开鼠标后调用);
        拖动过程中传 False, 避免每帧 setSceneRect 导致视图跳动。
        """
        if self.graph is None:
            return
        for nid, item in self.items_by_id.items():
            node = item.node
            p = item.pos()
            if node.x != p.x() or node.y != p.y():
                node.x, node.y = p.x(), p.y()
        if update_rect:
            self._sync_scene_rect()

    # ---- 撤销 ---------------------------------------------------------
    def push_undo(self) -> None:
        """变更操作前调用: 压入当前图快照。"""
        if self.graph is not None:
            self._undo_stack.append(self.graph.copy())
            if len(self._undo_stack) > 100:
                self._undo_stack.pop(0)
            self._redo_stack.clear()

    def undo(self) -> bool:
        """Ctrl+Z: 恢复到上一个快照。"""
        if not self._undo_stack:
            self.log(t("flow.no_undo"))
            return False
        self._redo_stack.append(self.graph.copy())
        self.graph = self._undo_stack.pop()
        self.set_graph(self.graph)
        self.graph_changed.emit()
        self.log(t("flow.undone", n=len(self._undo_stack)))
        return True

    def redo(self) -> bool:
        """Ctrl+Shift+Z: 重做。"""
        if not self._redo_stack:
            self.log(t("flow.no_redo"))
            return False
        self._undo_stack.append(self.graph.copy())
        self.graph = self._redo_stack.pop()
        self.set_graph(self.graph)
        self.graph_changed.emit()
        self.log(t("flow.redone", n=len(self._redo_stack)))
        return True

    def undo_depth(self) -> int:
        return len(self._undo_stack)

    # ---- 构建 ---------------------------------------------------------
    def set_graph(self, graph: FlowGraph) -> None:
        self.clear()
        self.graph = graph
        self.items_by_id = {}
        self.edges = []
        self._drag = None
        for nid in graph.order:
            node = graph.nodes[nid]
            item = NodeItem(node, self)
            self.items_by_id[nid] = item
            self.addItem(item)
        self.rebuild_edges()
        self._compute_label_map()
        self._sync_scene_rect()

    # ---- 标签树分组 (视觉) --------------------------------------------
    def _compute_label_map(self) -> None:
        """每个节点归属的标签树。

        第一遍: 沿 next 顺序链传播 (每棵树只覆盖自己的链);
        第二遍: 仅被 jump/选择支引用 (不在任何链上) 的孤岛节点
        归入引用源所属的树。
        """
        self._label_map = {}
        if self.graph is None:
            return
        # 第一遍: next 链
        for nid in self.graph.order:
            n = self.graph.nodes.get(nid)
            if n is None or n.kind != "label":
                continue
            cur = nid
            while cur and cur not in self._label_map \
                    and cur in self.graph.nodes:
                self._label_map[cur] = nid
                nxt = self.graph.nodes[cur].next_id
                if nxt is None or nxt in self._label_map:
                    break
                cur = nxt
        # 第二遍: 孤岛节点 (被跳转/选择支引用)
        for nid in self.graph.nodes:
            if nid in self._label_map:
                continue
            for src in self.graph.nodes.values():
                owner = None
                if src.kind == "jump" and src.data.get("target") == nid:
                    owner = self._label_map.get(src.node_id)
                else:
                    for _t, tg in src.options:
                        if tg == nid:
                            owner = self._label_map.get(src.node_id)
                            break
                if owner:
                    self._label_map[nid] = owner
                    break

    @staticmethod
    def _label_color(label: str):
        """标签树颜色 (按名 hash 到色相)。"""
        from PySide6.QtGui import QColor
        if not label:
            return QColor("#666")
        hue = (sum(ord(c) for c in label) * 47) % 360
        return QColor.fromHsl(hue, 130, 62)

    def _sync_scene_rect(self) -> None:
        """sceneRect 跟随内容 (修复: 固定区域时超出部分无法滚动)。"""
        rect = self.itemsBoundingRect()
        if rect.isNull():
            rect = QRectF(-2000, -2000, 4000, 4000)
        margin = 160
        self.setSceneRect(rect.adjusted(-margin, -margin, margin, margin))

    def rebuild_edges(self) -> None:
        # EdgeItem 为纯数据 (场景前景绘制), 不 addItem/removeItem
        self.edges = []
        if self.graph is None:
            return
        for nid in self.graph.order:
            node = self.graph.nodes[nid]
            if node.kind == "choice":
                for i, (_t, target) in enumerate(node.options):
                    if target and target in self.items_by_id:
                        self._add_edge(nid, target, i)
            elif node.kind == "jump" and node.data.get("target"):
                t = node.data["target"]
                if t in self.items_by_id:
                    self._add_edge(nid, t, 0)
            elif node.next_id and node.next_id in self.items_by_id:
                self._add_edge(nid, node.next_id, 0)
        # 通知 FlowEditor 刷新状态行 (节点/连线/撤销计数)
        self.graph_changed.emit()

    def _add_edge(self, src_id, dst_id, port) -> None:
        edge = EdgeItem(self.items_by_id[src_id],
                        self.items_by_id[dst_id], port, self)
        self.edges.append(edge)
        self.update()

    def delete_edge(self, edge: EdgeItem) -> None:
        """删除一条连线 (右键): 清空对应连接并重建。"""
        self.push_undo()
        src = edge.src.node
        if src.kind == "choice" and edge.port < len(src.options):
            src.options[edge.port][1] = None
        elif src.kind == "jump":
            src.data["target"] = None
        else:
            src.next_id = None
        self.rebuild_edges()
        self.log(t("flow.edge_deleted"))

    def delete_edge_at(self, scene_pos) -> None:
        """右键点击 (视图层): 命中连线则删除。"""
        for e in self.edges:
            if e.hit_test(scene_pos):
                self.delete_edge(e)
                return

    def edges_changed(self) -> None:
        self.update()
        self._sync_scene_rect()

    # ---- 绘制 ---------------------------------------------------------
    def drawBackground(self, painter, rect):
        super().drawBackground(painter, rect)
        grid = 40
        painter.setPen(QPen(QColor("#262638"), 1))
        x = int(rect.left()) // grid * grid
        while x < rect.right():
            painter.drawLine(x, rect.top(), x, rect.bottom())
            x += grid
        y = int(rect.top()) // grid * grid
        while y < rect.bottom():
            painter.drawLine(rect.left(), y, rect.right(), y)
            y += grid

    def drawForeground(self, painter, rect):
        super().drawForeground(painter, rect)
        for e in self.edges:
            path = e.build_path()
            painter.setPen(QPen(QColor("#e94560"), 2.5)
                           if e.hover else QPen(QColor("#9aa5c8"), 2))
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(path)
            # 标注: 目标节点 id (退化 path 跳过, 避免 NaN 坐标)
            if path.length() >= 1:
                pt = path.pointAtPercent(0.5)
                f = painter.font()
                f.setPointSize(7)
                painter.setFont(f)
                painter.setPen(QColor("#6a6a8a"))
                painter.drawText(QPointF(pt.x() + 6, pt.y() - 4),
                                 e.dst.node.node_id)

    # ---- 交互 ---------------------------------------------------------
    def mousePressEvent(self, event):
        pos = event.scenePos()
        # 右键删除连线已移至视图层 (右键拖动画布; 点击删除), 见 ZoomView
        for nid, item in self.items_by_id.items():
            port = item.output_port_at(pos)
            if port is not None and event.button() == Qt.LeftButton:
                start = item.mapToScene(item._output_positions()[
                    min(port, len(item._output_positions()) - 1)])
                self._drag = (nid, port, start)
                self._temp_line = QGraphicsPathItem()
                path = QPainterPath(start)
                path.lineTo(pos)
                self._temp_line.setPath(path)
                self._temp_line.setPen(QPen(QColor("#e94560"), 2,
                                            Qt.DashLine))
                self.addItem(self._temp_line)
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        # 悬停高亮连线
        pos = event.scenePos()
        for e in self.edges:
            e.hover = e.hit_test(pos)
        if self._drag is not None:
            start = self._drag[2]
            path = QPainterPath(start)
            path.lineTo(event.scenePos())
            self._temp_line.setPath(path)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._drag is not None:
            src_id, port, _start = self._drag
            self.push_undo()
            self._drag = None
            if self._temp_line is not None:
                self.removeItem(self._temp_line)
                self._temp_line = None
            target = None
            for nid, item in self.items_by_id.items():
                if nid != src_id and item.input_hit(event.scenePos()):
                    target = nid
                    break
            if target is not None:
                self.graph.connect(src_id, target, port)
                self.rebuild_edges()
                self.log(t("flow.edge_connected", a=src_id, b=target,
                           p=port))
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Delete:
            self.push_undo()
            for item in list(self.selectedItems()):
                if isinstance(item, NodeItem):
                    nid = item.node.node_id
                    self.graph.remove_node(nid)
                    self.log(t("flow.node_deleted", id=nid))
            self.set_graph(self.graph)   # 重建 (清理连线引用)
            event.accept()
            return
        if event.key() == Qt.Key_Z and (event.modifiers() & Qt.ControlModifier):
            if event.modifiers() & Qt.ShiftModifier:
                self.redo()
            else:
                self.undo()
            event.accept()
            return
        super().keyPressEvent(event)

    # ---- 编辑 ---------------------------------------------------------
    def edit_node(self, node) -> None:
        self.push_undo()
        if node.kind == "dialogue":
            self._edit_dialogue(node)
        elif node.kind == "choice":
            self._edit_choice(node)
        elif node.kind == "jump":
            self._edit_jump(node)
        elif node.kind == "ending":
            self._edit_ending(node)
        elif node.kind == "label":
            self._edit_label(node)
        elif node.kind == "stage":
            self._edit_stage(node)
        elif node.kind == "if":
            self._edit_if(node)
        elif node.kind == "action":
            self._edit_action(node)
        elif node.kind == "raw":
            self._edit_raw(node)

    def _edit_dialogue(self, node):
        dlg = QDialog()
        dlg.setWindowTitle(t("flow.edit_dialogue"))
        dlg.resize(560, 480)
        form = QVBoxLayout(dlg)
        # 说话者: 可编辑下拉 (候选 = cast.gal 角色)
        ed_speaker = QComboBox()
        ed_speaker.setEditable(True)
        chars = _char_ids_of(self.project)
        ed_speaker.addItems(chars)
        cur_sp = node.data.get("speaker", "")
        if cur_sp in chars:
            ed_speaker.setCurrentText(cur_sp)
        elif cur_sp:
            ed_speaker.setCurrentText(cur_sp)
        form.addWidget(QLabel(t("flow.speaker_hint")))
        form.addWidget(ed_speaker)
        # 台词: 显示当前语言效果 + 多语言编辑按钮
        form.addWidget(QLabel(t("flow.line_hint")))
        self._lang_row(form, node.data.get("text", ""),
                       lambda new_text: node.data.__setitem__("text",
                                                              new_text))
        # 合并的语句 (对话链): 文本可编辑; 清空文本 = 删除该句
        extra = list(node.extra_stmts)
        self._extra_orig = extra
        self._extra_table = None
        if extra:
            from PySide6.QtWidgets import QHeaderView
            form.addWidget(QLabel(t("flow.merged_hint", n=len(extra))))
            self._extra_table = QTableWidget(len(extra), 2)
            self._extra_table.setHorizontalHeaderLabels(
                [t("flow.speaker_hint"), t("flow.line_hint")])
            self._extra_table.horizontalHeader().setSectionResizeMode(
                1, QHeaderView.Stretch)
            for i, stmt in enumerate(extra):
                if stmt.op in ("say", "nar", "text"):
                    sp2 = stmt.args[0] if stmt.op == "say" and stmt.args \
                        else ""
                    tx2 = stmt.args[-1] if stmt.args else ""
                else:
                    sp2, tx2 = stmt.op, " ".join(stmt.args)
                it_sp = QTableWidgetItem(sp2)
                it_tx = QTableWidgetItem(tx2)
                if stmt.op not in ("say", "nar", "text"):
                    it_sp.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                    it_tx.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                self._extra_table.setItem(i, 0, it_sp)
                self._extra_table.setItem(i, 1, it_tx)
            form.addWidget(self._extra_table, 1)
        btns = QHBoxLayout()
        ok = QPushButton(t("flow.ok")); ok.clicked.connect(dlg.accept)
        cc = QPushButton(t("flow.cancel")); cc.clicked.connect(dlg.reject)
        btns.addStretch(1); btns.addWidget(ok); btns.addWidget(cc)
        form.addLayout(btns)
        if dlg.exec() == QDialog.Accepted:
            sp = ed_speaker.currentText().strip()
            node.data["op"] = "say" if sp else "text"
            node.data["speaker"] = sp
            self._apply_extra_edits(node)
            self.set_graph(self.graph)

    def _apply_extra_edits(self, node) -> None:
        """把合并语句编辑表写回 node.extra_stmts (空文本 = 删除)。"""
        if self._extra_table is None or not self._extra_orig:
            return
        from framework.engine.parser import Statement
        out = []
        for r in range(self._extra_table.rowCount()):
            if r >= len(self._extra_orig):
                break
            stmt = self._extra_orig[r]
            if stmt.op not in ("say", "nar", "text"):
                out.append(stmt)          # 非对话语句原样保留
                continue
            sp2 = (self._extra_table.item(r, 0).text().strip()
                   if self._extra_table.item(r, 0) else "")
            tx2 = (self._extra_table.item(r, 1).text()
                   if self._extra_table.item(r, 1) else "")
            if tx2.strip():
                args = [sp2, tx2] if sp2 else [tx2]
                out.append(Statement(op="say" if sp2 else "text",
                                     args=args))
        node.extra_stmts = out

    def _lang_row(self, layout, text: str, commit) -> None:
        """一行"当前语言预览 + 编辑多语言"控件。

        layout: 父布局; text: 原始文本 (可含 {@key}); commit: 保存回调。
        项目无语言表 (langs 空) 时回退为普通单行编辑框。
        """
        gl = self.lang
        if gl is None or not gl.langs:
            ed = QLineEdit(text)
            ed.textChanged.connect(commit)
            layout.addWidget(ed)
            return
        row = QHBoxLayout()
        resolved = gl.resolve(text)
        lbl = QLabel(resolved or " ")
        lbl.setWordWrap(True)
        lbl.setStyleSheet("color:#d8d8e0; background:#14141c; padding:6px;"
                          " border-radius:4px;")
        btn = QPushButton(t("flow.edit_lang"))
        btn.clicked.connect(lambda: self._open_lang_edit(text, commit))
        row.addWidget(lbl, 1)
        row.addWidget(btn)
        layout.addLayout(row)

    def _open_lang_edit(self, text: str, commit) -> None:
        from editor.lang_dialog import LangEditDialog
        gl = self.scene.lang
        dlg = LangEditDialog(gl, text, self)
        dlg.locate_requested.connect(self.locate_key.emit)
        if dlg.exec() == QDialog.Accepted:
            commit(dlg.result_text())
            self.set_graph(self.graph)

    def _edit_choice(self, node):
        dlg = QDialog()
        dlg.setWindowTitle(t("flow.edit_choice"))
        lay = QVBoxLayout(dlg)
        gl = self.scene.lang
        tbl = QTableWidget(len(node.options), 1)
        tbl.setHorizontalHeaderLabels([t("flow.choice_text")])
        tbl.horizontalHeader().setStretchLastSection(True)
        for i, (text, _tg) in enumerate(node.options):
            item = QTableWidgetItem(
                gl.resolve(text) if (gl is not None and gl.langs) else text)
            item.setData(Qt.UserRole, text)   # 原文 (含 {@key})
            if gl is not None and gl.langs:
                # 有语言表: 单元格只读, 编辑走"编辑多语言"按钮
                item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            tbl.setItem(i, 0, item)
        lay.addWidget(tbl, 1)
        # 选项增删
        row_btns = QHBoxLayout()
        b_add = QPushButton(t("flow.choice_add"))
        b_del = QPushButton(t("flow.choice_del"))
        b_add.clicked.connect(lambda: _choice_insert_row(tbl, row=tbl.rowCount()))
        b_del.clicked.connect(
            lambda: _choice_remove_row(tbl, tbl.currentRow()))
        row_btns.addWidget(b_add)
        row_btns.addWidget(b_del)
        row_btns.addStretch(1)
        # 多语言: 批量编辑全部选项文本
        if gl is not None and gl.langs:
            b_lang = QPushButton(t("flow.edit_lang_all"))
            b_lang.clicked.connect(
                lambda: self._edit_choice_lang(tbl, node))
            row_btns.addWidget(b_lang)
        lay.addLayout(row_btns)
        btns = QHBoxLayout()
        ok = QPushButton(t("flow.ok")); ok.clicked.connect(dlg.accept)
        cc = QPushButton(t("flow.cancel")); cc.clicked.connect(dlg.reject)
        btns.addStretch(1); btns.addWidget(ok); btns.addWidget(cc)
        lay.addLayout(btns)
        if dlg.exec() == QDialog.Accepted:
            node.options = [[(tbl.item(r, 0).text() if tbl.item(r, 0) else ""),
                             node.options[r][1] if r < len(node.options)
                             else None]
                            for r in range(tbl.rowCount())]
            self.set_graph(self.graph)

    def _edit_choice_lang(self, tbl, node) -> None:
        """批量编辑选择支全部选项的多语言 (逐选项打开 LangEditDialog)。"""
        from editor.lang_dialog import LangEditDialog
        gl = self.scene.lang
        for r in range(tbl.rowCount()):
            item = tbl.item(r, 0)
            if item is None:
                continue
            orig = item.data(Qt.UserRole) or item.text()
            dlg = LangEditDialog(gl, orig, self)
            if dlg.exec() == QDialog.Accepted:
                new_text = dlg.result_text()
                item.setText(new_text)
                item.setData(Qt.UserRole, new_text)

    def _edit_jump(self, node):
        dlg = QDialog()
        dlg.setWindowTitle("编辑跳转")
        lay = QVBoxLayout(dlg)
        ids = [nid for nid in self.graph.order if nid != node.node_id]
        cb = QComboBox()
        cb.addItems(ids)
        cur = node.data.get("target")
        if cur in ids:
            cb.setCurrentText(cur)
        lay.addWidget(QLabel("目标节点"))
        lay.addWidget(cb)
        chk = QCheckBox("用 call (子过程调用, 可 return)")
        chk.setChecked(bool(node.data.get("is_call")))
        lay.addWidget(chk)
        btns = QHBoxLayout()
        ok = QPushButton("确定"); ok.clicked.connect(dlg.accept)
        cc = QPushButton("取消"); cc.clicked.connect(dlg.reject)
        btns.addStretch(1); btns.addWidget(ok); btns.addWidget(cc)
        lay.addLayout(btns)
        if dlg.exec() == QDialog.Accepted:
            node.data["target"] = cb.currentText()
            node.data["is_call"] = chk.isChecked()
            self.rebuild_edges()

    def _edit_ending(self, node):
        dlg = QDialog()
        dlg.setWindowTitle(t("flow.edit_ending"))
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel(t("flow.ending_hint")))
        self._lang_row(lay, node.data.get("name", ""),
                       lambda new_text: node.data.__setitem__("name",
                                                              new_text))
        btns = QHBoxLayout()
        ok = QPushButton(t("flow.ok")); ok.clicked.connect(dlg.accept)
        cc = QPushButton(t("flow.cancel")); cc.clicked.connect(dlg.reject)
        btns.addStretch(1); btns.addWidget(ok); btns.addWidget(cc)
        lay.addLayout(btns)
        if dlg.exec() == QDialog.Accepted:
            self.set_graph(self.graph)

    def _edit_label(self, node):
        dlg = QDialog()
        dlg.setWindowTitle(t("flow.edit_label"))
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel(t("flow.label_hint")))
        self._lang_row(lay, node.data.get("text", ""),
                       lambda new_text: node.data.__setitem__("text",
                                                              new_text))
        btns = QHBoxLayout()
        ok = QPushButton(t("flow.ok")); ok.clicked.connect(dlg.accept)
        cc = QPushButton(t("flow.cancel")); cc.clicked.connect(dlg.reject)
        btns.addStretch(1); btns.addWidget(ok); btns.addWidget(cc)
        lay.addLayout(btns)
        if dlg.exec() == QDialog.Accepted:
            self.set_graph(self.graph)

    def _edit_stage(self, node):
        """场景分镜编辑: 背景 + 立绘动作列表。"""
        dlg = StageDialog(self.project, node, self)
        if dlg.exec() == QDialog.Accepted:
            dlg.apply(node)
            self.set_graph(self.graph)

    def _edit_if(self, node):
        """条件节点 (if/elif/else 边界): 编辑条件; 分支体为独立节点。"""
        from PySide6.QtWidgets import QPlainTextEdit
        role = node.data.get("role", "if")
        stmt = node.raw
        dlg = QDialog()
        dlg.setWindowTitle(t("flow.edit_if"))
        dlg.resize(520, 300)
        lay = QVBoxLayout(dlg)
        if role == "else":
            lay.addWidget(QLabel(t("flow.else_hint")))
        else:
            lay.addWidget(QLabel(
                t("flow.if_cond") if role == "if"
                else t("flow.elif_cond")))
            ed_cond = QLineEdit(node.data.get("cond", ""))
            lay.addWidget(ed_cond)
        hint = QLabel(t("flow.if_branch_nodes"))
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#888;")
        lay.addWidget(hint)
        btns = QHBoxLayout()
        ok = QPushButton(t("flow.ok")); ok.clicked.connect(dlg.accept)
        cc = QPushButton(t("flow.cancel")); cc.clicked.connect(dlg.reject)
        btns.addStretch(1); btns.addWidget(ok); btns.addWidget(cc)
        lay.addLayout(btns)
        if dlg.exec() == QDialog.Accepted and role != "else":
            cond = ed_cond.text().strip()
            node.data["cond"] = cond
            # 同步写回 raw 的 branches (保持导出一致)
            if stmt is not None:
                branches = stmt.kwargs.get("branches", [])
                if role == "if" and branches:
                    branches[0][0] = cond
                elif role == "elif":
                    # 匹配当前 elif 条件 (对应 branches[1..])
                    old_cond = node.data.get("cond", "")
                    for idx, (c, _b) in enumerate(branches[1:], start=1):
                        if c == old_cond:
                            branches[idx][0] = cond
                            break
            self.set_graph(self.graph)

    def _edit_action(self, node):
        """动作节点: 已知指令弹参数表单 (按插件能力给候选), 否则通用表单。"""
        if node.raw is None:
            return
        spec = action_edit_spec(node.raw.op, collect_plugin_caps(self.project))
        if spec is None:
            self._edit_action_generic(node)
            return
        form_key, (label, cands) = spec
        if form_key == "combo":
            self._edit_action_combo(node, label, cands)
        elif form_key == "multicombo":
            self._edit_action_multicombo(node, label, cands)
        elif form_key == "plugin":
            self._edit_action_plugin(node, cands)
        elif form_key == "volume":
            self._edit_action_volume(node, cands)
        elif form_key == "window":
            self._edit_action_window(node)
        elif form_key == "confirm":
            self._edit_action_confirm(node)
        elif form_key == "params":
            self._edit_action_params(node, cands, False)
        elif form_key == "none":
            self._edit_action_generic(node)

    def _edit_action_window(self, node):
        """window config 节点: 项目设置式表单 (写回 kwargs)。"""
        from PySide6.QtWidgets import QCheckBox as _Chk
        from PySide6.QtWidgets import QSpinBox as _Spin
        stmt = node.raw
        k = dict(stmt.kwargs)
        dlg = QDialog()
        dlg.setWindowTitle(t("flow.edit_window_cfg"))
        lay = QVBoxLayout(dlg)
        form = QFormLayout()
        ed_title = QLineEdit(str(k.get("title", "")))
        form.addRow(t("flow.win_title"), ed_title)
        sp_w = _Spin(); sp_w.setRange(320, 7680)
        sp_w.setValue(_to_int(k.get("width"), 1280))
        sp_h = _Spin(); sp_h.setRange(240, 4320)
        sp_h.setValue(_to_int(k.get("height"), 720))
        row = QHBoxLayout(); row.addWidget(sp_w)
        row.addWidget(QLabel("×")); row.addWidget(sp_h)
        form.addRow(t("flow.win_size"), row)
        sp_fps = _Spin(); sp_fps.setRange(15, 240)
        sp_fps.setValue(_to_int(k.get("fps"), 60))
        form.addRow(t("flow.win_fps"), sp_fps)
        ed_icon = QLineEdit(str(k.get("icon", "")))
        form.addRow(t("flow.win_icon"), ed_icon)
        chk_full = _Chk(t("flow.win_fullscreen"))
        chk_full.setChecked(str(k.get("fullscreen", "false")).lower()
                            in ("true", "1", "yes", "on"))
        chk_res = _Chk(t("flow.win_resizable"))
        chk_res.setChecked(str(k.get("resizable", "true")).lower()
                           in ("true", "1", "yes", "on"))
        form.addRow("", chk_full)
        form.addRow("", chk_res)
        lay.addLayout(form)
        btns = QHBoxLayout()
        ok = QPushButton(t("flow.ok")); ok.clicked.connect(dlg.accept)
        cc = QPushButton(t("flow.cancel")); cc.clicked.connect(dlg.reject)
        btns.addStretch(1); btns.addWidget(ok); btns.addWidget(cc)
        lay.addLayout(btns)
        if dlg.exec() == QDialog.Accepted:
            stmt.kwargs["title"] = ed_title.text().strip()
            stmt.kwargs["width"] = str(sp_w.value())
            stmt.kwargs["height"] = str(sp_h.value())
            stmt.kwargs["fps"] = str(sp_fps.value())
            if ed_icon.text().strip():
                stmt.kwargs["icon"] = ed_icon.text().strip()
            else:
                stmt.kwargs.pop("icon", None)
            stmt.kwargs["fullscreen"] = "true" if chk_full.isChecked() \
                else "false"
            stmt.kwargs["resizable"] = "true" if chk_res.isChecked() \
                else "false"
            self.set_graph(self.graph)

    def _edit_action_confirm(self, node):
        """confirm 节点: 文本 + yes/no + -> 变量。"""
        stmt = node.raw
        args = list(stmt.args)
        text = args[0] if args else ""
        yes = no = var = ""
        i = 1
        while i < len(args):
            if args[i] == "yes" and i + 1 < len(args):
                yes = args[i + 1]; i += 2
            elif args[i] == "no" and i + 1 < len(args):
                no = args[i + 1]; i += 2
            elif args[i] == "->" and i + 1 < len(args):
                var = args[i + 1]; i += 2
            else:
                i += 1
        dlg = QDialog()
        dlg.setWindowTitle(t("flow.edit_confirm"))
        lay = QVBoxLayout(dlg)
        form = QFormLayout()
        ed_text = QLineEdit(text)
        form.addRow(t("flow.confirm_text"), ed_text)
        ed_yes = QLineEdit(yes)
        form.addRow(t("flow.confirm_yes"), ed_yes)
        ed_no = QLineEdit(no)
        form.addRow(t("flow.confirm_no"), ed_no)
        ed_var = QLineEdit(var)
        ed_var.setPlaceholderText(t("flow.confirm_var_hint"))
        form.addRow(t("flow.confirm_var"), ed_var)
        lay.addLayout(form)
        btns = QHBoxLayout()
        ok = QPushButton(t("flow.ok")); ok.clicked.connect(dlg.accept)
        cc = QPushButton(t("flow.cancel")); cc.clicked.connect(dlg.reject)
        btns.addStretch(1); btns.addWidget(ok); btns.addWidget(cc)
        lay.addLayout(btns)
        if dlg.exec() == QDialog.Accepted:
            out = [ed_text.text()]
            if ed_yes.text().strip():
                out += ["yes", ed_yes.text().strip()]
            if ed_no.text().strip():
                out += ["no", ed_no.text().strip()]
            if ed_var.text().strip():
                out += ["->", ed_var.text().strip()]
            stmt.args = out
            self.set_graph(self.graph)

    def _edit_action_generic(self, node):
        """未知/无参数指令: 通用参数表单 (不再"后续版本提供")。"""
        from PySide6.QtWidgets import QPlainTextEdit
        stmt = node.raw
        dlg = QDialog()
        dlg.setWindowTitle("编辑动作 — %s" % stmt.op)
        lay = QVBoxLayout(dlg)
        eds: list = []
        if not stmt.args and not stmt.kwargs:
            lay.addWidget(QLabel("语句: %s (无参数)" % stmt.op))
        else:
            for i, a in enumerate(stmt.args):
                lay.addWidget(QLabel("参数 %d:" % (i + 1)))
                e = QLineEdit(a)
                eds.append(e)
                lay.addWidget(e)
            for k, v in stmt.kwargs.items():
                lay.addWidget(QLabel("属性 %s:" % k))
                e = QLineEdit(str(v))
                eds.append(e)
                lay.addWidget(e)
        btns = QHBoxLayout()
        ok = QPushButton("确定"); ok.clicked.connect(dlg.accept)
        cc = QPushButton("取消"); cc.clicked.connect(dlg.reject)
        btns.addStretch(1); btns.addWidget(ok); btns.addWidget(cc)
        lay.addLayout(btns)
        if dlg.exec() == QDialog.Accepted:
            n_args = len(stmt.args)
            if stmt.args or stmt.kwargs:
                stmt.args = [e.text() for e in eds[:n_args]]
                for i, k in enumerate(stmt.kwargs.keys()):
                    stmt.kwargs[k] = eds[n_args + i].text()
            self.set_graph(self.graph)

    def _edit_raw(self, node):
        """代码节点 (python:: 块或未知语句): 原样内容可编辑。"""
        from PySide6.QtWidgets import QPlainTextEdit
        from PySide6.QtGui import QFont as _QF
        if node.raw is None:
            return
        stmt = node.raw
        dlg = QDialog()
        dlg.setWindowTitle("代码节点 — %s" % stmt.op)
        dlg.resize(560, 360)
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel("语句: %s (内容原样保留)" % stmt.op))
        if "code" in stmt.kwargs:
            ed = QPlainTextEdit(stmt.kwargs.get("code", ""))
            ed.setFont(_QF("Consolas", 10))
            lay.addWidget(ed, 1)
            eds = None
        else:
            eds = []
            for i, a in enumerate(stmt.args):
                lay.addWidget(QLabel("参数 %d:" % (i + 1)))
                e = QLineEdit(a)
                eds.append(e)
                lay.addWidget(e)
            ed = None
        btns = QHBoxLayout()
        ok = QPushButton("确定"); ok.clicked.connect(dlg.accept)
        cc = QPushButton("取消"); cc.clicked.connect(dlg.reject)
        btns.addStretch(1); btns.addWidget(ok); btns.addWidget(cc)
        lay.addLayout(btns)
        if dlg.exec() == QDialog.Accepted:
            if ed is not None:
                stmt.kwargs["code"] = ed.toPlainText()
            elif eds:
                stmt.args = [e.text() for e in eds]
            self.set_graph(self.graph)

    def _edit_action_volume(self, node, cands):
        dlg = QDialog()
        dlg.setWindowTitle("音量 — %s" % node.raw.op)
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel("目标:"))
        cb = QComboBox()
        cb.addItems(cands)
        cur = node.raw.args[0] if node.raw.args else "music"
        if cur in cands:
            cb.setCurrentText(cur)
        lay.addWidget(cb)
        lay.addWidget(QLabel("音量 (0-1):"))
        ed = QLineEdit(node.raw.args[-1] if len(node.raw.args) > 1
                       else "1.0")
        lay.addWidget(ed)
        btns = QHBoxLayout()
        ok = QPushButton("确定"); ok.clicked.connect(dlg.accept)
        cc = QPushButton("取消"); cc.clicked.connect(dlg.reject)
        btns.addStretch(1); btns.addWidget(ok); btns.addWidget(cc)
        lay.addLayout(btns)
        if dlg.exec() == QDialog.Accepted:
            node.raw.args = [cb.currentText(), ed.text().strip()]
            self.set_graph(self.graph)

    def _edit_action_params(self, node, fields, doc_mode: bool):
        """通用逐参表单: fields = [(标签, 类型, 默认)] 或 [参数名...]。"""
        if doc_mode:
            fields = [(f, "text", "") for f in fields]
        dlg = QDialog()
        dlg.setWindowTitle("编辑动作参数 — %s" % node.raw.op)
        lay = QVBoxLayout(dlg)
        eds = []
        args = list(node.raw.args)
        for i, (label, _typ, default) in enumerate(fields):
            lay.addWidget(QLabel(label + ":"))
            ed = QLineEdit(args[i] if i < len(args) else str(default))
            eds.append(ed)
        btns = QHBoxLayout()
        ok = QPushButton("确定"); ok.clicked.connect(dlg.accept)
        cc = QPushButton("取消"); cc.clicked.connect(dlg.reject)
        btns.addStretch(1); btns.addWidget(ok); btns.addWidget(cc)
        lay.addLayout(btns)
        if dlg.exec() == QDialog.Accepted:
            node.raw.args = [e.text().strip() for e in eds]
            self.set_graph(self.graph)

    def _show_action_raw(self, node):
        from editor.serializer import serialize as _ser
        from framework.engine.parser import Script
        tmp = Script()
        tmp.statements = [node.raw]
        text = _ser(tmp).strip()
        _NL = chr(10)
        QMessageBox.information(
            None, "动作节点",
            ("此节点是引擎语句 (%s), 已原样保留。" % node.raw.op) + _NL + _NL
            + "完整可视化编辑将在后续版本提供。" + _NL + _NL + "---"
            + _NL + text)

    def _edit_action_combo(self, node, label, cands):
        dlg = QDialog()
        dlg.setWindowTitle("编辑动作参数 — %s" % node.raw.op)
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel(label + ":"))
        cb = QComboBox()
        cb.setEditable(True)
        cb.addItems(cands)
        cur = node.raw.args[0] if node.raw.args else ""
        if cur in cands:
            cb.setCurrentText(cur)
        lay.addWidget(cb)
        btns = QHBoxLayout()
        ok = QPushButton("确定"); ok.clicked.connect(dlg.accept)
        cc = QPushButton("取消"); cc.clicked.connect(dlg.reject)
        btns.addStretch(1); btns.addWidget(ok); btns.addWidget(cc)
        lay.addLayout(btns)
        if dlg.exec() == QDialog.Accepted:
            node.raw.args = [cb.currentText().strip()]
            self.set_graph(self.graph)

    def _edit_action_multicombo(self, node, label, cands):
        dlg = QDialog()
        dlg.setWindowTitle("编辑动作参数 — %s" % node.raw.op)
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel(label + " (逗号分隔):"))
        ed = QLineEdit(", ".join(node.raw.args))
        ed.setPlaceholderText("如: fx, custom_actions")
        lay.addWidget(ed)
        hint = QLabel("候选: " + ", ".join(cands[:12]) +
                      ("…" if len(cands) > 12 else ""))
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#888;")
        lay.addWidget(hint)
        btns = QHBoxLayout()
        ok = QPushButton("确定"); ok.clicked.connect(dlg.accept)
        cc = QPushButton("取消"); cc.clicked.connect(dlg.reject)
        btns.addStretch(1); btns.addWidget(ok); btns.addWidget(cc)
        lay.addLayout(btns)
        if dlg.exec() == QDialog.Accepted:
            node.raw.args = [a.strip() for a in ed.text().split(",")
                             if a.strip()]
            self.set_graph(self.graph)

    def _edit_action_plugin(self, node, cands):
        dlg = QDialog()
        dlg.setWindowTitle("插件管理 — %s" % node.raw.op)
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel("动作:"))
        cb_op = QComboBox()
        cb_op.addItems(["load", "unload", "list"])
        cur_op = node.raw.args[0] if node.raw.args else "load"
        if cur_op in ("load", "unload", "list"):
            cb_op.setCurrentText(cur_op)
        lay.addWidget(cb_op)
        lay.addWidget(QLabel("插件名:"))
        cb_pl = QComboBox()
        cb_pl.setEditable(True)
        cb_pl.addItems(cands)
        cur_pl = node.raw.args[1] if len(node.raw.args) > 1 else ""
        if cur_pl in cands:
            cb_pl.setCurrentText(cur_pl)
        lay.addWidget(cb_pl)
        btns = QHBoxLayout()
        ok = QPushButton("确定"); ok.clicked.connect(dlg.accept)
        cc = QPushButton("取消"); cc.clicked.connect(dlg.reject)
        btns.addStretch(1); btns.addWidget(ok); btns.addWidget(cc)
        lay.addLayout(btns)
        if dlg.exec() == QDialog.Accepted:
            args = [cb_op.currentText()]
            if cb_op.currentText() != "list" and cb_pl.currentText().strip():
                args.append(cb_pl.currentText().strip())
            node.raw.args = args
            self.set_graph(self.graph)


class ZoomView(QGraphicsView):
    """带缩放比例反馈的视图 + 右键拖动画布 (右键点击连线=删除)。"""

    zoom_changed = Signal(float)
    _PAN_THRESHOLD = 6

    def __init__(self, scene=None, parent=None):
        super().__init__(scene, parent)
        self._pan_start = None
        self._panning = False

    def wheelEvent(self, event):
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.scale(factor, factor)
        self.zoom_changed.emit(self.transform().m11())
        event.accept()

    def showEvent(self, event):
        super().showEvent(event)
        self.zoom_changed.emit(self.transform().m11())

    # ---- 右键: 拖动画布 / 点击删除连线 --------------------------------
    def mousePressEvent(self, event):
        if event.button() == Qt.RightButton:
            self._pan_start = event.position().toPoint()
            self._panning = False
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._pan_start is not None:
            pos = event.position().toPoint()
            if not self._panning and (pos - self._pan_start).manhattanLength() \
                    > self._PAN_THRESHOLD:
                self._panning = True
                self.setCursor(Qt.ClosedHandCursor)
            if self._panning:
                delta = pos - self._pan_start
                self._pan_start = pos
                self.horizontalScrollBar().setValue(
                    self.horizontalScrollBar().value() - delta.x())
                self.verticalScrollBar().setValue(
                    self.verticalScrollBar().value() - delta.y())
                event.accept()
                return
            # 未开始平移: 让场景处理 (悬停高亮)
            super().mouseMoveEvent(event)
            return
        super().mouseMoveEvent(event)
        # 拖动同步 (PySide6 6.11: setPos 不触发 itemChange)
        sync = getattr(self.scene(), "_sync_positions", None)
        if sync is not None:
            sync(update_rect=False)
        # 显式全场景重绘: Qt 增量重绘只更新节点附近区域,
        # 长连线远处段会残留旧位置 (拖动时连线"一坨")
        self.scene().update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.RightButton and self._pan_start is not None:
            pos = event.position().toPoint()
            moved = (pos - self._pan_start).manhattanLength() \
                > self._PAN_THRESHOLD
            self._pan_start = None
            self._panning = False
            self.unsetCursor()
            if not moved:
                # 右键点击 (未拖动): 命中连线则删除
                self._right_click_handle(event)
            event.accept()
            return
        super().mouseReleaseEvent(event)
        # 松开后: 回写坐标 + 扩展 sceneRect (滚动条跟随)
        sync = getattr(self.scene(), "_sync_positions", None)
        if sync is not None:
            sync(update_rect=True)

    def _right_click_handle(self, event) -> None:
        """右键点击: 命中连线 -> 删除 (等价原 scene 右键行为)。"""
        scene = self.scene()
        pos = self.mapToScene(event.position().toPoint())
        delete = getattr(scene, "delete_edge_at", None)
        if delete is not None:
            delete(pos)


class FlowEditor(QWidget):
    """流程节点编辑器 (逻辑 Tab)。"""

    log = Signal(str)
    locate_key = Signal(str)   # 请求主窗口在多语言面板定位 key
    node_selected = Signal(object)   # 选中节点 (FlowNode | None) -> 属性面板

    def __init__(self, parent=None):
        super().__init__(parent)
        self.project = None
        self.graph = FlowGraph()
        self._dirty = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        bar = QHBoxLayout()
        self._tool_btns = []
        for key, kind in (("flow.add_dialogue", "dialogue"),
                          ("flow.add_choice", "choice"),
                          ("flow.add_jump", "jump"),
                          ("flow.add_ending", "ending"),
                          ("flow.add_label", "label"),
                          ("flow.add_stage", "stage"),
                          ("flow.add_if", "if"),
                          ("flow.add_action", "action"),
                          ("flow.add_raw", "raw")):
            btn = QPushButton(t(key))
            btn.clicked.connect(lambda _c=False, k=kind: self._add(k))
            bar.addWidget(btn)
            self._tool_btns.append((btn, key))
        bar.addStretch(1)
        self.btn_layout = QPushButton(t("flow.layout"))
        self.btn_layout.clicked.connect(self._auto_layout)
        self.btn_fit = QPushButton(t("flow.fit"))
        self.btn_fit.clicked.connect(self._fit)
        self.btn_save = QPushButton(t("flow.save"))
        self.btn_save.clicked.connect(self.save)
        bar.addWidget(self.btn_layout)
        bar.addWidget(self.btn_fit)
        bar.addWidget(self.btn_save)
        self._tool_btns += [(self.btn_layout, "flow.layout"),
                            (self.btn_fit, "flow.fit"),
                            (self.btn_save, "flow.save")]
        layout.addLayout(bar)

        self.scene = FlowScene()
        self.scene.log = lambda msg: self.log.emit(msg)
        self.scene.graph_changed.connect(self._on_graph_changed)
        # 选中变化 -> 属性面板 (右键画布空白处取消选中 -> None)
        self.scene.selectionChanged.connect(self._emit_selection)
        self.view = ZoomView(self.scene)
        self.view.setRenderHint(QPainter.Antialiasing)
        self.view.setDragMode(QGraphicsView.RubberBandDrag)
        layout.addWidget(self.view, 1)

        status = QHBoxLayout()
        self.lbl_status = QLabel("")
        self.lbl_status.setStyleSheet("color:#888;")
        self.lbl_zoom = QLabel("100%")
        self.lbl_zoom.setStyleSheet("color:#888;")
        status.addWidget(self.lbl_status)
        status.addStretch(1)
        status.addWidget(self.lbl_zoom)
        layout.addLayout(status)
        self.view.zoom_changed.connect(
            lambda z: self.lbl_zoom.setText("%d%%" % int(z * 100)))
        self._update_status()
        self.scene.set_graph(self.graph)

    # ---- 语言刷新 -----------------------------------------------------
    def apply_lang(self) -> None:
        for btn, key in self._tool_btns:
            btn.setText(t(key))
        self._update_status()

    # ---- 项目绑定 -----------------------------------------------------
    def set_project(self, project) -> None:
        self.project = project
        self.scene.project = project
        # 项目多语言表 (节点摘要/编辑对话框显示当前语言文本)
        if project is not None:
            from editor.lang_utils import GameLang
            self.scene.lang = GameLang(project.root, project.main_script())
        else:
            self.scene.lang = None
        _clear_thumb_cache()
        self.load()

    def load(self) -> None:
        """从项目 story.gal 导入节点图。"""
        if self.project is None:
            self.graph = FlowGraph()
            self.scene.set_graph(self.graph)
            self._dirty = False
            return
        script = self.project.scripts.get("story.gal")
        if script is None:
            self.graph = FlowGraph()
        else:
            self.graph = FlowGraph.from_script(script)
        self.scene.set_graph(self.graph)
        self.log.emit(t("flow.story_imported", n=len(self.graph.nodes)))
        self._fit()
        self._dirty = False

    def save(self) -> None:
        if self.project is None:
            self.log.emit(t("flow.no_project"))
            return
        script = self.graph.to_script()
        save_script(script, os.path.join(self.project.root, "story.gal"))
        self.log.emit(t("flow.story_saved", n=len(script.labels)))
        self.project.load()
        self.scene.set_graph(self.graph)   # 重建 (id 可能新增)
        self._dirty = False

    def is_dirty(self) -> bool:
        """画布有未保存修改 (供关闭/切项目确认)。"""
        return self._dirty

    # ---- 操作 ---------------------------------------------------------
    def _on_graph_changed(self):
        """scene 内部替换 graph (撤销) 后同步引用, 避免保存旧数据。"""
        self.graph = self.scene.graph
        self._dirty = True
        self._update_status()

    def _emit_selection(self) -> None:
        """把当前选中节点发给属性面板 (多选/空选 -> None)。"""
        sel = self.scene.selectedItems()
        node = None
        for item in sel:
            if isinstance(item, NodeItem):
                node = item.node
                break
        self.node_selected.emit(node)

    def _update_status(self):
        if self.scene is not None:
            self.lbl_status.setText(t(
                "flow.status", n=len(self.scene.items_by_id),
                e=len(self.scene.edges), u=self.scene.undo_depth(),
                r=len(self.scene._redo_stack)))

    def _add(self, kind: str):
        self.scene.push_undo()
        node = self.graph.add_node(kind)
        # 给新节点一个可读的默认内容
        if kind == "dialogue":
            node.data["op"] = "text"
            node.data["text"] = "新对话…"
        elif kind == "choice":
            node.options = [["选项一", None], ["选项二", None]]
        elif kind == "jump":
            node.data["target"] = None
        elif kind == "ending":
            node.data["name"] = "结局"
        elif kind == "stage":
            node.data["bg"] = ["", "", ""]
        elif kind == "if":
            from framework.engine.parser import Statement
            node.data["cond"] = ""
            node.raw = Statement(op="if",
                                 kwargs={"branches": [["", []]]})
        elif kind == "action":
            from framework.engine.parser import Statement
            op = self._pick_action_op()
            if op is None:
                self.graph.remove_node(node.node_id)
                return
            node.raw = Statement(op=op, args=[])
        elif kind == "raw":
            from framework.engine.parser import Statement
            node.raw = Statement(op="python",
                                 kwargs={"code": "# 在此编写 Python 代码"})
        self.scene.set_graph(self.graph)
        self.scene.items_by_id[node.node_id].setSelected(True)

    def _pick_action_op(self) -> str | None:
        """动作节点指令选择: 内核常用指令 + 插件注册指令/动作。"""
        cands = list(KERNEL_OPS)
        try:
            from editor.plugins_api import registry
            for name, p in registry.plugins().items():
                cands.extend(p.commands.keys())
            for a in registry.actions():
                if a not in cands:
                    cands.append("do_action: %s" % a)
        except Exception:
            pass
        seen, out = set(), []
        for c in cands:
            if c not in seen:
                seen.add(c)
                out.append(c)
        dlg = QDialog(self)
        dlg.setWindowTitle(t("flow.pick_action"))
        lay = QVBoxLayout(dlg)
        cb = QComboBox()
        cb.setEditable(True)
        cb.addItems(out)
        cb.setCurrentText("say")
        lay.addWidget(QLabel(t("flow.pick_action_hint")))
        lay.addWidget(cb)
        btns = QHBoxLayout()
        ok = QPushButton(t("flow.ok")); ok.clicked.connect(dlg.accept)
        cc = QPushButton(t("flow.cancel")); cc.clicked.connect(dlg.reject)
        btns.addStretch(1); btns.addWidget(ok); btns.addWidget(cc)
        lay.addLayout(btns)
        if dlg.exec() != QDialog.Accepted:
            return None
        op = cb.currentText().strip()
        if op.startswith("do_action: "):
            op = "do_action"
        return op or None

    def _auto_layout(self):
        self.graph.auto_layout()
        self.scene.set_graph(self.graph)
        self._fit()
        self.log.emit(t("flow.layout"))

    def _fit(self):
        rect = self.scene.itemsBoundingRect()
        if rect.isNull():
            return
        self.view.fitInView(rect.adjusted(-80, -80, 80, 80),
                            Qt.KeepAspectRatio)


class StageDialog(QDialog):
    """场景分镜编辑: 背景 (场景/背景名/过渡) + 立绘动作表。"""

    def __init__(self, project, node, parent=None):
        super().__init__(parent)
        self.setWindowTitle("场景分镜")
        self.setMinimumWidth(580)
        self.project = project
        self._moves = []

        self.scene_ids, self.char_ids = [], []
        if project is not None:
            cast = project.scripts.get("cast.gal")
            if cast is not None:
                from editor.definitions import iter_defs
                self.scene_ids = [s.args[0] for s in iter_defs(cast, "scene")]
                self.char_ids = [c.args[0] for c in iter_defs(cast, "char")]

        bg = node.data.get("bg", ["", "", ""])
        form = QFormLayout()
        self.cb_scene = QComboBox()
        self.cb_scene.setEditable(True)
        self.cb_scene.addItems(self.scene_ids)
        self.cb_scene.setCurrentText(bg[0] or bg[1] or "")
        self.cb_scene.lineEdit().setPlaceholderText("场景 ID 或直接输入图片路径")
        form.addRow("背景", self.cb_scene)
        self.ed_pose = QLineEdit(bg[1] if bg[0] else "")
        self.ed_pose.setPlaceholderText("场景内背景名 (如 morning)")
        form.addRow("背景名", self.ed_pose)
        self.cb_effect = QComboBox()
        self.cb_effect.setEditable(True)
        # 过渡效果候选: 引擎内核 + 插件注册 (transitions_plus 等)
        effect_cands = ["", "fade", "dissolve", "blinds", "slide",
                        "circle", "pixelate", "zoom"]
        try:
            from editor.plugins_api import registry
            for tr in registry.transitions():
                if tr and tr not in effect_cands:
                    effect_cands.append(tr)
        except Exception:
            pass
        self.cb_effect.addItems(effect_cands)
        self.cb_effect.setCurrentText(bg[2] or "")
        form.addRow("过渡效果", self.cb_effect)
        btn_preview = QPushButton("引擎真实预览…")
        btn_preview.clicked.connect(self._engine_preview)
        form.addRow("", btn_preview)

        layout = QVBoxLayout(self)
        layout.addLayout(form)

        self.lbl_preview = QLabel()
        self.lbl_preview.setMinimumHeight(150)
        self.lbl_preview.setAlignment(Qt.AlignCenter)
        self.lbl_preview.setStyleSheet("background:#101018; color:#777;")
        layout.addWidget(self.lbl_preview)
        self.cb_scene.lineEdit().textChanged.connect(self._update_preview)
        self.ed_pose.textChanged.connect(self._update_preview)
        self._update_preview()

        lbl = QLabel("立绘动作 (动作 / 角色 / 表情 / 效果)")
        layout.addWidget(lbl)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["动作", "角色", "表情", "效果"])
        self.table.horizontalHeader().setStretchLastSection(True)
        for row in node.data.get("sprites", []):
            self._add_row(row)
        layout.addWidget(self.table, 1)

        btns = QHBoxLayout()
        for text, row in (("＋显示", ["show", "", "", ""]),
                          ("＋隐藏", ["hide", "", "", ""]),
                          ("＋清除", ["clear", "", "", ""])):
            b = QPushButton(text)
            b.clicked.connect(lambda _c=False, r=row: self._add_row(r))
            btns.addWidget(b)
        btns.addStretch(1)
        b_ok = QPushButton("确定")
        b_ok.clicked.connect(self.accept)
        b_cc = QPushButton("取消")
        b_cc.clicked.connect(self.reject)
        btns.addWidget(b_ok)
        btns.addWidget(b_cc)
        layout.addLayout(btns)

        # ---- 音频轨时间线 (音乐/音效/音量/控制) ----
        lbl2 = QLabel("音频轨时间线 (双击编辑, 拖拽排序, 选中后删除) — 名称可参考项目 audio.gal")
        lbl2.setStyleSheet("color:#888;")
        layout.addWidget(lbl2)
        self.timeline = AudioTimeline()
        self.timeline.set_items(node.data.get("audio", []))
        self.timeline.item_activated.connect(self._edit_audio_item)
        layout.addWidget(self.timeline, 1)
        abtns = QHBoxLayout()
        for text, row in (("＋音乐", ["music", "", "1", ""]),
                          ("＋音效", ["sfx", "", "", ""]),
                          ("＋音量", ["volume", "music", "", "1.0"]),
                          ("＋暂停/恢复/停止", ["pause", "music", "", ""])):
            b = QPushButton(text)
            b.clicked.connect(lambda _c=False, r=row: self._add_audio_row(r))
            abtns.addWidget(b)
        btn_del = QPushButton("删除选中")
        btn_del.clicked.connect(self.timeline.remove_selected)
        abtns.addWidget(btn_del)
        # 声音名称候选 (项目 audio.gal 的 sound 定义)
        self._sound_names = []
        if self.project is not None:
            audio = self.project.scripts.get("audio.gal")
            if audio is not None:
                from editor.definitions import iter_defs
                self._sound_names = [s.args[0]
                                     for s in iter_defs(audio, "sound")]
        if self._sound_names:
            hint = QLabel("名称候选: " + ", ".join(self._sound_names[:10]))
            hint.setStyleSheet("color:#777;")
            abtns.addWidget(hint, 1)
        layout.addLayout(abtns)

    def _preview_path(self):
        """按当前表单值解析背景图绝对路径 (无图返回 None)。"""
        if self.project is None:
            return None
        scene = self.cb_scene.currentText().strip()
        pose = self.ed_pose.text().strip()
        path = ""
        if scene in self.scene_ids:
            from editor.definitions import iter_defs
            cast = self.project.scripts.get("cast.gal")
            if cast is not None:
                for s in iter_defs(cast, "scene"):
                    if s.args[0] == scene:
                        path = s.kwargs.get(pose) or s.kwargs.get("default", "")
                        break
        elif scene:
            path = scene
        elif pose:
            path = pose
        if not path:
            return None
        full = os.path.join(self.project.root, path)
        return full if os.path.isfile(full) else None

    def _update_preview(self, *_a):
        p = self._preview_path()
        if p is None:
            self.lbl_preview.setText("无背景图 (场景未定义或路径不存在)")
            return
        pix = QPixmap(p)
        if pix.isNull():
            self.lbl_preview.setText("无法加载: %s" % os.path.basename(p))
            return
        w = self.lbl_preview.width() or 480
        self.lbl_preview.setPixmap(pix.scaled(
            w, 150, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.lbl_preview.setText("")

    def _add_row(self, row):
        """新增立绘动作行 (全下拉化: 动作/角色/表情/效果)。"""
        r = self.table.rowCount()
        self.table.insertRow(r)
        # 动作
        cb_act = QComboBox()
        cb_act.addItems(["show", "hide", "clear"])
        cb_act.setCurrentText(row[0] if row and row[0] in
                              ("show", "hide", "clear") else "show")
        self.table.setCellWidget(r, 0, cb_act)
        # 角色 (可编辑下拉, 候选 = cast.gal 角色)
        cb_char = QComboBox()
        cb_char.setEditable(True)
        cb_char.addItems(self.char_ids)
        if row and row[1]:
            cb_char.setCurrentText(row[1])
        self.table.setCellWidget(r, 1, cb_char)
        # 表情 (联动所选角色的表情表)
        cb_expr = QComboBox()
        cb_expr.setEditable(True)
        self.table.setCellWidget(r, 2, cb_expr)
        cb_char.currentTextChanged.connect(
            lambda c, w=cb_expr: self._fill_expressions(w, c))
        self._fill_expressions(cb_expr, cb_char.currentText())
        if row and row[2]:
            cb_expr.setCurrentText(row[2])
        # 效果 (内核 + 插件注册)
        cb_eff = QComboBox()
        cb_eff.setEditable(True)
        cb_eff.addItems(_sprite_effect_cands())
        if row and row[3]:
            cb_eff.setCurrentText(row[3])
        self.table.setCellWidget(r, 3, cb_eff)

    def _fill_expressions(self, cb: QComboBox, char_id: str) -> None:
        """按角色填充表情候选 (char 定义的立绘名)。"""
        cb.blockSignals(True)
        cur = cb.currentText()
        cb.clear()
        cands = [""]
        if self.project is not None:
            cast = self.project.scripts.get("cast.gal")
            if cast is not None:
                from editor.definitions import iter_defs
                for s in iter_defs(cast, "char"):
                    if s.args[0] == char_id:
                        cands += [k for k in s.kwargs.keys()
                                  if k not in ("name", "default",
                                               "voice_volume", "desc",
                                               "description", "bio",
                                               "intro", "cv", "birthday",
                                               "height", "age")]
                        break
        cb.addItems(cands)
        if cur in cands:
            cb.setCurrentText(cur)
        cb.blockSignals(False)

    def _add_audio_row(self, row):
        items = self.timeline.items_data()
        items.append((list(row) + ["", "", "", ""])[:4])
        self.timeline.set_items(items)

    def _edit_audio_item(self, index):
        """双击时间线条目: 操作/对象下拉 + 参数编辑。"""
        data = self.timeline.items_data()[index]
        dlg = QDialog(self)
        dlg.setWindowTitle(t("flow.edit_audio"))
        lay = QVBoxLayout(dlg)
        form = QFormLayout()
        # 操作 (下拉)
        cb_op = QComboBox()
        cb_op.addItems(["music", "sfx", "volume", "pause", "resume", "stop"])
        cur_op = data[0] if data and data[0] in (
            "music", "sfx", "volume", "pause", "resume", "stop") else "music"
        cb_op.setCurrentText(cur_op)
        form.addRow(t("flow.audio_op"), cb_op)
        # 对象 (可编辑下拉: sound 注册名 + music/sfx/voice)
        cb_obj = QComboBox()
        cb_obj.setEditable(True)
        cands = list(self._sound_names)
        for x in ("music", "sfx", "voice"):
            if x not in cands:
                cands.append(x)
        cb_obj.addItems(cands)
        if len(data) > 1 and data[1]:
            cb_obj.setCurrentText(data[1])
        form.addRow(t("flow.audio_obj"), cb_obj)
        ed_a = QLineEdit(data[2] if len(data) > 2 else "")
        ed_a.setPlaceholderText(t("flow.audio_a"))
        form.addRow(t("flow.audio_a"), ed_a)
        ed_b = QLineEdit(data[3] if len(data) > 3 else "")
        ed_b.setPlaceholderText(t("flow.audio_b"))
        form.addRow(t("flow.audio_b"), ed_b)
        lay.addLayout(form)
        btns = QHBoxLayout()
        ok = QPushButton(t("flow.ok")); ok.clicked.connect(dlg.accept)
        cc = QPushButton(t("flow.cancel")); cc.clicked.connect(dlg.reject)
        btns.addStretch(1); btns.addWidget(ok); btns.addWidget(cc)
        lay.addLayout(btns)
        if dlg.exec() == QDialog.Accepted:
            self.timeline.set_item_data(
                index, [cb_op.currentText(), cb_obj.currentText().strip(),
                        ed_a.text().strip(), ed_b.text().strip()])

    def _engine_preview(self):
        from editor.stage_preview import StagePreviewDialog
        if self.project is None:
            QMessageBox.information(self, "提示", "请先打开项目")
            return
        # 用当前表单值生成临时节点
        import editor.flow as _flow
        tmp_node = _flow.FlowNode("preview", "stage",
                                  data={"bg": ["", "", ""], "sprites": []})
        scene = self.cb_scene.currentText().strip()
        pose = self.ed_pose.text().strip()
        effect = self.cb_effect.currentText().strip()
        if scene in self.scene_ids:
            tmp_node.data["bg"] = [scene, pose, effect]
        else:
            tmp_node.data["bg"] = ["", scene or pose, effect]
        for r in range(self.table.rowCount()):
            vals = []
            for c in range(4):
                w = self.table.cellWidget(r, c)
                if isinstance(w, QComboBox):
                    vals.append(w.currentText().strip())
                else:
                    it = self.table.item(r, c)
                    vals.append(it.text().strip() if it else "")
            if vals[0]:
                tmp_node.data["sprites"].append(vals)
        dlg = StagePreviewDialog(self.project, tmp_node, self,
                                 on_apply=self._apply_moves)
        dlg.exec()

    def _apply_moves(self, moves):
        """立绘排布位置 -> 保存到本节点 (apply 时写回模型)。"""
        self._moves = moves

    def apply(self, node):
        scene = self.cb_scene.currentText().strip()
        pose = self.ed_pose.text().strip()
        effect = self.cb_effect.currentText().strip()
        if scene in self.scene_ids:
            bg = [scene, pose, effect]
        else:
            bg = ["", scene or pose, effect]   # 直接路径
        sprites = []
        for r in range(self.table.rowCount()):
            vals = []
            for c in range(4):
                w = self.table.cellWidget(r, c)
                if isinstance(w, QComboBox):
                    vals.append(w.currentText().strip())
                else:
                    it = self.table.item(r, c)
                    vals.append(it.text().strip() if it else "")
            if vals[0]:
                sprites.append(vals)
        node.data["bg"] = bg
        node.data["sprites"] = sprites
        if self._moves:
            node.data["moves"] = self._moves
        else:
            node.data.pop("moves", None)
        audio = [row for row in self.timeline.items_data() if row[0]]
        if audio:
            node.data["audio"] = audio
        else:
            node.data.pop("audio", None)
