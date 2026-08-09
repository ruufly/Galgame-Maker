# Galgame Maker 运行时引擎 (framework)

基于 **Python 3.10 + pygame** 的视觉小说引擎, 用于运行 `.gal` 脚本,
兼容 Galgame-Maker 编辑器的语法风格, 并预留插件 API。

```
framework/
├── api/           插件 API: 事件总线 / 指令注册表 / 插件管理器
├── engine/        引擎核心: 解析器 / 运行时 / 渲染层 / 音频 / 存档
├── plugins/       插件目录 (自动加载, 含 2 个示例)
├── tests/         冒烟测试 (dummy 驱动, 无窗口可跑)
└── run_demo.py    演示入口
```

## 快速开始

```powershell
# 运行内置演示
py -3.10 framework/run_demo.py

# 运行自己的脚本
py -3.10 framework/run_demo.py path/to/your.gal

# 运行冒烟测试
py -3.10 framework/tests/smoke.py
```

引擎最小用法 (Python):

```python
from framework.api import GameEngine

engine = GameEngine(1280, 720, "My Game")
engine.run("script.gal")
```

操作: 左键/空格 推进, F5 快速存档, F9 读档, ESC 退出。

## DSL 语法

脚本为 UTF-8 文本, `#` 开头为注释, 缩进 (空格) 表示块结构。

```gal
# 声明与元信息
widgets @ "widgets/"            # 加载 .wid 模板目录
name: demo                      # 项目名 (可选)

# 标签块 (脚本入口是 start:)
start:
    # 背景: weight 块 + `->` 绑定 id (effect: fade 淡入)
    weight
        image: "materials/bg.png"
        mode: full
        effect: fade
    -> bg1
    show bg1

    # 立绘: sprite 块 (pos: center/left/right/top/bottom 或 x,y)
    sprite girl
        image: "materials/girl.png"
        pos: center
        effect: fade
    show girl

    # 对话
    text "无角色旁白"
    say 主角 "角色对话, 支持 $变量 插值"
    hide girl                   # 隐藏立绘 (withdraw 同义)
    clear                       # 清除全部立绘
    sleep 1                     # 等待 1 秒

    # 选项分支
    choice:
        "选项一" -> label_a
        "选项二" -> label_b

    # 变量与条件
    set love = 0
    set love = love + 1
    if love > 0 and name == "xx":
        text "好感度高"
    elif love == 0:
        text "无感"
    else:
        text "负好感"
    endif

    # 流程控制
    jump label_a                # 跳转
    call sub_routine            # 调用 (可 return)
    return

    # 音频 / 转场 / 存档 / 结束
    music "bgm.mp3"             # 循环播放
    sound "click.wav"           # 播放一次
    stop                        # 停止音乐
    fade                        # 黑幕淡入 (显示画面)
    fadeout                     # 黑幕淡出
    save                        # 存档到槽位 0 (save/slot0.json)
    load                        # 读档
    ending                      # 结束画面后退出

label_a:
    text "结局 A"
```

表达式支持 `+ - * /`、比较 `== != < > <= >=`、逻辑 `and or not`,
变量引用可写 `$var` 或裸 `var`, 字符串用引号。求值环境无内置函数,
表达式内不允许函数调用 (安全限制)。

## 插件 API

插件是放在 `framework/plugins/` 下的 `.py` 文件 (下划线开头会被忽略),
引擎启动时自动发现加载。两种写法:

### 1. 装饰器写法 (推荐, 简单)

```python
# framework/plugins/my_plugin.py
from framework.api import command, event_listener

@command("mycmd")                       # 自定义 DSL 指令: 脚本写 `mycmd 参数`
def mycmd(engine, stmt, **kw):
    engine.show_notice("指令被调用!")
    return None                          # 返回 "block" 可阻塞等外部事件

@event_listener("bg_change")            # 订阅事件 (engine 参数自动注入)
def on_bg(path, engine, **kw):
    print("背景切换到", path)
```

### 2. 类写法 (需要生命周期管理)

```python
from framework.api import Plugin

class MyPlugin(Plugin):
    name = "my_plugin"
    version = "1.0"

    def on_load(self):
        @self.listen("draw_overlay")     # 每帧渲染钩子
        def overlay(surface, **kw):
            pass
        @self.add_command("greet")
        def greet(engine, stmt, **kw):
            engine.say("插件", "你好")

    def on_unload(self):
        pass
```

### 事件一览

| 事件 | 载荷 |
| --- | --- |
| engine_start / engine_quit | engine |
| script_load / script_start / script_end | path / name |
| label_enter | label |
| statement | stmt, label |
| text_show / text_advance / text_complete | text, speaker |
| choice_show / choice_made | choices / index, label, text |
| bg_change | path, effect |
| sprite_show / sprite_hide | id, path |
| var_set | name, value |
| music_play / music_stop / sound_play | path, loop |
| save / load | slot, path |
| draw_overlay (每帧) | surface |

### 引擎公共 API (供插件/游戏代码调用)

```python
engine.display      # 渲染: set_bg/show_sprite/hide_sprite/show_text/show_choices...
engine.audio        # play_music/play_sound/stop_music/set_volume
engine.save         # save(slot,data)/load(slot)
engine.runtime      # vars / evaluate / jump / _interp...
engine.events       # 事件总线 (on/emit)
engine.commands     # 指令注册表 (register/has/call)
engine.plugins      # 插件管理器
engine.ui           # UI 绘制原语 (见下)
engine.say(speaker, text)
engine.set_var(name, value) / engine.get_var(name)
engine.show_notice(text)
engine.save_game(slot) / engine.load_game(slot)
engine.resolve_path(rel)   # 相对脚本目录解析资源路径
```

### UI 绘制原语 (`engine.ui`)

"画一个框、往里填内容"的高频操作已封装, 引擎内部与插件共用:

```python
from pygame import Rect

engine.ui.panel(surface, Rect(10, 10, 200, 60),            # 半透明面板+边框+圆角
                bg_color=(0, 0, 0, 185),
                border_color=(255, 255, 255, 80), border_width=2, radius=8)

engine.ui.text(surface, font, "文字", center=(100, 40))     # 文字 (pos/center/alpha)
engine.ui.wrap_text(font, "长文本", max_width=180)          # 逐字符换行 -> [行]
engine.ui.multiline_text(surface, font, "多行文本", 20, 20,  # 自动换行绘制
                         max_width=180, max_lines=3)
engine.ui.dim_overlay(surface, alpha=150)                   # 全屏半透明遮罩
```

插件在 `draw_overlay` 事件里可以直接用这些原语叠加 HUD / 调试信息,
不必再自造轮子。

## 已知限制

* `.wid` 组件仅支持模板化兼容 (reg class + when run 块), 编辑器特有的
  `#id` 引用 / `general.page.height` 等组件树表达式不解析, 会警告跳过
* 音频/图片找不到时仅告警, 不中断游戏
* 存档只保存变量、当前标签位置与立绘状态; 调用栈不恢复 (从最近标签重开)
