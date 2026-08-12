"""P2 测试: 流程节点图 (FlowGraph v2) 导入/导出。

v2 模型: 每个标签 = 剧情树入口 (label 节点), 标签内每行语句 = 一个节点,
jump/if/动作等全部独立呈现 (不再合并对话链/并入 stage)。

验证:
1. 导入 demo story.gal -> 节点图 (标签齐全, 每行语句有节点, if/jump 呈现)
2. 导出 -> Script: 与原文**逐行结构等价** (op/args/choice options)
3. 新建图: label 入口 + 对话链 + 选择支 + 结局 -> 生成解析
4. stage 单节点 (bg), 后续 show/music 为独立 action 节点
5. if 节点条件保留; 台词 voice 参数保留
6. 删除节点清理引用; 自动布局坐标有限
7. 幂等: 导入 -> 导出 -> 再导入, 节点结构稳定
"""

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)

from framework.engine.parser import parse, parse_file
from editor.flow import FlowGraph, DIALOGUE_OPS

FAILURES: list = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print("  [OK]   %s" % name)
    else:
        FAILURES.append(name)
        print("  [FAIL] %s %s" % (name, detail))


def _render(script) -> str:
    from editor.serializer import serialize
    return serialize(script)


def stmt_eq(a, b) -> bool:
    """两条语句语义等价 (op + args + choice options/if cond)。"""
    if a.op != b.op or tuple(a.args) != tuple(b.args):
        return False
    if a.op == "choice":
        def norm(opts):
            return [(str(t), str(tg)) for t, tg in opts or []]
        return norm(a.kwargs.get("options")) == norm(b.kwargs.get("options"))
    if a.op == "if":
        return (str(a.kwargs.get("cond", "")) == str(b.kwargs.get("cond", "")))
    return True


