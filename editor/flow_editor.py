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
from editor.plugins_registry import (framework_plugins_dir,
                                     scan_plugins_dir)
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
}
KIND_NAMES = {"dialogue": "对话", "choice": "选择支", "jump": "跳转",
              "ending": "结局", "label": "标签", "raw": "代码",
              "action": "动作", "stage": "场景"}

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
        lines = _summary_lines(self.node)
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
        # 标题条
        title = "%s  [%s]" % (KIND_NAMES.get(self.node.kind, self.node.kind),
                              self.node.node_id)
        painter.setPen(Qt.white)
        f = painter.font()
        f.setBold(True)
        painter.setFont(f)
        painter.drawText(QRectF(8, 6, NODE_W - 16, 22), Qt.AlignLeft, title)
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
        for line in _summary_lines(self.node):
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


def _summary_lines(node) -> list:
    s = node.summary()
    lines = []
    if node.kind == "choice":
        lines.append("选择支 (%d 项):" % len(node.options))
        for i, (text, _tg) in enumerate(node.options[:4]):
            lines.append("  %d. %s" % (i + 1, (text or "")[:24]))
        if len(node.options) > 4:
            lines.append("  …")
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
            lines.append(ln[:36])
    return lines


# ----------------------------------------------------------------------
# action 节点参数提示 (P3): 按插件能力给出候选 (可测试纯逻辑)
# ----------------------------------------------------------------------
KERNEL_ACTIONS_HINT = ["start", "quit", "title", "continue", "slot_menu",
                       "save", "load", "close"]
KERNEL_TEXT_MODES = ["typewriter", "instant", "terminal", "lines"]
KERNEL_TRANSITIONS = ["fade", "dissolve", "blinds", "slide", "circle",
                      "pixelate", "zoom"]


def _dedup(items):
    seen, out = set(), []
    for it in items:
        if it not in seen:
            seen.add(it)
            out.append(it)
    return out


def collect_plugin_caps(project=None) -> dict:
    """内置插件 + 项目插件能力。"""
    caps = scan_plugins_dir(framework_plugins_dir())
    if project is not None:
        caps.update(scan_plugins_dir(os.path.join(project.root, "plugins")))
    return caps


