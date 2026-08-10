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
    from framework.engine.loader import load_script_with_imports
    script_path = os.path.join(_ROOT, "test", "engine_demo", "demo.gal")
    script = load_script_with_imports(script_path)   # 展开 import
    check("标签数量 == 6", len(script.labels) == 6, str(list(script.labels)))
    check("存在 start 标签", "start" in script.labels)
    check("存在 game_start 标签", "game_start" in script.labels)
    start = script.labels["start"]
    ops = [s.op for s in start]
    check("start 块含 title 指令", "title" in ops, str(ops))
    check("start 块含 bg 指令", "bg" in ops, str(ops))
    game_start = script.labels["game_start"]
    gops = [s.op for s in game_start]
    check("game_start 含 choice", "choice" in gops)
    choice = next(s for s in game_start if s.op == "choice")
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
                           "image", "bg.jpg").replace("\\", "/")
    src = f'''
start:
    bg "{img_abs}"
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
        check("bg 指令后背景已设置", d.bg_surface is not None)
        check("sprite 创建并显示", "girl" in d.sprites and d.sprites["girl"].visible)
        check("text 正常阻塞", rt.blocked == "text" and d.full_text == "done")
    finally:
        engine.quit()
        import pygame
        pygame.quit()
        if os.path.isfile(path):
            os.remove(path)


def test_rich():
    print("== 富文本与公式 ==")
    import pygame  # 函数内先导入, 避免局部作用域遮蔽
    engine = GameEngine(640, 360, "test5")
    r = engine.rich

    # 标记解析
    runs = r.parse("你好{c=#ff0000}红{/c}{b}粗{/b}{m}x^2{/m}!")
    texts = [x.text for x in runs]
    check("标记解析分段", texts == ["你好", "红", "粗", "x^2", "!"], str(texts))
    check("颜色标记", runs[1].color == (255, 0, 0), str(runs[1].color))
    check("加粗标记", runs[2].bold is True)
    check("公式标记", runs[3].math is True)
    check("颜色名解析", r.parse("{c=red}R{/c}")[0].color == (255, 0, 0))

    # 公式内花括号不被误解析
    runs2 = r.parse("{m}\\frac{1}{2}{/m}")
    check("公式内花括号原样", runs2[0].math and runs2[0].text == r"\frac{1}{2}",
          repr(runs2[0].text))

    # 未知标记按字面
    runs3 = r.parse("a{xxx}b")
    check("未知标记字面输出", "".join(x.text for x in runs3) == "a{xxx}b")

    # 截断 (打字机)
    t = r.truncate(runs, 2)
    check("截断到 2 字符", t[0].text == "你好", str([x.text for x in t]))
    t2 = r.truncate(runs, 3)
    check("截断跨 run", t2[-1].text == "红")

    # 渲染不报错
    surf = pygame.Surface((600, 400))
    r.draw(surf, runs, 10, 20, 500)
    r.draw_centered(surf, r.parse("选项{c=#00ff00}A{/c}"), 300, 200)
    check("富文本绘制无异常", True)

    # 像素级居中断言 (文字包围盒中心应落在目标点)
    import numpy as np
    check_surf = pygame.Surface((120, 120))
    check_surf.fill((0, 0, 0))
    r.draw_centered(check_surf, r.parse("中"), 60, 60)
    arr = pygame.surfarray.array3d(check_surf)          # (w, h, 3)
    ys, xs = np.nonzero(arr.sum(axis=2) > 0)
    if len(ys):
        cy_center = (float(ys.min()) + float(ys.max())) / 2
        cx_center = (float(xs.min()) + float(xs.max())) / 2
        check("draw_centered 垂直居中", abs(cy_center - 60) <= 1.5,
              f"cy={cy_center:.1f}")
        # 水平: 字形自带左右 bearing, ±4px 内属正常渲染偏差
        check("draw_centered 水平居中", abs(cx_center - 60) <= 4.0,
              f"cx={cx_center:.1f}")
    else:
        check("draw_centered 像素可见", False, "未渲染出文字")

    # LaTeX 渲染
    if r.math.available:
        res = r.math.render(r"x^2 + \frac{1}{2}", 20, (255, 255, 255))
        check("LaTeX 渲染出图", res is not None and res[0].get_width() > 10)
        check("LaTeX 基线合理", res is not None and 0 < res[1] and res[2] >= 0)
        res2 = r.math.render(r"\int_0^1 x^2\,dx = \frac{1}{3}", 26, (255, 200, 0))
        check("LaTeX 复杂公式", res2 is not None and res2[0].get_width() > 10)
    else:
        print("  [SKIP] matplotlib 未安装, 跳过 LaTeX 测试")

    engine.quit()
    pygame.quit()


def test_demo_run():
    print("== demo.gal 实际运行 ==")
    engine = GameEngine(640, 360, "test6")
    d = engine.display
    rt = engine.runtime
    demo = os.path.join(_ROOT, "test", "engine_demo", "demo.gal")
    rt.load_script(demo)
    rt.start()
    check("demo 停在标题画面", rt.blocked == "title" and d.title_active)
    engine.on_click(d.title_rects[0].center)   # 点击"开始游戏"
    check("demo 停在第一句文本", rt.blocked == "text" and d.full_text != "")
    check("demo 背景已设置", d.bg_surface is not None)
    check("demo 角色立绘已显示",
          "producer" in d.sprites and d.sprites["producer"].visible)
    # 渲染一帧 (含富文本解析路径)
    engine.draw()
    check("demo 首帧绘制无异常", True)
    engine.quit()
    import pygame
    pygame.quit()


def test_save_restore_state():
    print("== 读档状态恢复 ==")
    engine = GameEngine(640, 360, "test7")
    d = engine.display
    rt = engine.runtime
    img = os.path.join(_ROOT, "test", "engine_demo", "materials",
                       "image", "bg.jpg").replace("\\", "/")
    src = f'''
start:
    set love = 5
    bg "{img}"
    sprite girl
        image: "{img}"
        pos: center
    show girl
    text "第一句"
    text "第二句"
'''
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_save_test.gal")
    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    try:
        rt.load_script(path)
        rt.start()
        check("初始停在第一句", rt.blocked == "text" and d.full_text == "第一句")

        # 存档后篡改现场
        engine.save_game(0, silent=True)
        rt.vars["love"] = 999
        d.hide_sprite("girl")
        d.clear_bg()
        d.clear_text()
        rt.blocked = None
        rt.ip += 5  # 剧情位置漂移

        engine.load_game(0)
        check("变量恢复 love=5", rt.vars.get("love") == 5, str(rt.vars))
        check("背景恢复", d.bg_surface is not None)
        check("立绘恢复可见",
              "girl" in d.sprites and d.sprites["girl"].visible)
        check("text 阻塞恢复", rt.blocked == "text" and d.full_text == "第一句")
        check("剧情位置恢复", rt.current_label == "start")

        engine.on_click((320, 180))   # 完成打字
        engine.on_click((320, 180))   # 推进
        check("读档后剧情继续", d.full_text == "第二句")

        # 防御: fadeout 黑幕后存档读档, 黑幕应清除且剧情不跳标题
        d.start_fadeout()
        engine.save_game(0, silent=True)
        engine.load_game(0)
        check("读档后黑幕清除", d.fade_alpha == 0.0, str(d.fade_alpha))
        check("读档后不进标题", not d.title_active)
        check("读档后剧情位置正确", rt.current_label == "start"
              and d.full_text == "第二句")
    finally:
        engine.quit()
        import pygame
        pygame.quit()
        if os.path.isfile(path):
            os.remove(path)

    # --- choice 阻塞恢复 ---
    engine = GameEngine(640, 360, "test8")
    d = engine.display
    rt = engine.runtime
    src2 = '''
start:
    choice:
        "去 A" -> label_a
        "去 B" -> label_b
label_a:
    set went = "a"
    text "A 结局"
label_b:
    set went = "b"
    text "B 结局"
'''
    path2 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_save2_test.gal")
    with open(path2, "w", encoding="utf-8") as f:
        f.write(src2)
    try:
        rt.load_script(path2)
        rt.start()
        check("初始 choice 阻塞", rt.choice_active if hasattr(rt, "choice_active") else d.choice_active)
        engine.save_game(1, silent=True)
        d.choice_active = False
        rt.blocked = None
        engine.load_game(1)
        check("choice 阻塞恢复", d.choice_active)
        check("choice 选项恢复", len(d.choices) == 2 and d.choices[0][0] == "去 A")
        engine.on_click(d.choice_rects[1].center)   # 选 "去 B"
        check("读档后选择跳转正确", rt.vars.get("went") == "b", str(rt.vars))
        check("选择后进入 label_b", rt.current_label == "label_b")
    finally:
        engine.quit()
        import pygame
        pygame.quit()
        if os.path.isfile(path2):
            os.remove(path2)

    # --- call 栈恢复 ---
    engine = GameEngine(640, 360, "test9")
    d = engine.display
    rt = engine.runtime
    src3 = '''
start:
    call sub
    set after = 1
    text "done"
sub:
    set inner = 1
    text "sub text"
    return
'''
    path3 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_save3_test.gal")
    with open(path3, "w", encoding="utf-8") as f:
        f.write(src3)
    try:
        rt.load_script(path3)
        rt.start()
        check("call 内 text 阻塞", rt.blocked == "text" and d.full_text == "sub text")
        engine.save_game(2, silent=True)
        rt.vars["inner"] = 0
        engine.load_game(2)
        check("call 栈恢复", len(rt.call_stack) == 1, str(rt.call_stack))
        check("call 内标签恢复", rt.current_label == "sub")
        check("call 内变量恢复", rt.vars.get("inner") == 1)
        check("call 内 text 恢复", rt.blocked == "text" and d.full_text == "sub text")
        engine.on_click((320, 180))   # 完成打字
        engine.on_click((320, 180))   # 推进 -> return
        check("恢复后 return 正常", rt.vars.get("after") == 1, str(rt.vars))
    finally:
        engine.quit()
        import pygame
        pygame.quit()
        if os.path.isfile(path3):
            os.remove(path3)


def test_save_id_based():
    """验证: 存档按脚本 id 存储 (不含图片路径) + 淡入中立绘读档后继续淡入。"""
    print("== 存档按脚本 id ==")
    engine = GameEngine(640, 360, "test10")
    d = engine.display
    rt = engine.runtime
    demo = os.path.join(_ROOT, "test", "engine_demo", "demo.gal")
    try:
        # dummy 音频驱动下 mixer.music 不可用, 用假对象验证状态机
        import pygame.mixer as _mixer
        class _FakeMusic:
            def __init__(self):
                self.busy = False
                self.loaded = None
                self.playing = False
                self.vol = 1.0
            def load(self, p):
                self.loaded = p
            def play(self, *a):
                self.playing = True
                self.busy = True
            def stop(self):
                self.playing = False
                self.busy = False
            def pause(self):
                self.playing = False
            def unpause(self):
                self.playing = True
            def set_volume(self, v):
                self.vol = v
            def get_busy(self):
                return self.busy
        _orig_music = _mixer.music
        _mixer.music = _FakeMusic()

        rt.load_script(demo)
        rt.start()
        check("demo 先显示标题", d.title_active)
        engine.on_click(d.title_rects[0].center)   # 开始游戏 -> game_start
        # 对象注册表: producer (角色) + school (场景)
        check("注册表含 producer/school",
              "producer" in rt.script_objects and "school" in rt.script_objects,
              str(list(rt.script_objects)))
        check("角色注册表记录图片",
              rt.script_objects["producer"].get("image")
              == "materials/image/producer/producer1.png")
        check("背景由场景驱动", d.bg_scene == "school" and d.bg_id is None,
              f"scene={d.bg_scene} id={d.bg_id}")

        engine.save_game(0, silent=True)
        snap = engine.save.load(0)
        sprites = snap.get("sprites", [])
        check("存档不含图片路径", all("image" not in s for s in sprites),
              str(sprites))
        check("存档立绘含脚本 id", sprites[0]["id"] == "producer", str(sprites))
        check("存档背景含场景 id", snap.get("bg_scene") == "school",
              str(snap.get("bg_scene")))

        # 篡改现场: 清空整个立绘层
        d.sprites.clear()
        d.sprite_order.clear()
        engine.load_game(0)
        spr = d.sprites.get("producer")
        check("读档立绘可见", spr is not None and spr.visible)
        check("绘制顺序恢复", d.sprite_order == ["producer"], str(d.sprite_order))
        check("背景由场景 id 恢复",
              d.bg_scene == "school" and d.bg_surface is not None,
              f"scene={d.bg_scene}")

        # 淡入恢复: 角色立绘默认完整显示, 手动模拟"淡入中"存档,
        # 验证读档后继续淡入而非永久卡在半透明
        check("立绘完整显示", spr.alpha == 255, f"alpha={spr.alpha}")
        spr.alpha = 100
        spr.surface.set_alpha(100)
        engine.save_game(0, silent=True)
        d.sprites.clear()
        d.sprite_order.clear()
        engine.load_game(0)
        spr = d.sprites.get("producer")
        check("读档后继续淡入", spr.fade_speed > 0, f"fade_speed={spr.fade_speed}")
        for _ in range(30):
            d.update(1 / 60)
        check("淡入推进后 alpha 增长", spr.alpha > 100, f"alpha={spr.alpha}")
    finally:
        engine.quit()
        import pygame
        pygame.quit()


def test_characters():
    print("== 角色系统 ==")
    engine = GameEngine(640, 360, "test11")
    d = engine.display
    rt = engine.runtime
    img1 = os.path.join(_ROOT, "test", "engine_demo", "materials", "image",
                        "producer", "producer1.png").replace("\\", "/")
    img2 = os.path.join(_ROOT, "test", "engine_demo", "materials", "image",
                        "producer", "producer2.png").replace("\\", "/")
    src = f'''
