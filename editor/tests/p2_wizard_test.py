"""P2 测试: 新建项目向导核心逻辑 create_project()。

验证:
1. 模板复制完整 (脚本/素材/字体), 排除 save/logs/__pycache__
2. 项目身份替换: meta name / window title / language default / main.yml
3. 生成的项目可解析、可往返 (序列化保真)
4. 不复制素材时 materials 为空骨架
5. 目标目录非空时报错 / 非法项目名报错

运行::

    py -3.10 editor/tests/p2_wizard_test.py
"""

import os
import shutil
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)

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
    tmp = tempfile.mkdtemp(prefix="galmake_wizard_")
    try:
        print("== P2 新建项目向导测试 ==")

        # 1. 完整模板
        target = os.path.join(tmp, "我的第一个游戏")
        path = create_project("我的第一个游戏", target,
                              resolution=(1280, 720), language="zh-CN",
                              with_materials=True)
        check("目录创建", os.path.isdir(path))
        gals = [f for f in os.listdir(path) if f.endswith(".gal")]
        check("脚本齐全 (7 个)", len(gals) == 7, "got %s" % gals)
        check("素材已复制", os.path.isdir(os.path.join(path, "materials", "image")))
        check("字体已复制", os.path.isdir(os.path.join(path, "fonts")))
        check("无运行时产物",
              not os.path.exists(os.path.join(path, "save"))
              and not os.path.exists(os.path.join(path, "logs")))

        # 2. 身份替换
        project = Project(path).load()
        main = project.main_script()
        check("meta name 替换", main.meta.get("name") == "我的第一个游戏",
              "got %r" % main.meta.get("name"))
        title = None
        lang_default = None
        for stmt in main.statements:
            if stmt.op == "window" and not stmt.args:
                title = stmt.kwargs.get("title")
            elif stmt.op == "language":
                lang_default = stmt.kwargs.get("default")
        check("window title 替换", title == "我的第一个游戏", "got %r" % title)
        check("language default", lang_default == "zh-CN",
              "got %r" % lang_default)
        with open(os.path.join(path, "main.yml"), encoding="utf-8") as fh:
            check("main.yml name", "name: 我的第一个游戏" in fh.read())

        # 3. 往返保真
        ok = all(roundtrip_ok(s) for s in project.scripts.values())
        check("全部脚本往返保真", ok)

        # 4. 无素材模式
        target2 = os.path.join(tmp, "no_mats")
        path2 = create_project("no_mats", target2, with_materials=False)
        mats = os.path.join(path2, "materials")
        check("无素材: 目录为空骨架",
              os.path.isdir(os.path.join(mats, "image"))
              and os.path.isdir(os.path.join(mats, "audio"))
              and not [f for f in os.listdir(mats) if f != "image" and f != "audio"])

        # 5. 错误处理
        err = False
        try:
            create_project("x", tmp)  # 非空目录
        except FileExistsError:
            err = True
        check("非空目录报错", err)
        err = False
        try:
            create_project("bad/name!", os.path.join(tmp, "bad"))
        except ValueError:
            err = True
        check("非法项目名报错", err)

    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    if FAILURES:
        print("结果: %d 项失败 -> %s" % (len(FAILURES), FAILURES))
        return 1
    print("结果: 全部通过 ✓")
    return 0


if __name__ == "__main__":
    # os._exit: 跳过 pygame/SDL 解释器关闭时的 atexit 清理竞态
    os._exit(main())
