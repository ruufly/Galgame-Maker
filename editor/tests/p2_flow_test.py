"""P2 测试: 流程节点图 (FlowGraph) 导入/导出。

验证:
1. 导入 demo story.gal -> 节点图 (标签齐全, 语句转节点正确)
2. 导出 -> Script -> 解析: 标签集合等价、对话内容等价、choice 选项等价
3. 新建节点图: 对话链 + 选择支 + 结局, 生成后解析验证
4. 删除节点清理引用
5. 自动布局不抛错 (坐标可读)

运行::

    py -3.10 editor/tests/p2_flow_test.py
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


def main() -> int:
    print("== P2 流程节点图测试 ==")

    demo = os.path.join(_ROOT, "test", "engine_demo", "story.gal")
    orig = parse_file(demo)

    # 1. 导入
    g = FlowGraph.from_script(orig)
    check("导入标签齐全", set(g.nodes) >= set(orig.labels),
          "nodes=%s labels=%s" % (sorted(g.nodes), sorted(orig.labels)))
    check("导入有对话节点", any(n.kind == "dialogue" for n in g.nodes.values()))
    check("导入有选择支", any(n.kind == "choice" for n in g.nodes.values()))
    check("导入有结局", any(n.kind == "ending" for n in g.nodes.values()))

    # 2. 导出 -> 解析: 语义等价
    s2 = g.to_script()
    text = "\n".join("%s:\n    %s" % (lab, _body_to_text(body))
                     for lab, body in s2.labels.items())
    s2p = parse(_render(s2), "story.gal")
    check("导出保留全部原标签", set(orig.labels) <= set(s2p.labels),
          "缺失: %s" % (set(orig.labels) - set(s2p.labels)))

    # 对话链合并: 导出标签数应远小于语句数
    # (stage 结构化后每个场景切换一个节点, 允许适度增加)
    stmt_count = sum(len(b) for b in orig.labels.values())
    check("对话链已合并 (%d 标签 < %d 语句)" % (len(s2p.labels), stmt_count),
          len(s2p.labels) < stmt_count
          and len(s2p.labels) <= len(orig.labels) + 30,
          "labels=%d" % len(s2p.labels))
    orig_dlg = sum(1 for body in orig.labels.values()
                   for st in body if st.op in DIALOGUE_OPS)
    new_dlg = sum(1 for body in s2p.labels.values()
                  for st in body if st.op in DIALOGUE_OPS)
    check("对话语句数等价", new_dlg == orig_dlg, "%d vs %d" % (new_dlg, orig_dlg))

    orig_choice_opts = sum(len(st.kwargs.get("options", []))
                           for body in orig.labels.values()
                           for st in body if st.op == "choice")
    new_choice_opts = sum(len(st.kwargs.get("options", []))
                          for body in s2p.labels.values()
                          for st in body if st.op == "choice")
    check("选择支选项数等价", new_choice_opts == orig_choice_opts,
          "%d vs %d" % (new_choice_opts, orig_choice_opts))

    # 动作语句保留 (bg/music/show/set 等, action 节点兜底)
    for op in ("bg", "music", "show", "set"):
        orig_n = sum(1 for body in orig.labels.values()
                     for st in body if st.op == op)
        new_n = sum(1 for body in s2p.labels.values()
                    for st in body if st.op == op)
        check("动作语句保留 (%s)" % op, new_n == orig_n,
              "%d vs %d" % (new_n, orig_n))

    # 幂等: 导入 -> 导出 -> 再导入, 节点结构稳定
    g_again = FlowGraph.from_script(s2p)
    counts = lambda gg: sorted(
        (n.kind, len(n.extra_stmts), len(n.options)) for n in gg.nodes.values())
    check("二次导入节点结构稳定", counts(g_again) == counts(g),
          "%s vs %s" % (counts(g_again), counts(g)))

    # 3. 新建图: 对话链 + 选择支 + 结局
    g2 = FlowGraph()
    a = g2.add_node("dialogue", data={"op": "say", "speaker": "主角",
                                      "text": "你好世界"})
    ch = g2.add_node("choice", options=[["喜欢", None], ["讨厌", None]])
    good = g2.add_node("ending", data={"name": "好结局"})
    bad = g2.add_node("ending", data={"name": "坏结局"})
    g2.connect(a.node_id, ch.node_id)
    g2.set_option(ch.node_id, 0, "喜欢", good.node_id)
    g2.set_option(ch.node_id, 1, "讨厌", bad.node_id)
    s3 = g2.to_script()
    p3 = parse(_render(s3), "story.gal")
    check("新建图标签数 (4)", len(p3.labels) == 4)
    dlg = next(iter(p3.labels.values()))[0]
    check("对话生成", dlg.op == "say" and dlg.args[0] == "主角"
          and dlg.args[1] == "你好世界")
    ch_stmt = [st for body in p3.labels.values()
               for st in body if st.op == "choice"][0]
    check("选择支选项目标", ch_stmt.kwargs["options"] ==
          [("喜欢", good.node_id), ("讨厌", bad.node_id)])
    endings = [st for body in p3.labels.values()
               for st in body if st.op == "ending"]
    check("结局生成 (2)", len(endings) == 2)

    # 3.5 场景节点 (stage): bg + show/hide 结构化导入导出
    stage_src = (
        "s1:\n"
        "    bg school morning with fade\n"
        "    show producer normal with slide_right\n"
        "    hide producer with slide_left\n"
        "    text \"你好\"\n"
        "    clear\n"
    )
    gs = FlowGraph.from_script(parse(stage_src, "story.gal"))
    stages = [n for n in gs.nodes.values() if n.kind == "stage"]
    check("bg 转 stage 节点", len(stages) == 1,
          "got %d" % len(stages))
    if stages:
        st = stages[0]
        check("stage 背景解析", st.data["bg"] == ["school", "morning", "fade"],
              "got %r" % st.data["bg"])
        sprites = st.data["sprites"]
        check("show/hide 并入 sprites", len(sprites) == 2,
              "got %r" % sprites)
        if len(sprites) >= 2:
            check("show 解析", sprites[0] ==
                  ["show", "producer", "normal", "slide_right"])
            check("hide 解析", sprites[1] ==
                  ["hide", "producer", "", "slide_left"])
        check("对话不并入 stage (另建节点)",
              any(n.kind == "dialogue" for n in gs.nodes.values()))
        # 导出等价
        sp = parse(_render(gs.to_script()), "story.gal")
        ops = [st2.op for body in sp.labels.values() for st2 in body]
        check("导出 bg/show/hide/clear 齐全",
              ops.count("bg") == 1 and ops.count("show") == 1
              and ops.count("hide") == 1 and ops.count("clear") == 1,
              "ops=%s" % ops)
        bg_stmt = [st2 for body in sp.labels.values()
                   for st2 in body if st2.op == "bg"][0]
        check("导出 bg 参数", bg_stmt.args ==
              ["school", "morning", "with", "fade"], "args=%s" % bg_stmt.args)
        # 幂等: 二次导入 stage 结构一致
        gs2 = FlowGraph.from_script(sp)
        st2n = [n for n in gs2.nodes.values() if n.kind == "stage"]
        check("stage 二次导入稳定", len(st2n) == 1
              and st2n[0].data["bg"] == ["school", "morning", "fade"]
              and len(st2n[0].data["sprites"]) == 2)

    # 3.6 立绘排布 (move 语句并入 stage moves)
    move_src = (
        "s1:\n"
        "    bg school\n"
        "    show producer normal\n"
        "    move producer to 400,300 0\n"
        "    move producer to 800,500 1 ease in_out\n"
    )
    gm = FlowGraph.from_script(parse(move_src, "story.gal"))
    sm = [n for n in gm.nodes.values() if n.kind == "stage"]
    check("move 并入 stage", len(sm) == 1 and len(sm[0].data.get("moves", [])) == 2,
          "got %r" % (sm[0].data if sm else None))
    if sm:
        moves = sm[0].data["moves"]
        check("move 解析 1", moves[0][:4] == ["producer", "400,300", "0", ""],
              "got %r" % moves[0])
        check("move 解析 2 (ease)", moves[1][:5] ==
              ["producer", "800,500", "1", "", "in_out"], "got %r" % moves[1])
        # 导出等价
        mp = parse(_render(gm.to_script()), "story.gal")
        moves_out = [st for body in mp.labels.values()
                     for st in body if st.op == "move"]
        check("导出 move 语句", len(moves_out) == 2
              and moves_out[0].args[:3] == ["producer", "to", "400,300"])
        # 幂等
        gm2 = FlowGraph.from_script(mp)
        sm2 = [n for n in gm2.nodes.values() if n.kind == "stage"]
        check("move 二次导入稳定",
              sm2 and len(sm2[0].data.get("moves", [])) == 2)

    # 3.7 音频轨 (music/sfx/volume 并入 stage audio)
    audio_src = (
        "s1:\n"
        "    bg school\n"
        "    music bgm_piano41 loop 1 fade 1.0\n"
        "    sfx sfx_boom\n"
        "    volume music 0.5\n"
        "    volume voice producer 0.8\n"
        "    pause music fade 0.8\n"
    )
    ga = FlowGraph.from_script(parse(audio_src, "story.gal"))
    sa = [n for n in ga.nodes.values() if n.kind == "stage"]
    check("音频并入 stage", len(sa) == 1
          and len(sa[0].data.get("audio", [])) == 5,
          "got %r" % (sa[0].data if sa else None))
    if sa:
        aud = sa[0].data["audio"]
        check("music 解析", aud[0][:4] == ["music", "bgm_piano41", "1", "1.0"],
              "got %r" % aud[0])
        check("sfx 解析", aud[1][:2] == ["sfx", "sfx_boom"])
        check("volume music 解析", aud[2][:4] == ["volume", "music", "", "0.5"])
        check("volume voice 角色 解析", aud[3][:4] ==
              ["volume", "voice", "producer", "0.8"])
        check("pause 解析", aud[4][:4] == ["pause", "music", "", "0.8"])
        # 导出等价
        ap = parse(_render(ga.to_script()), "story.gal")
        ops = [st for body in ap.labels.values()
               for st in body if st.op in ("music", "sfx", "volume",
                                           "pause", "resume", "stop")]
        check("导出音频语句 5 条", len(ops) == 5)
        music = next(st for st in ops if st.op == "music")
        # loop=1 为默认值, 导出时省略 (语义等价)
        check("导出 music 参数", music.args ==
              ["bgm_piano41", "fade", "1.0"],
              "got %s" % music.args)
        vv = next(st for st in ops if st.op == "volume"
                  and st.args[0] == "voice")
        check("导出 volume voice 角色", vv.args ==
              ["voice", "producer", "0.8"])
        # 幂等
        ga2 = FlowGraph.from_script(ap)
        sa2 = [n for n in ga2.nodes.values() if n.kind == "stage"]
        check("audio 二次导入稳定",
              sa2 and len(sa2[0].data.get("audio", [])) == 5)

    # 4. 删除节点清理引用
    g3 = FlowGraph.from_script(orig)
    victim = next(nid for nid, n in g3.nodes.items() if n.kind == "choice")
    refs_before = sum(1 for n in g3.nodes.values()
                      for _t, tg in n.options if tg == victim)
    g3.remove_node(victim)
    refs_after = sum(1 for n in g3.nodes.values()
                     for _t, tg in n.options if tg == victim)
    check("删除清理引用", victim not in g3.nodes and refs_after == 0,
          "%d -> %d" % (refs_before, refs_after))

    # 5. 自动布局
    g.auto_layout()
    coords = [(n.x, n.y) for n in g.nodes.values()]
    check("自动布局坐标有限", all(isinstance(x, (int, float))
                                and isinstance(y, (int, float))
                                for x, y in coords))

    print()
    if FAILURES:
        print("结果: %d 项失败 -> %s" % (len(FAILURES), FAILURES))
        return 1
    print("结果: 全部通过 ✓")
    return 0


def _render(script) -> str:
    """临时渲染: 标签 + 语句文本 (测试解析用)。"""
    from editor.serializer import serialize
    return serialize(script)


def _body_to_text(body) -> str:
    return " / ".join("%s %s" % (st.op, st.args) for st in body)


if __name__ == "__main__":
    os._exit(main())
