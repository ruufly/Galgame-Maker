"""P3 测试: 编译打包 (export_project_zip)。

运行::

    py -3.10 editor/tests/p3_build_test.py
"""

import os
import shutil
import sys
import tempfile
import zipfile

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)

from editor.build import export_project_zip
from editor.project_wizard import create_project

FAILURES: list = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print("  [OK]   %s" % name)
    else:
        FAILURES.append(name)
        print("  [FAIL] %s %s" % (name, detail))


def main() -> int:
    tmp = tempfile.mkdtemp(prefix="galmake_build_")
    try:
        print("== P3 编译打包测试 ==")
        proj = os.path.join(tmp, "proj")
        create_project("proj", proj)
        # 制造运行时产物 (应被排除)
        os.makedirs(os.path.join(proj, "save"))
        os.makedirs(os.path.join(proj, "logs"))
        with open(os.path.join(proj, "save", "slot0.json"), "w") as f:
            f.write("{}")
        with open(os.path.join(proj, "logs", "engine.log"), "w") as f:
            f.write("x")

        dest = os.path.join(tmp, "proj.zip")
        n = export_project_zip(proj, dest)
        check("zip 已生成", os.path.isfile(dest))
        check("打包文件数 > 10", n > 10, "got %d" % n)
        with zipfile.ZipFile(dest) as zf:
            names = zf.namelist()
        check("含脚本 story.gal", any(x.endswith("story.gal") for x in names))
        check("含素材 materials", any("materials" in x for x in names))
        check("含字体 fonts", any("fonts" in x for x in names))
        check("排除 save/", not any(x.startswith("save") for x in names))
        check("排除 logs/", not any(x.startswith("logs") for x in names))
        check("排除 __pycache__",
              not any("__pycache__" in x for x in names))
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
