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
py -3.10 gamelauncher.py

# 运行自己的脚本 (也支持直接把 .gal 文件拖到 gamelauncher.py 上)
py -3.10 gamelauncher.py path/to/your.gal

# 运行冒烟测试
py -3.10 framework/tests/smoke.py
```

### 脚本拆分 (import)

`.gal` 支持按功能拆分多个文件, 顶层用 `import` 合并:

```gal
import "ui.gal"          # 界面样式定义
import "cast.gal"        # 角色与场景定义
import "branches.gal"    # 分支流程标签
```

合并规则:
* 被导入文件的标签全部并入 (重复标签报错), 子文件的 `start` 标签忽略
* 顶层声明 (window/style/char/scene/plugins/selection_style) 按 import
  位置顺序并入, 运行时静态注册
* 相对路径 (相对 import 语句所在文件), 支持链式 import, 循环导入报错

demo (`test/engine_demo/`) 已按此拆分: `demo.gal` (主流程) +
`ui.gal` (样式) + `cast.gal` (角色/场景) + `branches.gal` (分支)。

窗口配置 / 插件配置的预解析 (启动器) 同样递归展开 import。

### 插件

框架自带 5 个正式插件 (`framework/plugins/`), 默认全部自动装载,
可在脚本顶层用 `plugins` 块选择装载 (插件文件名, 不含 .py):

```gal
plugins
    only: "shake, scene_notice"    # 只装载列出的
    # 或
    except: "fps_overlay"          # 排除列出的
```

| 插件 | 提供 |
| --- | --- |
| shake | `shake`/`flash` 指令, 屏幕震动与白闪 |
| fps_overlay | 右上角 FPS 浮层 |
| scene_notice | 场景切换时左上角通知 |
| wipe_transition | `bg ... with wipe` 擦除过渡 |
| custom_actions | `explode` 动作 + `do_action` 指令 |

插件开发见 [插件 API](#插件-api)。

窗口配置写在脚本顶层, 启动器创建窗口前读取::

```gal
window
    title: "我的游戏"
    width: 1280
    height: 720
    icon: "materials/image/icon.png"
    fps: 60
    fullscreen: false
    confirm_quit: true                   # 对话框 (dialog) 统一配置:
    confirm_quit_text: "确定要退出游戏吗？"   #   退出确认 (关窗口/ESC/退出按钮)
    confirm_quit_yes: "退出"
    confirm_quit_no: "继续游戏"
    confirm_load: true                   #   读档确认
    confirm_load_text: "确定要读取这个存档吗？"
    confirm_load_yes: "读档"
    confirm_load_no: "取消"
    confirm_title: true                  #   返回标题确认 (菜单"返回标题")
    confirm_title_text: "确定要返回标题画面吗？"
    confirm_title_yes: "返回标题"
    confirm_title_no: "取消"
    key_up: "up, w"                # 菜单键盘导航: 上移 (可自定义多键)
    key_down: "down, s"            # 下移
    key_confirm: "return, space"   # 确认活动选项 (开始/ESC/选择支菜单通用)
    # 活动选项由 键盘移动 或 鼠标悬停 激活; 初始无活动项 (-1) 不高亮,
    # 无活动项时 Enter/空格 不触发确认 (文本推进仅限无菜单时)

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
    # 背景: 统一走场景方案 (bg <场景id> [背景名], 或直接 bg "路径")
    bg school
    bg school morning
    bg "materials/bg.png"            # 直接指定路径

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

    # 角色系统
    char producer                      # 角色定义 (可放脚本顶层, 静态注册)
        name: "制作人"                  #   显示名 (台词名字框用)
        default: "materials/char/producer/producer1.png"  # 默认立绘
        normal: "materials/char/producer/producer1.png"   # 立绘名: 路径
        happy: "materials/char/producer/producer2.png"
    show producer normal               # 显示角色立绘 (默认居中)
    show producer happy                # 切换立绘 (保持中心点原位替换)
    hide producer
    move producer to left 1            # 立绘位移: 瞬间 (无时长) 或缓动动画
    move producer to 400,300 2 ease in_out   # 目标中心坐标 + 时长 + 缓动
    rotate producer 90 1               # 旋转 (逆时针为正; 带时长=旋转动画)
    flip producer                      # 水平翻转 (再次调用恢复)
    flip producer vertical             # 垂直翻转
    say producer "角色台词, 名字框显示'制作人'"   # 角色 id -> 显示名
    nar "旁白台词, 无名字框"            # text 的别名
    say 旁白 "也按旁白处理"            # 兼容写法

    # 场景系统
    scene school                       # 场景定义 (可放脚本顶层, 静态注册)
        name: "学校"                    #   显示名
        default: "materials/image/bg.png"   # 默认背景
        morning: "materials/image/bg.png"   # 背景名: 路径
    bg school                          # 切到场景默认背景 (触发 scene_change 事件)
    bg school morning                  # 场景内切换背景
    bg school with fade                # 背景过渡效果: fade 黑幕淡入淡出
    bg school with dissolve            #   dissolve 交叉溶解
    bg school with blinds              #   blinds 百叶窗
    bg school with wipe                #   wipe 等插件自定义效果

