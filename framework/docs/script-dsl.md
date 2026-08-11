# DSL 语法全参考

`.gal` 脚本为 UTF-8 文本，`#` 开头为注释，**缩进（空格）表示块结构**。

## 1. 表达式

```gal
set love = 0
set love = love + 1
if love > 0 and name == "xx":
    ...
```

* 支持 `+ - * /`、比较 `== != < > <= >=`、逻辑 `and or not`
* 变量引用 `$var` 或裸 `var`（命名空间：`$main::x` / `$plugin::cnt`）
* 字符串用引号；**表达式内不允许函数调用**（安全限制）
* 文本插值：`$var` 出现在台词/选项/标题中会被替换；`$$` 转义为字面 `$`

## 2. 标签与流程控制

```gal
start:                    # 脚本入口 (必为 start)
label_a:                  # 普通标签

jump label_a              # 跳转
call sub_routine          # 调用 (可 return)
return
if cond: ... elif ...: ... else: ... endif

choice:                   # 选择支
    "选项一" -> label_a
    "选项二" -> label_b
```

## 3. 背景与场景

```gal
scene school                       # 场景定义 (可顶层, 静态注册)
    name: "学校"
    type: normal                    # normal (默认) / cg
    default: "materials/image/bg.png"
    morning: "materials/image/bg.png"

bg school                          # 切到默认背景
bg school morning                  # 场景内切换
bg "materials/bg.png"              # 直接路径
bg school with fade                # 过渡: fade/dissolve/blinds/slide/circle/pixelate/zoom/插件
```

* `type: cg` 的场景每次 `bg` 展示都会记入**全局 CG 收集**（`save/global.json`，跨存档）
* 场景名支持 `{@key}`（显示时按当前语言解析）

## 4. 立绘与角色

```gal
char producer
    name: "{@char.producer.name}"   # 显示名 (支持 {@key})
    default: "producer1.png"         # 默认立绘
    normal: "producer1.png"          # 立绘名: 路径
    happy: "producer2.png"
    voice_volume: 0.6                # 该角色语音音量
    desc: "描述" / cv: "配音"         # 元信息 (鉴赏用, 支持 {@key})

show producer normal                # 显示 (默认居中)
show producer happy with slide_right  # 切换 + 登场效果
hide producer with slide_left       # 退场效果 (播完自动隐藏)
clear                               # 清除全部立绘
move producer to left 1             # 位移 (时长+缓动)
move producer to 400,300 2 ease in_out
rotate producer 90 1                # 旋转 (逆时针正, 时长=动画)
flip producer [vertical]            # 水平/垂直翻转
```

登场/退场效果：`fade / slide_* / zoom / drop / bounce / rotate / wobble / sway / zoom_bounce / fade_rotate / float / squash`（内置 + 插件）。

## 5. 对话与语音

```gal
text "无角色旁白"           # 或 nar "旁白"
say 主角 "角色对话, 支持 $变量"
say producer "语音台词" voice voice_demo
say 旁白 "也按旁白处理"      # 旁白关键字 (narrator 同义)
```

* 台词/旁白支持富文本与 `{@key}` 占位符（`$var` 先插值，`{@key}` 解析后再插值一次）
* `voice` 语音随台词显示播放、推进时立即停止

## 6. 富文本与 LaTeX

```gal
say a "普通 {c=#ff6600}彩色{/c} {b}粗体{/b} {u}下划线{/u} {i}斜体{/i}"
say a "大字 {s=34}放大{/s}"
say a "公式: {m}\frac{1}{2}{/m}"
```

* 标记：`{c=颜色}` `{b}` `{u}` `{i}` `{s=字号}` `{o=描边色}` `{m}公式{/m}`（或 `{math}`）
* 公式源码允许嵌套花括号（配对扫描），整体作为一个"逻辑字符"（打字机/逐行模式不截断公式）
* 需要 matplotlib；未安装时公式按原文显示

## 7. 文字显示模式

```gal
typing typewriter     # 默认: 打字机逐字
typing instant        # 整段直接出现
typing terminal       # 逐字 + 行尾闪烁光标
typing lines          # 逐行显示 + 节奏停顿
typing wave           # 插件模式 (custom_actions)
```

插件注册：`display.register_text_mode(name, {"reset": fn, "update": fn(display, dt)})`。

## 8. 声音系统

