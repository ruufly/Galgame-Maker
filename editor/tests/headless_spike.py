"""P0 技术验证 2: 无头渲染取帧 (Qt 嵌入预览的前置验证)。

问题: 编辑器要内嵌"真实引擎画面"预览, 必须能在无窗口环境下
驱动 GameEngine 渲染, 并取出帧。本脚本验证:

1. SDL dummy 视频/音频驱动下, GameEngine 可完成 初始化/加载/渲染
2. 主循环可用 register_frame_hook 数帧后安全退出 (无需用户输入)
3. display.capture() 可取出真实渲染帧 (PNG 非空白)

运行::

    py -3.10 editor/tests/headless_spike.py
"""

import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)

import pygame
from framework.api import GameEngine

W, H = 640, 360
MAX_FRAMES = 45


def main() -> None:
    engine = GameEngine(W, H, "headless spike")

    frames = [0]

    def hook(dt):
        frames[0] += 1
        if frames[0] >= MAX_FRAMES:
            engine.running = False

    engine.register_frame_hook(hook)
    engine.run(os.path.join(_ROOT, "test", "engine_demo", "demo.gal"))

    # 取最后一帧
    frame = engine.display.capture()
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "headless_frame.png")
    pygame.image.save(frame, out)

    # 简单非空白检查: 采样像素, 统计不同颜色数
    w, h = frame.get_size()
    sample = [frame.get_at((x, y))[:3]
              for x in range(0, w, max(1, w // 32))
              for y in range(0, h, max(1, h // 18))]
    distinct = len(set(sample))
    avg = tuple(sum(c[i] for c in sample) // len(sample) for i in range(3))

    print(f"frames rendered : {frames[0]}")
    print(f"surface size    : {w}x{h}")
    print(f"distinct colors : {distinct} (非空白 > 2)")
    print(f"avg color       : {avg}")
    print(f"saved           : {out}")
    pygame.quit()
    if frames[0] < 5 or distinct <= 2:
        print("RESULT: FAIL")
        sys.exit(1)
    print("RESULT: OK")
    sys.exit(0)


if __name__ == "__main__":
    main()
