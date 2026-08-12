"""P3 测试: 编辑器国际化 (i18n)。

运行::

    py -3.10 editor/tests/p3_i18n_test.py
"""

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)

from editor.i18n import EditorI18n

FAILURES: list = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print("  [OK]   %s" % name)
    else:
        FAILURES.append(name)
        print("  [FAIL] %s %s" % (name, detail))


def main() -> int:
    import tempfile as _t
    print("== P3 编辑器 i18n 测试 ==")
    i18n = EditorI18n()
    # 隔离: 用临时配置路径, 避免污染/受污染真实用户配置
    i18n._config_path = os.path.join(_t.gettempdir(), "galmake_i18n_test.json")
    if os.path.isfile(i18n._config_path):
        os.remove(i18n._config_path)
    i18n.set_lang("zh-CN")

    check("默认中文", i18n.lang() == "zh-CN")
    check("中文查找", i18n.t("menu.file") == "文件(&F)")
    check("英文切换", i18n.set_lang("en") or i18n.lang() == "en")
    check("英文翻译", i18n.t("menu.file") == "&File")
    check("英文窗口标题", i18n.t("app.title") == "Galgame Maker Editor")

    # 回退: 缺 key -> zh-CN -> 原文
    check("未知 key 回退原文", i18n.t("no.such.key") == "no.such.key")

    # 格式化
    i18n.set_lang("zh-CN")
    s = i18n.t("status.project_open", path="/tmp/x", n=5)
    check("格式化 {path}/{n}", s == "项目已打开: /tmp/x (5 个脚本)",
          "got %r" % s)

    # 非法语言回退
    i18n.set_lang("xx")
    check("非法语言回退 zh-CN", i18n.lang() == "zh-CN")

    print()
    if FAILURES:
        print("结果: %d 项失败 -> %s" % (len(FAILURES), FAILURES))
        return 1
    print("结果: 全部通过 ✓")
    return 0


if __name__ == "__main__":
    os._exit(main())