```gal
sound sfx_click
    type: sfx_ui                # music / sfx_ui / sfx_story / voice
    file: "materials/audio/sfx_click.wav"
    volume: 0.6

music bgm_piano41               # 播放 (默认循环)
music bgm_piano39 fade 1.0      # 切换/淡入
music bgm_piano39 loop 0        # 单次
pause music fade 0.8            # 暂停 (淡出)   | resume music 恢复
volume music 0.3                # 临时音量     | volume sfx / volume voice
stop music                      # 停止 (淡出)   | stop all 全局静音
sfx sfx_boom                    # 剧情音效
pause all / stop all            # 全局暂停/停止
```

* fade 时长支持变量/表达式；默认时长由 window 的 `music_fade` 控制
* 语音音量四层相乘：全局 sfx × 全局 voice × 声音块 volume × 角色 voice_volume
* UI 音效：window 全局默认 + menu 块级 + choice 行内（`ui_click_sound`/`ui_hover_sound`）

## 9. 菜单与键盘导航

```gal
menu title                       # 命名菜单 (title/system/自定义)
    start_button
        text: "{@title.start}"
        image: "默认.png, 焦点.png"
        width: 262 / height: 98 / stretch: false / text_visible: false
        action: start game_start
    ui_hover_sound: "sfx_hover"  # 菜单级 UI 音效

window
    key_up: "up, w"              # 键盘导航配置
    key_down: "down, s"
    key_confirm: "return, space"
```

* 键盘移动/鼠标悬停激活活动选项；初始无活动项（Enter 不误触）
* `action` 类型：`start label` / `slot_menu save|load` / `save` / `load` / `title` / `continue` / `quit` / `close` / 插件自定义动作

### bar 常驻菜单栏

```gal
window
    menu_mode: "bar"             # popup (默认) / bar
    menu_bar_pos: "bottom"       # bottom / top

menu_bar                          # bar 样式块
    bg: "#1a1a2e"
    bg_image: "bar.png"           # 图片键 (图优先于纯色)
    button_image / button_image_hover / button_image_active / button_image_disabled
    height: 56 / btn_h: 38 / gap: 12 / padding: 18 / align: center
    button_bg / button_border / button_radius / text_color / text_size ...
```

## 10. 界面样式

```gal
use style modern        # 内置: modern / classic / dark / light / cyber
use style default       # 恢复默认

style my_theme
    textbox_bg / textbox_alpha / textbox_border / textbox_radius
    text_color / text_size / speaker_color / speaker_bg
    textbox_image / speaker_image / choice_image ...

selection_style           # 选择列表全局样式
    width_ratio / height / gap / anchor_x / anchor_y
    button_bg / button_bg_hover / button_border / button_radius
    button_image / button_image_hover / button_stretch / button_text
    text_color / text_color_hover / dialog_image
selection_style default   # 重置

ui                        # UI 主题素材 (九宫格)
    textbox: "dialog.png"
    title_buttons: "默认.png, 焦点.png; 组2默认.png, 组2焦点.png"
    # 支持: textbox/choice_button/title_buttons/menu_button/
    #       confirm_panel/confirm_button/slot_frame/slot_panel
```

## 11. 标题画面

```gal
title
    image: "materials/title.png"
    caption: "标题文字"            # 支持富文本与 {@key}
    start: game_start              # 必填
    start_text: "{@title.start}"
    load: 0 / load_text: "读取存档"
    quit: true / quit_text: "退出游戏"
    menu: title                    # 引用命名菜单替代内置按钮
    button_x: center / button_y: 420 / button_columns: 2
```

## 12. 窗口配置 (window 块)

```gal
window
    title: "我的游戏" / width: 1280 / height: 720
    icon: "icon.png" / fps: 60
    fullscreen: false / resizable: true
    confirm_quit: true / confirm_quit_text: "{@dialog.quit.text}" / ...
    confirm_load / confirm_title    # 读档/回标题确认框
    key_up / key_down / key_confirm / key_left / key_right
    ui_click_sound: "sfx_click" / music_fade: 1.0
    menu_continue / menu_save / menu_load / menu_title / menu_quit
    font: "fonts/Ubuntu-R.ttf"     # 或 "sys:Microsoft YaHei"
```

* 确认框/菜单文案支持 `{@key}`，**显示时按当前语言解析**
* `window config` 可在运行时改标题/尺寸/图标/全屏/可缩放/fps；内容等比缩放（letterbox）
* 声明支持 `$变量`（如 `width: "$res_w"`，由设置项 resolution 写入）

## 13. 插件装载与命名空间

```gal
plugins
    only: "fx, notice"     # 只装载列出的
    # except: "debug_mode"  # 或排除

using fx custom_actions    # 导入插件命名空间 (之后可裸名调用指令)
plugin load custom_actions # 运行时装载/卸载/列出
plugin unload shake
plugin list
```

