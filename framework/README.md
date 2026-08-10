# Galgame Maker 运行时引擎 (framework)

基于 **Python 3.10 + pygame** 的视觉小说引擎, 用于运行 `.gal` 脚本,
兼容 Galgame-Maker 编辑器的语法风格, 并预留完整插件 API。
本 README 为**完整交接文档**, 覆盖全部开发细节、接口与特性。

---

## 1. 项目概览

```
framework/
├── api/                      插件 API
│   ├── __init__.py           导出 GameEngine / Plugin / command / event_listener...
│   ├── events.py             事件总线 (on/emit/off)
│   ├── commands.py           指令注册表 (按命名空间分组: main/builtin/<插件名>)
│   └── plugin.py             插件管理器 (发现/装载/实例化/卸载/模块级注册追踪)
├── engine/                   引擎核心
│   ├── core.py               GameEngine 主循环 / 输入处理 / 动作分发 / 音频 API
│   ├── parser.py             .gal DSL 解析器
│   ├── loader.py             import 递归展开合并 (循环导入检测)
│   ├── runtime.py            脚本执行器 (变量/分支/跳转/调用栈/存档/角色/场景/
│   │                         菜单/声音/命名空间/using/plugin 指令)
│   ├── display.py            渲染层 (精灵/背景/文本框/确认框/选择列表/槽位界面/
│   │                         过渡/立绘效果/文字模式/截图/缩略图钩子)
│   ├── audio.py              BGM 淡入淡出状态机 / 音效 / 语音独立通道 / 全局静音
│   ├── save.py               存档/读档 (JSON 槽位 + 元数据 API)
│   ├── rich.py               富文本解析渲染 + LaTeX 公式 (MathRenderer)
│   ├── ui.py                 UI 绘制原语 (面板/文字/换行/九宫格 nine_slice)
│   ├── error.py              错误处理 (日志 + 弹窗 + 剪贴板复制)
│   ├── styles.py             内置 5 套 UI 主题样式
│   └── transitions.py        背景过渡效果 (7 种 + 插件可注册)
├── plugins/                  插件目录 (自动装载)
│   ├── shake.py              屏幕震动 + 白闪 (shake/flash 指令)
│   ├── fps_overlay.py        FPS 浮层
│   ├── scene_notice.py       场景切换通知
│   ├── wipe_transition.py    擦除过渡
│   ├── custom_actions.py     explode 动作 + do_action 指令 + wobble 立绘效果 +
│   │                         wave 文字模式
│   ├── bgm_notice.py         BGM 播放/暂停/恢复/停止通知
│   ├── slot_thumbnails.py    存档画面快照 (槽位缩略图)
│   └── gallery.py            鉴赏: 标题菜单按钮 + CG/BGM/角色/场景鉴赏
│                            (结局解锁, 配置在 gallery.gal)
└── tests/
    └── smoke.py              冒烟测试 (dummy 驱动, 无窗口可跑, 573 项断言)
```

项目根: `gamelauncher.py` 独立启动器 (命令行传参 / 拖拽 `.gal` 文件)。

**当前测试状态: 573 项断言全部通过** (parser/runtime/交互推进/样式表/
selection/存档/过渡/角色/场景/对话框/菜单/动作/立绘效果/文字模式/插件/
命名空间/音频/快照/LaTeX/分角色语音音量/窗口配置与等比缩放/常驻菜单栏/
鉴赏系统/结局记录/CG 收集)。

---

## 2. 快速开始

```powershell
# 运行内置演示 (test/engine_demo/)
py -3.10 gamelauncher.py

# 运行自己的脚本 (也支持把 .gal 文件拖到 gamelauncher.py 上)
py -3.10 gamelauncher.py path/to/your.gal

# 命令行参数 (启动器支持)
#   --width/--height/--fullscreen 等窗口参数
#   --plugin-dir <目录>           指定插件目录

# 运行冒烟测试
py -3.10 framework/tests/smoke.py
```

引擎最小用法:

```python
from framework.api import GameEngine

engine = GameEngine(1280, 720, "My Game")
engine.run("script.gal")
```

操作: 左键/空格 推进, 方向键/WASD 在菜单中移动活动选项, Enter/空格 确认,
F5 快速存档, F9 读档, ESC 打开系统菜单。

---

## 3. 脚本拆分 (import)

`.gal` 支持按功能拆分多个文件, 顶层用 `import` 合并:

```gal
import "ui.gal"          # 界面样式定义
import "cast.gal"        # 角色与场景定义
import "audio.gal"       # 声音注册
import "branches.gal"    # 分支流程标签
```

合并规则:

* 被导入文件的标签全部并入 (重复标签报错), 子文件的 `start` 标签忽略
* 顶层声明 (window/style/char/scene/plugins/selection_style/sound/using)
  按 import 位置顺序并入, 运行时静态注册
* 相对路径 (相对 import 语句所在文件), 支持链式 import, 循环导入报错

demo (`test/engine_demo/`) 拆分: `demo.gal` (主流程) + `ui.gal` (样式/菜单)
+ `cast.gal` (角色/场景) + `audio.gal` (声音) + `branches.gal` (分支)。
窗口配置 / 插件配置的预解析 (启动器) 同样递归展开 import。

---

## 4. DSL 语法全参考

脚本为 UTF-8 文本, `#` 开头为注释, 缩进 (空格) 表示块结构。

### 4.1 表达式

支持 `+ - * /`、比较 `== != < > <= >=`、逻辑 `and or not`。
变量引用可写 `$var` 或裸 `var` (命名空间: `$main::x` / `$plugin::cnt`),
字符串用引号。求值环境无内置函数, 表达式内不允许函数调用 (安全限制)。

```gal
set love = 0
set love = love + 1
if love > 0 and name == "xx":
    ...
```

### 4.2 标签与流程控制

```gal
start:                    # 脚本入口 (必为 start)
label_a:                  # 普通标签

jump label_a              # 跳转
call sub_routine          # 调用 (可 return)
return
if cond: ... elif ...: ... else: ... endif

choice:                   # 选择支 (也支持行内参数, 见 4.9)
    "选项一" -> label_a
    "选项二" -> label_b
```

### 4.3 背景与场景

```gal
scene school                       # 场景定义 (可放顶层, 静态注册)
    name: "学校"
    type: normal                    # normal (默认) / cg
    default: "materials/image/bg.png"
    morning: "materials/image/bg.png"     # 背景名: 路径

bg school                          # 切到场景默认背景 (触发 scene_change)
bg school morning                  # 场景内切换背景
bg "materials/bg.png"              # 直接指定路径
bg school with fade                # 过渡: fade/dissolve/blinds/slide/
                                   #       circle/pixelate/zoom + 插件自定义
```