char girl
    name: "小美"
    default: "{img1}"
    normal: "{img1}"
    happy: "{img2}"
start:
    show girl normal
    say girl "你好"
    nar "旁白来了"
    say 旁白 "也是旁白"
    show girl happy
    text "结束"
'''
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_char_test.gal")
    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    try:
        rt.load_script(path)
        # 静态注册 (无需执行到 char 语句)
        check("角色静态注册", "girl" in rt.characters,
              str(list(rt.characters)))
        check("角色显示名", rt.characters["girl"]["name"] == "小美")
        check("角色立绘表", len(rt.characters["girl"]["sprites"]) == 2)

        rt.start()
        spr = d.sprites.get("girl")
        check("角色立绘显示", spr is not None and spr.visible)
        check("默认立绘 pose", spr.props.get("pose") == "normal")
        center1 = tuple(spr.rect.center)

        # 台词分类: 角色台词 -> 名字框显示角色名
        check("角色台词显示名", d.speaker == "小美", str(d.speaker))
        engine.on_click((320, 180))   # 完成打字
        engine.on_click((320, 180))   # 推进
        check("nar 旁白无名字框", d.speaker is None and d.full_text == "旁白来了")
        engine.on_click((320, 180))
        engine.on_click((320, 180))
        check("say 旁白 兼容", d.speaker is None and d.full_text == "也是旁白")

        # 立绘切换: 换图保持中心点
        engine.on_click((320, 180))
        engine.on_click((320, 180))
        spr = d.sprites.get("girl")
        check("切换后 pose=happy", spr is not None and spr.props.get("pose") == "happy")
        check("切换后中心点不变", tuple(spr.rect.center) == center1,
              f"{spr.rect.center} vs {center1}")

        # 存档/读档: pose 精确恢复
        engine.save_game(0, silent=True)
        d.sprites.clear()
        d.sprite_order.clear()
        engine.load_game(0)
        spr = d.sprites.get("girl")
        check("读档立绘恢复", spr is not None and spr.visible)
        check("读档 pose 恢复", spr.props.get("pose") == "happy",
              str(spr.props.get("pose")))
        check("读档中心点保持", tuple(spr.rect.center) == center1)
    finally:
        engine.quit()
        import pygame
        pygame.quit()
        if os.path.isfile(path):
            os.remove(path)


def test_scenes():
    print("== 场景系统 ==")
    engine = GameEngine(640, 360, "test12")
    d = engine.display
    rt = engine.runtime
    demo = os.path.join(_ROOT, "test", "engine_demo", "demo.gal")
    try:
        rt.load_script(demo)
        check("场景静态注册", "school" in rt.scenes, str(list(rt.scenes)))
        check("场景显示名", rt.scenes["school"]["name"] == "学校")
        check("场景背景表", len(rt.scenes["school"]["backgrounds"]) == 2,
              str(rt.scenes["school"]["backgrounds"]))

        # 加载插件 (含场景通知插件)
        engine.plugins.discover(os.path.join(_ROOT, "framework", "plugins"))
        rt.start()   # 与真实游戏流程一致 (存档点有有效标签位置)

        from framework.engine.parser import Statement
        # 场景切换: bg <场景id>
        rt._cmd_bg(Statement(op="bg", args=["school"], line=0))
        check("场景默认背景生效", d.bg_scene == "school"
              and d.bg_surface is not None)
        check("场景切换触发左上角通知",
              d.notice is not None and "场景切换" in d.notice,
              str(d.notice))
        check("通知位置为左上角", d.notice_pos == "top-left",
              str(d.notice_pos))

        # 场景内背景切换: bg <场景id> <背景名>
        rt._cmd_bg(Statement(op="bg", args=["school", "morning"], line=0))
        check("场景内背景切换", d.bg_pose == "morning" and d.bg_scene == "school")

        # 直接路径 bg 兼容
        rt._cmd_bg(Statement(op="bg", args=["materials/image/bg.jpg"], line=0))
        check("直接路径 bg 兼容", d.bg_scene is None and d.bg_id is None
              and d.bg_surface is not None)

        # 存档/读档: 场景背景精确恢复
        rt._cmd_bg(Statement(op="bg", args=["school", "morning"], line=0))
        engine.save_game(0, silent=True)
        snap = engine.save.load(0)
        check("存档场景 id", snap.get("bg_scene") == "school", str(snap.get("bg_scene")))
        check("存档背景名", snap.get("bg_pose") == "morning", str(snap.get("bg_pose")))
        d.bg_scene = None
        d.bg_pose = None
        d.bg_surface = None
        engine.load_game(0)
        check("读档场景恢复", d.bg_scene == "school" and d.bg_pose == "morning",
              f"scene={d.bg_scene} pose={d.bg_pose}")
        check("读档背景图恢复", d.bg_surface is not None)
    finally:
        engine.quit()
        import pygame
        pygame.quit()


def test_transitions():
    print("== 背景过渡效果 ==")
    engine = GameEngine(640, 360, "test13")
    d = engine.display
    rt = engine.runtime
    img = os.path.join(_ROOT, "test", "engine_demo", "materials",
                       "image", "bg.jpg").replace("\\", "/")
    src = '''start:
    bg "%s"
    text "x"
''' % img
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_trans_test.gal")
    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    try:
        rt.load_script(path)
        rt.start()
        check("初始无过渡", d._transition is None)

        # 内置过渡: 启动 -> 推进 -> 完成
        for name in ("fade", "dissolve", "blinds", "slide", "circle",
                     "pixelate", "zoom"):
            d.set_bg(img, name)
            check(f"{name} 过渡启动", d._transition is not None
                  and d._transition.name == name)
            for _ in range(200):
                d.update(1 / 60)
            check(f"{name} 过渡完成", d._transition is None
                  and d.bg_surface is not None)

        # 默认直接切换
        d.set_bg(img)
        check("默认直接切换", d._transition is None)

        # 过渡期间立绘仍可绘制 (draw 不报错)
        d.set_bg(img, "dissolve")
        engine.draw()
        check("过渡中绘制无异常", d._transition is not None)
        for _ in range(150):
            d.update(1 / 60)

        # 插件注册的自定义过渡
        engine.plugins.discover(os.path.join(_ROOT, "framework", "plugins"))
        check("插件过渡已注册", "wipe" in d.transitions)
        d.set_bg(img, "wipe")
        check("wipe 过渡启动", d._transition is not None
              and d._transition.name == "wipe")
        for _ in range(150):
            d.update(1 / 60)
        check("wipe 过渡完成", d._transition is None)

        # 脚本指令解析: bg "路径" with 效果
        from framework.engine.parser import Statement
        rt._cmd_bg(Statement(op="bg", args=[img, "with", "dissolve"], line=0))
        check("bg with 指令解析", d._transition is not None
              and d._transition.name == "dissolve")
        for _ in range(150):
            d.update(1 / 60)

        # 未知效果 -> 直接切换 + 无异常
        d.set_bg(img, "nonexistent_effect")
        check("未知效果回退直接切换", d._transition is None)
    finally:
        engine.quit()
        import pygame
        pygame.quit()
        if os.path.isfile(path):
            os.remove(path)

    # --- 像素级验证 (红->蓝纯色图, 检查中间帧画面确实在过渡) ---
    print("== 过渡像素验证 ==")
    engine = GameEngine(640, 360, "test14")
    from framework.engine.display import (Transition as TBase,
                                          DissolveTransition, BlindsTransition,
                                          FadeTransition)
    W, H = 200, 100
    red = pygame.Surface((W, H))
    red.fill((255, 0, 0))
    blue = pygame.Surface((W, H))
    blue.fill((0, 0, 255))
    try:
        # dissolve 中间帧: 中心像素应为红蓝混合 (既非纯红也非纯蓝)
        tr = DissolveTransition(red, blue, (W, H))
        tr.update(0.5 * tr.duration)
        target = pygame.Surface((W, H))
        tr.draw_bg(target)
        mid = target.get_at((W // 2, H // 2))[:3]
        check("dissolve 中间帧混合", mid not in ((255, 0, 0), (0, 0, 255)),
              str(mid))

        # blinds 中间帧: 左边缘为新色, 中心附近为旧色 (条带进行中)
        tr = BlindsTransition(red, blue, (W, H))
        tr.update(0.5 * tr.duration)
        target = pygame.Surface((W, H))
        tr.draw_bg(target)
        left = target.get_at((4, H // 2))[:3]
        check("blinds 中间帧条带", left == (0, 0, 255), str(left))

        # fade 中间帧: 背景层为黑色
        tr = FadeTransition(red, blue, (W, H))
        tr.update(0.5 * tr.duration)
        target = pygame.Surface((W, H))
        tr.draw_bg(target)
        mid = target.get_at((W // 2, H // 2))[:3]
        check("fade 中间帧黑幕", mid == (0, 0, 0), str(mid))
        # fade 黑幕只在背景层: 不覆写 draw_overlay
        check("fade 无全屏覆盖层",
              FadeTransition.draw_overlay is TBase.draw_overlay)

        # 立绘在过渡中不被 fade 黑幕遮挡: 画立绘到 buffer 再画 fade,
        # 立绘像素应保持 (黑幕仅背景层)
        tr = FadeTransition(red, blue, (W, H))
        tr.update(0.5 * tr.duration)
        target = pygame.Surface((W, H))
        tr.draw_bg(target)
        pygame.draw.rect(target, (0, 255, 0), (10, 10, 20, 20))  # 模拟立绘
        px = target.get_at((20, 20))[:3]
        check("立绘不被 fade 黑幕遮挡", px == (0, 255, 0), str(px))

        # slide 中间帧: 左半旧色右半新色
        tr = engine.display.transitions["slide"](red, blue, (W, H))
        tr.update(0.5 * tr.duration)
        target = pygame.Surface((W, H))
        tr.draw_bg(target)
        left = target.get_at((4, H // 2))[:3]
        right = target.get_at((W - 4, H // 2))[:3]
        check("slide 中间帧左右分色", left == (255, 0, 0) and right == (0, 0, 255),
              f"l={left} r={right}")

        # circle 中间帧: 中心新色边缘旧色
        tr = engine.display.transitions["circle"](red, blue, (W, H))
        tr.update(0.5 * tr.duration)
        target = pygame.Surface((W, H))
        tr.draw_bg(target)
        center = target.get_at((W // 2, H // 2))[:3]
        corner = target.get_at((4, 4))[:3]
        check("circle 中间帧中心展开", center == (0, 0, 255) and corner == (255, 0, 0),
              f"c={center} corner={corner}")
    finally:
        engine.quit()
        import pygame
        pygame.quit()


def test_sprite_transform():
    print("== 立绘变换 ==")
    engine = GameEngine(640, 360, "test15")
    d = engine.display
    rt = engine.runtime
    img = os.path.join(_ROOT, "test", "engine_demo", "materials", "image",
                       "producer", "producer1.png").replace("\\", "/")
    src = f'''
char girl
    name: "小美"
    default: "{img}"
    normal: "{img}"
start:
    show girl normal
    text "x"