## 14. 存档 / 结束 / 转场

```gal
save                        # 存档到槽位 0
load                        # 读档
fade / fadeout              # 黑幕淡入/淡出
ending                      # 结束画面后回标题
ending {@ending.true_end}   # 带结局名 (原文记录, 显示时解析; 全局进度)
```

## 15. 询问对话框

```gal
confirm "继续吗？" -> choice      # 结果 yes/no 存变量
if choice == "yes": ...
confirm "再来一次？" yes "好的" no "算了" -> again
```

* 键盘左右键在确认/取消间移动（可配 `key_left`/`key_right`）；初始无活动项

## 16. 设置系统 (settings 块)

```gal
settings
    title: "{@settings.title}"
    columns: 2
    bg: "panel.png"
    item_image / item_image_hover / tab_image / tab_image_hover
    back_image / slider_track_image        # UI 图片键
    setting bgm_volume
        label: "{@settings.bgm_volume}"
        section: "音量"
        default: 0.8
    setting my_slider
        label: "{@settings.my_slider}"
        type: slider / checkbox / cycle / input / keybind / button
        var: my_val
        min: 0 / max: 100 / step: 5
    setting player_name
        type: cycle
        options: "{@settings.name.a}, {@settings.name.b}, {@settings.name.c}"
```

详见 [styles-settings.md](styles-settings.md)。

## 17. 嵌入 Python (python::)

```gal
start:
    python::
        import random
        engine.set_var("luck", random.randint(1, 100))
    text "幸运值: $luck"
```

* **双冒号**语法，块内行原样捕获（含空行/注释/缩进），不按 DSL 解析
* 命名空间：`engine/runtime/display/audio/save/i18n/ui/pygame/os/math`
* 拥有完整解释器权限（如同插件），异常记录日志不中断游戏
* 详见 [plugin-dev.md](plugin-dev.md#嵌入-python)

## 18. 指令速查表

| 指令 | 语法 | 说明 |
| --- | --- | --- |
| 对话 | `say <角色> "文本" [voice 名]` / `nar "文本"` / `text "文本"` | 台词/旁白 |
| 背景 | `bg <场景> [背景名] [with 效果]` | 场景/路径背景 |
| 场景 | `scene <id>` 块 | 场景定义 (name/背景名/type) |
| 角色 | `char <id>` 块 | 角色定义 |
| 立绘 | `show/hide <角色> [立绘名] [with 效果]` / `clear` | 显示/隐藏/清除 |
| 变换 | `move/rotate/flip <角色> ...` | 位移/旋转/翻转 |
| 样式 | `use style <名>` / `style <名>` 块 / `selection_style` 块 | 主题 |
| UI 素材 | `ui` 块 | 九宫格主题切片 |
| 菜单 | `menu <id>` 块 / `menu_bar` 块 | 命名菜单/常驻栏 |
| 标题 | `title` 块 | 标题画面 |
| 选择支 | `choice` 块 | 分支选择 |
| 询问 | `confirm <文本> [yes X] [no Y] [-> 变量]` | 确认框 |
| 变量 | `set <名> = <表达式>` | 赋值 |
| 条件 | `if/elif/else/endif` | 分支 |
| 跳转 | `jump/call <标签>` / `return` | 流程 |
| 等待 | `sleep <秒>` | 阻塞等待 |
| 文字模式 | `typing <模式>` | typewriter/instant/terminal/lines/插件 |
| 声音 | `sound <名>` 块 | 声音注册 |
| 音乐 | `music <名/路径> [loop 0/1] [fade 秒]` | 播放/切换 |
| 暂停/恢复 | `pause/resume music [fade 秒]` / `pause all` | 音乐/全局 |
| 音量 | `volume music|sfx|voice [角色] <0-1>` | 临时音量 |
| 停止 | `stop music [fade 秒]` / `stop all` | 停止 |
| 音效 | `sfx <声音名>` | 剧情音效 |
| 窗口 | `window config` 块 / `fullscreen true/false` | 运行时窗口配置 |
| 命名空间 | `using <ns...>` | 导入插件命名空间 |
| 插件 | `plugin load/unload/list <名>` | 运行时插件管理 |
| 存档 | `save` / `load` | 槽位 0 存档/读档 |
| 转场 | `fade` / `fadeout` | 黑幕 |
| 结束 | `ending [结局名]` | 结束画面 + 结局记录 |
| 设置 | `settings` 块 + `setting <key>` 子块 | 设置界面配置 |
| Python | `python::` 块 | 嵌入 Python 代码 |