**场景分类**: `type: cg` 的 CG 场景显示逻辑与 normal 完全一致,
但每次用 `bg` 展示 (含背景名) 都会记入**全局 CG 收集**
(`save/global.json`, 跨存档), 供鉴赏插件分门别类展示
(见 4.15 鉴赏系统)。

### 4.4 立绘与角色

```gal
char producer
    name: "制作人"                   # 显示名 (台词名字框用)
    default: "materials/char/producer1.png"
    normal: "materials/char/producer1.png"    # 立绘名: 路径
    happy: "materials/char/producer2.png"
    voice_volume: 0.6                # 该角色语音音量 0-1 (可选, 默认 1.0)
    desc: "引擎的制作者，温和而执着。"   # 描述性信息 (角色鉴赏用, 可选)
    cv: "演示配音"                    # 声优 / 生日 / 身高 / 年龄 等均可

show producer normal                # 显示角色立绘 (默认居中)
show producer happy                 # 切换立绘 (保持中心点原位替换)
show producer normal with slide_right   # 登场效果
hide producer                       # 隐藏 (withdraw 同义)
hide producer with slide_left       # 退场效果 (动画播完自动隐藏)
clear                               # 清除全部立绘
move producer to left 1             # 位移: 瞬间或缓动动画 (时长+缓动)
move producer to 400,300 2 ease in_out
rotate producer 90 1                # 旋转 (逆时针为正, 带时长=动画)
flip producer                       # 水平翻转 (再次调用恢复)
flip producer vertical              # 垂直翻转
```

**描述性信息**: `desc/description/bio/intro/cv/birthday/height/age`
等键不进入立绘表, 存于 `characters[<id>]["meta"]`, 供角色鉴赏等使用。

### 4.5 对话与语音

```gal
text "无角色旁白"
nar "旁白别名"                      # text 的别名
say 主角 "角色对话, 支持 $变量 插值"
say producer "角色 id -> 显示名"
say producer "台词" voice voice_demo    # 语音: say/nar 结束立即停止
say 旁白 "也按旁白处理"              # 兼容写法
```

### 4.6 富文本与 LaTeX

行内标记 (对话/旁白/标题文字/按钮文字通用):

```gal
say a "普通 {c=#ff6600}彩色文字{/c}"
say a "加粗 {b}粗体{/b} 与 {u}下划线{/u} 和 {i}斜体{/i}"
say a "大字号 {s=34}放大{/s}"
say a "公式: {m}\frac{1}{2}{/m} 行内显示"
```

* 富文本标记: `{c=颜色}` `{b}` `{u}` `{i}` `{s=字号}` `{m}公式{/m}`
  (颜色支持 `#RRGGBB` / `R,G,B` / 命名色)
* **公式语法**: `{m}LaTeX 源码{/m}` 或 `{math}...{/math}` (成对闭合)。
  公式源码允许嵌套大括号 (`\frac{1}{2}` 的参数), 解析器按大括号配对
  扫描, 不做标记解析, 原样交给 MathRenderer 渲染。
* **与逐字模式兼容**: 公式在打字机效果中**整体一次性出现** (逻辑字符
  计 1), 不会被逐字符截断成残缺源码; reveal 推进/完成判定基于
  "逻辑长度" (普通文字逐字 + 公式整体计 1), 见 `rich.logic_len()`。

### 4.7 文字显示模式 (typing)

```gal
typing typewriter     # 默认: 打字机逐字符
typing instant        # 整段直接出现
typing terminal       # 终端: 逐字输入 + 行尾闪烁光标 (光标按富文本布局
                      #       精确定位在已输入文本末尾)
typing lines          # 逐行显示 + 节奏停顿
typing wave           # 插件自定义模式 (custom_actions 插件示例)
```

插件 API: `display.register_text_mode(name, {"reset": fn(display),
"update": fn(display, dt)})`。

### 4.8 声音系统

```gal
# 声音注册 (建议独立 audio.gal)
sound sfx_click
    type: sfx_ui                # music / sfx_ui / sfx_story / voice
    file: "materials/audio/sfx_click.wav"
    volume: 0.6

# 音乐: 播放 / 切换 / 循环 / 暂停 / 恢复 / 音量 / 停止
music bgm_piano41               # 播放 (注册名或直接路径, 默认循环)
music bgm_piano39 fade 1.0      # 切换/淡入 (fade 秒; 切换自动旧曲淡出新曲淡入)
music bgm_piano39 loop 0        # loop 1=循环(播完自动重播) / 0=单次
pause music fade 0.8            # 暂停 (淡出后暂停)
resume music fade 0.8           # 恢复 (淡入)
volume music 0.3                # 临时音量 (music/sfx)
stop music                      # 停止 (淡出)

# 全局静音
stop all                        # BGM 淡出停止 + 音效/语音全停
pause all                       # BGM 淡出暂停 + 音效/语音全停

# 音效与语音
sfx sfx_boom                    # 剧情音效
say producer "..." voice voice_demo   # 台词语音 (可省略)

# 语音音量分层 (四层相乘, 每层默认 1.0 不衰减):
#   全局 sfx 音量 × 全局 voice 音量 × 声音块 volume × 角色 voice_volume
volume voice 0.5                # 全局语音音量
volume voice producer 0.3       # 指定角色的语音音量 (改 char voice_volume)
# 角色语音音量也可在 char 块里预设: voice_volume: 0.6

# 自动行为
#   ending 指令 / 标题"开始游戏" 动作: 自动 stop music (淡出, 非全局静音)
#   存档保存 BGM 注册名 (非路径), 读档按名称恢复
```

**fade 淡入淡出**: 所有 `fade`/`stop`/`pause` 的时长值支持
变量/表达式 (如 `stop music fade $f`)。默认时长由 window 配置
`music_fade: 1.0` 控制; 指令显式 `fade N` 覆盖 (0=无淡变)。
淡入淡出为每帧音量线性渐变 (引擎 update 驱动), 暂停菜单时渐变不中断。

**UI 交互音效** (三层配置):

```gal
# window 全局默认 (按钮确认时播放)
window
    ui_click_sound: "sfx_click"
    music_fade: 1.0

# menu 块级 (该菜单活动项变化/确认时)
menu system
    ...按键...
    ui_hover_sound: "sfx_hover"
    ui_click_sound: "sfx_click"

# choice 行内参数
choice ui_click sfx_a ui_hover sfx_b
    "A" -> a
```