# 内置插件指令参数模式 (framework/plugins, 与源码实现对应)
# 格式: [(参数标签, 类型, 默认值)]  type: number/int/color/text
BUILTIN_CMD_PARAMS = {
    "shake": [("时长 (秒)", "number", "0.3"), ("幅度 (像素)", "int", "8")],
    "flash": [("时长 (秒)", "number", "0.15")],
    "blackflash": [("时长 (秒)", "number", "0.3")],
    "strobe": [("时长 (秒)", "number", "0.8")],
    "tint": [("颜色 r,g,b", "color", "255,0,0"), ("时长 (秒)", "number", "0.5")],
    "pulse": [("颜色 r,g,b", "color", "0,255,128"), ("时长 (秒)", "number", "1.0")],
}


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
    # 内置插件指令参数表 (fx 等, 与 framework/plugins 对应)
    if op in BUILTIN_CMD_PARAMS:
        return ("params", ("参数", BUILTIN_CMD_PARAMS[op]))
    # 插件 docstring 约定: 指令函数 docstring 写 "<参数名> ..." 即得表单
    for c in caps.values():
        if op in c.get("command_params", {}):
            return ("textparams", ("参数", c["command_params"][op]))
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
        self.items_by_id: dict = {}
        self.edges: list = []
        self._drag = None          # (src_id, port, temp_line)
        self.log = lambda msg: None
        self._undo_stack: list = []
        self._redo_stack: list = []
        self.setBackgroundBrush(QColor("#1c1c28"))

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

    def edges_changed(self) -> None:
        self.update()

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
        # 右键删除连线 (EdgeItem 不覆盖 contextMenuEvent)
        if event.button() == Qt.RightButton:
            for e in self.edges:
                if e.hit_test(pos):
                    self.delete_edge(e)
                    event.accept()
                    return
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
        elif node.kind == "action":
            self._edit_action(node)

    def _edit_dialogue(self, node):
        from PySide6.QtWidgets import QDialog as _D
        dlg = _D()
        dlg.setWindowTitle("编辑对话")
        form = QVBoxLayout(dlg)
        ed_speaker = QLineEdit(node.data.get("speaker", ""))
        ed_text = QLineEdit(node.data.get("text", ""))
        form.addWidget(QLabel("说话者 (留空=旁白)"))
        form.addWidget(ed_speaker)
        form.addWidget(QLabel("台词"))
        form.addWidget(ed_text)
        btns = QHBoxLayout()
        ok = QPushButton("确定"); ok.clicked.connect(dlg.accept)
        cc = QPushButton("取消"); cc.clicked.connect(dlg.reject)
        btns.addStretch(1); btns.addWidget(ok); btns.addWidget(cc)
        form.addLayout(btns)
        if dlg.exec() == _D.Accepted:
            sp = ed_speaker.text().strip()
            node.data["op"] = "say" if sp else "text"
            node.data["speaker"] = sp
            node.data["text"] = ed_text.text()
            self.set_graph(self.graph)

    def _edit_choice(self, node):
        dlg = QDialog()
        dlg.setWindowTitle("编辑选择支 (连线设定选项目标)")
        lay = QVBoxLayout(dlg)
        t = QTableWidget(len(node.options), 1)
        t.setHorizontalHeaderLabels(["选项文本"])
        t.horizontalHeader().setStretchLastSection(True)
        for i, (text, _tg) in enumerate(node.options):
            t.setItem(i, 0, QTableWidgetItem(text))
        lay.addWidget(t)
        btns = QHBoxLayout()
        ok = QPushButton("确定"); ok.clicked.connect(dlg.accept)
        cc = QPushButton("取消"); cc.clicked.connect(dlg.reject)
        btns.addStretch(1); btns.addWidget(ok); btns.addWidget(cc)
        lay.addLayout(btns)
        if dlg.exec() == QDialog.Accepted:
            for i in range(t.rowCount()):
                it = t.item(i, 0)
                if i < len(node.options):
                    node.options[i][0] = it.text() if it else ""
            self.set_graph(self.graph)

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
        name, ok = QInputDialog.getText(None, "编辑结局", "结局名 (可留空)",
                                        text=node.data.get("name", ""))
        if ok:
            node.data["name"] = name.strip()
            self.set_graph(self.graph)

    def _edit_label(self, node):
        text, ok = QInputDialog.getText(None, "编辑标签", "说明文字 (显示用)",
                                        text=node.data.get("text", ""))
        if ok:
            node.data["text"] = text.strip()
            self.set_graph(self.graph)

    def _edit_stage(self, node):
        """场景分镜编辑: 背景 + 立绘动作列表。"""
        dlg = StageDialog(self.project, node, self)
        if dlg.exec() == QDialog.Accepted:
            dlg.apply(node)
            self.set_graph(self.graph)

    def _edit_action(self, node):
        """动作节点: 已知指令弹参数表单 (按插件能力给候选), 否则只读。"""
        if node.raw is None:
            return
        spec = action_edit_spec(node.raw.op, collect_plugin_caps(self.project))
        if spec is None:
            self._show_action_raw(node)
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
        elif form_key == "params":
            self._edit_action_params(node, cands, False)
        elif form_key == "textparams":
            self._edit_action_params(node, cands, True)
        elif form_key == "none":
            self._show_action_raw(node)

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
    """带缩放比例反馈的视图。"""

    zoom_changed = Signal(float)

    def wheelEvent(self, event):
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.scale(factor, factor)
        self.zoom_changed.emit(self.transform().m11())
        event.accept()

    def showEvent(self, event):
        super().showEvent(event)
        self.zoom_changed.emit(self.transform().m11())


