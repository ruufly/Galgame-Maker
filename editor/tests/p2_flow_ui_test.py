"""P2 测试: 流程画布 UI (FlowEditor/FlowScene)。

验证:
1. 打开 demo 项目 -> 画布导入节点与连线
2. 程序化加节点/连线 -> scene 同步
3. 保存 -> story.gal 生成 -> 解析通过
4. 删除节点 -> 图与画布同步

运行::

    py -3.10 editor/tests/p2_flow_ui_test.py
"""

import os
import shutil
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)

from PySide6.QtWidgets import QApplication

from framework.engine.parser import parse_file
from editor.flow_editor import FlowEditor, NodeItem
from editor.flow import FlowGraph
from editor.model import Project

FAILURES: list = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print("  [OK]   %s" % name)
    else:
        FAILURES.append(name)
        print("  [FAIL] %s %s" % (name, detail))


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    print("== P2 流程画布 UI 测试 ==")

    # 1. 打开 demo 项目 -> 自动导入
    demo_dir = os.path.join(_ROOT, "test", "engine_demo")
    project = Project(demo_dir).load()
    ed = FlowEditor()
    ed.set_project(project)
    n_items = len(ed.scene.items_by_id)
    n_edges = len(ed.scene.edges)
    check("导入节点数 > 5", n_items > 5, "got %d" % n_items)
    check("导入有连线", n_edges > 0, "got %d" % n_edges)
    check("画布项含 NodeItem",
          any(isinstance(i, NodeItem) for i in ed.scene.items()))

    # 2. 加节点 + 连线
    dlg = ed.graph.add_node("dialogue", data={"op": "text", "text": "测试台词"})
    end = ed.graph.add_node("ending", data={"name": "测试结局"})
    ed.graph.connect(dlg.node_id, end.node_id)
    ed.scene.set_graph(ed.graph)
    check("画布节点数同步 +2",
          len(ed.scene.items_by_id) == n_items + 2)
    check("连线 +1", len(ed.scene.edges) == n_edges + 1)

    # 3. 保存 -> 解析
    tmp = tempfile.mkdtemp(prefix="galmake_flowui_")
    try:
        ed.project = Project(tmp).load()
        # 让 project 有 story.gal 位置可写
        shutil.copy(os.path.join(demo_dir, "story.gal"),
                    os.path.join(tmp, "story.gal"))
        ed.graph.auto_layout()
        ed.save()
        sp = parse_file(os.path.join(tmp, "story.gal"))
        check("保存后 story.gal 可解析 (%d 标签)" % len(sp.labels),
              len(sp.labels) >= 5)
        # 再导入一次 (保存 -> 导入闭环)
        ed.load()
        check("保存后重新导入成功",
              len(ed.scene.items_by_id) >= 5)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # 3.6 舞台缩略图解析 (demo 场景图存在)
    from editor.flow_editor import resolve_bg_image
    stage_paths = [resolve_bg_image(project, n) for n in
                   ed.graph.nodes.values() if n.kind == "stage"]
    real = [p for p in stage_paths if p and os.path.isfile(p)]
    check("stage 背景图可解析", len(real) >= 1, "ok=%d/%d"
          % (len(real), len(stage_paths)))

    # 3.7 撤销: 加节点 -> Ctrl+Z
    n_before = len(ed.scene.items_by_id)
    ed.scene.push_undo()
    ed.graph.add_node("ending", data={"name": "临时"})
    ed.scene.set_graph(ed.graph)
    check("撤销前节点 +1", len(ed.scene.items_by_id) == n_before + 1)
    ed.scene.undo()
    check("撤销后恢复", len(ed.scene.items_by_id) == n_before)

    # 3.8 连线删除 (delete_edge 清空连接) 与撤销
    ed2 = FlowEditor()
    ed2.set_project(project)
    baseline = len(ed2.scene.edges)
    a2 = ed2.graph.add_node("dialogue", data={"op": "text", "text": "A"})
    b2 = ed2.graph.add_node("dialogue", data={"op": "text", "text": "B"})
    ed2.graph.connect(a2.node_id, b2.node_id)
    ed2.scene.set_graph(ed2.graph)
    check("连线建立 (+1)", len(ed2.scene.edges) == baseline + 1,
          "got %d (baseline %d)" % (len(ed2.scene.edges), baseline))
    edge = next(e for e in ed2.scene.edges
                if e.src.node.node_id == a2.node_id)
    ed2.scene.delete_edge(edge)
    check("连线删除后清空", len(ed2.scene.edges) == baseline
          and ed2.graph.nodes[a2.node_id].next_id is None)
    check("删除可撤销", ed2.scene.undo()
          and ed2.scene.graph.nodes[a2.node_id].next_id == b2.node_id)

    # 4. 删除节点 -> 同步
    victim = dlg.node_id
    ed.graph.remove_node(victim)
    ed.scene.set_graph(ed.graph)
    check("删除后画布移除",
          victim not in ed.scene.items_by_id
          and all(e.src.node.node_id != victim
                  and e.dst.node.node_id != victim for e in ed.scene.edges))

    print()
    if FAILURES:
        print("结果: %d 项失败 -> %s" % (len(FAILURES), FAILURES))
        return 1
    print("结果: 全部通过 ✓")
    return 0


if __name__ == "__main__":
    os._exit(main())