点击音只在**明确确认操作**时播放 (菜单/选择支/确认框确认/槽位选中);
文本推进与取消返回不响。语音在台词推进时**先停语音再播 UI 音效**
(避免抢语音通道)。

### 4.9 菜单与键盘导航

```gal
# 命名菜单 (标题画面 / ESC 系统菜单统一架构)
menu title                       # title 块用 menu: title 引用
    start_button
        text: "开始游戏"
        image: "默认.png, 焦点.png"
        width: 262
        height: 98
        stretch: false           # 不拉伸 (原尺寸居中)
        text_visible: false      # 图自带文字时不渲染文案
        action: start game_start # 动作: 类型 [参数]
    ui_hover_sound: "sfx_hover"  # 菜单级 UI 音效 (见 4.8)
    ui_click_sound: "sfx_click"

menu system                      # ESC 菜单: 定义即覆盖内置五项
    continue_button ...          # 按键属性同 title (action: continue/save/...)

# 按键属性: text / image(默认,焦点) / width / height / stretch /
#           text_visible / action (无名参数按类型映射: start->label,
#           slot_menu->mode, save/load->slot; 自定义动作默认 label)

# 选择支行内参数 (见 4.2) 也支持 ui_click/ui_hover 配置
```

**键盘导航** (开始/ESC/选择支菜单通用):

```gal
window
    key_up: "up, w"              # 上移 (可配多键, 逗号分隔)
    key_down: "down, s"          # 下移
    key_confirm: "return, space" # 确认活动选项
```

* 键名: 方向键/功能键 (up/down/left/right/return/space/esc/tab/...) +
  单个字母/数字 ("a"/"1")
* 活动选项 (active_index) 由**键盘移动或鼠标悬停**激活; 初始无活动项 (-1),
  不高亮, 无活动项时 Enter/空格不触发确认
* 键盘移动循环切换; 鼠标点击同步活动索引 (键盘/鼠标状态一致)
* ESC 菜单 (paused) 下鼠标悬停同步依然工作 (见 `sync_mouse_active`)

### 4.9.1 系统菜单两种模式: popup 弹窗 / bar 常驻菜单栏

开发者可在 window 块选择系统菜单形态 (也可用 `window config` 运行时切换):

```gal
window
    menu_mode: "popup"        # popup=ESC 弹窗 (默认) / bar=常驻按钮条
    menu_bar_pos: "bottom"    # bar 模式位置: bottom=对话框下方 / top=窗口上方
```

* **popup (默认)**: 游戏时按 ESC 打开系统菜单 (选择列表覆盖层, 暂停游戏)
* **bar**: 对话框下方或窗口上方常驻一排按钮 (存档/读档/返回标题/退出),
  **游戏过程中随时点击**; ESC 不再弹窗 (仅用于关闭槽位界面等覆盖层)。
  bar 按钮复用 `menu system` 块的按钮定义 (自动过滤无意义的
  `continue`), 未定义时用默认四项。标题画面始终使用自己的按钮, bar 隐藏。

**bar 样式** (独立 `menu_bar` 块, `menu_bar default` 重置):

```gal
menu_bar
    bg: "#1a1a2e"              # 条背景 (含 alpha: "#1a1a2ee0" 或 R,G,B,A)
    border: "#5a5a7a"
    align: center              # 按钮水平对齐: left / center / right
    gap: 12                    # 按钮间距
    padding: 18                # 按钮左右内边距 (决定按钮宽度)
    height: 56                 # 条高度
    btn_h: 38                  # 按钮高度
    y_offset: 0                # 位置微调 (bottom 向上 / top 向下)
    button_bg: "#2a2a44" / button_bg_hover: "#e94560"
    button_border: "#44446a" / button_border_hover: "#ffd282"
    button_radius: 8
    text_color: "#eaeaea" / text_color_hover: "#ffffff"
    text_size: 22
```

bar 模式下对话框自动上移让位 (bottom); 打开槽位界面/确认框等覆盖层时
菜单栏被 dim 盖住, 关闭覆盖层后恢复。

### 4.10 界面样式

```gal
use style modern        # 内置: modern / classic / dark / light / cyber
use style default       # 恢复默认

style my_theme          # 自定义样式块 (同名可重载内置)
    textbox_bg: "#1a1a2e"
    textbox_alpha: 210
    textbox_border: "#e94560"
    textbox_border_width: 3
    textbox_radius: 12
    text_color: "#eaeaea"
    text_size: 28
    speaker_color: "#ffd282"
    speaker_bg: "#1e3a5f"
    arrow_color: "#e94560"
    textbox_image: "..."          # 文本框背景图 (9-slice)
    speaker_image: "..."
    choice_image: "..." / choice_image_hover: "..."
    choice_text_size: 26 / choice_text_color / choice_text_color_hover
    choice_bg / choice_bg_hover / choice_border / choice_border_hover

selection_style          # 选择列表全局样式 (标题/ESC 菜单按钮)
    width_ratio: 0.32 / width: 400 / height: 56 / gap: 14
    anchor_x: center / anchor_y: center
    button_bg / button_bg_hover / button_border / button_border_hover
    button_radius / text_size / dim_alpha
    button_image / button_image_hover / button_stretch / button_text
    text_color / text_color_hover / dialog_image
selection_style default  # 重置

ui                       # UI 主题素材 (九宫格切片, 相对路径)
    textbox: "materials/.../对话_adv对话框_llf.png"
    title_buttons: "默认.png, 焦点.png; 默认2.png, 焦点2.png"
    #   逗号 = 默认图,焦点图; 分号 = 多组按按钮索引取图
    #   单个路径 = 无状态图
    #   支持: textbox/choice_button/title_buttons/menu_button/
    #         confirm_panel/confirm_button/slot_frame/slot_panel
    #   style 图片键优先级更高, 值为 none 禁用主题图
```

### 4.11 标题画面

```gal
title
    image: "materials/title.png"   # 可选: 标题图片
    caption: "Galgame Maker"       # 标题文字 (支持富文本)
    title_x: center / title_y: 210
    start: game_start              # "开始游戏" -> 跳转标签 (必填)
    start_text: "开始游戏"
    load: 0 / load_text: "读取存档"   # 可选: 读档槽位按钮
    quit: true / quit_text: "退出游戏"
    button_x: center / button_y: 420
    menu: title                    # 引用命名菜单 (menu title) 替代内置按钮
```

