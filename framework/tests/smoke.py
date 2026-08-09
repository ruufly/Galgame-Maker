"""冒烟测试: 在无窗口环境 (SDL dummy 驱动) 下验证引擎核心逻辑。

运行::

    py -3.10 framework/tests/smoke.py

覆盖:
    1. 解析器: demo.gal 结构 (标签 / choice / weight 块 / if 块)
    2. 运行时: 变量 / 条件分支 / jump / call+return
    3. 阻塞推进: text -> 点击 -> choice -> 跳转
    4. 插件加载与自定义指令
    5. 存档快照与恢复
"""

import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from framework.engine.parser import parse  # noqa: E402
from framework.engine import log  # noqa: E402
from framework import GameEngine  # noqa: E402

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [OK] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name} {detail}")


def test_parser():
    print("== 解析器 ==")
    script_path = os.path.join(_ROOT, "test", "engine_demo", "demo.gal")
    with open(script_path, "r", encoding="utf-8") as f:
        text = f.read()
    script = parse(text, script_path)
    check("标签数量 == 5", len(script.labels) == 5, str(list(script.labels)))
    check("存在 start 标签", "start" in script.labels)
    check("存在 like_it 标签", "like_it" in script.labels)
    start = script.labels["start"]
    ops = [s.op for s in start]
    check("start 块含 weight 创建", "weight" in ops)
    check("start 块含 choice", "choice" in ops)
    choice = next(s for s in start if s.op == "choice")
    check("choice 有 3 个选项", len(choice.kwargs["options"]) == 3,
          str(choice.kwargs))
    after = script.labels["after_choice"]
    check("after_choice 含 if 块", any(s.op == "if" for s in after))

    def stmts_contain(ss, needle):
        for s in ss:
            if needle in s.raw:
                return True
            for cond, body in s.kwargs.get("branches", []):
                if stmts_contain(body, needle):
                    return True
            if stmts_contain(s.kwargs.get("else") or [], needle):
                return True
        return False

    check("after_choice 含变量插值 text", stmts_contain(after, "$love"))

    # 未知指令在解析层不报错
    s2 = parse("start:\n    hello world\n    text \"ok\"\n")
    check("未知指令可解析", s2.labels["start"][0].op == "hello")
    return script_path


def test_runtime_logic():
    print("== 运行时逻辑 ==")
    engine = GameEngine(640, 360, "test")
    rt = engine.runtime

    # 变量 / if / jump / call+return
    src = """
start:
    set x = 1
    set y = x + 4
    if y > 4:
        set branch = "big"
    else:
        set branch = "small"
    endif
    jump mid
mid:
    call sub
    set after_call = 1
    text "done"
sub:
    set called = "yes"
    return
    text "never"
"""
    engine.script_dir = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(engine.script_dir, "_logic_test.gal")
    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    rt.load_script(path)
    rt.start()
    check("变量 x=1", rt.vars.get("x") == 1)
    check("变量 y=5 (算术)", rt.vars.get("y") == 5)
    check("if 分支 branch=big", rt.vars.get("branch") == "big")
    check("call 进入 sub 并返回", rt.vars.get("called") == "yes")
    check("call 后语句执行", rt.vars.get("after_call") == 1)
    check("text 阻塞", rt.blocked == "text")
    check("jump 后当前标签 mid", rt.current_label == "mid")

    # 变量插值
    check("插值 $x", rt._interp("value=$x") == "value=1")
    check("插值 $$ 转义", rt._interp("a$$b") == "a$b")

    # 条件求值
    check("evaluate 比较", rt.evaluate("y >= 5 and x == 1") is True)
    check("evaluate 字符串", rt.evaluate("'a' == 'a'") is True)

    # 未知指令警告但继续
    src2 = "start:\n    unknown_cmd foo\n    set ok = 1\n"
    path2 = os.path.join(engine.script_dir, "_unknown_test.gal")
    with open(path2, "w", encoding="utf-8") as f:
        f.write(src2)
    rt2 = engine.runtime  # 复用同一个 runtime 需要重新 load
    rt2.load_script(path2)
    rt2.start()
    check("未知指令后继续执行", rt2.vars.get("ok") == 1)
    engine.quit()
    import pygame
    pygame.quit()