# 流程控制
    jump label_a                # 跳转
    call sub_routine            # 调用 (可 return)
    return

# 标题画面 (放在 start 标签开头)
    title
        image: "materials/title.png"     # 可选: 标题图片 (显示在文字上方)
        caption: "Galgame Maker"         # 标题文字 (支持富文本, 可留空)
        title_x: center                  # 标题水平: center/left/right/数字
        title_y: 210                     # 标题垂直中心 (像素)
        start: game_start                # "开始游戏" -> 跳转标签 (必填)
        start_text: "开始游戏"           # 自定义按钮文本
        load: 0                          # 可选: 读取存档槽位
        load_text: "读取存档"
        quit: true                       # 可选: 退出按钮
        quit_text: "退出游戏"
        button_x: center                 # 按钮区水平锚点
        button_y: 420                    # 按钮区垂直锚点

    # 界面样式
    use style modern                   # 内置样式随时取用 (无需定义):
    use style classic                  #   modern / classic / dark / light / cyber
    use style dark
    use style light
    use style cyber
    selection_style                    # 选择列表 (标题/ESC菜单) 全局样式:
        width_ratio: 0.32             #   按钮宽占比
        height: 56 / gap: 14
        anchor_x: center               #   水平锚点 (center/left/right/数字)
        anchor_y: center               #   垂直: center=整体居中 / 数字(顶部)
        button_bg: "#202020" / button_bg_hover / button_border / button_border_hover
        button_radius: 6 / text_size: 28 / dim_alpha: 120
    selection_style default            # 重置为默认
    style my_theme                     # 自定义样式块 (同名可重载内置)
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
        textbox_image: "materials/image/ui/say.png"      # 文本框背景图 (9-slice)
        speaker_image: "materials/image/ui/button.png"   # 角色名框背景图
        choice_image: "materials/image/ui/button.png"    # 选择支按钮背景图
        choice_image_hover: "materials/image/ui/button.png"
        choice_text_size: 26                             # 选择支字号
        choice_text_color: "#e6e6eb" / choice_text_color_hover
        # 选项按钮配色: choice_bg / choice_bg_hover / choice_border / choice_border_hover
    use style my_theme                 # 切换样式 (存档记录当前样式名)
    use style default                  # 恢复默认
    selection_style                    # 选择列表全局样式补充:
        width: 400                     #   固定像素宽度 (优先于 width_ratio)
        button_image: "..."            #   按钮背景图
        button_image_hover: "..."
        button_stretch: false          #   按钮图不拉伸 (原尺寸居中)
        button_text: false             #   不渲染按钮文字 (图自带文字时)
        text_color: "#3a3a4e"          #   按钮文字色 (亮色主题用深色)
        text_color_hover: "#18182a"
        dialog_image: "..."
    ui                                 # UI 主题素材 (直接相对路径):
        textbox: "materials/image/素材切片/对话/对话_adv对话框_llf.png"
        title_buttons: "…/标题_开始游戏_默认_llf.png, …/标题_开始游戏_焦点_llf.png; …/标题_读取存档_默认_llf.png, …/标题_读取存档_焦点_llf.png; …/标题_退出游戏_默认_llf.png, …/标题_退出游戏_焦点_llf.png"
        #   逗号 = 默认图,焦点图; 分号 = 多组按按钮索引取图 (不同按键不同图)
        #   单个路径 = 无状态图
        #   支持: textbox/choice_button/title_buttons/menu_button/
        #         confirm_panel/confirm_button/slot_frame/slot_panel
        #   style 图片键 (textbox_image 等) 优先级更高, 值为 none 禁用主题图

    # 标题画面 / ESC 菜单 (命名菜单, 每个按键可精细配置)
    menu title                       # 标题菜单: title 块用 menu: title 引用
        start_button
            text: "开始游戏"
            image: "…/标题_开始游戏_默认_llf.png, …/标题_开始游戏_焦点_llf.png"
            width: 262
            height: 98
            stretch: false           # 不拉伸 (原尺寸居中)
            text_visible: false      # 图自带文字时不渲染文案
            action: start game_start # 动作: 类型 [参数] (内置/插件自定义)
    menu system                      # ESC 菜单: 定义即覆盖内置五项
        continue_button
            text: "继续游戏"
            image: "…/确认_按钮_默认_llf.png, …/确认_按钮_焦点_llf.png"
            width: 240
            height: 60
            action: continue
        save_button ...              # 其余按键同理 (slot_menu/title/quit)
    # 按键属性: text / image(默认,焦点) / width / height / stretch /
    #           text_visible / action (无名参数按类型映射: start->label,
    #           slot_menu->mode, save/load->slot; 自定义动作默认 label)

    # 立绘登场/退场效果
    show producer with bounce          # 登场效果 (fade/slide_left/slide_right/
    show producer normal with slide_right  # slide_up/slide_down/zoom/drop/bounce/spin)
    hide producer with slide_left      # 退场效果 (动画播完自动隐藏)
    # 插件可注册自定义效果 (display.register_sprite_effect):
    #   apply_func(sprite, t, direction, display), t∈[0,1]
    #   可修改 sprite 的 center/alpha/scale/angle

    # 对话框文字显示模式 (typing 切换)
    typing typewriter                 # 默认: 打字机逐字符
    typing instant                    # 整段直接出现
    typing terminal                   # 终端: 逐字输入 + 行尾闪烁光标
    typing lines                      # 逐行显示 + 节奏停顿
    typing wave                       # 插件自定义模式 (display.register_text_mode)
    # 插件 API: register_text_mode(name, {"reset": fn(display),
    #                                     "update": fn(display, dt)})

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
| scene_change | id, name, background, pose |
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

