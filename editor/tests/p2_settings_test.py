"""P2 测试: 项目设置 (window 块) 读写逻辑。

验证 get_window_block / apply_window_values / save_script:
1. 找到主 window 块并读取关键键
2. 修改值 -> 序列化 -> 再解析 -> 值一致 (往返保真)
3. 写盘后重新加载项目, 模型可见新值
4. 无 window 块脚本: 新建块插入 import 之前

运行::

    py -3.10 editor/tests/p2_settings_test.py
"""

import os
import shutil
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)

from framework.engine.parser import parse, parse_file, Statement
from editor.project_settings import (apply_window_values, get_window_block,
                                     save_script)
from editor.project_wizard import create_project
from editor.model import Project
from editor.compare import roundtrip_ok

FAILURES: list = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print("  [OK]   %s" % name)
    else:
        FAILURES.append(name)
        print("  [FAIL] %s %s" % (name, detail))


def main() -> int:
    tmp = tempfile.mkdtemp(prefix="galmake_settings_")
    try:
        print("== P2 项目设置测试 ==")

        proj_dir = os.path.join(tmp, "proj")
        create_project("proj", proj_dir, language="zh-CN")
        project = Project(proj_dir).load()
        main = project.main_script()
        main_path = os.path.join(proj_dir, project.main)

        # 1. 读取
        block = get_window_block(main)
        check("找到 window 块", block is not None)
        check("读取 title", block.kwargs.get("title") == "proj",
              "got %r" % block.kwargs.get("title"))
        check("读取 save_slots", block.kwargs.get("save_slots") == "12")
        check("读取 confirm_quit_text (含 {@key})",
              block.kwargs.get("confirm_quit_text") == "{@dialog.quit.text}")

        # 2. 修改 -> 写盘 -> 再解析
        apply_window_values(block, {
            "title": "改过的标题",
            "width": "1600", "height": "900",
            "save_slots": "6",
            "fullscreen": "true",
            "music_fade": "0.5",
        })
        save_script(main, main_path)

        re = parse_file(main_path)
        b2 = get_window_block(re)
        check("写盘后 title", b2.kwargs.get("title") == "改过的标题")
        check("写盘后 分辨率", b2.kwargs.get("width") == "1600"
              and b2.kwargs.get("height") == "900")
        check("写盘后 save_slots", b2.kwargs.get("save_slots") == "6")
        check("写盘后 fullscreen", b2.kwargs.get("fullscreen") == "true")
        check("写盘后 music_fade", b2.kwargs.get("music_fade") == "0.5")
        check("其余键保留 (confirm_quit_text)",
              b2.kwargs.get("confirm_quit_text") == "{@dialog.quit.text}")

        # 3. 重新加载模型可见 + 往返保真
        project2 = Project(proj_dir).load()
        b3 = get_window_block(project2.main_script())
        check("模型重载可见新值", b3.kwargs.get("title") == "改过的标题")
        check("往返保真", all(roundtrip_ok(s) for s in project2.scripts.values()))

        # 4. 无 window 块: 新建块插入 import 前
        text = ('name: bare\n\nimport "a.gal"\nimport "b.gal"\n\n'
                "start:\n    text \"hi\"\n")
        s = parse(text, "bare.gal")
        assert get_window_block(s) is None
        from framework.engine.parser import Statement
        nb = Statement(op="window", args=[], kwargs={"title": "新窗口"})
        insert_at = 0
        for i, st in enumerate(s.statements):
            if st.op == "import":
                insert_at = i
                break
        s.statements.insert(insert_at, nb)
        save_script(s, os.path.join(tmp, "bare.gal"))
        s2 = parse_file(os.path.join(tmp, "bare.gal"))
        check("新 window 块插入 import 前",
              s2.statements[0].op == "window"
              and s2.statements[0].kwargs.get("title") == "新窗口"
              and s2.statements[1].op == "import")
        check("标签内容保留", "hi" in s2.labels["start"][0].args[0])

    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    if FAILURES:
        print("结果: %d 项失败 -> %s" % (len(FAILURES), FAILURES))
        return 1
    print("结果: 全部通过 ✓")
    return 0


if __name__ == "__main__":
    os._exit(main())