def main() -> int:
    print("== P2 流程节点图测试 (v2 每行节点化) ==")

    demo = os.path.join(_ROOT, "test", "engine_demo", "story.gal")
    orig = parse_file(demo)

    # 1. 导入
    g = FlowGraph.from_script(orig)
    check("导入标签入口齐全", set(g.nodes) >= set(orig.labels),
          "缺失: %s" % (set(orig.labels) - set(g.nodes)))
    kinds = {n.kind for n in g.nodes.values()}
    check("每行语句节点化 (节点数 >= 语句数)",
          len(g.nodes) >= sum(len(b) for b in orig.labels.values()))
    check("if 节点独立呈现", "if" in kinds, str(kinds))
    check("jump 节点独立呈现 (不折叠)", "jump" in kinds, str(kinds))
    check("动作节点覆盖声音/立绘/插件指令",
          any(n.kind == "action" and n.raw and n.raw.op in
              ("music", "show", "set", "typing") for n in g.nodes.values()))

    # 2. 导出 -> 与原文逐行结构等价
    s2 = g.to_script()
    check("导出保留全部原标签", set(orig.labels) == set(s2.labels),
          "差异: %s" % (set(orig.labels) ^ set(s2.labels)))
    diff_lines = 0
    for lab in orig.labels:
        a, b = orig.labels[lab], s2.labels.get(lab, [])
        if len(a) != len(b):
            diff_lines += 1
            continue
        for sa, sb in zip(a, b):
            if not stmt_eq(sa, sb):
                diff_lines += 1
                break
    check("导出逐行结构等价 (0 差异)", diff_lines == 0, "%d 处差异" % diff_lines)

    orig_dlg = sum(1 for body in orig.labels.values()
                   for st in body if st.op in DIALOGUE_OPS)
    new_dlg = sum(1 for body in s2.labels.values()
                  for st in body if st.op in DIALOGUE_OPS)
    check("对话语句数等价", new_dlg == orig_dlg, "%d vs %d" % (new_dlg, orig_dlg))

    # 3. 新建图: label 入口 + 对话链 + 选择支 + 结局
    g2 = FlowGraph()
    entry = g2.add_node("label", node_id="start", data={"text": "start"})
    a = g2.add_node("dialogue", data={"op": "say", "speaker": "主角",
                                      "text": "你好世界"})
    ch = g2.add_node("choice", options=[["喜欢", None], ["讨厌", None]])
    good = g2.add_node("ending", data={"name": "好结局"})
    bad = g2.add_node("ending", data={"name": "坏结局"})
    g2.connect(entry.node_id, a.node_id)
    g2.connect(a.node_id, ch.node_id)
    g2.set_option(ch.node_id, 0, "喜欢", good.node_id)
    g2.set_option(ch.node_id, 1, "讨厌", bad.node_id)
    s3 = g2.to_script()
    p3 = parse(_render(s3), "story.gal")
    check("新建图标签数 (1 入口 + 2 提升)", len(p3.labels) == 3
          and "start" in p3.labels, "labels=%s" % sorted(p3.labels))
    body = p3.labels["start"]
    check("对话在入口链上", body[0].op == "say"
          and body[0].args == ["主角", "你好世界"])
    ch_stmt = next(st for st in body if st.op == "choice")
    check("选择支选项目标", ch_stmt.kwargs["options"] ==
          [("喜欢", good.node_id), ("讨厌", bad.node_id)])
    # 选项目标 (非 label 节点) 被提升为宿主标签
    check("选项目标提升为标签",
          good.node_id in p3.labels and bad.node_id in p3.labels)
    endings = [st for body in p3.labels.values()
               for st in body if st.op == "ending"]
    check("结局生成 (2)", len(endings) == 2)

    # 3.5 stage 单节点 (bg), show 等为独立 action 节点
    stage_src = (
        "s1:\n"
        "    bg school morning with fade\n"
        "    show producer normal with slide_right\n"
        "    text \"你好\"\n"
        "    clear\n"
    )
    gs = FlowGraph.from_script(parse(stage_src, "story.gal"))
    stages = [n for n in gs.nodes.values() if n.kind == "stage"]
    check("bg 转 stage 节点", len(stages) == 1)
    if stages:
        check("stage 背景解析", stages[0].data["bg"] ==
              ["school", "morning", "fade"])
    acts = [n for n in gs.nodes.values() if n.kind == "action"]
    check("show/clear 独立 action 节点",
          any(n.raw and n.raw.op == "show" for n in acts)
          and any(n.raw and n.raw.op == "clear" for n in acts))
    check("对话独立节点", any(n.kind == "dialogue" for n in gs.nodes.values()))
    # 导出等价
    sp = parse(_render(gs.to_script()), "story.gal")
    ops = [st.op for body in sp.labels.values() for st in body]
    check("导出 bg/show/clear 齐全", ops.count("bg") == 1
          and ops.count("show") == 1 and ops.count("clear") == 1,
          "ops=%s" % ops)
    bg_stmt = next(st for body in sp.labels.values()
                   for st in body if st.op == "bg")
    check("导出 bg 参数", bg_stmt.args == ["school", "morning", "with", "fade"])

    # 3.6 if 节点 + 台词 voice 参数
    if_src = (
        "s1:\n"
        "    set love = 1\n"
        "    if love > 0:\n"
        "        nar \"{@love_high}\"\n"
        "    else:\n"
        "        nar \"{@love_low}\"\n"
        "    endif\n"
        "    nar \"{@voice_intro}\" voice voice_demo\n"
    )
    gi = FlowGraph.from_script(parse(if_src, "story.gal"))
    if_nodes = [n for n in gi.nodes.values() if n.kind == "if"]
    check("if 节点解析", len(if_nodes) == 1)
    if if_nodes:
        check("if 条件保留", if_nodes[0].data.get("cond") == "love > 0",
              "got %r" % if_nodes[0].data.get("cond"))
    dlg_voice = [n for n in gi.nodes.values()
                 if n.kind == "dialogue" and n.data.get("voice")]
    check("台词 voice 参数保留", len(dlg_voice) == 1
          and dlg_voice[0].data["voice"] == "voice_demo")
    ip = parse(_render(gi.to_script()), "story.gal")
    check("导出 if 语句", any(st.op == "if" for body in ip.labels.values()
                              for st in body))
    check("导出 voice 参数", any(st.op == "nar" and "voice" in st.args
                                 for body in ip.labels.values()
                                 for st in body))

    # 4. 删除节点清理引用
    g3 = FlowGraph.from_script(orig)
    victim = next(nid for nid, n in g3.nodes.items() if n.kind == "choice")
    g3.remove_node(victim)
    check("删除清理引用", victim not in g3.nodes
          and all(n.next_id != victim for n in g3.nodes.values())
          and all(tg != victim for n in g3.nodes.values()
                  for _t, tg in n.options))

    # 5. 自动布局
    g.auto_layout()
    coords = [(n.x, n.y) for n in g.nodes.values()]
    check("自动布局坐标有限", all(isinstance(x, (int, float))
                                and isinstance(y, (int, float))
                                for x, y in coords))
    # 竖向布局: 主链 y 递增
    entry = g.nodes.get("game_start")
    if entry is not None and entry.next_id:
        first = g.nodes[entry.next_id]
        check("竖向布局 (后继 y 更大)", first.y >= entry.y)

    # 6. 幂等: 导入 -> 导出 -> 再导入, 节点结构稳定
    g_again = FlowGraph.from_script(s2)
    counts = lambda gg: sorted(
        (n.kind, n.raw.op if n.raw else "",
         tuple(n.data.get("bg", [])), tuple(tuple(o) for o in n.options))
        for n in gg.nodes.values())
    check("二次导入节点结构稳定", counts(g_again) == counts(g),
          "%s vs %s" % (counts(g_again), counts(g)))
    s3b = g_again.to_script()
    check("二次导出稳定", all(stmt_eq(a, b)
                              for lab in s2.labels
                              for a, b in zip(s2.labels[lab],
                                              s3b.labels.get(lab, []))))

    print()
    if FAILURES:
        print("结果: %d 项失败 -> %s" % (len(FAILURES), FAILURES))
        return 1
    print("结果: 全部通过 ✓")
    return 0


if __name__ == "__main__":
    os._exit(main())