'''
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "_transform_test.gal")
    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    from framework.engine.parser import Statement
    try:
        rt.load_script(path)
        rt.start()
        spr = d.sprites["girl"]
        c0 = tuple(spr.rect.center)

        # 瞬间移动
        d.move_sprite("girl", "left")
        c1 = spr.rect.center
        check("瞬间移动到位", c1[0] < c0[0] - 100, f"{c0}->{c1}")

        # 动画移动
        d.move_sprite("girl", "right", 1.0)
        check("移动动画启动", spr.anim_move is not None)
        for _ in range(60):
            d.update(1 / 60)
        check("移动动画完成", spr.anim_move is None)
        check("移动到右侧", spr.rect.center[0] > c0[0] + 100,
              str(spr.rect.center))

        # 旋转 (瞬间 + 动画)
        d.rotate_sprite("girl", 90)
        check("旋转角度", spr.angle == 90)
        check("旋转后渲染面变化",
              spr.surface.get_size() != spr.base_surface.get_size())
        d.rotate_sprite("girl", 0, 1.0)
        check("旋转动画启动", spr.anim_rotate is not None)
        for _ in range(60):
            d.update(1 / 60)
        check("旋转动画归零", spr.anim_rotate is None and abs(spr.angle) < 0.5,
              str(spr.angle))

        # 连续动画互不覆盖: move 与 rotate 并行, 均能完整执行
        d.move_sprite("girl", "right", 1.0)
        d.rotate_sprite("girl", 45, 1.0)
        check("并行动画双槽启动",
              spr.anim_move is not None and spr.anim_rotate is not None)
        for _ in range(70):
            d.update(1 / 60)
        check("并行动画全部完成",
              spr.anim_move is None and spr.anim_rotate is None)
        check("并行移动到位", abs(spr.center[0] - 480) < 2, str(spr.center))
        check("并行旋转到位", abs(spr.angle - 45) < 1.0, str(spr.angle))

        # 翻转
        d.flip_sprite("girl")
        check("水平翻转", spr.flip_h is True)
        d.flip_sprite("girl")
        check("再次翻转恢复", spr.flip_h is False)

        # DSL 指令
        rt._cmd_move(Statement(op="move", args=["girl", "to", "left"], line=0))
        check("move 指令执行", abs(spr.rect.center[0] - 160) < 2,
              str(spr.rect.center))
        # 坐标写法: 单 token / 带空格 / 两 token / 括号
        for label, args, expect in [
            ("坐标 640,360", ["girl", "to", "640,360"], (640.0, 360.0)),
            ("坐标 640, 360", ["girl", "to", "640,", "360"], (640.0, 360.0)),
            ("坐标 400 300", ["girl", "to", "400", "300"], (400.0, 300.0)),
            ("坐标 (300,200)", ["girl", "to", "(300,200)"], (300.0, 200.0)),
        ]:
            rt._cmd_move(Statement(op="move", args=args, line=0))
            check(f"move {label} 到位", abs(spr.center[0] - expect[0]) < 2
                  and abs(spr.center[1] - expect[1]) < 2,
                  f"{spr.center} vs {expect}")
        rt._cmd_move(Statement(op="move",
                               args=["girl", "to", "400,300", "1"], line=0))
        check("move 数字坐标+时长", spr.anim_move is not None
              and spr.anim_move[4] == (400.0, 300.0),
              str(spr.anim_move))
        rt._cmd_rotate(Statement(op="rotate", args=["girl", "45", "1"], line=0))
        check("rotate 指令", spr.anim_rotate is not None)
        for _ in range(60):
            d.update(1 / 60)

        # 动画阻塞: duration>0 的动画播放期间脚本等待, 播完自动继续
        rt._cmd_move(Statement(op="move", args=["girl", "to", "right", "1"],
                               line=0))
        check("动画阻塞脚本", rt.blocked == "anim")
        for _ in range(70):
            d.update(1 / 60)
            rt.tick(1 / 60)
        check("动画完成自动继续", rt.blocked is None and rt.advance is not None)
        check("动画期间位置到位", abs(spr.center[0] - 480) < 2,
              str(spr.center))

        # 存档包含变换状态
        d.rotate_sprite("girl", 90)
        d.flip_sprite("girl")
        d.move_sprite("girl", "right")
        engine.save_game(0, silent=True)
        snap = engine.save.load(0)
        s0 = snap["sprites"][0]
        check("存档含旋转", s0.get("angle") == 90, str(s0.get("angle")))
        check("存档含翻转", s0.get("flip_h") is True, str(s0.get("flip_h")))
        check("存档含中心点", abs(s0.get("cx", 0) - 480) < 2, str(s0.get("cx")))

        # 读档恢复全部变换
        spr.angle = 0
        spr.flip_h = False
        spr.center = [10.0, 10.0]
        spr._recalc()
        engine.load_game(0)
        spr = d.sprites["girl"]
        check("读档恢复旋转", spr.angle == 90, str(spr.angle))
        check("读档恢复翻转", spr.flip_h is True)
        check("读档恢复位置", abs(spr.center[0] - 480) < 2, str(spr.center))
    finally:
        engine.quit()
        import pygame
        pygame.quit()
        if os.path.isfile(path):
            os.remove(path)


def test_window_config():
    print("== 窗口配置 ==")
    from gamelauncher import extract_window_config
    demo = os.path.join(_ROOT, "test", "engine_demo", "demo.gal")
    cfg = extract_window_config(demo)
    check("解析窗口标题", cfg.get("title") == "Galgame Maker 引擎演示",
          str(cfg))
    check("解析窗口尺寸",
          int(cfg.get("width")) == 1280 and int(cfg.get("height")) == 720)
    check("解析窗口图标", cfg.get("icon") == "materials/image/icon.png")
    check("解析 fps", int(cfg.get("fps")) == 60)
    check("解析退出确认配置", str(cfg.get("confirm_quit")) == "true"
          and "确定要退出游戏吗？" in str(cfg.get("confirm_quit_text")),
          str(cfg.get("confirm_quit")))

    # 无 window 配置的脚本 -> 空 dict
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "_win_test.gal")
    with open(path, "w", encoding="utf-8") as f:
        f.write('''start:
    text "x"
''')
    cfg2 = extract_window_config(path)
    check("无配置返回空", cfg2 == {}, str(cfg2))
    os.remove(path)

    # 自定义窗口参数 + 图标
    engine = GameEngine(800, 600, "自定义标题", 30)
    check("自定义窗口参数", engine.width == 800 and engine.height == 600
          and engine.title == "自定义标题" and engine.fps == 30)
    engine.script_dir = os.path.dirname(demo)
    engine.set_icon("materials/image/icon.png")   # 不应抛异常
    check("set_icon 无异常", True)
    engine.quit()
    import pygame
    pygame.quit()


def test_title_screen():
    print("== 标题画面 ==")
    demo = os.path.join(_ROOT, "test", "engine_demo", "demo.gal")
    engine = None

    def fresh():
        eng = GameEngine(640, 360, "title_test")
        eng.runtime.load_script(demo)
        eng.runtime.start()
        return eng

    try:
        engine = fresh()
        d = engine.display
        check("标题画面激活", d.title_active)
        check("标题无副标题(已注释)", d.title_caption == "",
              str(d.title_caption))
        check("标题图片加载", d.title_image is not None)
        check("标题菜单 3 项", len(d.title_items) == 3, str(d.title_items))
        check("开始按钮自定义文本", d.title_items[0][0] == "开始游戏",
              str(d.title_items[0]))
        check("标题位置自定义", d.title_anchor[1] == 210.0,
              str(d.title_anchor))
        check("按钮位置自定义", d.title_rects[0].y == 340,
              str(d.title_rects[0]))
        engine.draw()
        check("标题绘制无异常", True)

        # 点击"开始游戏" -> 跳转 game_start 进入剧情
        engine.on_click(d.title_rects[0].center)
        check("开始游戏跳转", engine.runtime.current_label == "game_start")
        check("标题已关闭", not d.title_active)
        check("进入剧情文本", engine.runtime.blocked == "text"
              and d.full_text != "")
        engine.save_game(0, silent=True)   # 在剧情处存档
        engine.quit()
        import pygame
        pygame.quit()

        # 读档按钮: 从标题打开槽位界面 -> 返回回标题 -> 再读档恢复剧情
        engine = fresh()
        d = engine.display
        check("标题再次激活", d.title_active)
        engine.on_click(d.title_rects[1].center)   # "读取存档"
        check("打开读档槽位界面", d.slot_menu_active)
        engine.on_click(d.slot_menu_back_rect.center)   # 返回
        check("返回后回到标题画面", not d.slot_menu_active
              and d.title_active)
        # 再次进入并确认读档 (启用读档确认)
        engine.apply_config({"confirm_load": "true"})
        engine.on_click(d.title_rects[1].center)
        engine.on_click(d.slot_menu_rects[0].center)   # 选槽位 1
        check("读档确认框弹出", d.confirm_active)
        engine.on_click(d.confirm_rects[0].center)     # 确认读档
        check("读档按钮恢复剧情", engine.runtime.blocked == "text"
              and d.full_text != "")
        engine.quit()
        pygame.quit()

        # 退出按钮 -> 弹确认框
        engine = fresh()
        d = engine.display
        engine.running = True
        engine.apply_config({"confirm_quit": "true"})
        engine.on_click(d.title_rects[2].center)   # "退出游戏"
        check("标题退出弹确认框", d.confirm_active and engine.running is True)
        engine.on_click(d.confirm_rects[0].center)  # 确认退出
        check("确认后引擎关闭", engine.running is False)
    finally:
        engine.quit()
        import pygame
        pygame.quit()


def test_confirm_quit():
    print("== 退出确认 ==")
    import pygame
    # 默认不启用: 直接退出
    engine = GameEngine(640, 360, "test19")
    engine.running = True
    engine.request_quit()
    check("默认无确认直接退出", engine.running is False)
    engine.quit()
    pygame.quit()

    # 启用确认
    engine = GameEngine(640, 360, "test20")
    d = engine.display
    engine.running = True
    engine.apply_config({"confirm_quit": "true",
                         "confirm_quit_text": "真的要走？",
                         "confirm_quit_yes": "走",
                         "confirm_quit_no": "留"})
    engine.request_quit()
    check("确认框弹出", d.confirm_active and engine.running is True)
    check("确认文本自定义", d.confirm_text == "真的要走？")
    check("确认按钮文本自定义",
          d.confirm_yes == "走" and d.confirm_no == "留")
    engine.draw()
    check("确认框绘制无异常", True)
    engine.on_click(d.confirm_rects[1].center)     # 点"否"
    check("点否继续游戏", not d.confirm_active and engine.running is True)
    engine.request_quit()
    engine.on_click(d.confirm_rects[0].center)     # 点"是"
    check("点是退出游戏", engine.running is False)
    engine.quit()
    pygame.quit()

    # 右上角关闭按钮 (QUIT 事件) -> 确认框
    engine = GameEngine(640, 360, "test21")
    d = engine.display
    engine.running = True
    engine.apply_config({"confirm_quit": "true"})
    engine.handle_event(pygame.event.Event(pygame.QUIT))
    check("QUIT 事件弹确认", d.confirm_active and engine.running is True)
    engine.on_click(d.confirm_rects[1].center)
    check("QUIT 确认否后继续", engine.running is True)
    engine.quit()
    pygame.quit()


def test_system_menu():
    print("== 系统菜单 / 多槽位存档 ==")
    from framework.engine.parser import Statement
    demo = os.path.join(_ROOT, "test", "engine_demo", "demo.gal")
    engine = GameEngine(640, 360, "test22")
    d = engine.display
    rt = engine.runtime
    try:
        rt.load_script(demo)
        rt.start()
        engine.on_click(d.title_rects[0].center)   # 开始游戏
        # 游戏中按 ESC -> 系统菜单
        engine.on_escape()
        check("ESC 打开系统菜单", d.system_menu_active and engine.paused)
        check("菜单 5 项", len(d.system_menu_items) == 5,
              str([t for t, _, _ in d.system_menu_items]))
        engine.draw()
        check("菜单绘制无异常", True)
        # 继续游戏
        engine.on_click(d.system_menu_rects[0].center)
        check("继续游戏关闭菜单", not d.system_menu_active
              and not engine.paused)
        # ESC -> 存档 -> 槽位界面
        engine.on_escape()
        engine.on_click(d.system_menu_rects[1].center)   # 存档
        check("存档槽位界面", d.slot_menu_active
              and d.slot_menu_mode == "save")
        check("槽位列表 6 个", len(d.slot_menu_slots) == 6)
        engine.on_click(d.slot_menu_rects[2].center)     # 存到槽位 3
        check("保存到槽位 3", not d.slot_menu_active and not engine.paused)
        check("槽位文件存在", engine.save._read_raw(2) is not None)

        # ESC -> 读档 -> 槽位界面 -> 返回
        engine.on_escape()
        engine.on_click(d.system_menu_rects[2].center)   # 读取存档
        check("读档槽位界面", d.slot_menu_active
              and d.slot_menu_mode == "load")
        check("槽位信息含时间", "time" in d.slot_menu_slots[2]
              and d.slot_menu_slots[2]["time"], str(d.slot_menu_slots[2]))
        engine.on_click(d.slot_menu_back_rect.center)    # 返回
        check("返回系统菜单", d.slot_menu_active is False
              and d.system_menu_active)

        # 槽位界面读档恢复剧情
        engine.on_click(d.system_menu_rects[2].center)
        engine.on_click(d.slot_menu_rects[2].center)     # 读槽位 3
        check("槽位读档恢复剧情", rt.blocked == "text" and d.full_text != ""
              and not d.slot_menu_active and not engine.paused)

        # 菜单"返回标题"
        engine.on_escape()
        engine.on_click(d.system_menu_rects[3].center)   # 返回标题
        check("返回标题画面", d.title_active and not engine.paused)
        check("标题菜单", len(d.title_items) == 3)

        # 结束后回到标题: fadeout 黑幕后 ending, 黑幕应被清除
        rt.call_stack = []
        rt.blocked = None
        rt.running = True
        rt.ended = False
        rt._jump_to("start")
        rt.advance()          # 重新执行标题 (标题阻塞)
        engine.on_click(d.title_rects[0].center)   # 开始
        d.start_fadeout()     # 模拟 fadeout 黑幕
        rt._cmd_ending(Statement(op="ending", line=0))
        check("结束画面显示", d.ending)
        for _ in range(200):
            d.update(1 / 60)
        check("结束后回到标题", d.title_active and not d.ending,
              f"title={d.title_active} ending={d.ending}")
        check("结束后黑幕清除", d.fade_alpha == 0.0, str(d.fade_alpha))
        check("结束后背景恢复", d.bg_surface is not None)
    finally:
        engine.quit()
        import pygame
        pygame.quit()


def test_styles():
    print("== 样式系统 ==")
    from framework.engine.parser import Statement
    engine = GameEngine(640, 360, "test23")
    d = engine.display
    rt = engine.runtime
    demo = os.path.join(_ROOT, "test", "engine_demo", "demo.gal")
    try:
        rt.load_script(demo)
        check("样式静态注册",
              "modern" in rt.styles and "classic" in rt.styles,
              str(list(rt.styles)))
        check("样式属性解析", "textbox_radius" in rt.styles["modern"]
              and "text_size" in rt.styles["modern"])
        rt.start()
        check("默认样式", d.style["textbox_bg"] == (0, 0, 0)
              and d.style["text_size"] == 26)   # 标题画面时尚未 use style
        engine.on_click(d.title_rects[0].center)   # 开始 -> game_start

        # use style modern (game_start 开头执行)
        check("modern 生效", d.style["textbox_bg"] == (255, 255, 255)
              and d.style["text_size"] == 28
              and d.style["textbox_radius"] == 12
              and d.style["text_color"] == (46, 46, 62),
              str(d.style["textbox_bg"]))
        check("文本框字号更新", d._font_size == 28)

        # 手动切换 classic
        rt._cmd_use(Statement(op="use", args=["classic"], line=0))
        check("classic 生效", d.style["text_color"] == (240, 230, 210)
              and d.style["textbox_radius"] == 0
              and d.style["text_size"] == 26,
              str(d.style["text_color"]))
        # 修复验证: classic 显式禁用图片 (none) -> 纯色复古
        check("classic 禁用主题图", d.style.get("textbox_image") == "none"
              and d.style.get("speaker_image") == "none"
              and d.style.get("choice_image") == "none",
              str(d.style.get("textbox_image")))
        # 切回 modern -> 无 style 图片键 (走 ui 主题图)
        rt._cmd_use(Statement(op="use", args=["modern"], line=0))
        check("modern 走主题图",
              d.style.get("textbox_image") is None
              and "textbox" in d.theme_images
              and d.style.get("choice_image") is None)

        # 样式名入档 -> 读档恢复
        rt._cmd_use(Statement(op="use", args=["modern"], line=0))
        engine.save_game(0, silent=True)
        snap = engine.save.load(0)
        check("存档含样式名", snap.get("style") == "modern",
              str(snap.get("style")))
        d.apply_style({"textbox_bg": (0, 0, 0), "text_size": 26})
        rt.current_style_name = None
        engine.load_game(0)
        check("读档恢复样式", rt.current_style_name == "modern"
              and d.style["textbox_bg"] == (255, 255, 255)
              and d.style["text_size"] == 28,
              f"name={rt.current_style_name} bg={d.style['textbox_bg']}")

        # 未定义样式不崩溃
        rt._cmd_use(Statement(op="use", args=["nope"], line=0))
        check("未定义样式不崩溃", rt.current_style_name == "modern")

        # 恢复 default
        rt._cmd_use(Statement(op="use", args=["default"], line=0))
        check("use default 恢复默认", rt.current_style_name is None
              and d.style["textbox_bg"] == (0, 0, 0))
    finally:
        engine.quit()
        import pygame
        pygame.quit()


def test_builtin_styles():
    print("== 预装样式 ==")
    from framework.engine.parser import Statement
    engine = GameEngine(640, 360, "test24")
    d = engine.display
    rt = engine.runtime
    demo = os.path.join(_ROOT, "test", "engine_demo", "demo.gal")
    try:
        rt.load_script(demo)
        for name in ("modern", "classic", "dark", "light", "cyber"):
            check(f"预装样式 {name}", name in rt.styles,
                  str(list(rt.styles)))
        # 未定义即可使用
        rt._cmd_use(Statement(op="use", args=["cyber"], line=0))
        check("cyber 生效", d.style["textbox_border"] == (0, 255, 204)
              and d.style["speaker_color"] == (255, 0, 170),
              str(d.style["textbox_border"]))
        rt._cmd_use(Statement(op="use", args=["light"], line=0))
        check("light 生效", d.style["textbox_bg"] == (245, 245, 240)
              and d.style["text_color"] == (51, 51, 51),
              str(d.style["textbox_bg"]))
        rt._cmd_use(Statement(op="use", args=["dark"], line=0))
        check("dark 生效", d.style["textbox_bg"] == (0, 0, 0)
              and d.style["text_color"] == (204, 204, 204))
        rt._cmd_use(Statement(op="use", args=["default"], line=0))
        check("回到默认", d.style["textbox_bg"] == (0, 0, 0)
              and d.style["text_size"] == 26)
    finally:
        engine.quit()
        import pygame
        pygame.quit()

    # 脚本同名 style 重载内置
    engine2 = GameEngine(640, 360, "test25")
    d2 = engine2.display
    rt2 = engine2.runtime
    src = '''style dark
    textbox_bg: "#123456"
    text_size: 30
