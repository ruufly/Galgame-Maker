"""P3 测试: 插件设置项可视化 (AST detail 提取 + setting.gal 生成)。

运行::

    py -3.10 editor/tests/p3_plugin_settings_test.py
"""

import os
import shutil
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)

from framework.engine.parser import parse, parse_file
from editor.plugins_registry import scan_plugin_source
from editor.plugin_settings import (add_plugin_settings, ensure_setting_item,
                                    settings_block_of)
from editor.project_settings import save_script

FAILURES: list = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print("  [OK]   %s" % name)
    else:
        FAILURES.append(name)
        print("  [FAIL] %s %s" % (name, detail))


PLUGIN_SRC = '''\
"""测试插件: 注册设置项。"""
from framework.api import Plugin

class MyPlugin(Plugin):
    name = "my_plugin"
    version = "1.0"

    def on_load(self):
        self.engine.settings.register(
            "my_slider",
            label="自定滑条",
            kind="slider",
            var="my_val",
            default=50,
            min=0,
            max=100,
            step=5,
            section="游戏",
        )
        self.engine.settings.register(
            "my_choice",
            label="自定选择",
            kind="cycle",
            options=["红", "绿", "蓝"],
        )
        self.engine.settings.register("plain_toggle", "简单开关")
'''


def main() -> int:
    print("== P3 插件设置项测试 ==")

    cap = scan_plugin_source(PLUGIN_SRC)
    check("发现 3 个设置项", len(cap["settings"]) == 3,
          "got %s" % cap["settings"])
    check("key/label 提取", ("my_slider", "自定滑条") in cap["settings"])
    check("无 label 用位置参数", ("plain_toggle", "简单开关")
          in cap["settings"])

    d = cap["settings_detail"].get("my_slider", {})
    check("kind 提取", d.get("kind") == "slider", "got %s" % d)
    check("数值参数提取", d.get("min") == 0 and d.get("max") == 100
          and d.get("step") == 5 and d.get("default") == 50)
    check("var/section 提取", d.get("var") == "my_val"
          and d.get("section") == "游戏")
    d2 = cap["settings_detail"].get("my_choice", {})
    check("options 提取", d2.get("options") == ["红", "绿", "蓝"],
          "got %s" % d2)

    # 生成: 无 settings 块 -> 新建
    tmp = tempfile.mkdtemp(prefix="galmake_plgset_")
    try:
        text = 'name: demo\n\nimport "story.gal"\n\nstart:\n    text "hi"\n'
        s = parse(text, "demo.gal")
        caps = {"my_plugin": cap}
        added = add_plugin_settings(s, caps)
        check("无 settings 块时新建并添加 3 项", len(added) == 3,
              "got %s" % added)
        block = settings_block_of(s)
        check("settings 块在 import 前",
              s.statements.index(block) < s.statements.index(
                  next(st for st in s.statements if st.op == "import")))
        keys = [it.args[0] for it in block.block]
        check("子块 key 齐全", set(keys) == {"my_slider", "my_choice",
                                             "plain_toggle"})
        slider = next(it for it in block.block if it.args[0] == "my_slider")
        check("slider 子块属性", slider.kwargs.get("type") == "slider"
              and slider.kwargs.get("min") == "0"
              and slider.kwargs.get("max") == "100"
              and slider.kwargs.get("step") == "5"
              and slider.kwargs.get("default") == "50"
              and slider.kwargs.get("section") == "游戏"
              and slider.kwargs.get("var") == "my_val")
        choice = next(it for it in block.block
                      if it.args[0] == "my_choice")
        check("cycle options 字符串化",
              choice.kwargs.get("options") == "红, 绿, 蓝")

        # 写盘 -> 再解析 -> 幂等 (不重复添加)
        save_script(s, os.path.join(tmp, "setting.gal"))
        s2 = parse_file(os.path.join(tmp, "setting.gal"))
        added2 = add_plugin_settings(s2, caps)
        check("二次生成无新增", added2 == [])
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
