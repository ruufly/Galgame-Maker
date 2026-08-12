"""P0 往返测试: 解析 -> 序列化 -> 再解析, 结构必须等价。

覆盖:
1. test/engine_demo 全部 .gal 文件
2. 合成样例: window config / menu / settings / if-elif-else / choice /
   set / python:: raw / -> 绑定 / language / gallery / style / import
3. 集成: 重新生成全部文件到临时目录, 用 loader 合并加载,
   对比合并后的 statements + labels 结构

运行::

    py -3.10 editor/tests/roundtrip_test.py
"""

import os
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)

from framework.engine.parser import Script, Statement, parse, parse_file
from framework.engine.loader import load_script_with_imports
from editor.serializer import serialize
from editor.compare import norm_script

DEMO_DIR = os.path.join(_ROOT, "test", "engine_demo")

FAILURES: list = []


# ----------------------------------------------------------------------
def roundtrip_file(rel: str) -> str:
    path = os.path.join(DEMO_DIR, rel)
    a = parse_file(path)
    text = serialize(a)
    b = parse(text, path)
    if norm_script(a) != norm_script(b):
        FAILURES.append(rel)
        print("  [FAIL] %s 结构不一致" % rel)
    else:
        print("  [OK]   %s  (%d 语句, %d 标签)" % (rel, len(a.statements), len(a.labels)))
    return text


SYNTHETIC = '''\
name: synthetic
author: test

window
    title: "测试项目"
    width: 1280
    height: 720
    save_slots: 12
    confirm_quit_text: "{@dialog.quit.text}"
    key_up: "up, w"

window config
    title: "运行时标题"
    fullscreen: false

language
    default: en
    en: "English"
    zh-CN: "简体中文"

plugins
    only: "fx, notice"

import "story.gal"

gallery
    unlock_ending: "{@ending.true_end}"
    categories: "cg, bgm"

style custom
    textbox_bg: "#1a1a2e"
    text_size: 28
    font: "ui"

menu title
    ui_hover_sound: "sfx_hover"
    ui_click_sound: "sfx_click"
    start_button
        text: "开始游戏"
        image: "默认.png, 焦点.png"
        width: 262
        stretch: false
        action: start game_start
    gallery_button
        text: "鉴赏"
        action: gallery_open
        image_disabled: "off.png"

settings
    title: "设置"
    columns: 2
    setting bgm_volume
        label: "音乐音量"
        type: slider
    setting voice:producer
        label: "制作人语音"
        section: "语音"

char producer
    name: "制作人"
    default: "materials/char/producer1.png"
    happy: "materials/char/producer2.png"
    voice_volume: 0.6

scene school
    name: "学校"
    default: "materials/image/bg.png"
    morning: "materials/image/bg.png"

sound sfx_click
    type: sfx_ui
    file: "materials/audio/sfx_click.wav"
    volume: 0.6

start:
    set love = 0
    set name = "小明"
    if love > 0 and name == '小明':
        text "好感度高"
        music bgm_piano41 fade 1.0
    elif love == 0:
        text "中立"
    else:
        text "好感度低"
    endif
    choice:
        "选项一" -> label_a
        "选项二" -> label_b
    jump label_a
    python::
        import random
        engine.set_var("luck", random.randint(1, 100))
    say producer "你好, $name"
    ending 真结局

label_a:
    text "分支A"
    -> bg1

label_b:
    nar "{@love_high}"
'''


def roundtrip_synthetic() -> None:
    a = parse(SYNTHETIC, "synthetic.gal")
    text = serialize(a)
    b = parse(text, "synthetic.gal")
    if norm_script(a) != norm_script(b):
        FAILURES.append("synthetic")
        print("  [FAIL] synthetic 结构不一致")
        print("--- 序列化输出 ---")
        print(text)
    else:
        print("  [OK]   synthetic (%d 语句, %d 标签)" % (len(a.statements), len(a.labels)))


def roundtrip_merged() -> None:
    """把全部重新生成的 demo 文件写进临时目录, loader 合并加载对比。"""
    gals = sorted(f for f in os.listdir(DEMO_DIR) if f.endswith(".gal"))
    with tempfile.TemporaryDirectory() as tmp:
        for rel in gals:
            a = parse_file(os.path.join(DEMO_DIR, rel))
            with open(os.path.join(tmp, rel), "w", encoding="utf-8") as fh:
                fh.write(serialize(a))
        m_orig = load_script_with_imports(os.path.join(DEMO_DIR, "demo.gal"))
        m_new = load_script_with_imports(os.path.join(tmp, "demo.gal"))
        if norm_script(m_orig) != norm_script(m_new):
            FAILURES.append("merged")
            print("  [FAIL] 合并加载结构不一致")
        else:
            print("  [OK]   合并加载一致: %d 顶层语句, %d 标签"
                  % (len(m_new.statements), len(m_new.labels)))


def main() -> None:
    print("== P0 往返测试 ==")
    gals = sorted(f for f in os.listdir(DEMO_DIR) if f.endswith(".gal"))
    print("[1/3] engine_demo 文件往返")
    for rel in gals:
        roundtrip_file(rel)
    print("[2/3] 合成样例往返")
    roundtrip_synthetic()
    print("[3/3] 合并加载集成")
    roundtrip_merged()

    print()
    if FAILURES:
        print("结果: %d 项失败 -> %s" % (len(FAILURES), FAILURES))
        sys.exit(1)
    print("结果: 全部通过 ✓")
    sys.exit(0)


if __name__ == "__main__":
    main()