### 4.12 窗口配置 (window 块)

```gal
window
    title: "我的游戏"
    width: 1280
    height: 720
    icon: "materials/image/icon.png"
    fps: 60
    fullscreen: false              # 全屏启动
    resizable: true                # 允许拖拽窗口边缘 (内容等比缩放)
    confirm_quit: true             # 对话框统一配置 (退出/读档/返回标题):
    confirm_quit_text: "确定要退出游戏吗？"
    confirm_quit_yes: "退出" / confirm_quit_no: "继续游戏"
    confirm_load: true / confirm_load_text / confirm_load_yes / confirm_load_no
    confirm_title: true / confirm_title_text / confirm_title_yes / confirm_title_no
    key_up: "up, w"                # 键盘导航 (见 4.9)
    key_down: "down, s"
    key_confirm: "return, space"
    ui_click_sound: "sfx_click"    # 全局 UI 点击音
    music_fade: 1.0                # BGM 淡入淡出默认时长 (秒)
    menu_continue: "继续游戏"      # ESC 菜单文案 (可自定义)
    menu_save: "存档" / menu_load: "读取存档" / menu_title: "返回标题"
    menu_quit: "退出游戏"
```

### 4.12.1 运行时窗口配置 (window config) 与等比缩放

`window config` 命令可在**程序运行过程中**即时修改窗口配置
(标题/大小/图标/全屏/可缩放/帧率), 无需重启:

```gal
window config
    title: "新的标题"              # 窗口名
    width: 1600                    # 窗口大小 (像素)
    height: 900
    icon: "materials/image/x.png"  # 图标 (相对脚本目录)
    fullscreen: true               # 全屏开关
    resizable: false               # 是否允许拖拽缩放
    fps: 60

fullscreen true                    # 独立全屏指令 (true/false)
```

**等比缩放 (letterbox)**: 引擎以**固定逻辑分辨率** (初始 width/height) 绘制,
窗口可自由调整大小 (拖拽边缘 / window config / 全屏), 画面整体等比拉伸,
保持比例不变; 宽高比不一致时上下/左右留黑边。鼠标坐标自动映射回逻辑坐标,
命中检测/悬停在任何窗口尺寸下都准确。

相关 API (插件/游戏代码):

```python
engine.set_window_title(title)       # 改窗口名
engine.set_window_size(w, h)         # 改窗口大小 (内容等比缩放)
engine.set_fullscreen(True/False)    # 全屏切换
engine.apply_window_config(cfg)      # 批量应用 window 配置 dict
engine.to_logical(pos)               # 窗口坐标 -> 逻辑坐标
```

### 4.13 插件装载配置

```gal
plugins
    only: "shake, scene_notice"    # 只装载列出的
    # 或
    except: "fps_overlay"          # 排除列出的
```

### 4.14 存档/结束/转场

```gal
save                        # 存档到槽位 0 (save/slot0.json)
load                        # 读档
fade / fadeout              # 黑幕淡入/淡出
ending                      # 结束画面 (同时淡出停止 BGM) 后回标题
ending 真结局                # 带结局名: 显示 "— 结局：真结局 —",
                            # 并记入全局进度 (save/global.json, 跨存档)
```

**全局进度** (`save/global.json`, 跨存档):

* `endings` — 已达成结局名列表 (`ending <名>` 触发, 事件 `ending_recorded`)
* `cgs` — 已解锁 CG: `{场景id: [背景名列表]}` (CG 场景 `bg` 展示触发,
  事件 `cg_unlocked`)

```python
engine.get_endings()                 # -> [结局名]
engine.record_ending(name)           # 记录结局 (ending 指令内部调用)
engine.get_unlocked_cgs()            # -> {场景id: [背景名]}
engine.record_cg(scene_id, pose)     # 记录 CG (bg 指令内部调用)
engine.cg_unlocked(scene_id, pose)   # -> bool
```

### 4.15 鉴赏系统 (gallery 插件)

标题画面的「鉴赏」按钮可解锁 **CG / BGM / 角色 / 场景** 四类鉴赏。
配置在独立 `.gal` 文件 (如 `gallery.gal`, 被主脚本 import):

```gal
gallery
    unlock_ending: "真结局"          # 达成此结局解锁鉴赏按钮 (空=不锁)
    button_text: "鉴赏"              # 标题菜单按钮文本
    title: "鉴赏"                    # 鉴赏界面标题
    categories: "cg, bgm, character, scene"   # 可用分类
    locked_hint: "达成「真结局」后解锁鉴赏"

scene cg_school                     # CG 场景定义 (type: cg)
    type: cg
    name: "学园CG"
    default: "materials/cg/a.png"
    morning: "materials/cg/b.png"   # 每张背景 = 一张可收集 CG
```

* **解锁**: 达成 `unlock_ending` 指定的结局 (用 `ending <名>` 指令) 后,
  标题菜单的「鉴赏」按钮从禁用态变为可用; 未解锁时按钮呈禁用态
* **按钮样式**: 在 `ui.gal` 的 `menu title` 中定义
  (子块名任意, `action: gallery_open`, 样式照常配置);
  未在脚本中定义时插件自动追加默认样式按钮
* **禁用图**: 按钮支持 `image_disabled` 键 (禁用态专用图片, 系统菜单通用;
  未配置时禁用态为纯色暗化)
* **数据来源**: CG 来自 `type: cg` 场景的已解锁背景; BGM 来自
  `sound` 注册表 `type: music`; 角色来自 `char` (含 desc 等描述);
  场景来自 `scene` 定义 (CG 场景只出现在 CG 鉴赏, 场景鉴赏仅展示
  normal 场景)
* **CG 鉴赏**: 同一 CG 场景的多个形态**合并为一个条目** (缩略图 +
  形态进度 x/y); 点击放大后**点击图片轮播切换形态**, 播完最后一个
  形态后再点击退出 (ESC 随时退出); 未解锁的 CG 显示**灰色占位框**
  (问号 + "未解锁"), 点击无效
* **界面**: 分类按钮行 + 内容网格 (BGM 点击后先在页面显示"正在切换"
  提示再实际切换试听), ESC/返回 关闭回标题
* **标题 BGM**: `start:` 块可用 `music` 配置标题背景音乐, 回标题/
  退出鉴赏时自动恢复播放 (engine 记录 `runtime.title_bgm`)

---

## 5. 命名空间系统

三个域:

| 域 | 内容 |
| --- | --- |
| `builtin::` | 引擎内置指令/变量 (`builtin::set`、`builtin::text`) |
| `main::` | 项目文件定义的变量 (`set love = 1` 归此域) |
| `<插件名>::` | 插件注册的指令/变量 (`shake::shake`、`custom_actions::do_action`) |

**无命名空间解析顺序**:

* **变量**: `main::` → `builtin::` (引擎预置 `builtin_vars`) → 找不到
  返回默认 (插值空串) / 表达式求值报错
* **指令**: `builtin::` → `main::` → **已 using 的插件命名空间** →
  找不到时报错并**提示所在命名空间** ("指令 shake 位于 shake::shake,
  需 using 或用完整命名空间调用")

**using 导入** (类似 C++):

```gal
using shake                 # 之后 shake 可省略前缀
using shake custom_actions  # 一次导入多个
```

没有 using 时, 插件指令裸名调用被拒绝并提示 —— 杜绝名称冲突。
顶层 using 在 `load_script` 时**静态生效** (不依赖执行流程)。

**变量细节**:

* `set love = 1` 与 `set main::love = 1` 等价 (main 域键规范化)
* `set plugin::cnt = 3` 存为带前缀键 `plugin::cnt`
* `$main::love` / `$love` / `$plugin::cnt` 均可用于插值/表达式/条件

**指令注册表** (`engine.commands`):

* `register(name, fn, ns="main")` / `register_builtin(name, fn)`
* `has(name, ns=None)` / `get(name, ns=None)` / `find(name)` (定位提示)
* `call(name, stmt, ns=None)` / `unregister(name, ns)`
* `names(ns=None)`

---

## 6. 声音系统详解

### 6.1 三类声音

| 类型 | 管理 | 播放 |
| --- | --- | --- |
| 音乐 music | mixer.music 流式 + fade 状态机 | `music <名/路径>` |
| 音效 sfx_ui / sfx_story | Sound 实例 | UI 自动 / `sfx <名>` |
| 语音 voice | **独立通道** (Channel 0) | `say/nar ... voice <名>` |

### 6.2 BGM 淡入淡出状态机 (`audio.update`)

* `play_music(path, loop, fade, name)` — 切换时旧曲淡出 (音量渐降) →
  完成后新曲淡入 (0 音量渐升); loop=True 循环 / False 单次
* `stop_music(fade)` / `pause_music(fade)` / `resume_music(fade)`
* `set_bgm_volume(v)` / `set_sfx_volume(v)`
* `stop_all(fade)` / `pause_all(fade)` — 全局 (BGM 淡出 + 音效/语音停)
* `play_voice(path)` / `stop_voice()` / `voice_playing()`
* `current_bgm` (路径) / `current_bgm_name` (注册名, 存档/显示用)
* 事件: `music_play` (name/loop/fade/path) / `music_pause` /
  `music_resume` / `music_stop` / `voice_play` / `voice_stop` /
  `sound_all_pause` / `sound_all_stop` / `sound_register`

### 6.3 语音生命周期

* 台词带 `voice` 时显示即播; **该句推进时立即停止** (先停语音再播
  UI 音效, 避免通道竞争); 回标题/读档也停语音
* 语音独立通道, 不干扰音效

### 6.4 存档与 BGM

* 存档保存 `current_bgm_name` (注册名, 非绝对路径); 读档用
  `engine.play_music` (名称/路径都兼容) 恢复
* `ending` 指令与标题"开始游戏"动作自动 `stop_music` (淡出)

---

## 7. 存档系统

* 槽位: 6 个 (save/slot0-5.json), 由 ESC 菜单或标题"读取存档"打开
* 存档内容: 变量 / 剧情位置 (标签+语句索引) / 调用栈 / 阻塞状态 /
  背景 (场景 id + 背景名) / 立绘 (id/立绘名/透明度/旋转/翻转/中心点) /
  BGM 注册名 / 当前样式名 / 文本与选择支状态
* 对象以**脚本 id** 存储 (不存图片路径) —— 重命名图片不破坏旧存档
* 读档精确恢复; `sleep` 阻塞中读档不恢复剩余等待时间
* 元数据 API (快照插件用):
  `save.set_meta(slot, key, value)` / `get_meta(slot, key, default)` /
  `meta_path(slot, rel)` (相对路径 → 存档目录绝对路径) /
  `list_slots(count)` (含 time/label/preview/**screenshot**/empty)

**存档画面快照** (插件 `slot_thumbnails.py`):

* 引擎每帧维护 `_last_game_frame` (无覆盖层时的纯游戏画面,
  槽位面板/菜单/确认框/选择支/错误弹窗都算覆盖层)
* 存档事件 → `engine.get_last_game_frame()` 截图 → 缩小 150×84 →
  存存档目录 (相对路径 `thumb_slotN.png`) → 元数据写 `screenshot`
  相对名 (不存绝对路径)
* 槽位界面通过 `display.register_slot_thumbnail_provider(fn)` 绘制,
  缩略图高度自动适配槽位 (保持比例), 文字区自适应字号+单行截断,
  宽度不足时省略时间

---

## 8. 渲染系统

| 组件 | 说明 |
| --- | --- |
| 背景 | `scene` + `bg <场景> <背景名> [with 过渡]`; cover/fit/center/stretch |
| 立绘 | `char` + `show/hide/move/rotate/flip`; 登场/退场 9 种效果 |
| 文本框 | `style` 配置 (背景图/颜色/字号); 富文本 + LaTeX |
| 选择支 | `choice:` 分支; 按钮样式/图片/字号/宽度可配 |
| 文字显示 | typewriter / instant / terminal (光标) / lines / 插件 |
| 过渡 | fade/dissolve/blinds/slide/circle/pixelate/zoom + 插件 |
| 错误弹窗 | 温和提示 + 剪贴板复制 + 日志追加 |
| UI 主题 | `ui` 块九宫格切片 (默认/焦点双态) |

### 8.1 截图与槽位界面 API

```python
engine.display.capture()                              # 当前画面 Surface 副本
engine.get_last_game_frame()                          # 最近纯游戏画面帧
engine.display.register_slot_thumbnail_provider(fn)   # 槽位缩略图绘制钩子
# fn(slot_index, slot_info) -> Surface | None
```

---

## 9. 插件体系

插件是 `framework/plugins/` 下的 `.py` 文件 (下划线开头忽略),
引擎启动自动发现。**命名空间 = 插件文件名**。

### 9.1 插件清单

| 插件 | 提供 |
| --- | --- |
| shake | `shake`/`flash` 指令, 屏幕震动与白闪 |
| fps_overlay | 右上角 FPS 浮层 |
| scene_notice | 场景切换时左上角通知 |
| wipe_transition | `bg ... with wipe` 擦除过渡 |
| custom_actions | `explode` 动作 + `do_action` 指令 + wobble 立绘效果 + wave 文字模式 |
| bgm_notice | BGM 播放/暂停/恢复/停止通知 (music_* 事件) |
| slot_thumbnails | 存档画面快照 + 槽位缩略图 |

### 9.2 两种写法

```python
# 1. 装饰器写法 (推荐)
from framework.api import command, event_listener

@command("mycmd")                       # 自定义 DSL 指令 (注册到 <插件名>::)
def mycmd(engine, stmt, **kw):
    engine.show_notice("指令被调用!")
    return None                          # 返回 "block" 可阻塞等外部事件

@event_listener("bg_change")            # 订阅事件 (engine 参数自动注入)
def on_bg(path, engine, **kw):
    print("背景切换到", path)
```

```python
# 2. 类写法 (生命周期管理)
from framework.api import Plugin

class MyPlugin(Plugin):
    name = "my_plugin"
    version = "1.0"

    def on_load(self):                   # 装载时 (可用 self.engine)
        @self.listen("draw_overlay")     # 每帧渲染钩子
        def overlay(surface, **kw):
            pass
        @self.add_command("greet")       # 指令 (命名空间 = 插件名)
        def greet(engine, stmt, **kw):
            engine.say("插件", "你好")

    def on_unload(self):                 # 卸载时清理 (如注销 provider)
        pass
```

### 9.3 事件一览

| 事件 | 载荷 |
| --- | --- |
| engine_start / engine_quit | engine |
| script_load / script_start / script_end | path / name |
| label_enter | label |
| statement | stmt, label |
| text_show / text_advance / text_complete | text, speaker |
| choice_show / choice_made | choices / index, label, text |
| bg_change | path, effect |
| scene_change | id, name, background, pose |
| sprite_show / sprite_hide | id, path |
| sprite_effect_complete | id, direction |
| var_set | name, value |
| using | namespaces |
| sound_register | name, type |
| music_play / music_pause / music_resume / music_stop | name, path, loop, fade |
| voice_play / voice_stop | path |
| save / load | slot, path |
| confirm_show / confirm_choice | text / index |
| action | type, params, source |
| draw_overlay (每帧) | surface |
| error / error_dismiss | exc / level |

### 9.4 引擎公共 API

```python
engine.display      # 渲染: set_bg/show_sprite/hide_sprite/show_text/show_choices...
engine.audio        # BGM 状态机 / play_sound / play_voice / stop_voice
engine.save         # save(slot,data)/load(slot)/set_meta/get_meta/meta_path
engine.runtime      # vars / evaluate / jump / _interp / sounds / using_ns...
engine.events       # 事件总线 (on/emit/off)
engine.commands     # 指令注册表 (register/has/get/call/find/unregister)
engine.plugins      # 插件管理器 (discover/load_module_from_path/unload_module)
engine.ui           # UI 绘制原语
engine.say(speaker, text)
engine.set_var(name, value) / engine.get_var(name)
engine.show_notice(text)
engine.save_game(slot) / engine.load_game(slot)
engine.resolve_path(rel)   # 相对脚本目录解析资源路径

# 音频 API (名称可为注册名或路径)
engine.play_music(name_or_path, loop=True, fade=None)
engine.stop_music(fade) / engine.pause_music(fade) / engine.resume_music(fade)
engine.play_sfx(name) / engine.play_voice(name) / engine.stop_voice()
engine.set_music_volume(v) / engine.set_sfx_volume(v)
engine.stop_all_sounds(fade) / engine.pause_all_sounds(fade)
engine.get_last_game_frame()

# 错误处理
engine.handle_error(exc, level="error")
engine.copy_to_clipboard(text)
```

### 9.5 注册接口汇总

| 接口 | 用途 |
| --- | --- |
| `engine.events.on/emit/off` | 事件总线 |
| `engine.commands.register` / `@command` | 自定义 DSL 指令 |
| `engine.register_action(name, fn)` | 选择列表按钮动作 |
| `display.register_transition(name, cls)` | 背景过渡效果 |
| `display.register_sprite_effect(name, fn, dur)` | 立绘登场/退场动画 |
| `display.register_text_mode(name, spec)` | 文字显示模式 |
| `display.register_slot_thumbnail_provider(fn)` | 槽位缩略图 |
| `engine.register_action` + `do_action` 指令 | 脚本触发动作 |

### 9.6 动作系统

| 动作 | 参数 | 说明 |
| --- | --- | --- |
| `start` | label | 启动游戏 (跳转标签) |
| `quit` | | 关闭游戏 (走退出确认) |
| `title` | | 回到标题画面 |
| `continue` | | 关闭菜单继续游戏 |
| `slot_menu` | mode=save/load | 打开存档/读档页面 |
| `save` / `load` | slot | 直接存档/读档 |
| `close` | | 关闭当前选择列表 |

自定义动作: `engine.register_action("explode", fn)` 其中
`fn(engine, params, source)`, 返回 True 执行后关闭选择列表。

### 9.7 运行时插件管理 (DSL 语句)

```gal
plugin load custom_actions   # 装载 (自动加入 using)
plugin unload shake          # 卸载 (清类实例 on_unload + 指令/事件/订阅)
plugin list                  # 列出已加载插件
```

`PluginManager` 记录 `directory` (discover 时), 运行时装载按插件名找
`<目录>/<名>.py`; `unload_module` 先卸载该模块的 Plugin 类实例再清
模块级注册。

---

## 10. UI 绘制原语 (`engine.ui`)

```python
from pygame import Rect

engine.ui.panel(surface, Rect(10, 10, 200, 60),
                bg_color=(0, 0, 0, 185),
                border_color=(255, 255, 255, 80), border_width=2, radius=8)
engine.ui.text(surface, font, "文字", center=(100, 40))
engine.ui.wrap_text(font, "长文本", max_width=180)     # -> [行]
engine.ui.multiline_text(surface, font, "多行", 20, 20,
                         max_width=180, max_lines=3)
engine.ui.dim_overlay(surface, alpha=150)
```

插件在 `draw_overlay` 事件里可直接叠加 HUD / 调试信息。

---

## 11. 错误处理

* **主循环隔离**: 每帧 update/draw/事件处理包在 try/except 中
* **全局兜底**: `sys.excepthook` 捕获主线程未捕获异常
* **温和弹窗**: 错误面板 (摘要 + 日志路径), 三按钮: 继续/复制/退出
* **日志文件**: `<项目目录>/logs/errors.log` (时间戳 + 错误编号)

**错误分级**: `warn` 仅记录 (未知指令/资源缺失); `error` 记录+弹窗
(跳转到不存在标签/表达式求值失败/脚本插件异常)。

---

## 12. 测试 (573 项断言)

`framework/tests/smoke.py`, dummy 视频/音频驱动, 无窗口可跑:

```
py -3.10 framework/tests/smoke.py
```

覆盖: 解析器 / 运行时逻辑 (变量/分支/跳转/调用栈/表达式) / 交互推进 /
样式表 / selection / 存档 (含 BGM 名称/快照元数据) / 过渡 / 角色 / 场景 /
对话框 / 菜单 / 动作 / 立绘效果 / 文字模式 / 插件装载配置 / import 拆分 /
键盘导航 / 命名空间 / 音频 (fade 状态机/全局静音/UI 音效) / 存档快照 /
运行时插件管理 / LaTeX 逐字兼容 / 语音生命周期 / 分角色语音音量 /
窗口配置与等比缩放 (to_logical/present letterbox/window config 指令) /
常驻菜单栏 (bar 模式: 构建/命中/点击/ESC 语义/样式/自定义项) /
错误弹窗。

---

## 13. 开发历史与关键坑位 (交接备忘)

1. **立绘重开消失**: `clear_sprites` 清 sprite_order 但保留 sprites 字典;
   `show_sprite` 需用 `sid not in sprite_order` 判断入序 (否则重开后
   立绘存在却不绘制)
2. **立绘首帧闪现**: `show ... with 效果` 启动效果后需立即应用 t=0 起始
   状态 (否则首帧在目标位置绘制一帧)
3. **terminal 语义**: terminal = 逐字+行尾闪烁光标; 原逐行效果改名 `lines`
4. **语音与 UI 音效抢通道**: 文本推进先 `stop_voice` 再播 click 音
5. **ESC 菜单键盘导航失效**: paused 跳过 display.update → 鼠标悬停同步
   需在 paused 时单独调用 `sync_mouse_active`
6. **active_index 语义**: 初始 -1 (无活动项), 键盘/鼠标激活; 无活动项
   Enter 不确认
7. **插件指令命名空间**: 插件名 = 文件名 (`gm_plugin_` 前缀剥离);
   `Plugin.add_command` 与模块级注册都要带 ns; 卸载也要带 ns 否则残留
8. **顶层 using 静态生效**: using 写在非标签顶层时, load_script 阶段
   静态应用 (不依赖执行流程)
9. **evaluate 的 `$var`**: 翻译成 `__vars__['x']` 后安全正则
   `\b__(?!vars__)\w+__\b` 需排除内部名 `__vars__`
10. **LaTeX 嵌套**: `find("}")` 不配对会截断公式 → 标记提取需大括号
    配对扫描; 公式与逐字模式: 公式计 1 逻辑字符 (rich.logic_len),
    reveal 完成判定用逻辑长度
11. **BGM 存名称**: 存档存 `current_bgm_name` (注册名); 事件载荷含
    name/loop/fade/path
12. **show_slot_menu 参数顺序**: `show_slot_menu(slots, mode)` —
    slots 在前!
13. **存档快照**: 截图必须用 `get_last_game_frame()` (纯游戏画面帧),
    不能截当前画面 (槽位面板会入镜); 缩略图路径存相对名
14. **旧版方法残留**: 类中同名方法后者覆盖前者 —— 修改指令实现时
    务必 grep 确认无重复定义 (曾两次踩坑: _cmd_sound/_cmd_music)

---

## 14. 已知限制

* `.wid` 组件仅支持模板化兼容 (reg class + when run 块), 编辑器特有的
  `#id` 引用 / `general.page.height` 等组件树表达式不解析 (警告跳过)
* `weight` 语法可解析但已不承担背景职责 (统一走 scene/bg)
* 音频/图片缺失仅告警不中断
* `sleep` 阻塞中读档不恢复剩余等待时间
* 存档槽位固定 6 个
---

## 15. 变更日志 (开发时间线)

按里程碑记录整个引擎的演进过程, 便于接手者理解设计动机。

| 阶段 | 内容 |
| --- | --- |
| 0. 骨架 | 空 framework/ 目录, 目标: 运行时引擎 + 插件 API |
| 1. 解析器 | .gal DSL 解析 (属性块/标签/流控/表达式/import 递归合并) |
| 2. 运行时 | 变量/分支/跳转/调用栈/角色/场景/选择支/存档骨架 |
| 3. 渲染 | 背景/立绘/文本框/富文本 (颜色/加粗/LaTeX)/选择列表/槽位界面 |
| 4. 菜单统一 | title/ESC 菜单归并 selection 组件 + 通用 action 分发 |
| 5. 命名菜单 | `menu <id>` 块: 每按键独立图片/尺寸/动作; menu title/system |
| 6. 存档完善 | 变量/调用栈/阻塞状态/背景/立绘/音乐/样式全量保存恢复 |
| 7. 插件体系 | 事件总线/指令注册/动作/过渡/立绘效果/文字模式 5 大扩展点 |
| 8. 立绘效果 | 9 种登场/退场预设 + 插件 wobble |
| 9. 文字模式 | typewriter/instant/terminal/lines + 插件 wave |
| 10. 键盘导航 | key_up/key_down/key_confirm 配置; 活动选项 -1 语义 |
| 11. 声音系统 | sound 注册块 / music/sfx/voice 三分管理; 语音独立通道 |
| 12. BGM 增强 | fade 状态机 (淡入淡出/暂停/恢复/音量/切换); music_fade 配置 |
| 13. UI 音效 | window 全局默认 + menu 块级 + choice 行内 (hover/click) |
| 14. 存档名称 | BGM 存注册名; ending/开始游戏自动淡出停止 |
| 15. 命名空间 | builtin::/main::/插件名:: 三域 + using + 解析顺序 + 报错提示 |
| 16. 运行时插件 | plugin load/unload/list 语句; 卸载完整清理 |
| 17. 存档快照 | 纯游戏画面帧 + 槽位缩略图 (相对路径) |
| 18. LaTeX 兼容 | 大括号配对扫描 + 公式逻辑长度 (逐字模式) |
| 19. 交接文档 | 本 README 完整重写 (493 项测试全绿) |
| 20. 窗口/语音增强 | 分角色语音音量 (char voice_volume + volume voice) + 运行时 window config 命令 + 全屏切换 + 窗口等比缩放 (letterbox, 鼠标坐标映射) + 测试增至 519 项 |
| 21. 菜单双模式 | menu_mode: popup (ESC 弹窗) / bar (常驻菜单栏, 对话框下方或窗口上方, 随时点击) + menu_bar 样式块 + 运行时切换 + 测试增至 539 项 |
| 22. 鉴赏系统 | gallery 插件 (标题按钮+结局解锁+CG/BGM/角色/场景鉴赏) + 菜单按钮注册/禁用 API + ending 结局名 + char 描述 + scene type cg + 全局进度 (save/global.json) + 测试增至 562 项 |
| 23. 鉴赏完善 | 标题按钮多列布局 (button_columns) + 按钮禁用图 image_disabled + BGM 先显示后切换 + 标题 BGM (start 块, 退出鉴赏恢复) + 测试增至 568 项 |
| 24. CG 鉴赏细化 | CG 按场景合并 (形态轮播, 播完退出) + 未解锁灰色占位框 + 场景鉴赏排除 CG 场景 + 测试增至 573 项 |

---

## 16. demo 脚本逐文件说明

`test/engine_demo/` 是完整可运行的演示项目, 覆盖引擎全部特性:

| 文件 | 内容与演示点 |
| --- | --- |
| `demo.gal` | 主流程: window 配置 (键盘导航/UI 音效/确认框/music_fade) + plugins 装载 + **using 导入** + title 标题 + game_start 开场 (语音旁白) |
| `ui.gal` | 界面样式: style 自定义主题 + selection_style + ui 主题切片 + **menu title/system** (带菜单级 ui_hover/ui_click 音效) |
| `cast.gal` | 角色与场景定义: char producer (多立绘 + voice_volume 分角色语音音量) + scene school |
| `audio.gal` | 声音注册: sfx_click/sfx_hover/sfx_boom/voice_demo/bgm_piano41/bgm_piano39 |
| `gallery.gal` | 鉴赏配置 (gallery 块: 真结局解锁) + CG 场景定义 (scene type: cg) |
| `branches.gal` | 分支流程: 选择支 (like_it/neutral/dislike) + 立绘登场退场 + 场景过渡 + 文字模式演示 + **BGM 控制全流程** (淡入/暂停/恢复/音量/切歌/淡出) + **window config 运行时窗口配置** (改标题/改尺寸/全屏切换, 等比缩放) + **menu_mode 双模式切换** (bar 常驻菜单栏 ↔ popup ESC 弹窗) + **CG 展示与真结局** (解锁鉴赏) + ending |

素材目录:
* `materials/image/` — 背景/立绘/UI 九宫格切片素材包
* `materials/audio/` — 生成的测试音频 (点击哔/悬停嘀/轰鸣/语音占位) +
  两首测试 BGM (maou_bgm_piano41/39.mp3)

---

## 17. DSL 指令速查表

| 指令 | 语法 | 说明 |
| --- | --- | --- |
| 对话 | `say <角色> "文本" [voice 名]` / `nar "文本"` / `text "文本"` | 台词/旁白, 支持富文本与 $变量 |
| 背景 | `bg <场景> [背景名] [with 效果]` | 场景背景或直接路径 |
| 场景 | `scene <id>` 块 | 场景定义 (name/default/背景名) |
| 角色 | `char <id>` 块 | 角色定义 (name/立绘名:路径) |
| 立绘 | `show <角色> [立绘名] [with 效果]` / `hide <角色> [with 效果]` | 显示/隐藏 |
| 变换 | `move/rotate/flip <角色> ...` | 位移/旋转/翻转 |
| 清除 | `clear` | 清除全部立绘 |
| 样式 | `use style <名>` / `style <名>` 块 / `selection_style` 块 | 主题切换/定义 |
| UI 素材 | `ui` 块 | 九宫格主题切片 |
| 菜单 | `menu <id>` 块 | 命名菜单定义 (按钮支持 image_disabled 禁用图) |
| 菜单栏 | `menu_bar` 块 | 常驻菜单栏样式 (bar 模式) |
| 标题 | `title` 块 | 标题画面 (menu: 引用; button_columns 多列) |
| 选择支 | `choice [ui_click X] [ui_hover Y]` 块 | 分支选择 |
| 变量 | `set <名> = <表达式>` | 赋值 (main::/插件:: 前缀) |
| 条件 | `if/elif/else/endif` | 分支 |
| 跳转 | `jump <标签>` / `call <标签>` / `return` | 流程控制 |
| 等待 | `sleep <秒>` | 阻塞等待 |
| 文字模式 | `typing <模式>` | typewriter/instant/terminal/lines/插件 |
| 声音 | `sound <名>` 块 | 声音注册 |
| 音乐 | `music <名/路径> [loop 0/1] [fade 秒]` | 播放/切换 |
| 暂停 | `pause music [fade 秒]` / `pause all` | 暂停音乐/全局 |
| 恢复 | `resume music [fade 秒]` | 恢复 |
| 音量 | `volume music <0-1>` / `volume sfx <0-1>` / `volume voice [角色] <0-1>` | 临时音量 (voice 可全局或按角色) |
| 停止 | `stop music [fade 秒]` / `stop all` | 停止音乐/全局 |
| 音效 | `sfx <声音名>` | 剧情音效 |
| 窗口 | `window config` 块 | 运行时改 标题/尺寸/图标/全屏/可缩放/fps (即时生效) |
| 全屏 | `fullscreen true/false` | 切换全屏 (内容等比缩放) |
| 命名空间 | `using <命名空间...>` | 导入插件命名空间 |
| 插件 | `plugin load/unload/list <名>` | 运行时插件管理 |
| 存档 | `save` / `load` | 槽位 0 存档/读档 |
| 转场 | `fade` / `fadeout` | 黑幕淡入/淡出 |
| 结束 | `ending [结局名]` | 结束画面 + 结局记录 (全局进度) |
| 鉴赏 | `gallery` 块 / `scene type: cg` | 鉴赏配置 / CG 场景 (展示即收集) |
| 结束 | `ending [结局名]` | 结束画面 + 结局记录 (全局进度) 回标题 |

## 18. 已知限制 (补充)

* 语音为占位音效 (demo), 接入真实语音只需替换 audio.gal 中的文件路径
* BGM 切换为单通道 (pygame.mixer.music), 无交叉淡化 (旧曲淡出→新曲淡入
  顺序执行)

