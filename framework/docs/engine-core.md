# 引擎核心

## 初始化与主循环

```python
from framework import GameEngine

engine = GameEngine(1280, 720, "My Game", fps=60,
                    fullscreen=False, resizable=True)
engine.run("script.gal")
```

`run()` 流程：
1. 设置脚本目录/项目目录，日志写入 `<项目>/logs/engine.log`
2. 解析脚本（`load_script`：language 块 → settings 配置 → gallery 等插件块 → 广播 `script_load`）
3. 装载插件（`plugins.discover`，此时插件可注册指令/事件/扩展点）
4. 执行脚本（`start` 标签）→ 进入主循环

主循环每帧：`dt = clock.tick(fps)` → **每帧钩子**（`register_frame_hook`）→ 事件处理 → `update(dt)` → `draw()`。任何异常被捕获并温和弹窗（不崩溃）。

## 事件总线

插件订阅引擎事件（`engine.events.on` 或 `@event_listener`）。处理器返回 `False` 可标记"阻止默认行为"。事件会自动附带 `engine` 参数。

完整事件表见 [plugin-dev.md](plugin-dev.md#事件参考)。常用：

| 事件 | 时机 |
| --- | --- |
| `engine_start` / `engine_quit` | 引擎启动/退出 |
| `script_load` / `script_start` / `script_end` | 脚本阶段 |
| `script_block` | 未处理属性块广播（插件自定义块） |
| `statement` / `label_enter` | 每句/每标签 |
| `text_show` / `text_complete` | 文本 |
| `choice_prepare` | 选择支显示前（可改写选项） |
| `bg_change` / `scene_change` | 背景/场景 |
| `save` / `load` | 存档/读档 |
| `draw_overlay` | 每帧绘制钩子（最上层叠加） |
| `engine_click` / `engine_escape` | 点击/ESC（可拦截） |

## 动作系统

选择列表按钮/插件触发的事件动作：

| 动作 | 参数 |
| --- | --- |
| `start` | label |
| `quit` | —（走退出确认） |
| `title` | —（回标题） |
| `continue` | —（关菜单继续） |
| `slot_menu` | mode=save/load |
| `save` / `load` | slot |
| `close` | — |

插件注册：`engine.register_action("explode", fn)`，`fn(engine, params, source) -> bool`（True=执行后关闭选择列表）。脚本触发：`do_action explode duration=0.5`。

## 对话框（确认框）系统

退出/读档/回标题确认框统一由 `dialog` 表管理（`window` 块 `confirm_*` 配置），文案支持 `{@key}`、显示时按当前语言解析（语言切换即时刷新）。

```python
engine.ask_confirm(text, yes_text, no_text, on_yes, on_no=None)
```

* 键盘左右键移动活动项，初始无活动
* 已有确认框时关窗口会**叠加一层退出确认**（取消恢复原框）

## 窗口运行时配置与等比缩放

```python
engine.set_window_title(title)
engine.set_window_size(w, h)        # 内容等比缩放
engine.set_fullscreen(True/False)
engine.apply_window_config(cfg)     # 批量应用
engine.to_logical(pos)              # 窗口坐标 -> 逻辑坐标
```

引擎以**固定逻辑分辨率**绘制，窗口任意缩放内容等比拉伸（letterbox 留黑边），鼠标坐标自动映射。

## 快捷键系统 (keybinds)

`engine.keybinds`（`KeyBindManager`）统一管理键盘事件，每个命令含**主键+副键**双槽：

```python
engine.keybinds.register("my_toggle", "调试模式", callback,
                         primary="f3", label_key="debug_mode.toggle")
```

* 自动生成设置项（"按键"分栏，主/副同槽位一行显示）
* 冲突自动让位 + 提示；Backspace 清空；值存 `save/settings.json`
* 核心键位：key_up/down/left/right/confirm/escape

## 存档系统

* 槽位 6 个（`save/slot0-5.json`），由 ESC 菜单/标题打开
* 内容：变量/剧情位置/调用栈/阻塞状态/背景(场景id+背景名)/立绘(id/pose/透明度/旋转/翻转/中心点)/BGM注册名/样式名/文本与选择支
* 对象以**脚本 id** 存储（不存图片路径，重命名图片不破坏旧档）
* 元数据 API：`save.set_meta/get_meta/meta_path`、`list_slots`（含 time/label/preview/screenshot）
* 存档画面快照由 `slot_thumbnails` 插件提供（`engine.get_last_game_frame()` 纯游戏帧）

**全局进度**（`save/global.json`，跨存档）：`get_endings()` / `record_ending(name)` / `get_unlocked_cgs()` / `record_cg(scene, pose)`。

**状态快照（回滚）**：
```python
snap = engine.snapshot_state()   # 内存快照, 与存档同构, 不落盘
engine.restore_state(snap)       # 静默恢复到快照点 (撤销/分支探索)
```

## 错误处理

* 主循环每帧 try/except 隔离；`sys.excepthook` 全局兜底
* 温和弹窗（摘要 + 三按钮：继续/复制/退出）；详情写 `logs/errors.log`
* 错误分级：`warn` 仅日志 + 游戏界面顶部小提示（节流 2s）；`error` 记录 + 弹窗

## 音频系统

* music：`pygame.mixer.music` 流式 + fade 状态机（切换=旧曲淡出→新曲淡入）
* sfx_ui / sfx_story：`Sound` 实例
* voice：**独立通道**（Channel 0），随台词播放/停止
* 全局静音：`stop all` / `pause all`（BGM 淡出 + 音效/语音停）

```python
engine.play_music(name_or_path, loop=True, fade=None)
engine.stop_music(fade) / engine.pause_music(fade) / engine.resume_music(fade)
engine.play_sfx(name) / engine.play_voice(name) / engine.stop_voice()
engine.set_music_volume(v) / engine.set_sfx_volume(v)
```

## 渲染系统概览

绘制顺序：背景（含动态背景渲染器）→ 立绘（含立绘渲染器）→ 全局黑幕 → 文本/选项 → 通知 → 结束画面 → 插件 `draw_overlay` → 特效覆盖层。

* 文本/选择支/确认框/槽位界面均为代码绘制（样式可配置）
* UI 主题素材（`ui` 块九宫格）与 style 图片键覆盖
* 截图：`engine.display.capture()` / `engine.get_last_game_frame()`
