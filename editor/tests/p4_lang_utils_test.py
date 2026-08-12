"""P4 测试: 项目多语言文本 (GameLang) — 占位符解析/回退/编辑/落盘。"""

import os
import shutil
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)

from framework.engine.parser import parse
from editor.lang_utils import GameLang

FAILURES: list = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print("  [OK]   %s" % name)
    else:
        FAILURES.append(name)
        print("  [FAIL] %s %s" % (name, detail))


def make_project(tmp: str) -> str:
    """构造最小项目: demo.gal (language 块) + lang/ 两语言文件。"""
    demo = os.path.join(tmp, "demo.gal")
    with open(demo, "w", encoding="utf-8") as fh:
        fh.write('language\n    default: zh-CN\n    zh-CN: "简体中文"\n'
                 '    en: "English"\n')
    os.makedirs(os.path.join(tmp, "lang"))
    with open(os.path.join(tmp, "lang", "zh-CN.json"), "w",
              encoding="utf-8") as fh:
        fh.write('{"welcome": "欢迎！", "love_high": "好感 $love"}')
    with open(os.path.join(tmp, "lang", "en.json"), "w",
              encoding="utf-8") as fh:
        fh.write('{"welcome": "Welcome!"}')
    return demo


def main() -> int:
    print("== 项目多语言文本 (GameLang) 测试 ==")
    tmp = tempfile.mkdtemp(prefix="galmake_lang_")
    try:
        demo = make_project(tmp)
        script = parse(open(demo, encoding="utf-8").read(), "demo.gal")
        gl = GameLang(tmp, script)

        check("语言列表 (zh-CN, en)", gl.langs == ["zh-CN", "en"],
              str(gl.langs))
        check("默认语言 zh-CN", gl.default == "zh-CN", gl.default)
        check("current = default", gl.current == "zh-CN", gl.current)

        # resolve: 当前语言
        check("resolve 中文", gl.resolve("你好 {@welcome}") == "你好 欢迎！")
        # 回退默认语言 (en 缺 key -> 默认 zh-CN)
        gl.current = "en"
        check("resolve 英文", gl.resolve("{@welcome}") == "Welcome!")
        check("缺 key 回退默认语言",
              gl.resolve("{@love_high}") == "好感 $love")
        # 完全缺失 -> 保留占位符
        check("未知 key 保留原文", gl.resolve("{@nope}") == "{@nope}")
        # 富文本标记不混淆
        gl.current = "zh-CN"
        check("富文本标记保留",
              gl.resolve("{c=#ff6600}{@welcome}{/c}") ==
              "{c=#ff6600}欢迎！{/c}")
        # $var 插值保留 (引擎运行时再插值)
        check("变量插值保留", gl.resolve("{@love_high}") == "好感 $love")

        # key_of / ensure_key
        check("key_of 识别占位符", gl.key_of("{@welcome}") == "welcome")
        check("key_of 非占位符 None", gl.key_of("你好") is None)
        new_text = gl.ensure_key("一段新台词")
        check("ensure_key 生成占位符", new_text == "{@t1}", new_text)
        check("新 key 写入当前语言", gl.text("t1") == "一段新台词")
        # 其它语言缺失时 text() 回退默认语言 (与引擎运行时行为一致)
        check("新 key 其它语言回退默认",
              gl.text("t1", "en") == "一段新台词")

        # set_text + 落盘 + 重新加载
        gl.set_text("t1", "en", "A new line")
        gl.save()
        gl2 = GameLang(tmp, script)
        check("落盘后重新加载 (zh)", gl2.text("t1") == "一段新台词")
        check("落盘后重新加载 (en)", gl2.text("t1", "en") == "A new line")

        # 无 language 块: 扫描 lang 目录
        tmp2 = tempfile.mkdtemp(prefix="galmake_lang2_")
        try:
            os.makedirs(os.path.join(tmp2, "lang"))
            with open(os.path.join(tmp2, "lang", "fr.json"), "w",
                      encoding="utf-8") as fh:
                fh.write('{"a": "bonjour"}')
            gl3 = GameLang(tmp2)
            check("无 language 块扫描目录", gl3.langs == ["fr"],
                  str(gl3.langs))
            check("目录语言加载", gl3.text("a") == "bonjour")
        finally:
            shutil.rmtree(tmp2, ignore_errors=True)
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
