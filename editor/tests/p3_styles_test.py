"""P3 测试: 样式编辑器核心逻辑 (style 块读写)。

运行::

    py -3.10 editor/tests/p3_styles_test.py
"""

import os
import shutil
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)

from framework.engine.parser import parse, parse_file
from editor.styles_editor import (apply_style_values, ensure_style_block,
                                  get_style_block, _DEFAULTS)
from editor.project_settings import save_script
from editor.compare import roundtrip_ok

FAILURES: list = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print("  [OK]   %s" % name)
    else:
        FAILURES.append(name)
        print("  [FAIL] %s %s" % (name, detail))


UI_GAL = '''\
use style modern

style custom
    textbox_bg: "#1a1a2e"
    textbox_alpha: 210
    text_color: "#eaeaea"
    text_size: 28
    speaker_color: "#ffd282"

menu title
    start_button
        text: "开始游戏"
        action: start game_start
'''


def main() -> int:
    print("== P3 样式编辑器测试 ==")

    # 1. 读取现有 style 块
    s = parse(UI_GAL, "ui.gal")
    stmt = get_style_block(s)
    check("找到 style 块", stmt is not None and stmt.args[0] == "custom")
    check("读取 textbox_bg", stmt.kwargs.get("textbox_bg") == "#1a1a2e")
    check("读取 text_size", stmt.kwargs.get("text_size") == "28")

    # 2. 整体替换 + 写盘 + 再解析
    values = {"textbox_bg": "#ff0000", "textbox_alpha": "180",
              "text_color": "#00ff00", "text_size": "32",
              "font": "sys:Microsoft YaHei"}
    apply_style_values(stmt, values)
    tmp = tempfile.mkdtemp(prefix="galmake_style_")
    try:
        save_script(s, os.path.join(tmp, "ui.gal"))
        s2 = parse_file(os.path.join(tmp, "ui.gal"))
        b2 = get_style_block(s2)
        check("写盘后 textbox_bg", b2.kwargs.get("textbox_bg") == "#ff0000")
        check("写盘后 font", b2.kwargs.get("font") == "sys:Microsoft YaHei")
        check("旧键已替换 (无残留)",
              "text_size" in b2.kwargs and b2.kwargs["text_size"] == "32")
        check("往返保真", roundtrip_ok(s2))
        # 菜单块不受影响
        check("菜单块保留", any(st.op == "menu" for st in s2.statements))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # 3. 无 style 块: ensure 新建
    s3 = parse('name: bare\n\nstart:\n    text "hi"\n', "bare.gal")
    check("无 style 块", get_style_block(s3) is None)
    st3 = ensure_style_block(s3, "custom")
    check("ensure 新建", st3 is not None and st3.args[0] == "custom"
          and st3 in s3.statements)
    check("再 ensure 复用", ensure_style_block(s3, "custom") is st3)

    # 4. 默认值表完整 (所有字段有默认)
    check("默认值表完整", set(_DEFAULTS) ==
          {k for k, _l, _t in __import__(
              "editor.styles_editor", fromlist=["STYLE_FIELDS"]).STYLE_FIELDS})

    print()
    if FAILURES:
        print("结果: %d 项失败 -> %s" % (len(FAILURES), FAILURES))
        return 1
    print("结果: 全部通过 ✓")
    return 0


if __name__ == "__main__":
    os._exit(main())
