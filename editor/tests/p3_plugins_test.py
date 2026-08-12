"""P3 测试: 插件能力注册表 (AST 扫描) + plugins 块配置。

运行::

    py -3.10 editor/tests/p3_plugins_test.py
"""

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)

from framework.engine.parser import parse, parse_file
from editor.plugins_registry import (scan_plugins_dir, scan_plugin_file,
                                     framework_plugins_dir)
from editor.project_settings import save_script

FAILURES: list = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print("  [OK]   %s" % name)
    else:
        FAILURES.append(name)
        print("  [FAIL] %s %s" % (name, detail))


def main() -> int:
    print("== P3 插件注册表测试 ==")
    fw = framework_plugins_dir()
    all_plugins = scan_plugins_dir(fw)
    names = set(all_plugins)
    check("发现全部内置插件 (8)", len(names) == 8,
          "got %s" % sorted(names))

    # fx: 指令 shake/flash/blackflash/tint/strobe/pulse
    fx = all_plugins.get("fx", {})
    check("fx 指令齐全", {"shake", "flash", "blackflash", "tint",
                          "strobe", "pulse"} <= set(fx.get("commands", [])),
          "got %s" % fx.get("commands"))

    # custom_actions: 指令 do_action + 动作 + 立绘效果 + 文字模式
    ca = all_plugins.get("custom_actions", {})
    check("custom_actions 指令 do_action",
          "do_action" in ca.get("commands", []),
          "got %s" % ca.get("commands"))
    check("custom_actions 动作", {"explode", "quake", "freeze",
                                  "blackout"} <= set(ca.get("actions", [])),
          "got %s" % ca.get("actions"))
    check("custom_actions 立绘效果",
          {"wobble", "sway"} <= set(ca.get("sprite_effects", [])),
          "got %s" % ca.get("sprite_effects"))
    check("custom_actions 文字模式",
          {"wave", "rainbow"} <= set(ca.get("text_modes", [])),
          "got %s" % ca.get("text_modes"))

    # transitions_plus: 过渡
    tp = all_plugins.get("transitions_plus", {})
    check("transitions_plus 过渡",
          {"wipe", "iris", "curtain"} <= set(tp.get("transitions", [])),
          "got %s" % tp.get("transitions"))

    # debug_mode: 快捷键 (debug_toggle)
    dm = all_plugins.get("debug_mode", {})
    check("debug_mode 快捷键",
          any(k == "debug_toggle" for k, _l in dm.get("keybinds", [])),
          "got %s" % dm.get("keybinds"))

    # gallery: 事件 script_block (自定义属性块解析)
    gl = all_plugins.get("gallery", {})
    check("gallery 监听 script_block",
          "script_block" in gl.get("events", []),
          "got %s" % gl.get("events"))
    check("gallery 动作 gallery_open",
          "gallery_open" in gl.get("actions", []))

    # 无效文件安全
    import tempfile, os as _os
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False,
                                     encoding="utf-8") as f:
        f.write("this is not valid python {{{")
        bad = f.name
    check("非法源码安全返回 None", scan_plugin_file(bad) is None)
    _os.unlink(bad)

    # plugins 块配置读写 (模型 + 序列化)
    text = (
        "plugins\n"
        "    only: \"fx, notice\"\n"
        "\n"
        "start:\n"
        "    text \"hi\"\n"
    )
    s = parse(text, "demo.gal")
    block = next(st for st in s.statements if st.op == "plugins")
    check("plugins 块读取 only", block.kwargs.get("only") == "fx, notice")
    block.kwargs["only"] = "fx, custom_actions"
    import tempfile as _t, shutil
    tmp = _t.mkdtemp(prefix="galmake_plug_")
    try:
        save_script(s, _os.path.join(tmp, "demo.gal"))
        s2 = parse_file(_os.path.join(tmp, "demo.gal"))
        b2 = next(st for st in s2.statements if st.op == "plugins")
        check("plugins 块写回", b2.kwargs.get("only")
              == "fx, custom_actions")
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
