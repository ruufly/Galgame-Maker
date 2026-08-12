"""P3 测试: 插件注册中心 (editor/plugins 接口主动注册)。

运行::

    py -3.10 editor/tests/p3_plugins_test.py
"""

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)

import editor.plugins  # noqa: F401  加载内置 8 个编辑器接口
from editor.plugins_api import registry

FAILURES: list = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print("  [OK]   %s" % name)
    else:
        FAILURES.append(name)
        print("  [FAIL] %s %s" % (name, detail))


def main() -> int:
    print("== P3 插件注册中心测试 ==")

    # 1. 内置 8 插件全部注册
    names = set(registry.plugins())
    check("内置插件全注册 (8)", len(names) == 8,
          "got %s" % sorted(names))
    check("含 fx/custom_actions/transitions_plus",
          {"fx", "custom_actions", "transitions_plus",
           "gallery", "auto_skip"} <= names)

    # 2. fx: 指令 + 参数表单 (API 注册)
    fx = registry.get("fx")
    check("fx 指令齐全", {"shake", "flash", "blackflash", "tint",
                          "strobe", "pulse"} <= set(fx.commands))
    check("shake 参数表单", fx.commands["shake"][0][0] == "时长 (秒)"
          and fx.commands["shake"][1][2] == "8")
    check("tint 双参数", len(fx.commands["tint"]) == 2)

    # 3. custom_actions: 指令/动作/立绘效果/文字模式
    ca = registry.get("custom_actions")
    check("do_action 指令", "do_action" in ca.commands)
    check("动作 4 项", {"explode", "quake", "freeze",
                        "blackout"} <= set(ca.actions))
    check("立绘效果", {"wobble", "sway"} <= set(ca.sprite_effects))
    check("文字模式", {"wave", "rainbow"} <= set(ca.text_modes))

    # 4. transitions_plus: 过渡
    tp = registry.get("transitions_plus")
    check("过渡", {"wipe", "iris", "curtain"} <= set(tp.transitions))

    # 5. debug_mode: 快捷键
    dm = registry.get("debug_mode")
    check("debug_mode 快捷键",
          any(k == "debug_toggle" for k, _l in dm.keybinds))

    # 6. gallery: 动作 + 事件
    gl = registry.get("gallery")
    check("gallery_open 动作", "gallery_open" in gl.actions)
    check("script_block 事件", "script_block" in gl.events)

    # 7. 注册中心查询 API
    check("namespaces (fx/custom_actions)",
          set(registry.namespaces()) == {"fx", "custom_actions"})
    check("actions 聚合含 auto_toggle/gallery_open",
          "auto_toggle" in registry.actions()
          and "gallery_open" in registry.actions())
    check("text_modes 聚合含 wave",
          "wave" in registry.text_modes())
    check("command_params 查询",
          registry.command_params("shake") is not None
          and registry.command_params("unknown") is None)
    check("元信息存在 (fx)",
          registry.get("fx").meta.get("description", "") != "")

    # 8. 运行时注册/注销
    reg2 = registry.register_plugin("_tmp_test", meta={"description": "t"})
    reg2.add_command("tmp_cmd", params=[("x", "number", "1")])
    check("运行时注册生效",
          registry.command_params("tmp_cmd") == [("x", "number", "1")])
    registry.unregister_plugin("_tmp_test")
    check("注销清理", registry.get("_tmp_test") is None)

    print()
    if FAILURES:
        print("结果: %d 项失败 -> %s" % (len(FAILURES), FAILURES))
        return 1
    print("结果: 全部通过 ✓")
    return 0


if __name__ == "__main__":
    os._exit(main())