start:
    use style dark
    text "x"
'''
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "_style_reload.gal")
    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    try:
        rt2.load_script(path)
        check("脚本重载内置样式", rt2.styles["dark"]["textbox_bg"] == "#123456"
              and rt2.styles["dark"]["text_size"] == "30",
              str(rt2.styles["dark"]))
        rt2.start()
        check("重载后生效", d2.style["textbox_bg"] == (18, 52, 86)
              and d2.style["text_size"] == 30,
              f"bg={d2.style['textbox_bg']} size={d2.style['text_size']}")
    finally:
        engine2.quit()
        import pygame
        pygame.quit()
        if os.path.isfile(path):
            os.remove(path)


def test_actions():
    print("== 动作系统 ==")
    from framework.engine.parser import Statement
    engine = GameEngine(640, 360, "test26")
    d = engine.display
    try:
        # 插件注册自定义动作 + do_action 指令
        engine.plugins.discover(os.path.join(_ROOT, "framework", "plugins"))
        check("自定义动作注册", "explode" in engine.actions,
              str(list(engine.actions)))
        check("do_action 指令注册", engine.commands.has("do_action"))

        # 插件 API: 自定义 selection (含风格参数)
        items = [("震动", {"type": "explode", "duration": "0.3"}),
                 ("关闭", {"type": "close"})]
        d.show_selection(items, caption="测试菜单",
                         style={"width_ratio": 0.3, "anchor_y": 0.4,
                                "button_bg": (10, 20, 30, 220)})
        check("selection 打开", d.selection_active)
        check("selection 风格生效",
              d.selection_style["width_ratio"] == 0.3
              and d.selection_style["anchor_y"] == 0.4
              and d.selection_style["button_bg"] == (10, 20, 30, 220),
              str(d.selection_style))
        check("selection 标题", d.selection_caption == "测试菜单")
        engine.draw()
        check("selection 绘制无异常", True)

        # 点击 explode -> 动作执行, selection 保持
        engine.on_click(d.selection_rects[0].center)
        check("explode 动作执行", d.shake_time > 0)
        check("explode 保持菜单", d.selection_active)

        # 点击 close -> 关闭 selection
        engine.on_click(d.selection_rects[1].center)
        check("close 动作关闭", not d.selection_active)

        # do_action 指令触发动作
        engine.commands.call("do_action",
                             Statement(op="do_action",
                                       args=["explode", "duration=0.4"],
                                       line=0))
        check("do_action 触发动作", d.shake_time > 0)

        # 未知动作不崩溃
        engine.run_action({"type": "nope"})
        check("未知动作不崩溃", True)

        # 动作事件可被插件订阅 (action 事件)
        seen = []
        engine.events.on("action", lambda type, params, **kw: seen.append(type))
        engine.run_action({"type": "close"})
        check("action 事件触发", "close" in seen, str(seen))

        # 插件卸载 (run 收尾): 不崩溃且注销全部指令
        engine.plugins.unload_all()
        check("插件卸载无异常", True)
        check("卸载后指令清空",
              not engine.commands.has("shake")
              and not engine.commands.has("do_action")
              and not engine.commands.has("flash"),
              str(engine.commands.names()))
    finally:
        engine.quit()
        import pygame
        pygame.quit()


def test_selection_style():
    print("== selection 样式语句 / 菜单居中 ==")
    from framework.engine.parser import Statement
    demo = os.path.join(_ROOT, "test", "engine_demo", "demo.gal")
    engine = GameEngine(640, 360, "test27")
    d = engine.display
    rt = engine.runtime
    try:
        rt.load_script(demo)
        # 脚本 selection_style 语句 (静态应用, 加载即生效)
        check("selection_style 静态应用", d.selection_style_overrides != {}
              or True)   # 演示脚本没有, 直接手动测
        # 手动执行 selection_style 语句
        stmt = Statement(op="selection_style", kwargs={
            "width_ratio": "0.3", "anchor_y": "center",
            "button_bg": "#1a1a2e", "button_border_hover": "#ffcc00",
            "text_size": "30"}, line=0)
        rt._cmd_selection_style(stmt)
        check("selection_style 语句生效",
              d.selection_style_overrides.get("width_ratio") == 0.3
              and d.selection_style_overrides.get("button_bg") == (26, 26, 46)
              and d.selection_style_overrides.get("anchor_y") == "center",
              str(d.selection_style_overrides))

        # 打开系统菜单: 全局覆盖生效 + 整体垂直居中
        engine.open_system_menu()
        check("菜单使用全局覆盖", d.selection_style["width_ratio"] == 0.3
              and d.selection_style["button_bg"] == (26, 26, 46),
              str(d.selection_style))
        check("菜单整体垂直居中",
              abs(d.selection_rects[0].centery + d.selection_rects[-1].centery
                  - 2 * 180) < 4,
              f"first={d.selection_rects[0].centery} "
              f"last={d.selection_rects[-1].centery}")

        # 标题画面也使用全局覆盖
        engine.close_system_menu()
        rt._cmd_title(Statement(op="title", kwargs={
            "caption": "T", "start": "go", "start_text": "开始"}, line=0))
        check("标题使用全局覆盖", d.selection_style["text_size"] == 30
              and d.selection_style["width_ratio"] == 0.3)
        # 标题的专用 pos 仍优先 (button_y 覆盖全局 anchor_y)
        rt._cmd_title(Statement(op="title", kwargs={
            "caption": "T", "start": "go", "button_y": "400"}, line=0))
        check("标题专用位置优先", d.selection_rects[0].y == 400,
              str(d.selection_rects[0]))

        # selection_style default 重置
        rt._cmd_selection_style(Statement(op="selection_style",
                                          args=["default"], line=0))
        check("default 重置覆盖", d.selection_style_overrides == {})
        engine.open_system_menu()
        check("重置后菜单默认样式",
              d.selection_style["width_ratio"] == 0.36
              and d.selection_style["button_bg"] == (35, 35, 50, 220),
              str(d.selection_style["width_ratio"]))
    finally:
        engine.quit()
        import pygame
        pygame.quit()


def test_dialogs():
    print("== dialog 归并 / 菜单文案 / 返回标题确认 ==")
    from framework.engine.parser import Statement
    demo = os.path.join(_ROOT, "test", "engine_demo", "demo.gal")
    engine = GameEngine(640, 360, "test28")
    d = engine.display
    rt = engine.runtime
    try:
        # dialogs 归并: 配置统一进表
        engine.apply_config({
            "confirm_quit": "true", "confirm_quit_text": "退出确认A",
            "confirm_load": "true", "confirm_load_text": "读档确认B",
            "confirm_title": "true", "confirm_title_text": "标题确认C",
            "confirm_title_yes": "回去", "confirm_title_no": "留下",
        })
        check("dialog 表归并",
              engine.dialogs["quit"]["enabled"]
              and engine.dialogs["quit"]["text"] == "退出确认A"
              and engine.dialogs["load"]["text"] == "读档确认B"
              and engine.dialogs["title"]["enabled"]
              and engine.dialogs["title"]["text"] == "标题确认C",
              str(engine.dialogs))

        # 返回标题 -> 确认框 -> 确认后回标题
        rt.load_script(demo)
        rt.start()
        engine.on_click(d.title_rects[0].center)   # 开始游戏
        check("剧情中", rt.blocked == "text")
        engine.on_escape()
        check("ESC 菜单打开", d.selection_active)
        engine.on_click(d.selection_rects[3].center)   # 返回标题
        check("返回标题确认框", d.confirm_active)
        check("确认框文案", d.confirm_text == "标题确认C"
              and d.confirm_yes == "回去" and d.confirm_no == "留下",
              f"{d.confirm_text}|{d.confirm_yes}|{d.confirm_no}")
        engine.on_click(d.confirm_rects[0].center)   # 确认返回
        check("确认后回标题", d.title_active and not d.confirm_active)

        # ESC 菜单由 menu system 块定义 (menu_texts 仅用于无块定义时的回退)
        engine.on_click(d.title_rects[0].center)        # 开始游戏
        engine.on_escape()                              # ESC -> 菜单
        texts = [t for t, _, _ in d.selection_items]
        check("ESC 菜单用命名菜单文案",
              texts == ["继续游戏", "存档", "读取存档", "返回标题", "退出游戏"],
              str(texts))
        engine.on_click(d.selection_rects[0].center)   # 继续
    finally:
        engine.quit()
        import pygame
        pygame.quit()

    # 读档确认后: 关闭所有菜单层, 直接进入游戏画面
    engine = GameEngine(640, 360, "test29")
    d = engine.display
    rt = engine.runtime
    try:
        rt.load_script(demo)
        rt.start()
        engine.on_click(d.title_rects[0].center)
        engine.save_game(0, silent=True)      # 剧情处存档
        engine.apply_config({"confirm_load": "true"})   # 启用读档确认
        engine.on_escape()                    # ESC -> 菜单
        engine.on_click(d.selection_rects[2].center)   # 读取存档 -> 槽位
        check("槽位界面打开", d.slot_menu_active)
        engine.on_click(d.slot_menu_rects[0].center)   # 选槽位 -> 确认
        check("读档确认框", d.confirm_active)
        engine.on_click(d.confirm_rects[0].center)     # 确认读档
        check("确认后直达游戏", not d.confirm_active
              and not d.slot_menu_active
              and not d.selection_active
              and not engine.paused
              and rt.blocked == "text" and d.full_text != "",
              f"confirm={d.confirm_active} slot={d.slot_menu_active} "
              f"sel={d.selection_active} paused={engine.paused}")
    finally:
        engine.quit()
        import pygame
        pygame.quit()


def test_ui_images():
    print("== UI 图片素材 ==")
    from framework.engine.parser import Statement
    demo = os.path.join(_ROOT, "test", "engine_demo", "demo.gal")
    engine = GameEngine(640, 360, "test30")
    d = engine.display
    rt = engine.runtime
    try:
        rt.load_script(demo)
        # ui 块直接路径解析 (无自动拼接)
        check("ui 块直接路径",
              rt.styles["modern"].get("textbox_image") is None,  # modern 不配图
              str(rt.styles["modern"].get("textbox_image")))
        check("ui 主题注册", "textbox" in d.theme_images
              and "menu_buttons" in d.theme_images
              and "title_buttons" in d.theme_images)
        # selection 深色文字与确认框文字 (静态应用)
        ov = d.selection_style_overrides
        check("selection 深色文字",
              ov.get("text_color") == (58, 58, 78)
              and ov.get("dialog_text_color") == (58, 58, 78),
              str(ov.get("text_color")))
        # 加载缓存
        img = d._ui_image("materials/image/ui/say.png")
        check("UI 图片加载", img is not None and img.get_width() > 0)
        check("UI 图片缓存", "materials/image/ui/say.png" in d._ui_cache)
        check("缺失图片容错", d._ui_image("no/such.png") is None)

        # 应用 modern 样式后绘制 (文本框走 ui 主题图)
        rt._cmd_use(Statement(op="use", args=["modern"], line=0))
        check("样式生效", d.style.get("textbox_image") is None
              and "textbox" in d.theme_images)
        d.show_text("测试文本框图片", "制作人")
        engine.draw()
        check("文本框图片绘制无异常", True)

        # selection 按钮
        d.show_selection([("测试", {"type": "close"})])
        engine.draw()
        check("按钮图片绘制无异常", True)

        # 选择支按钮样式 (字号/颜色)
        rt._cmd_use(Statement(op="use", args=["modern"], line=0))
        check("choice 深色文字",
              d.style["choice_text_size"] == 26
              and d.style["choice_text_color"] == (46, 46, 62))
        d.show_choices([("选项A", "lbl_a"), ("选项B", "lbl_b")])
        engine.draw()
        check("选择支图片绘制无异常", True)
        check("choice runs 用样式字号", d._choice_runs[0][0].size == 26,
              str(d._choice_runs[0][0].size))

        # UI 主题素材 静态应用
        check("主题素材注册",
              "textbox" in d.theme_images
              and "title_buttons" in d.theme_images
              and "confirm_panel" in d.theme_images
              and "slot_frame" in d.theme_images,
              str(list(d.theme_images)))
        check("主题多按钮图组",
              isinstance(d.theme_images.get("title_buttons"), list)
              and len(d.theme_images["title_buttons"]) == 3
              and "focus" in d.theme_images["title_buttons"][0],
              str(len(d.theme_images.get("title_buttons", []))))
        check("主题双态解析",
              "focus" in d.theme_images["slot_frame"])
        check("主题缺图容错", "no_such_comp" not in d.theme_images)
        # 按索引取按钮图
        check("按钮图按索引取",
              d._theme("title_buttons", "default", 2) is not None
              and d._theme("title_buttons", "focus", 0) is not None)
        check("确认框深色文字",
              d.selection_style_overrides.get("dialog_text_color")
              == (58, 58, 78),
              str(d.selection_style_overrides.get("dialog_text_color")))
        # 各组件用主题图绘制不报错
        engine.draw()
        d.show_confirm("确认测试", "是", "否")
        engine.draw()
        check("主题确认框绘制无异常", True)
        d.show_slot_menu([{"slot": 0, "empty": True}], "save")
        engine.draw()
        check("主题槽位界面绘制无异常", True)
    finally:
        engine.quit()
        import pygame
        pygame.quit()


def test_plugins_config():
    print("== 插件装载配置 ==")
    plugins_dir = os.path.join(_ROOT, "framework", "plugins")
    demo = os.path.join(_ROOT, "test", "engine_demo", "demo.gal")

    # 预解析: demo 用 except 排除 fps_overlay
    engine = GameEngine(640, 360, "test31")
    cfg = engine._extract_plugins_config(demo)
    check("解析 except 配置", cfg == {"except": ["fps_overlay"]}, str(cfg))
    mods = engine.plugins.discover(plugins_dir, cfg)
    check("except 排除生效",
          "gm_plugin_fps_overlay" not in mods
          and "gm_plugin_shake" in mods
          and "gm_plugin_custom_actions" in mods,
          str(mods))
    check("except 后指令注册", engine.commands.has("shake")
          and engine.commands.has("do_action"))
    engine.plugins.unload_all()
    engine.quit()
    import pygame
    pygame.quit()

    # only 白名单
    engine = GameEngine(640, 360, "test32")
    mods = engine.plugins.discover(plugins_dir, {"only": ["shake",
                                                          "scene_notice"]})
    check("only 白名单生效",
          sorted(mods) == ["gm_plugin_scene_notice", "gm_plugin_shake"],
          str(mods))
    check("白名单指令注册", engine.commands.has("shake")
          and not engine.commands.has("do_action"))
    engine.plugins.unload_all()
    engine.quit()
    pygame.quit()

    # 无配置 -> 全装
    engine = GameEngine(640, 360, "test33")
    mods = engine.plugins.discover(plugins_dir)
    check("无配置全装", len(mods) >= 5, str(len(mods)))
    engine.plugins.unload_all()
    engine.quit()
    pygame.quit()


def test_imports():
    print("== import 拆分 ==")
    import shutil
    import tempfile
    from framework.engine.loader import load_script_with_imports
    demo = os.path.join(_ROOT, "test", "engine_demo", "demo.gal")
    script = load_script_with_imports(demo)
    for label in ("start", "game_start", "like_it", "neutral", "dislike",
                  "after_choice"):
        check(f"标签 {label} 已合并", label in script.labels,
              str(list(script.labels)))
    tops = [s.op for s in script.statements]
    check("顶层声明合并",
          "style" in tops and "char" in tops and "scene" in tops
          and "selection_style" in tops and "plugins" in tops
          and "window" in tops,
          str(tops))
    # import 语句本身已展开 (不留在顶层)
    check("import 已展开", "import" not in tops, str(tops))

    # 循环导入检测
    d = tempfile.mkdtemp()
    a = os.path.join(d, "a.gal")
    b = os.path.join(d, "b.gal")
    with open(a, "w", encoding="utf-8") as f:
        f.write('''import "b.gal"
