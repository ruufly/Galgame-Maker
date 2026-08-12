"""P2 测试: 定义管理器 (char/scene/sound 增删改 + 文件约定 + 往返)。

运行::

    py -3.10 editor/tests/p2_definitions_test.py
"""

import os
import shutil
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)

from framework.engine.parser import parse, parse_file
from editor.definitions import (add_def, def_file_for, find_def, iter_defs,
                                remove_def, update_def, char_expressions)
from editor.project_wizard import create_project
from editor.model import Project
from editor.project_settings import save_script
from editor.compare import roundtrip_ok

FAILURES: list = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print("  [OK]   %s" % name)
    else:
        FAILURES.append(name)
        print("  [FAIL] %s %s" % (name, detail))


def main() -> int:
    tmp = tempfile.mkdtemp(prefix="galmake_defs_")
    try:
        print("== P2 定义管理测试 ==")

        proj_dir = os.path.join(tmp, "proj")
        create_project("proj", proj_dir)
        project = Project(proj_dir).load()

        # 1. 文件约定
        check("char -> cast.gal", def_file_for("char") == "cast.gal")
        check("sound -> audio.gal", def_file_for("sound") == "audio.gal")

        # 2. 从 demo 模板读取现有定义
        cast = project.scripts["cast.gal"]
        chars = list(iter_defs(cast, "char"))
        scenes = list(iter_defs(cast, "scene"))
        check("模板有角色 (producer)", len(chars) == 1
              and chars[0].args[0] == "producer")
        check("模板有场景 (school)", len(scenes) == 1
              and scenes[0].args[0] == "school")
        check("读取立绘表情 (default/normal/happy)",
              {"default", "normal", "happy"} <= set(chars[0].kwargs))
        expr = char_expressions(chars[0])
        check("表情列表排除保留键", all(k not in
              ("name", "default", "voice_volume", "desc") for k, _v in expr))

        audio = project.scripts["audio.gal"]
        sounds = list(iter_defs(audio, "sound"))
        check("模板有声音 (sfx_click)", len(sounds) >= 1
              and any(s.args[0] == "sfx_click" for s in sounds))

        # 3. 新增角色 -> 写盘 -> 重载
        stmt = add_def(cast, "char", "new_girl", {
            "name": "新角色",
            "default": "materials/image/girl.png",
            "happy": "materials/image/girl_happy.png",
            "voice_volume": "0.8",
        })
        save_script(cast, os.path.join(proj_dir, "cast.gal"))
        cast2 = parse_file(os.path.join(proj_dir, "cast.gal"))
        found = find_def(cast2, "char", "new_girl")
        check("新增角色写盘", found is not None
              and found.kwargs.get("name") == "新角色")
        check("新增角色表情保留", found.kwargs.get("happy")
              == "materials/image/girl_happy.png")

        # 4. 更新角色 (整体替换 kwargs)
        update_def(found, {"name": "改名了", "default": "materials/x.png"})
        save_script(cast2, os.path.join(proj_dir, "cast.gal"))
        cast3 = parse_file(os.path.join(proj_dir, "cast.gal"))
        f2 = find_def(cast3, "char", "new_girl")
        check("更新角色", f2.kwargs == {"name": "改名了",
                                        "default": "materials/x.png"})

        # 5. 删除角色
        check("删除角色", remove_def(cast3, "char", "new_girl"))
        save_script(cast3, os.path.join(proj_dir, "cast.gal"))
        cast4 = parse_file(os.path.join(proj_dir, "cast.gal"))
        check("删除后不存在", find_def(cast4, "char", "new_girl") is None)
        check("原角色仍在", find_def(cast4, "char", "producer") is not None)

        # 6. 声音新增/删除
        audio2 = parse_file(os.path.join(proj_dir, "audio.gal"))
        add_def(audio2, "sound", "my_bgm", {"type": "music",
                                            "file": "materials/audio/bgm.mp3"})
        save_script(audio2, os.path.join(proj_dir, "audio.gal"))
        a3 = parse_file(os.path.join(proj_dir, "audio.gal"))
        check("新增声音", find_def(a3, "sound", "my_bgm").kwargs.get("type")
              == "music")
        check("删除声音", remove_def(a3, "sound", "my_bgm"))

        # 7. 全项目往返保真
        p2 = Project(proj_dir).load()
        check("往返保真", all(roundtrip_ok(s) for s in p2.scripts.values()))

        # 8. 合并加载仍正常
        from framework.engine.loader import load_script_with_imports
        merged = load_script_with_imports(os.path.join(proj_dir, "demo.gal"))
        check("合并加载", len(merged.labels) > 0)

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
