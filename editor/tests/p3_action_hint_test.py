"""P3 测试: action 节点参数提示 (action_edit_spec)。

运行::

    py -3.10 editor/tests/p3_action_hint_test.py
"""

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)

import editor.plugins  # noqa: F401  内置接口注册
from editor.flow_editor import action_edit_spec, collect_plugin_caps

FAILURES: list = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print("  [OK]   %s" % name)
    else:
        FAILURES.append(name)
        print("  [FAIL] %s %s" % (name, detail))


def main() -> int:
    print("== P3 action 参数提示测试 ==")
    caps = collect_plugin_caps()   # 内置插件

    # do_action: 内核动作 + 插件动作
    spec = action_edit_spec("do_action", caps)
    check("do_action 有表单", spec is not None and spec[0] == "combo")
    cands = spec[1][1] if spec else []
    check("候选含内核动作", "quit" in cands and "slot_menu" in cands)
    check("候选含插件动作 (explode/auto_toggle)",
          "explode" in cands and "auto_toggle" in cands)
    check("候选去重", len(cands) == len(set(cands)))

    # typing: 内核 4 + 插件文字模式
    spec = action_edit_spec("typing", caps)
    cands = spec[1][1] if spec else []
    check("typing 候选含内核", all(m in cands for m in
          ("typewriter", "instant", "terminal", "lines")))
    check("typing 候选含插件 (wave/rainbow)",
          "wave" in cands and "rainbow" in cands)

    # using: 插件命名空间
    spec = action_edit_spec("using", caps)
    cands = spec[1][1] if spec else []
    check("using 候选含插件", "fx" in cands and "custom_actions" in cands)

    # plugin: 插件名
    spec = action_edit_spec("plugin", caps)
    check("plugin 表单", spec is not None and spec[0] == "plugin")
    cands = spec[1][1] if spec else []
    check("plugin 候选 (8 内置)", len(cands) >= 8)

    # 内核简单指令表单
    spec = action_edit_spec("sleep", caps)
    check("sleep 表单", spec is not None and spec[0] == "combo")
    spec = action_edit_spec("volume", caps)
    check("volume 表单", spec is not None and spec[0] == "volume"
          and spec[1][1] == ["music", "sfx", "voice"])
    spec = action_edit_spec("fullscreen", caps)
    check("fullscreen 表单", spec is not None
          and spec[1][1] == ["true", "false"])
    spec = action_edit_spec("fade", caps)
    check("fade none 表单", spec is not None and spec[0] == "none")

    # 内置插件指令参数表 (fx)
    spec = action_edit_spec("shake", caps)
    check("shake 参数表单", spec is not None and spec[0] == "params")
    fields = spec[1][1] if spec else []
    check("shake 双参数 (时长/幅度)", len(fields) == 2
          and fields[0][2] == "0.3" and fields[1][2] == "8")
    spec = action_edit_spec("tint", caps)
    check("tint 参数表单 (颜色/时长)", spec is not None
          and len(spec[1][1]) == 2)
    spec = action_edit_spec("flash", caps)
    check("flash 单参数", spec is not None and len(spec[1][1]) == 1)

    # API 注册驱动: 插件经编辑器接口注册参数表单
    from editor.plugins_api import registry
    demo = registry.register_plugin("_demo_fx")
    demo.add_command("my_fx", params=[("强度", "number", "1"),
                                      ("颜色", "color", "255,0,0")])
    caps = collect_plugin_caps()
    spec = action_edit_spec("my_fx", caps)
    check("API 注册参数出表单", spec is not None
          and spec[0] == "params"
          and len(spec[1][1]) == 2)
    registry.unregister_plugin("_demo_fx")
    check("注销后回到只读",
          action_edit_spec("my_fx", collect_plugin_caps()) is None)

    # 未知指令 -> 只读
    check("未知指令返回 None", action_edit_spec("music", caps) is None)
    check("未知指令返回 None (xxx)", action_edit_spec("xxx", caps) is None)

    print()
    if FAILURES:
        print("结果: %d 项失败 -> %s" % (len(FAILURES), FAILURES))
        return 1
    print("结果: 全部通过 ✓")
    return 0


if __name__ == "__main__":
    os._exit(main())
