"""P2 测试: 素材库导入逻辑 (AssetPanel._import_files / categorize)。

不依赖 Qt 事件循环, 直接实例化面板调用导入函数。

运行::

    py -3.10 editor/tests/p2_assets_test.py
"""

import os
import shutil
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)

from PySide6.QtWidgets import QApplication

from editor.assets import AssetPanel, categorize
from editor.project_wizard import create_project

FAILURES: list = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print("  [OK]   %s" % name)
    else:
        FAILURES.append(name)
        print("  [FAIL] %s %s" % (name, detail))


def make_fake(src_dir: str) -> list:
    """生成各类假素材文件, 返回路径列表。"""
    paths = []
    for name, data in [("a.png", b"\x89PNG\r\n\x1a\nfake"),
                       ("b.wav", b"RIFFfake"),
                       ("c.ttf", b"fontfake"),
                       ("d.txt", b"other")]:
        p = os.path.join(src_dir, name)
        with open(p, "wb") as fh:
            fh.write(data)
        paths.append(p)
    return paths


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    tmp = tempfile.mkdtemp(prefix="galmake_assets_")
    try:
        print("== P2 素材导入测试 ==")

        check("分类: png -> image", categorize("x.png") == "image")
        check("分类: mp3 -> audio", categorize("x.mp3") == "audio")
        check("分类: otf -> font", categorize("x.otf") == "font")
        check("分类: txt -> other", categorize("x.txt") == "other")

        # 建一个无素材项目
        proj_dir = os.path.join(tmp, "proj")
        create_project("proj", proj_dir, with_materials=False)
        from editor.model import Project
        project = Project(proj_dir).load()

        panel = AssetPanel()
        panel.set_project(project)
        mats = os.path.join(proj_dir, "materials")

        # 导入
        src = os.path.join(tmp, "src")
        os.makedirs(src)
        files = make_fake(src)
        n = panel._import_files(files)
        check("导入 4 个文件", n == 4)
        check("png -> materials/image",
              os.path.isfile(os.path.join(mats, "image", "a.png")))
        check("wav -> materials/audio",
              os.path.isfile(os.path.join(mats, "audio", "b.wav")))
        check("ttf -> materials/font",
              os.path.isfile(os.path.join(mats, "font", "c.ttf")))
        check("txt -> materials/other",
              os.path.isfile(os.path.join(mats, "other", "d.txt")))

        # 重名自动改名
        n2 = panel._import_files([os.path.join(src, "a.png")])
        check("重名导入不覆盖", n2 == 1
              and os.path.isfile(os.path.join(mats, "image", "a_1.png")))

        # 刷新后列表数量
        panel.refresh()
        check("列表显示 5 项", panel.list.count() == 5,
              "got %d" % panel.list.count())

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