def test_interaction():
    print("== 交互推进 ==")
    engine = GameEngine(640, 360, "test2")
    d = engine.display
    rt = engine.runtime

    # text -> 点击推进
    rt.vars.clear()
    src = """
start:
    text "第一句"
    text "第二句"
    choice:
        "去 A" -> label_a
        "去 B" -> label_b
label_a:
    text "A 结局"
label_b:
    text "B 结局"
"""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_inter_test.gal")
    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    rt.load_script(path)
    rt.start()
    check("text 阻塞在第一句", rt.blocked == "text" and d.full_text == "第一句")

    engine.on_click((320, 180))          # 第一次点击: 完成打字
    check("点击完成打字", d.text_done() is True)
    engine.on_click((320, 180))          # 第二次点击: 推进
    check("推进后第二句", d.full_text == "第二句")

    engine.on_click((320, 180))          # 完成打字
    engine.on_click((320, 180))          # 推进 -> choice
    check("choice 激活", d.choice_active)
    check("choice 选项文本", d.choices[0][0] == "去 A")

    engine.on_click(d.choice_rects[0].center)
    check("选择后跳转 label_a", rt.current_label == "label_a")
    check("选择后 text 阻塞", rt.blocked == "text" and d.full_text == "A 结局")

    # 打字机未完成时点击 = 立即完成
    d.text_active = True
    d.full_text = "很长的一段文字" * 20
    d.reveal = 3
    engine.on_click((320, 180))
    check("打字中点击 -> 完成打字", d.text_done() is True)
    engine.quit()
    import pygame
    pygame.quit()


def test_scene_flow():
    print("== 场景对象全链路 ==")
    engine = GameEngine(640, 360, "test4")
    d = engine.display
    rt = engine.runtime
    img_abs = os.path.join(_ROOT, "test", "engine_demo", "materials",
                           "image", "bg.png").replace("\\", "/")
    src = f'''
start:
    weight
        image: "{img_abs}"
        mode: full
        effect: fade
    -> bg1
    show bg1
    sprite girl
        image: "{img_abs}"
        pos: center
    show girl
    text "done"
'''
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_scene_test.gal")
    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    try:
        rt.load_script(path)
        rt.start()
        check("weight -> 绑定 -> show 后背景已设置", d.bg_surface is not None)
        check("sprite 创建并显示", "girl" in d.sprites and d.sprites["girl"].visible)
        check("text 正常阻塞", rt.blocked == "text" and d.full_text == "done")
    finally:
        engine.quit()
        import pygame
        pygame.quit()
        if os.path.isfile(path):
            os.remove(path)


def test_plugins_and_save():
    print("== 插件与存档 ==")
    engine = GameEngine(640, 360, "test3")
    loaded = engine.plugins.discover(os.path.join(_ROOT, "framework", "plugins"))
    check("插件自动发现", len(loaded) >= 2, str(loaded))
    check("shake 指令已注册", engine.commands.has("shake"))
    check("flash 指令已注册", engine.commands.has("flash"))

    # 自定义指令执行
    rt = engine.runtime
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_plug_test.gal")
    with open(path, "w", encoding="utf-8") as f:
        f.write("start:\n    shake 0.2 5\n    set ok = 1\n")
    rt.load_script(path)
    rt.start()
    check("shake 后继续执行", rt.vars.get("ok") == 1)
    check("shake 状态被设置", engine.display.shake_time > 0)

    # 存档/读档
    rt.vars["score"] = 42
    rt.current_label = "after_choice"
    rt.statements = rt.labels.get("start", [])
    rt.ip = 0
    engine.project_dir = os.path.dirname(os.path.abspath(__file__))
    engine.save_game(0, silent=True)
    snap = engine.save.load(0)
    check("存档写入", snap is not None and snap["vars"].get("score") == 42)
    rt.vars["score"] = 0
    engine.load_game(0)
    check("读档恢复变量", rt.vars.get("score") == 42)

    engine.quit()
    import pygame
    pygame.quit()
    # 清理临时文件
    for name in ["_logic_test.gal", "_unknown_test.gal", "_inter_test.gal",
                 "_plug_test.gal"]:
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), name)
        if os.path.isfile(p):
            os.remove(p)


def main():
    print(f"运行环境: Python {sys.version.split()[0]}")
    try:
        test_parser()
    except Exception as exc:
        print(f"  [ERROR] 解析器测试异常: {exc}")
        import traceback
        traceback.print_exc()
    try:
        test_runtime_logic()
    except Exception as exc:
        print(f"  [ERROR] 运行时测试异常: {exc}")
        import traceback
        traceback.print_exc()
    try:
        test_interaction()
    except Exception as exc:
        print(f"  [ERROR] 交互测试异常: {exc}")
        import traceback
        traceback.print_exc()
    try:
        test_plugins_and_save()
    except Exception as exc:
        print(f"  [ERROR] 插件/存档测试异常: {exc}")
        import traceback
        traceback.print_exc()
    try:
        test_scene_flow()
    except Exception as exc:
        print(f"  [ERROR] 场景测试异常: {exc}")
        import traceback
        traceback.print_exc()

    print(f"\n结果: {PASS} 通过, {FAIL} 失败")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
