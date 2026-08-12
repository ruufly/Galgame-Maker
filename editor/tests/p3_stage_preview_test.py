"""P3 测试: 场景分镜引擎预览 (build_stage_script + 真实渲染)。

运行::

    py -3.10 editor/tests/p3_stage_preview_test.py
"""

import os
import shutil
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from PySide6.QtWidgets import QApplication

from framework.engine.parser import parse
from editor.stage_preview import build_stage_script, StagePreviewDialog
from editor.flow import FlowGraph
from editor.project_wizard import create_project
from editor.model import Project
from editor.preview import EnginePreviewThread

FAILURES: list = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print("  [OK]   %s" % name)
    else:
        FAILURES.append(name)
        print("  [FAIL] %s %s" % (name, detail))


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    print("== P3 场景分镜引擎预览测试 ==")

    tmp = tempfile.mkdtemp(prefix="galmake_stagepv_")
    try:
        proj_dir = os.path.join(tmp, "proj")
        create_project("proj", proj_dir)
        project = Project(proj_dir).load()

        # 构造 stage 节点 (school + producer 立绘)
        g = FlowGraph.from_script(project.scripts["story.gal"])
        stage = g.add_node("stage", data={
            "bg": ["school", "", "fade"],
            "sprites": [["show", "producer", "normal", "slide_right"],
                        ["hide", "producer", "", "slide_left"]],
        })

        text = build_stage_script(project, stage)
        s = parse(text, "stage_preview.gal")
        body = s.labels["start"]
        ops = [st.op for st in body]
        check("脚本含 bg", "bg" in ops)
        check("脚本含 show", "show" in ops)
        check("脚本含 hide", "hide" in ops)
        check("脚本含 text", "text" in ops)
        check("脚本含 window 块", any(st.op == "window" for st in s.statements))
        bg = next(st for st in body if st.op == "bg")
        check("bg 用绝对路径", bg.args and ":" in bg.args[0],
              "got %s" % bg.args)
        show = next(st for st in body if st.op == "show")
        check("show 参数", show.args[:2] == ["producer", "normal"])

        # 真实渲染: 跑 25 帧取帧
        script_path = os.path.join(tmp, "stage_preview.gal")
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(text)
        thread = EnginePreviewThread(script_path)
        frames = []
        thread.frame_ready.connect(frames.append)
        thread.start()
        # 跨线程信号走 queued 连接, 需跑事件循环才能送达
        import time as _t
        deadline = _t.time() + 15
        while thread.isRunning() and _t.time() < deadline:
            app.processEvents()
            _t.sleep(0.05)
        app.processEvents()
        check("引擎渲染出帧", len(frames) >= 10, "got %d" % len(frames))
        if frames:
            size = frames[-1].size()
            check("帧尺寸 1280x720", size.width() == 1280
                  and size.height() == 720, "got %dx%d"
                  % (size.width(), size.height()))
        # 清理 (线程已结束, pygame 已 quit)
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