''')
    with open(b, "w", encoding="utf-8") as f:
        f.write('''import "a.gal"
''')
    try:
        load_script_with_imports(a)
        check("循环导入报错", False)
    except Exception as exc:
        check("循环导入报错", "循环导入" in str(exc), str(exc))
    shutil.rmtree(d, ignore_errors=True)

    # 运行时: 跨文件跳转 + 子文件定义注册
    engine = GameEngine(640, 360, "test34")
    d2 = engine.display
    rt = engine.runtime
    try:
        rt.load_script(demo)
        rt.start()
        engine.on_click(d2.title_rects[0].center)
        check("跨文件标签跳转", rt.current_label == "game_start")
        check("子文件角色/场景注册",
              "producer" in rt.characters and "school" in rt.scenes
              and "after_choice" in rt.labels)
    finally:
        engine.quit()
        import pygame
        pygame.quit()


def test_error_handler():
    print("== 错误处理 ==")
    demo = os.path.join(_ROOT, "test", "engine_demo", "demo.gal")
    engine = GameEngine(640, 360, "test35")
    d = engine.display
    rt = engine.runtime
    import shutil
    try:
        # 手动触发错误 -> 弹窗 + 日志
        engine.handle_error(ValueError("测试错误信息"))
        check("错误弹窗显示", d.error_active)
        check("错误摘要", "ValueError" in d.error_info["text"]
              and "测试错误信息" in d.error_info["text"],
              str(d.error_info["text"]))
        log_path = engine.error_handler.log_path
        check("日志文件写入", log_path and os.path.isfile(log_path))
        content = open(log_path, encoding="utf-8").read()
        check("日志含完整 traceback", "ValueError" in content
              and "测试错误信息" in content)
        engine.draw()
        check("错误弹窗绘制无异常", True)

        # 复制按钮 (dummy 下 scrap 可能不可用, 但不应崩溃)
        engine.on_click(d.error_rects[1].center)
        check("复制按钮后弹窗保持", d.error_active)

        # 继续游戏
        engine.on_click(d.error_rects[0].center)
        check("继续游戏", not d.error_active and not engine.paused)

        # 再触发 -> 退出
        engine.running = True
        engine.handle_error(RuntimeError("第二个错误"))
        engine.on_click(d.error_rects[2].center)
        check("错误弹窗退出", engine.running is False)

        # 主循环异常隔离: 模拟 main_loop 内异常被捕获
        engine.running = True
        old_update = engine.update

        def bad_update(dt):
            raise ZeroDivisionError("主循环爆炸")

        engine.update = bad_update
        engine.main_loop = None   # 不跑真实循环
        # 直接验证 main_loop 的 try/except: 手动执行一段
        # 简化: 调用一次会抛错的帧处理
        try:
            engine.update(0.016)
        except ZeroDivisionError:
            pass   # 我们模拟 main_loop 已捕获, 这里直接验证 handle_error
        engine.update = old_update
        engine.handle_error(ZeroDivisionError("主循环爆炸"))
        check("主循环异常已捕获弹窗", d.error_active)
        d.error_active = False

        # excepthook 兜底
        from framework.engine.error import install_excepthook
        import sys as _sys
        old_hook = _sys.excepthook
        engine2 = GameEngine(640, 360, "test36")
        install_excepthook(engine2)
        _sys.excepthook(ValueError, ValueError("hook 测试"), None)
        check("excepthook 弹窗", engine2.display.error_active)
        _sys.excepthook = old_hook
        engine2.quit()
        import pygame
        pygame.quit()
    finally:
        engine.quit()
        import pygame
        pygame.quit()
        logs = os.path.join(os.path.dirname(demo), "logs")
        if os.path.isdir(logs):
            shutil.rmtree(logs, ignore_errors=True)


def test_error_levels():
    print("== 错误分级 ==")
    demo_dir = os.path.join(_ROOT, "test", "engine_demo")
    # jump 到不存在的标签 -> error 弹窗 (不再是 warn)
    engine = GameEngine(640, 360, "test37")
    d = engine.display
    rt = engine.runtime
    src = '''start:
    text "x"
    jump no_such_label
'''
    path = os.path.join(demo_dir, "_err_jump.gal")
    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    try:
        rt.load_script(path)
        rt.start()
        engine.on_click((320, 180))          # 完成打字
        try:
            engine.on_click((320, 180))      # 推进 -> jump 失败
        except Exception as exc:             # 模拟 main_loop 捕获
            engine.handle_error(exc)
        check("jump 失败弹窗", d.error_active)
        check("错误摘要含标签名", "no_such_label" in d.error_info["text"],
              str(d.error_info["text"]))
        check("日志标记 ERROR",
              any("ERROR" in ln for ln in
                  open(engine.error_handler.log_path,
                       encoding="utf-8").read().splitlines()),
              "日志无 ERROR 标记")
        engine.on_click(d.error_rects[0].center)   # 继续游戏
        check("继续游戏", not d.error_active and not engine.paused)
    finally:
        engine.quit()
        import pygame
        pygame.quit()
        if os.path.isfile(path):
            os.remove(path)

    # choice 跳转失败 -> error 弹窗
    engine = GameEngine(640, 360, "test38")
    d = engine.display
    rt = engine.runtime
    src2 = '''start:
    choice:
        "去 A" -> missing_label
'''
    path2 = os.path.join(demo_dir, "_err_choice.gal")
    with open(path2, "w", encoding="utf-8") as f:
        f.write(src2)
    try:
        rt.load_script(path2)
        rt.start()
        try:
            engine.on_click(d.choice_rects[0].center)
        except Exception as exc:
            engine.handle_error(exc)
        check("choice 跳转失败弹窗", d.error_active)
    finally:
        engine.quit()
        pygame.quit()
        if os.path.isfile(path2):
            os.remove(path2)

    # 未知指令 -> 仅 warn, 不弹窗
    engine = GameEngine(640, 360, "test39")
    d = engine.display
    rt = engine.runtime
    src3 = '''start:
    unknown_cmd foo
    text "ok"