class FlowEditor(QWidget):
    """流程节点编辑器 (逻辑 Tab)。"""

    log = Signal(str)

    def _edit_stage(self, node):
        """场景分镜编辑: 背景 + 立绘动作列表。"""
        dlg = StageDialog(self.project, node, self)
        if dlg.exec() == QDialog.Accepted:
            dlg.apply(node)
            self.set_graph(self.graph)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.project = None
        self.graph = FlowGraph()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        bar = QHBoxLayout()
        self._tool_btns = []
        for key, kind in (("flow.add_dialogue", "dialogue"),
                          ("flow.add_choice", "choice"),
                          ("flow.add_jump", "jump"),
                          ("flow.add_ending", "ending"),
                          ("flow.add_label", "label")):
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
        self.view = ZoomView(self.scene)
        self.view.setRenderHint(QPainter.Antialiasing)
        self.view.setDragMode(QGraphicsView.RubberBandDrag)
        self.view.setSceneRect(-2000, -2000, 4000, 4000)
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
        _clear_thumb_cache()
        self.load()

    def load(self) -> None:
        """从项目 story.gal 导入节点图。"""
        if self.project is None:
            self.graph = FlowGraph()
            self.scene.set_graph(self.graph)
            return
        script = self.project.scripts.get("story.gal")
        if script is None:
            self.graph = FlowGraph()
        else:
            self.graph = FlowGraph.from_script(script)
        self.scene.set_graph(self.graph)
        self.log.emit(t("flow.story_imported", n=len(self.graph.nodes)))
        self._fit()

    def save(self) -> None:
        if self.project is None:
            self.log.emit(t("flow.no_project"))
            return
        script = self.graph.to_script()
        save_script(script, os.path.join(self.project.root, "story.gal"))
        self.log.emit(t("flow.story_saved", n=len(script.labels)))
        self.project.load()
        self.scene.set_graph(self.graph)   # 重建 (id 可能新增)

    # ---- 操作 ---------------------------------------------------------
    def _on_graph_changed(self):
        """scene 内部替换 graph (撤销) 后同步引用, 避免保存旧数据。"""
        self.graph = self.scene.graph
        self._update_status()

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
        self.scene.set_graph(self.graph)
        self.scene.items_by_id[node.node_id].setSelected(True)

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
        self.cb_effect.addItems(
            ["", "fade", "dissolve", "blinds", "slide", "circle", "pixelate",
             "zoom", "wipe", "iris", "curtain", "sweep", "fade_white",
             "checker", "stripes"])
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
        r = self.table.rowCount()
        self.table.insertRow(r)
        for c, val in enumerate(row):
            self.table.setItem(r, c, QTableWidgetItem(val))

    def _add_audio_row(self, row):
        items = self.timeline.items_data()
        items.append((list(row) + ["", "", "", ""])[:4])
        self.timeline.set_items(items)

    def _edit_audio_item(self, index):
        """双击时间线条目: 4 字段编辑对话框。"""
        data = self.timeline.items_data()[index]
        dlg = QDialog(self)
        dlg.setWindowTitle("编辑音频条目")
        lay = QVBoxLayout(dlg)
        eds = []
        labels = ["操作 (music/sfx/volume/pause/resume/stop)",
                  "对象 (名称/目标)", "参数A (loop/角色)", "参数B (fade/音量)"]
        for i, (lab, val) in enumerate(zip(labels, data)):
            lay.addWidget(QLabel(lab + ":"))
            ed = QLineEdit(val)
            eds.append(ed)
            lay.addWidget(ed)
        btns = QHBoxLayout()
        ok = QPushButton("确定"); ok.clicked.connect(dlg.accept)
        cc = QPushButton("取消"); cc.clicked.connect(dlg.reject)
        btns.addStretch(1); btns.addWidget(ok); btns.addWidget(cc)
        lay.addLayout(btns)
        if dlg.exec() == QDialog.Accepted:
            self.timeline.set_item_data(
                index, [e.text().strip() for e in eds])

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