### 动作系统 (selection 按钮与插件共用)

`title` / ESC 系统菜单的按钮都是**动作** (action dict), 由
`engine.run_action` 分发; 插件可注册自定义动作类型:

| 动作 | 参数 | 说明 |
| --- | --- | --- |
| `start` | label | 启动游戏 (跳转标签) |
| `quit` | | 关闭游戏 (走退出确认) |
| `title` | | 回到标题画面 |
| `continue` | | 关闭菜单继续游戏 |
| `slot_menu` | mode=save/load | 打开存档/读档选择页面 |
| `save` | slot | 直接存档到槽位 |
| `load` | slot | 直接读档 |
| `close` | | 关闭当前选择列表 |

插件注册自定义动作 + 触发:

```python
# framework/plugins/my_action.py
class MyAction(Plugin):
    def on_load(self):
        def act_explode(engine, params, source):
            engine.display.shake(params.get("duration", 0.5), 10)
            return False     # True=执行后关闭选择列表
        engine.register_action("explode", act_explode)
```

脚本可通过 `do_action <类型> [k=v ...]` 指令触发任意已注册动作
(见 `framework/plugins/example_action.py`)。动作执行前触发
`action` 事件 (type/params/source), 插件可订阅拦截或扩展。

通用选择列表也可由插件/代码直接调用:
`display.show_selection(items, caption, image, style)`,
`style` 支持按钮宽高/配色/圆角/字号/锚点等 (见 DEFAULT_SELECTION_STYLE)。

