# 快速开始

## 环境要求

* Python 3.10（引擎按 3.10 开发与测试，其他版本未经充分验证）
* pygame（`pip install pygame`）
* 可选：matplotlib（LaTeX 公式渲染，未安装时公式按原文显示）

```powershell
pip install pygame
# 可选
pip install matplotlib
```

## 运行内置演示

项目自带完整可玩演示 `test/engine_demo/`（覆盖引擎全部特性）：

```powershell
# 在项目根目录
py -3.10 gamelauncher.py
# 或显式指定脚本
py -3.10 gamelauncher.py test/engine_demo/demo.gal
```

也可以把任意 `.gal` 文件**拖到 gamelauncher.py 上**直接运行。

## 运行自己的脚本

```powershell
py -3.10 gamelauncher.py path/to/your.gal
```

## 最小项目

一个 `.gal` 脚本 + 素材目录即可构成项目：

```
mygame/
├── demo.gal            # 主脚本 (入口)
├── lang/               # 可选: 游戏文本多语言
│   ├── zh-CN.json
│   └── en.json
└── materials/          # 素材 (背景/立绘/音频/UI)
    ├── image/
    └── audio/
```

最简 `demo.gal`：

```gal
window
    title: "我的游戏"
    width: 1280
    height: 720

start:
    bg school
    say producer "你好，世界！"
    ending
```

## 命令行参数（启动器）

| 参数 | 说明 |
| --- | --- |
| `<script.gal>` | 要运行的脚本（缺省运行内置 demo） |
| `--width` / `--height` | 窗口尺寸 |
| `--fullscreen` | 全屏启动 |
| `--plugin-dir <目录>` | 指定插件目录 |

## 引擎最小用法（Python API）

```python
from framework.api import GameEngine

engine = GameEngine(1280, 720, "My Game")
engine.run("script.gal")
```

## 操作键位

| 键 | 作用 |
| --- | --- |
| 左键 / 空格 | 推进文本 / 确认 |
| 上 / 下（或 W/S） | 菜单中移动活动选项 |
| Enter / 空格 | 确认活动选项 |
| 左 / 右（或 A/D） | 确认框移动（是/否） |
| F5 | 快速存档 |
| F9 | 读档 |
| ESC | 打开系统菜单（或关闭覆盖层） |

键位均可通过 `window` 块配置（`key_up`/`key_down`/`key_confirm`/`key_left`/`key_right`），也可在设置界面调整。

## 运行测试

```powershell
py -3.10 framework/tests/smoke.py    # 779 项断言, dummy 驱动无窗口
```
