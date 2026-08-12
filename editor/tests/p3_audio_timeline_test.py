"""P3 测试: 音乐轨时间线 (AudioTimeline 数据往返 + 排序)。

运行::

    py -3.10 editor/tests/p3_audio_timeline_test.py
"""

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)

from PySide6.QtCore import QPointF, Qt
from PySide6.QtWidgets import QApplication

from editor.audio_timeline import AudioTimeline

FAILURES: list = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print("  [OK]   %s" % name)
    else:
        FAILURES.append(name)
        print("  [FAIL] %s %s" % (name, detail))


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    print("== P3 音乐轨时间线测试 ==")

    tl = AudioTimeline()
    items = [["music", "bgm_piano41", "1", "1.0"],
             ["sfx", "sfx_boom", "", ""],
             ["volume", "voice", "producer", "0.8"],
             ["pause", "music", "", "0.5"]]
    tl.set_items(items)
    check("条目数", len(tl.items) == 4)

    # 数据往返 (含参数保留)
    back = tl.items_data()
    check("往返保留参数", back == items, "got %s" % back)

    # 轨分类
    check("music 归音乐轨", tl.items[0]["row"] == "music")
    check("sfx 归音效轨", tl.items[1]["row"] == "sfx")
    check("volume 归音量轨", tl.items[2]["row"] == "volume")
    check("pause 归控制轨", tl.items[3]["row"] == "control")

    # 拖拽排序: 模拟 mousePress/Move/Release
    tl.resize(800, 200)
    r0 = tl._block_rect(0)
    r3 = tl._block_rect(3)
    p = QPointF(r0.center().x(), r0.center().y())
    tl.mousePressEvent(_fake_event("press", p))
    # 移动到第 3 块位置 (循环触发交换)
    target = QPointF(r3.center().x(), r3.center().y())
    for _i in range(6):
        tl.mouseMoveEvent(_fake_event("move", target))
    tl.mouseReleaseEvent(_fake_event("release", target))
    ops = [d["op"] for d in tl.items]
    check("拖拽后 music 移到末尾", ops[-1] == "music", "ops=%s" % ops)

    # 删除选中
    tl.selected = 1
    tl.remove_selected()
    check("删除后 3 项", len(tl.items) == 3)

    # 编辑回写
    tl.set_item_data(0, ["music", "new_bgm", "0", "0.5"])
    check("编辑回写", tl.items_data()[0] == ["music", "new_bgm", "0", "0.5"])

    # 时间轴: 时长估算 / 布局累计 / 总时长
    tl2 = AudioTimeline()
    tl2.set_items([["music", "a", "1", ""],        # 默认 3s
                   ["music", "b", "1", "1.0"],     # fade 1.0 -> max(2, 2)=2s
                   ["sfx", "c", "", ""],           # 0.6s
                   ["pause", "music", "", ""]])    # 0.5s
    durs = [tl2._duration_of(d) for d in tl2.items]
    check("时长估算", durs == [3.0, 2.0, 0.6, 0.5], "durs=%s" % durs)
    lays = tl2._layout()
    check("起点累计", abs(lays[1][0] - 3.2) < 0.01
          and abs(lays[3][0] - (3.2 + 2.2 + 0.8)) < 0.01,
          "lays=%s" % lays)
    check("总时长", abs(tl2.total_seconds()
                        - (lays[3][0] + 0.5)) < 0.01)
    # 块宽 ∝ 时长
    w0 = tl2._block_rect(0).width()
    w2 = tl2._block_rect(2).width()
    check("块宽与时长成正比", w0 > w2, "w0=%s w2=%s" % (w0, w2))
    # 时间标签文本在 _layout 起点
    check("起点标签数据", round(lays[0][0], 1) == 0.0)

    print()
    if FAILURES:
        print("结果: %d 项失败 -> %s" % (len(FAILURES), FAILURES))
        return 1
    print("结果: 全部通过 ✓")
    return 0


def _fake_event(kind, pos):
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QMouseEvent
    types = {"press": QEvent.Type.MouseButtonPress,
             "move": QEvent.Type.MouseMove,
             "release": QEvent.Type.MouseButtonRelease}
    return QMouseEvent(types[kind], pos, Qt.LeftButton,
                       Qt.LeftButton, Qt.NoModifier)


if __name__ == "__main__":
    os._exit(main())