## 错误处理

游戏运行中的任何未捕获异常都不会崩溃退出:

* **主循环隔离**: 每帧 update/draw/事件处理包在 try/except 中
* **全局兜底**: `sys.excepthook` 捕获主线程未处理异常 (启动器自动安装)
* **温和弹窗**: 错误出现时游戏暂停, 弹出错误面板 (摘要 + 日志路径),
  提供三个按钮: **继续游戏** (跳过出错帧) / **复制错误** (完整
  traceback 到剪贴板) / **退出游戏**
* **日志文件**: 完整 traceback 追加写入 `<项目目录>/logs/errors.log`
  (含时间戳与错误编号), 方便事后排查

**错误分级**:

| 级别 | 处理 | 典型场景 |
| --- | --- | --- |
| `warn` | 仅记录日志 | 未知指令、资源缺失、show 不存在的对象 (兼容旧脚本) |
| `error` | 记录 + 弹窗 | jump/call/choice 跳转到不存在的标签、条件表达式求值失败、脚本/插件异常 |

引擎 API: `engine.handle_error(exc, level="error")` /
`engine.copy_to_clipboard(text)`。

### 背景过渡效果

`bg ... with <效果>` 切换背景时播放过渡, 内置:

| 效果 | 说明 |
| --- | --- |
| `fade` | 黑幕淡出→切换→淡入 (黑幕只在背景层, 不影响立绘/文本) |
| `dissolve` | 交叉溶解 |
| `blinds` | 垂直百叶窗 (12 条竖带逐条显现) |
| `slide` | 新背景从右侧滑入 |
| `circle` | 圆形从中心展开 |
| `pixelate` | 马赛克: 大像素块逐渐变清晰 + 溶解 |
| `zoom` | 缩放淡入 (60% → 100%) |

未知效果名回退为直接切换。插件可注册自定义过渡
(见 `framework/plugins/example_transition.py`):

```python
from framework.engine.display import Transition

class WipeTransition(Transition):
    name = "wipe"
    duration = 0.8

    def draw_bg(self, target):
        if self.old is not None:
            target.blit(self.old, (0, 0))
        w, h = self.new.get_size()
        x1 = int(w * min(1.0, self.t))
        if x1 > 0:
            target.blit(self.new.subsurface((0, 0, x1, h)), (0, 0))

# 插件 on_load 中注册:
#   self.engine.display.register_transition("wipe", WipeTransition)
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
* `weight` 语法可解析但已不承担背景职责 (背景统一走 `scene`/`bg`),
  旧脚本中 `weight ... -> id` + `show id` 会按"全屏立绘"显示并给出警告
* 音频/图片找不到时仅告警, 不中断游戏
* 存档完整保存变量、剧情位置 (标签+语句索引)、调用栈、正在显示的
  文本/选择支、背景 (场景 id + 背景名)、立绘 (id/立绘名/透明度/旋转
  角度/翻转/中心点) 与音乐; 在 `sleep` 阻塞时存档, 读档不会恢复
  剩余等待时间
* 存档槽位: 6 个 (save/slot0-5.json), 由游戏内菜单 (ESC) 或标题画面的
  "读取存档" 打开槽位选择界面; 槽位显示存档时间与进度摘要
* 剧情结束 (`ending` 指令) 后自动回到标题画面; 菜单可随时"返回标题"
* 存档中的背景/立绘以**脚本对象 id** 保存 (不存图片路径), 图片路径
  以脚本中的 `weight`/`sprite` 定义为准 —— 日后重命名图片文件不会
  破坏旧存档 (需同步修改脚本)