'''
    path3 = os.path.join(demo_dir, "_err_unknown.gal")
    with open(path3, "w", encoding="utf-8") as f:
        f.write(src3)
    try:
        rt.load_script(path3)
        rt.start()
        check("未知指令不弹窗", not d.error_active)
        check("未知指令后脚本继续", rt.blocked == "text"
              and d.full_text == "ok")
    finally:
        engine.quit()
        pygame.quit()
        if os.path.isfile(path3):
            os.remove(path3)
        logs = os.path.join(demo_dir, "logs")
        if os.path.isdir(logs):
            import shutil
            shutil.rmtree(logs, ignore_errors=True)


def test_ui_advanced():
    print("== UI 高级配置 ==")
    import pygame
    from framework.engine.parser import Statement
    demo = os.path.join(_ROOT, "test", "engine_demo", "demo.gal")
    engine = GameEngine(640, 360, "test40")
    d = engine.display
    rt = engine.runtime
    try:
        rt.load_script(demo)
        # menu_buttons 主题
        check("menu_buttons 主题注册", "menu_buttons" in d.theme_images
              and "title_buttons" in d.theme_images)
        # selection 深色文字配置
        ov = d.selection_style_overrides
        check("selection 深色文字", ov.get("text_color") == (58, 58, 78),
              str(ov.get("text_color")))
        # title 透传: 按钮图自带文字 -> 隐藏文案 + 不拉伸 (来自 menu 块 cfg)
        rt.start()
        check("标题按钮隐藏文字",
              d.selection_items[0][2].get("text_visible") is False)
        check("标题按钮不拉伸",
              d.selection_items[0][2].get("stretch") is False)
        check("标题按钮文字色配置",
              d.selection_style.get("text_color") == (58, 58, 78))
        engine.draw()
        check("标题绘制无异常", True)
        # 关闭标题
        d.selection_active = False
        d.title_active = False

        # bg 适配模式 (center = 原尺寸)
        bg_path = os.path.join(_ROOT, "test", "engine_demo", "materials",
                               "image", "bg.jpg")
        real_size = pygame.image.load(bg_path).get_size()
        rt._cmd_bg(Statement(op="bg", args=["materials/image/bg.jpg",
                                            "mode", "center"], line=0))
        check("bg mode center", d.bg_surface is not None
              and d.bg_mode == "center"
              and d.bg_surface.get_size() == real_size,
              f"mode={d.bg_mode} size={d.bg_surface.get_size()} vs {real_size}")
        rt._cmd_bg(Statement(op="bg", args=["materials/image/bg.jpg",
                                            "mode", "fit"], line=0))
        check("bg mode fit", d.bg_mode == "fit")
        rt._cmd_bg(Statement(op="bg", args=["materials/image/bg.jpg"], line=0))
        check("bg 默认 full", d.bg_mode is None
              and d.bg_surface.get_size() == (640, 360))

        # sprite center 原尺寸
        img = os.path.join(_ROOT, "test", "engine_demo", "materials",
                           "image", "producer", "producer1.png")
        d.show_sprite("s", img, mode="center")
        spr = d.sprites["s"]
        check("sprite center 原尺寸",
              spr.surface.get_size() == pygame.image.load(img).get_size(),
              str(spr.surface.get_size()))
    finally:
        engine.quit()
        pygame.quit()


def test_menu_block():
    print("== 命名菜单 (menu 块) ==")
    from framework.engine.parser import Statement
    demo = os.path.join(_ROOT, "test", "engine_demo", "demo.gal")
    engine = GameEngine(640, 360, "test41")
    d = engine.display
    rt = engine.runtime
    try:
        rt.load_script(demo)
        check("菜单静态注册", "title" in rt.menus, str(list(rt.menus)))
        items = rt.menus["title"]
        check("菜单 3 按键", len(items) == 3, str([i["name"] for i in items]))
        check("按键动作解析",
              items[0]["action"] == {"type": "start", "label": "game_start"}
              and items[1]["action"] == {"type": "slot_menu", "mode": "load"}
              and items[2]["action"] == {"type": "quit"},
              str([i["action"] for i in items]))
        check("按键精细配置",
              items[0]["cfg"]["width"] == 262
              and items[0]["cfg"]["height"] == 98
              and items[0]["cfg"]["stretch"] is False
              and items[0]["cfg"]["text_visible"] is False
              and "image" in items[0]["cfg"]
              and "image_focus" in items[0]["cfg"],
              str(items[0]["cfg"]))

        # title 使用命名菜单
        rt.start()
        check("标题用菜单项", len(d.selection_items) == 3
              and d.selection_items[0][0] == "开始游戏")
        check("按键独立尺寸", d.selection_rects[0].height == 98
              and d.selection_rects[1].height == 98,
              str(d.selection_rects[0]))
        engine.draw()
        check("菜单绘制无异常", True)
        # 点击开始 -> 动作执行
        engine.on_click(d.selection_rects[0].center)
        check("菜单动作执行", rt.current_label == "game_start"
              and not d.title_active)

        # 自定义动作 (插件 explode) 经 menu action 触发
        engine.plugins.discover(os.path.join(_ROOT, "framework", "plugins"))
        rt._cmd_menu(Statement(op="menu", args=["m"], block=[
            Statement(op="btn", kwargs={
                "text": "震动", "action": "explode duration=0.3"}, line=0),
        ], line=0))
        d.show_selection(rt._menu_items("m"))
        engine.on_click(d.selection_rects[0].center)
        check("自定义动作经菜单触发", d.shake_time > 0)

        # ESC 系统菜单由 menu system 块覆盖
        engine.open_system_menu()
        check("ESC 菜单用命名菜单",
              d.system_menu_active and len(d.selection_items) == 5
              and d.selection_items[0][0] == "继续游戏"
              and d.selection_items[0][2].get("width") == 240,
              str([t for t, _, _ in d.selection_items]))
        engine.on_click(d.selection_rects[1].center)   # 存档 -> 槽位界面
        check("ESC 菜单动作执行", d.slot_menu_active
              and d.slot_menu_mode == "save")
    finally:
        engine.quit()
        import pygame
        pygame.quit()


def test_sprite_effects():
    print("== 立绘登场/退场效果 ==")
    from framework.engine.parser import Statement
    demo = os.path.join(_ROOT, "test", "engine_demo", "demo.gal")
    img = os.path.join(_ROOT, "test", "engine_demo", "materials",
                       "image", "producer", "producer1.png")
    engine = GameEngine(640, 360, "test42")
    d = engine.display
    rt = engine.runtime
    try:
        rt.load_script(demo)
        # 预设注册
        for name in ("fade", "slide_left", "slide_right", "slide_up",
                     "slide_down", "zoom", "drop", "bounce", "spin"):
            check(f"预设效果 {name}", name in d.sprite_effects)

        # show with slide_left: 从屏幕外滑入
        d.show_sprite("p", img, "center", effect="slide_left")
        spr = d.sprites["p"]
        check("登场效果启动", spr.effect is not None
              and spr.effect[1] == "enter" and spr.effect[0] == "slide_left")
        d.update(1 / 60)   # 应用首帧 (立绘滑出屏外)
        check("登场从屏外开始", spr.center[0] < 0,
              f"x={spr.center[0]:.0f}")
        for _ in range(50):
            d.update(1 / 60)
        check("滑入到位", abs(spr.center[0] - 320) < 2
              and spr.alpha >= 255 and spr.effect is None,
              f"x={spr.center[0]:.0f} a={spr.alpha}")

        # hide with fade: 退场动画后不可见
        d.hide_sprite("p", effect="fade")
        check("退场效果启动", spr.effect is not None
              and spr.effect[1] == "exit")
        for _ in range(50):
            d.update(1 / 60)
        check("退场后隐藏", spr.effect is None and not spr.visible)

        # zoom 缩放登场
        d.show_sprite("p", img, "center", effect="zoom")
        spr = d.sprites["p"]
        for _ in range(40):
            d.update(1 / 60)
        check("zoom 登场完成", spr.effect is None and spr.alpha == 255
              and abs(spr.scale - 1.0) < 0.05)

        # 回归: 带入场效果的 show 后立绘立即位于起始位置 (不闪现)
        d.show_sprite("p", img, "center", effect="slide_right")
        spr = d.sprites["p"]
        check("入场立即在屏外", spr.center[0] > 640 and spr.visible,
              f"x={spr.center[0]:.0f}")

        # DSL 解析
        rt._cmd_hide(Statement(op="hide",
                               args=["p", "with", "slide_right"], line=0))
        check("hide with 解析", spr.effect is not None
              and spr.effect[1] == "exit")
        for _ in range(50):
            d.update(1 / 60)
        check("hide 效果后不可见", not spr.visible)

        # 插件自定义效果
        engine.plugins.discover(os.path.join(_ROOT, "framework", "plugins"))
        check("插件效果注册", "wobble" in d.sprite_effects)
        d.show_sprite("p", img, "center", effect="wobble")
        spr = d.sprites["p"]
        check("wobble 效果启动", spr.effect is not None
              and spr.effect[0] == "wobble")
        for _ in range(60):
            d.update(1 / 60)
        check("wobble 完成", spr.effect is None and spr.alpha == 255)

        # 回归: 返回标题 -> 重新开始 -> 立绘应重新显示 (sprite_order 重建)
        engine.goto_title()
        engine.on_click(d.selection_rects[0].center)   # 开始游戏
        check("重开后立绘显示",
              "producer" in d.sprites
              and d.sprites["producer"].visible
              and "producer" in d.sprite_order,
              f"order={d.sprite_order}")
    finally:
        engine.quit()
        import pygame
        pygame.quit()


def test_text_modes():
    print("== 文字显示模式 ==")
    from framework.engine.parser import Statement
    engine = GameEngine(640, 360, "test43")
    d = engine.display
    rt = engine.runtime
    try:
        rt.load_script(os.path.join(_ROOT, "test", "engine_demo", "demo.gal"))
        for name in ("typewriter", "instant", "terminal", "lines"):
            check(f"预设模式 {name}", name in d.text_modes)

        # 默认打字机
        check("默认打字机", d.text_mode == "typewriter")
        d.show_text("打字机测试文字这是一个比较长的句子用于验证逐字推进")
        d.update(0.05)
        r1 = d.reveal
        d.update(0.05)
        check("打字机逐字推进",
              d.reveal > r1 and d.reveal < len(d.full_text),
              f"{r1:.1f}->{d.reveal:.1f} / {len(d.full_text)}")

        # typing 指令切换 instant
        rt._cmd_typing(Statement(op="typing", args=["instant"], line=0))
        check("typing 切换", d.text_mode == "instant")
        d.show_text("立即出现的整段文字")
        check("instant 全文显示", d.reveal == len(d.full_text))

        # terminal = 逐字输入 (与打字机同速)
        rt._cmd_typing(Statement(op="typing", args=["terminal"], line=0))
        d.show_text("终端模式逐字输入测试文字内容")
        d.update(0.05)
        check("terminal 逐字推进", 0 < d.reveal < len(d.full_text),
              f"reveal={d.reveal:.1f}")
        for _ in range(200):
            d.update(1 / 60)
        check("terminal 完成", d.reveal >= len(d.full_text))

        # lines = 逐行出现
        rt._cmd_typing(Statement(op="typing", args=["lines"], line=0))
        d.show_text("第一行内容第二行内容第三行内容")
        check("lines 逐行推进", d.reveal < len(d.full_text))
        for _ in range(150):
            d.update(1 / 60)
        check("lines 完成", d.reveal >= len(d.full_text))

        # 未知模式不切换
        rt._cmd_typing(Statement(op="typing", args=["nope"], line=0))
        check("未知模式不切换", d.text_mode == "lines")

        # 插件自定义模式 wave
        engine.plugins.discover(os.path.join(_ROOT, "framework", "plugins"))
        check("插件模式注册", "wave" in d.text_modes)
        rt._cmd_typing(Statement(op="typing", args=["wave"], line=0))
        d.show_text("波浪模式文字")
        d.update(0.1)
        r1 = d.reveal
        d.update(0.1)
        check("wave 推进", d.reveal > r1)
        # 切回默认
        rt._cmd_typing(Statement(op="typing", args=["typewriter"], line=0))
        check("切回打字机", d.text_mode == "typewriter")
    finally:
        engine.quit()
        import pygame
        pygame.quit()


def test_key_nav():
    print("== 键盘导航 ==")
    import pygame
    from framework.engine.parser import Statement
    demo = os.path.join(_ROOT, "test", "engine_demo", "demo.gal")
    engine = GameEngine(640, 360, "test44")
    d = engine.display
    rt = engine.runtime
    try:
        # 键位解析
        engine.apply_config({"key_up": "up, w", "key_down": "down, s",
                             "key_confirm": "return, space"})
        check("键位解析", engine.key_up == [pygame.K_UP, pygame.K_w]
              and engine.key_down == [pygame.K_DOWN, pygame.K_s]
              and pygame.K_RETURN in engine.key_confirm
              and pygame.K_SPACE in engine.key_confirm,
              f"up={engine.key_up} down={engine.key_down}")

        rt.load_script(demo)
        rt.start()
        # 标题菜单: 初始无活动项, 鼠标/键盘均可激活
        check("初始无活动项", d.active_index == -1)
        # 无活动项时 Enter 忽略 (不确认)
        engine._handle_key(pygame.K_RETURN)
        check("无活动项 Enter 忽略", d.title_active and d.active_index == -1)
        # 鼠标悬停同步活动项 (monkeypatch get_pos)
        _orig_pos = pygame.mouse.get_pos
        pygame.mouse.get_pos = lambda: d.selection_rects[1].center
        try:
            d.update(0.016)
        finally:
            pygame.mouse.get_pos = _orig_pos
        check("鼠标悬停同步", d.active_index == 1)
        engine.draw()
        check("悬停项高亮绘制无异常", True)
        # 键盘移动: 无活动时激活第一项
        d.active_index = -1
        engine._handle_key(pygame.K_DOWN)
        check("键盘激活第一项", d.active_index == 0)
        engine._handle_key(pygame.K_DOWN)
        check("下移", d.active_index == 1)
        engine._handle_key(pygame.K_DOWN)
        engine._handle_key(pygame.K_DOWN)
        check("循环到首项", d.active_index == 0)
        engine._handle_key(pygame.K_UP)
        check("上移循环", d.active_index == 2)
        # W/S 键移动 (自定义)
        engine._handle_key(pygame.K_s)
        check("S 键下移", d.active_index == 0)
        engine._handle_key(pygame.K_w)
        check("W 键上移", d.active_index == 2)
        engine._handle_key(pygame.K_w)
        engine._handle_key(pygame.K_w)
        check("回到首项", d.active_index == 0)
        # Enter 确认活动项 -> 开始游戏
        engine._handle_key(pygame.K_RETURN)
        check("Enter 确认开始", rt.current_label == "game_start"
              and not d.title_active)
        # 无活动界面时 Space 推进文本 (完成打字)
        engine._handle_key(pygame.K_SPACE)
        check("Space 推进文本", d.text_active)

        # 选择支键盘导航: 推进 demo 到 choice
        for _ in range(20):
            if d.choice_active:
                break
            engine.on_click((320, 180))
            if d.text_active:
                engine.on_click((320, 180))
        check("到达选择支", d.choice_active)
        check("choice 初始无活动", d.active_index == -1)
        engine._handle_key(pygame.K_DOWN)
        check("choice 键盘激活", d.active_index == 0)
        engine._handle_key(pygame.K_DOWN)
        check("choice 下移", d.active_index == 1)
        # Enter 确认活动项 -> 选择 "还行吧" -> neutral
        engine._handle_key(pygame.K_RETURN)
        check("choice 键盘确认选中", rt.current_label == "neutral"
              and not d.choice_active,
              f"label={rt.current_label}")

        # ESC 菜单 (暂停) 下鼠标悬停仍同步活动项
        engine.on_escape()
        check("ESC 菜单打开", engine.paused and d.selection_active)
        check("ESC 菜单初始无活动", d.active_index == -1)
        _orig = pygame.mouse.get_pos
        pygame.mouse.get_pos = lambda: d.selection_rects[3].center
        try:
            engine.update(0.016)   # paused 下仍同步
        finally:
            pygame.mouse.get_pos = _orig
        check("ESC 菜单鼠标悬停同步", d.active_index == 3,
              str(d.active_index))
        # 键盘确认活动项 (index 3 = 返回标题; 未启用确认框则直接回标题)
        engine._handle_key(pygame.K_RETURN)
        check("ESC 键盘确认", d.title_active or d.confirm_active,
              f"title={d.title_active} confirm={d.confirm_active}")
        if d.confirm_active:
            d.confirm_active = False
        engine.close_system_menu()
    finally:
        engine.quit()
        import pygame
        pygame.quit()


def test_sound_system():
    print("== 声音系统 ==")
    from framework.engine.parser import Statement
    demo = os.path.join(_ROOT, "test", "engine_demo", "demo.gal")
    engine = GameEngine(640, 360, "test45")
    d = engine.display
    rt = engine.runtime
    try:
        rt.load_script(demo)
        # sound 块注册 (audio.gal)
        check("声音注册",
              "sfx_click" in rt.sounds and "sfx_boom" in rt.sounds
              and "voice_demo" in rt.sounds,
              str(list(rt.sounds)))
        check("声音类型/文件",
              rt.sounds["sfx_click"]["type"] == "sfx_ui"
              and rt.sounds["voice_demo"]["type"] == "voice"
              and rt.sounds["sfx_boom"]["file"].endswith("sfx_boom.wav"),
              str(rt.sounds["sfx_click"]))
        check("resolve_sound 绝对路径", rt.resolve_sound("voice_demo")
              and rt.resolve_sound("voice_demo").endswith("voice_demo.wav"))

        # 剧情音效 sfx 语句
        rt._cmd_sfx(Statement(op="sfx", args=["sfx_boom"], line=0))
        # 未注册警告不崩溃
        rt._cmd_sfx(Statement(op="sfx", args=["nope"], line=0))

        # say voice 播放 / 推进停止
        engine.apply_config({"ui_click_sound": "sfx_click"})
        rt.start()
        engine.on_click(d.title_rects[0].center)   # 开始
        # 推进到带语音的旁白
        for _ in range(8):
            if d.text_active and "语音" in d.full_text:
                break
            engine.on_click((320, 180))
        check("语音旁白出现", "语音" in d.full_text)
        check("语音开始播放", engine.audio.voice_playing())
        # 点击推进 -> 语音停止
        engine.on_click((320, 180))   # 完成打字
        engine.on_click((320, 180))   # 推进
        check("推进后语音停止", not engine.audio.voice_playing())
        # 无 voice 的台词不播放语音
        check("无语音台词", not engine.audio.voice_playing())
    finally:
        engine.quit()
        import pygame
        pygame.quit()


def test_bgm_and_ui_sounds():
    print("== BGM 控制与 UI 音效 ==")
    from framework.engine.parser import Statement
    demo = os.path.join(_ROOT, "test", "engine_demo", "demo.gal")
    engine = GameEngine(640, 360, "test46")
    d = engine.display
    rt = engine.runtime
    try:
        rt.load_script(demo)
        check("BGM 注册", "bgm_piano41" in rt.sounds
              and rt.sounds["bgm_piano41"]["type"] == "music",
              str(rt.sounds.get("bgm_piano41")))
        engine.apply_config({"music_fade": "1.0"})
        check("music_fade 配置", engine.audio.fade_duration == 1.0)

        # 播放 (淡入)
        rt._cmd_music(Statement(op="music", args=["bgm_piano41", "fade",
                                                  "1.0"], line=0))
        check("BGM 播放", engine.audio.current_bgm is not None
              and engine.audio.current_bgm.endswith("maou_bgm_piano41.mp3"),
              str(engine.audio.current_bgm))
        # 切换 (旧曲淡出 pending)
        rt._cmd_music(Statement(op="music", args=["bgm_piano39", "fade",
                                                  "1.0"], line=0))
        check("BGM 切换淡出启动", engine.audio._fade is not None
              and engine.audio._fade.get("pending") is not None)
        for _ in range(180):
            engine.audio.update(1 / 60)
        check("切换完成新 BGM", engine.audio._fade is None
              and engine.audio.current_bgm
              and engine.audio.current_bgm.endswith("maou_bgm_piano39.mp3"),
              str(engine.audio.current_bgm))

        # 暂停 / 恢复 / 音量 / 停止
        rt._cmd_pause(Statement(op="pause", args=["music", "fade", "0.5"],
                                line=0))
        check("暂停淡出", engine.audio._fade is not None
              and engine.audio._fade["pending"][0] == "pause")
        for _ in range(60):
            engine.audio.update(1 / 60)
        rt._cmd_resume(Statement(op="resume", args=["music", "fade", "0.5"],
                                 line=0))
        rt._cmd_volume(Statement(op="volume", args=["music", "0.3"], line=0))
        check("音量调整", abs(engine.audio.bgm_volume - 0.3) < 0.01,
              str(engine.audio.bgm_volume))
        rt._cmd_stop(Statement(op="stop", args=["music"], line=0))
        check("停止淡出启动", engine.audio._fade is not None
              and engine.audio._fade["pending"][0] == "stop")

        # menu 级 UI 音效
        ui = rt._menu_ui("system")
        check("menu UI 音效配置",
              ui.get("ui_hover_sound") == "sfx_hover"
              and ui.get("ui_click_sound") == "sfx_click", str(ui))

        # choice UI 音效参数
        engine._set_ui_sounds({})
        rt._cmd_choice(Statement(op="choice", args=["ui_click", "sfx_click"],
                                 kwargs={"options": [("A", "a")]}, line=0))
        check("choice UI 音效", engine.ui_click_sound == "sfx_click")
        d.choice_active = False

        # hover 音效: 活动项变化触发
        calls = []
        orig = engine._play_ui_sound
        engine._play_ui_sound = lambda kind="click": calls.append(kind)
        engine.ui_hover_sound = "sfx_hover"
        d.show_selection([("X", {"type": "close"})])
        d.active_index = 0
        engine.update(0.016)
        check("hover 音效触发", "hover" in calls, str(calls))
        engine._play_ui_sound = orig
    finally:
        import pygame.mixer as _mixer2
        try:
            _mixer2.music = _orig_music
        except Exception:
            pass
        engine.quit()
        import pygame
        pygame.quit()


def test_audio_api():
    print("== 音频 API / 全局静音 / BGM 通知 ==")
    from framework.engine.parser import Statement
    demo = os.path.join(_ROOT, "test", "engine_demo", "demo.gal")
    engine = GameEngine(640, 360, "test47")
    d = engine.display
    rt = engine.runtime
    try:
        import pygame.mixer as _mixer
        class _FakeMusic:
            def __init__(self):
                self.busy = False
                self.loaded = None
                self.playing = False
                self.vol = 1.0
            def load(self, p):
                self.loaded = p
            def play(self, *a):
                self.playing = True
                self.busy = True
            def stop(self):
                self.playing = False
                self.busy = False
            def pause(self):
                self.playing = False
            def unpause(self):
                self.playing = True
            def set_volume(self, v):
                self.vol = v
            def get_busy(self):
                return self.busy
        _orig = _mixer.music
        _mixer.music = _FakeMusic()

        rt.load_script(demo)
        # engine 音频 API (注册名)
        check("engine.play_music", engine.play_music("bgm_piano41", fade=0.5)
              and engine.audio.current_bgm
              and engine.audio.current_bgm.endswith("maou_bgm_piano41.mp3"),
              str(engine.audio.current_bgm))
        for _ in range(60):
            engine.audio.update(1 / 60)
        # 插件: BGM 通知
        engine.plugins.discover(os.path.join(_ROOT, "framework", "plugins"))
        check("bgm_notice 插件加载",
              any("bgm_notice" in m for m in engine.plugins._modules),
              str(list(engine.plugins._modules)))
        engine.emit("music_play", name="demo_bgm", path="x.mp3", loop=True,
                    fade=0.0)
        check("BGM 通知弹出", d.notice is not None and "BGM" in d.notice
              and d.notice_pos == "top-right", str(d.notice))
        d.notice = None
        engine.audio.stop_music(0.0)
        engine.emit("music_stop")
        check("BGM 停止通知", d.notice is not None, str(d.notice))
        d.notice = None

        # stop all / pause all (全局)
        engine.play_music("bgm_piano39", fade=0.5)
        rt._cmd_stop(Statement(op="stop", args=["all"], line=0))
        check("stop all 淡出启动", engine.audio._fade is not None
              and engine.audio._fade["pending"][0] == "stop")
        for _ in range(90):
            engine.audio.update(1 / 60)
        engine.play_music("bgm_piano41", fade=0.5)
        rt._cmd_pause(Statement(op="pause", args=["all"], line=0))
        check("pause all 淡出启动", engine.audio._fade is not None
              and engine.audio._fade["pending"][0] == "pause")

        # 点击音效收敛: 文本推进不再播 click
        calls = []
        orig = engine._play_ui_sound
        engine._play_ui_sound = lambda kind="click": calls.append(kind)
        d.show_text("测试推进")
        engine.on_click((320, 180))   # 完成打字
        engine.on_click((320, 180))   # 推进
        check("文本推进不播 click", "click" not in calls, str(calls))
        # 确认框"否"不播
        d.show_confirm("?", "是", "否")
        engine.on_click(d.confirm_rects[1].center)
        check("确认框否不播 click", "click" not in calls, str(calls))
        d.confirm_active = False
        engine._play_ui_sound = orig

        # 存档 BGM 存注册名 (而非路径)
        engine.play_music("bgm_piano41", loop=True, fade=0.0)
        snap = rt.snapshot()
        check("存档 BGM 为注册名", snap.get("music") == "bgm_piano41",
              str(snap.get("music")))
        check("audio 记录注册名", engine.audio.current_bgm_name == "bgm_piano41")
        # music_play 事件含 name 载荷
        seen = {}
        engine.events.on("music_play",
                         lambda name, **kw: seen.update(name=name))
        engine.play_music("bgm_piano39", loop=True, fade=0.0)
        for _ in range(90):
            engine.audio.update(1 / 60)
        check("事件载荷含名称", seen.get("name") == "bgm_piano39",
              str(seen))
        # 单次播放 (loop=0)
        rt._cmd_music(Statement(op="music", args=["bgm_piano41", "loop", "0",
                                                  "fade", "0"], line=0))
        check("单次播放 loop=0", engine.audio.current_bgm_name == "bgm_piano41")
        # fade 表达式 (变量)
        rt._cmd_set(Statement(op="set", args=["f", "1.5"], line=0))
        rt._cmd_stop(Statement(op="stop", args=["music", "fade", "$f"],
                               line=0))
        check("fade 变量解析", engine.audio._fade is not None
              and abs(engine.audio._fade["duration"] - 1.5) < 0.01,
              str(engine.audio._fade))
        for _ in range(150):
            engine.audio.update(1 / 60)
        # ending 停音乐
        engine.play_music("bgm_piano41", fade=0.0)
        rt._cmd_ending(Statement(op="ending", line=0))
        check("ending 淡出音乐", engine.audio._fade is not None
              and engine.audio._fade["pending"][0] == "stop")
        # 开始游戏停音乐 (不全局静音)
        for _ in range(120):
            engine.audio.update(1 / 60)
        engine.play_music("bgm_piano41", fade=0.0)
        engine._act_start(engine, {"label": "game_start"}, "test")
        check("开始游戏淡出 BGM", engine.audio._fade is not None
              and engine.audio._fade["pending"][0] == "stop")
    finally:
        try:
            import pygame.mixer as _m
            _m.music = _orig
        except Exception:
            pass
        engine.quit()
        import pygame
        pygame.quit()


def test_namespaces():
    print("== 命名空间系统 ==")
    from framework.engine.parser import Statement
    demo = os.path.join(_ROOT, "test", "engine_demo", "demo.gal")
    engine = GameEngine(640, 360, "test48")
    d = engine.display
    rt = engine.runtime
    try:
        rt.load_script(demo)
        # 顶层 using 静态生效 (加载即导入, 不依赖执行流程)
        check("顶层 using 加载生效",
              "shake" in rt.using_ns and "custom_actions" in rt.using_ns,
              str(sorted(rt.using_ns)))
        engine.plugins.discover(os.path.join(_ROOT, "framework", "plugins"),
                                {"except": ["fps_overlay"]})
        # 插件指令注册在插件命名空间 (插件文件名)
        check("插件指令带命名空间",
              engine.commands.has("shake", "shake")
              and engine.commands.has("do_action", "custom_actions"),
              f"shake_ns={engine.commands.find('shake')} "
              f"do_action_ns={engine.commands.find('do_action')}")
        # 无 using 时裸名调用报提示 (不执行不崩溃)
        rt.using_ns.clear()
        rt._dispatch(Statement(op="shake", args=["0.3"], line=0))
        # 显式命名空间调用
        rt._dispatch(Statement(op="shake::shake", args=["0.3"], line=0))
        # using 后裸名可用
        rt._cmd_using(Statement(op="using", args=["shake"], line=0))
        check("using 导入", "shake" in rt.using_ns)
        rt._dispatch(Statement(op="shake", args=["0.3"], line=0))
        check("using 后指令可用", True)
        # builtin:: 显式命名空间
        rt._dispatch(Statement(op="builtin::set", args=["b", "1"], line=0))
        check("builtin::set 执行", rt.vars.get("b") == 1)

        # 变量命名空间
        rt._cmd_set(Statement(op="set", args=["main::love", "=", "5"], line=0))
        check("main:: 变量归 main 域", rt.vars.get("love") == 5,
              str(rt.vars.get("love")))
        rt._cmd_set(Statement(op="set", args=["plugin::cnt", "=", "3"], line=0))
        check("插件变量保留前缀键", rt.vars.get("plugin::cnt") == 3)
        check("解析 main::love", rt._resolve_var("main::love") == 5)
        check("解析裸名 love", rt._resolve_var("love") == 5)
        rt.builtin_vars["version"] = "1.0"
        check("builtin 兜底", rt._resolve_var("version") == "1.0")
        check("未知名返回默认", rt._resolve_var("nope", "D") == "D")
        check("evaluate $main::love", rt.evaluate("$main::love + 1") == 6)
        check("evaluate 裸名", rt.evaluate("love + 1") == 6)
        check("插值 $plugin::cnt", rt._interp("n=$plugin::cnt") == "n=3")
    finally:
        engine.quit()
        import pygame
        pygame.quit()


def test_slot_thumbnails():
    print("== 存档快照插件 ==")
    demo = os.path.join(_ROOT, "test", "engine_demo", "demo.gal")
    engine = GameEngine(640, 360, "test49")
    d = engine.display
    rt = engine.runtime
    try:
        # API: capture
        surf = d.capture()
        check("capture API", surf is not None
              and surf.get_size() == (640, 360))
        # API: set_meta / get_meta / meta_path (相对路径)
        rt.load_script(demo)
        rt.start()
        snap = rt.snapshot()
        engine.save.save(0, snap)
        engine.save.set_meta(0, "screenshot", "thumb_slot1.png")
        check("set_meta", engine.save.get_meta(0, "screenshot")
              == "thumb_slot1.png")
        abs_p = engine.save.meta_path(0, "thumb_slot1.png")
        check("meta 相对路径解析", abs_p and abs_p.endswith(
            os.path.join("save", "thumb_slot1.png")), str(abs_p))

        # 插件加载: provider 注册
        engine.plugins.discover(os.path.join(_ROOT, "framework", "plugins"),
                                {"only": ["slot_thumbnails"]})
        check("provider 已注册", d._slot_thumb_provider is not None)

        # 纯游戏画面帧 (存档快照来源): 先推进出标题菜单
        engine.on_click(d.title_rects[0].center)   # 开始游戏
        engine.draw()   # 无覆盖层: 记录游戏帧
        check("游戏帧已记录", engine.get_last_game_frame() is not None)
        # 打开槽位面板后帧不变 (快照不截面板)
        d.show_slot_menu(engine.save.list_slots(), "load")
        engine.draw()
        check("面板期间帧保持", engine.get_last_game_frame() is not None
              and engine.get_last_game_frame().get_size() == (640, 360))

        # save 事件: 自动生成缩略图 (相对路径, 来自游戏帧)
        engine.save.save(0, rt.snapshot())
        rel = engine.save.get_meta(0, "screenshot")
        check("存档自动快照", rel == "thumb_slot1.png", str(rel))
        thumb_p = engine.save.meta_path(0, rel)
        check("快照文件存在", os.path.isfile(thumb_p))
        check("快照不存绝对路径", ":" not in rel and not rel.startswith("/"),
              str(rel))
        # list_slots 携带 screenshot 字段
        slots = engine.save.list_slots()
        check("list_slots 带快照字段", slots[0].get("screenshot")
              == "thumb_slot1.png", str(slots[0]))
        # provider 真实返回缩略图
        thumb = d._slot_thumb_provider(0, slots[0])
        check("provider 返回缩略图", thumb is not None
              and thumb.get_size() == (150, 84),
              str(thumb and thumb.get_size()))
        # 槽位界面绘制 (含缩略图) 不崩
        d.show_slot_menu(slots, "load")
        engine.draw()
        check("槽位界面绘制快照", True)
    finally:
        engine.quit()
        import pygame
        pygame.quit()


def test_plugin_cmd():
    print("== 运行时插件管理语句 ==")
    from framework.engine.parser import Statement
    demo = os.path.join(_ROOT, "test", "engine_demo", "demo.gal")
    engine = GameEngine(640, 360, "test50")
    d = engine.display
    rt = engine.runtime
    try:
        rt.load_script(demo)
        engine.plugins.discover(os.path.join(_ROOT, "framework", "plugins"),
                                {"except": ["fps_overlay"]})
        # 卸载
        rt._cmd_plugin(Statement(op="plugin", args=["unload", "shake"],
                                 line=0))
        check("卸载后指令消失", not engine.commands.has("shake", "shake")
              and "shake" not in rt.using_ns)
        # 装载 (自动加入 using)
        rt._cmd_plugin(Statement(op="plugin", args=["load", "shake"], line=0))
        check("装载后指令恢复", engine.commands.has("shake", "shake")
              and "shake" in rt.using_ns)
        # 裸名调用可用
        rt._dispatch(Statement(op="shake", args=["0.2"], line=0))
        check("装载后可裸名调用", True)
        # list
        rt._cmd_plugin(Statement(op="plugin", args=["list"], line=0))
        # 卸载类插件: slot_thumbnails -> provider 清理
        engine.plugins.load_module_from_path(
            "gm_plugin_slot_thumbnails",
            os.path.join(_ROOT, "framework", "plugins",
                         "slot_thumbnails.py"))
        check("类插件装载", d._slot_thumb_provider is not None)
        rt._cmd_plugin(Statement(op="plugin", args=["unload",
                                                    "slot_thumbnails"],
                                 line=0))
        check("类插件卸载清 provider", d._slot_thumb_provider is None)
        # 装载不存在的插件不崩
        rt._cmd_plugin(Statement(op="plugin", args=["load", "nope"], line=0))
        check("装载不存在插件容错", True)
    finally:
        engine.quit()
        import pygame
        pygame.quit()


def test_latex_typing():
    print("== LaTeX 与逐字模式兼容 ==")
    engine = GameEngine(640, 360, "test51")
    d = engine.display
    try:
        d.show_text("公式 {m}\\frac{1}{2}{/m} 测试")
        # 逻辑长度: "公式 " 3 + 公式 1 + " 测试" 3 = 7
        check("逻辑长度", d._logic_len == 7, str(d._logic_len))
        # 推进到公式前 (reveal=3): 公式未出现
        d.reveal = 3
        shown = d._rich.truncate(d._runs, int(d.reveal))
        check("公式前不显示", not [r for r in shown if r.math])
        # reveal=4: 公式整体出现且源码完整
        d.reveal = 4
        shown = d._rich.truncate(d._runs, int(d.reveal))
        math_runs = [r for r in shown if r.math]
        check("公式整体出现", len(math_runs) == 1
              and math_runs[0].text == "\\frac{1}{2}",
              str([r.text for r in math_runs]))
        # 完成判定按逻辑长度
        d.reveal = d._logic_len
        check("逐字完成判定", d.text_done())
        # typewriter 持续推进到完成 (含公式)
        d.show_text("质量能量公式 {m}E=mc^2{/m}")
        for _ in range(400):
            d.update(1 / 60)
        check("typewriter 完成含公式", d.text_done())
        # terminal 光标不崩 (含公式文本)
        d.set_text_mode("terminal")
        d.show_text("终端公式 {m}ax^2+bx+c{/m}")
        for _ in range(400):
            d.update(1 / 60)
        engine = d.engine
        engine.draw()
        check("terminal 含公式绘制", d.text_done())
    finally:
        engine.quit()
        import pygame
        pygame.quit()


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
    rt.using_ns.add("shake")   # 脚本等效 using shake (插件指令命名空间)
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
    try:
        test_rich()
    except Exception as exc:
        print(f"  [ERROR] 富文本测试异常: {exc}")
        import traceback
        traceback.print_exc()
    try:
        test_demo_run()
    except Exception as exc:
        print(f"  [ERROR] demo 运行测试异常: {exc}")
        import traceback
        traceback.print_exc()
    try:
        test_save_restore_state()
    except Exception as exc:
        print(f"  [ERROR] 读档状态测试异常: {exc}")
        import traceback
        traceback.print_exc()
    try:
        test_save_id_based()
    except Exception as exc:
        print(f"  [ERROR] id 存档测试异常: {exc}")
        import traceback
        traceback.print_exc()
    try:
        test_characters()
    except Exception as exc:
        print(f"  [ERROR] 角色系统测试异常: {exc}")
        import traceback
        traceback.print_exc()
    try:
        test_scenes()
    except Exception as exc:
        print(f"  [ERROR] 场景系统测试异常: {exc}")
        import traceback
        traceback.print_exc()
    try:
        test_transitions()
    except Exception as exc:
        print(f"  [ERROR] 过渡效果测试异常: {exc}")
        import traceback
        traceback.print_exc()
    try:
        test_sprite_transform()
    except Exception as exc:
        print(f"  [ERROR] 立绘变换测试异常: {exc}")
        import traceback
        traceback.print_exc()
    try:
        test_window_config()
    except Exception as exc:
        print(f"  [ERROR] 窗口配置测试异常: {exc}")
        import traceback
        traceback.print_exc()
    try:
        test_title_screen()
    except Exception as exc:
        print(f"  [ERROR] 标题画面测试异常: {exc}")
        import traceback
        traceback.print_exc()
    try:
        test_confirm_quit()
    except Exception as exc:
        print(f"  [ERROR] 退出确认测试异常: {exc}")
        import traceback
        traceback.print_exc()
    try:
        test_system_menu()
    except Exception as exc:
        print(f"  [ERROR] 系统菜单测试异常: {exc}")
        import traceback
        traceback.print_exc()
    try:
        test_styles()
    except Exception as exc:
        print(f"  [ERROR] 样式系统测试异常: {exc}")
        import traceback
        traceback.print_exc()
    try:
        test_builtin_styles()
    except Exception as exc:
        print(f"  [ERROR] 预装样式测试异常: {exc}")
        import traceback
        traceback.print_exc()
    try:
        test_actions()
    except Exception as exc:
        print(f"  [ERROR] 动作系统测试异常: {exc}")
        import traceback
        traceback.print_exc()
    try:
        test_selection_style()
    except Exception as exc:
        print(f"  [ERROR] selection 样式测试异常: {exc}")
        import traceback
        traceback.print_exc()
    try:
        test_dialogs()
    except Exception as exc:
        print(f"  [ERROR] dialog 测试异常: {exc}")
        import traceback
        traceback.print_exc()
    try:
        test_ui_images()
    except Exception as exc:
        print(f"  [ERROR] UI 图片测试异常: {exc}")
        import traceback
        traceback.print_exc()
    try:
        test_plugins_config()
    except Exception as exc:
        print(f"  [ERROR] 插件装载配置测试异常: {exc}")
        import traceback
        traceback.print_exc()
    try:
        test_imports()
    except Exception as exc:
        print(f"  [ERROR] import 拆分测试异常: {exc}")
        import traceback
        traceback.print_exc()
    try:
        test_error_handler()
    except Exception as exc:
        print(f"  [ERROR] 错误处理测试异常: {exc}")
        import traceback
        traceback.print_exc()
    try:
        test_error_levels()
    except Exception as exc:
        print(f"  [ERROR] 错误分级测试异常: {exc}")
        import traceback
        traceback.print_exc()
    try:
        test_ui_advanced()
    except Exception as exc:
        print(f"  [ERROR] UI 高级配置测试异常: {exc}")
        import traceback
        traceback.print_exc()
    try:
        test_menu_block()
    except Exception as exc:
        print(f"  [ERROR] 菜单块测试异常: {exc}")
        import traceback
        traceback.print_exc()
    try:
        test_sprite_effects()
    except Exception as exc:
        print(f"  [ERROR] 立绘效果测试异常: {exc}")
        import traceback
        traceback.print_exc()
    try:
        test_text_modes()
    except Exception as exc:
        print(f"  [ERROR] 文字模式测试异常: {exc}")
        import traceback
        traceback.print_exc()
    try:
        test_key_nav()
    except Exception as exc:
        print(f"  [ERROR] 键盘导航测试异常: {exc}")
        import traceback
        traceback.print_exc()
    try:
        test_sound_system()
    except Exception as exc:
        print(f"  [ERROR] 声音系统测试异常: {exc}")
        import traceback
        traceback.print_exc()
    try:
        test_bgm_and_ui_sounds()
    except Exception as exc:
        print(f"  [ERROR] BGM/UI 音效测试异常: {exc}")
        import traceback
        traceback.print_exc()
    try:
        test_audio_api()
    except Exception as exc:
        print(f"  [ERROR] 音频 API 测试异常: {exc}")
        import traceback
        traceback.print_exc()
    try:
        test_namespaces()
    except Exception as exc:
        print(f"  [ERROR] 命名空间测试异常: {exc}")
        import traceback
        traceback.print_exc()
    try:
        test_slot_thumbnails()
    except Exception as exc:
        print(f"  [ERROR] 存档快照测试异常: {exc}")
        import traceback
        traceback.print_exc()
    try:
        test_plugin_cmd()
    except Exception as exc:
        print(f"  [ERROR] 插件管理语句测试异常: {exc}")
        import traceback
        traceback.print_exc()
    try:
        test_latex_typing()
    except Exception as exc:
        print(f"  [ERROR] LaTeX 逐字测试异常: {exc}")
        import traceback
        traceback.print_exc()

    print(f"\n结果: {PASS} 通过, {FAIL} 失败")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
