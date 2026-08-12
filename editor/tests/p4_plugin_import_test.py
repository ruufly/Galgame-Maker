"""P4 测试: 插件导入 (.galpkg) 与注册生效。

运行::

    py -3.10 editor/tests/p4_plugin_import_test.py
"""

import os
import shutil
import sys
import tempfile
import zipfile

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)

import yaml

from editor.plugin_importer import import_plugin_package, load_plugin_editor_file
from editor.plugins_api import registry

FAILURES: list = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print("  [OK]   %s" % name)
    else:
        FAILURES.append(name)
        print("  [FAIL] %s %s" % (name, detail))


FW_IMPL = '''\
"""示例插件引擎侧实现。"""
from framework.api import command

@command("demo_boom")
def demo_boom(engine, stmt, **kw):
    engine.show_notice("boom!")
'''

ED_IMPL = '''\
"""示例插件编辑器接口。"""
from editor.plugins_api import registry


def setup(reg):
    p = reg.register_plugin("demo_pkg", meta={
        "name": "demo_pkg",
        "author": "测试",
        "description": "导入测试插件",
    })
    p.add_command("demo_boom", params=[("强度", "number", "1")])
    p.add_action("demo_action")
    p.add_setting("demo_speed", "演示速度", kind="slider", min=0, max=10)
'''


def build_galpkg(path, name="demo_pkg"):
    meta = {
        "name": name,
        "author": "测试作者",
        "description": "导入测试插件",
        "version": "1.0",
        "date": "2026-08-12",
        "copyright": "测试 2026",
        "framework": "gal_impl.py",
        "editor": "ed_impl.py",
    }
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("main.yml", yaml.safe_dump(meta, allow_unicode=True))
        zf.writestr("gal_impl.py", FW_IMPL)
        zf.writestr("ed_impl.py", ED_IMPL)
    return meta


def main() -> int:
    print("== P4 插件导入测试 ==")
    tmp = tempfile.mkdtemp(prefix="galmake_pkg_")
    try:
        # 隔离目录 (不污染真实 editor/plugins 与 framework/plugins)
        ed_dir = os.path.join(tmp, "editor_plugins")
        fw_dir = os.path.join(tmp, "framework_plugins")
        os.makedirs(ed_dir)
        os.makedirs(fw_dir)

        pkg = os.path.join(tmp, "demo_pkg.galpkg")
        meta = build_galpkg(pkg)

        result = import_plugin_package(pkg, ed_dir, fw_dir)
        check("返回 name", result["name"] == "demo_pkg")
        fw_file = os.path.join(fw_dir, "demo_pkg.py")
        ed_file = os.path.join(ed_dir, "demo_pkg.py")
        check("引擎侧文件就位", os.path.isfile(fw_file))
        check("编辑器文件就位", os.path.isfile(ed_file))
        with open(fw_file, encoding="utf-8") as f:
            check("引擎侧内容", "demo_boom" in f.read())

        # 加载编辑器接口 -> 注册生效
        loaded = load_plugin_editor_file(ed_file, meta=meta)
        check("接口加载注册", loaded == "demo_pkg"
              and registry.get("demo_pkg") is not None)
        if registry.get("demo_pkg") is not None:
            p = registry.get("demo_pkg")
            check("指令参数注册", p.commands.get("demo_boom")
                  == [("强度", "number", "1")])
            check("动作注册", "demo_action" in p.actions)
            check("设置项注册", "demo_speed" in p.settings)
            check("main.yml 元信息", p.meta.get("author") == "测试作者"
                  and p.meta.get("copyright") == "测试 2026")
        registry.unregister_plugin("demo_pkg")

        # 错误处理: 缺 main.yml / 非法名 / 声明文件缺失
        bad = os.path.join(tmp, "bad.galpkg")
        with zipfile.ZipFile(bad, "w") as zf:
            zf.writestr("x.py", "pass")
        err = False
        try:
            import_plugin_package(bad, ed_dir, fw_dir)
        except ValueError:
            err = True
        check("缺 main.yml 报错", err)

        bad2 = os.path.join(tmp, "bad2.galpkg")
        with zipfile.ZipFile(bad2, "w") as zf:
            zf.writestr("main.yml", yaml.safe_dump(
                {"name": "bad name!", "framework": "nope.py"}))
        err = False
        try:
            import_plugin_package(bad2, ed_dir, fw_dir)
        except ValueError:
            err = True
        check("非法名/缺文件报错", err)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        registry.unregister_plugin("demo_pkg")

    print()
    if FAILURES:
        print("结果: %d 项失败 -> %s" % (len(FAILURES), FAILURES))
        return 1
    print("结果: 全部通过 ✓")
    return 0


if __name__ == "__main__":
    os._exit(main())
