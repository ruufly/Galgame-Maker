# 样式 / 设置 / bar 菜单

## 样式系统

```gal
use style modern        # 内置: modern / classic / dark / light / cyber
use style default       # 恢复默认
```

自定义样式块（同名可重载内置）：

```gal
style my_theme
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
    textbox_image: "..."          # 背景图 (9-slice), 优先于纯色
    speaker_image: "..."
    choice_image: "..." / choice_image_hover: "..."
    choice_text_size: 26 / choice_text_color / choice_text_color_hover
    choice_bg / choice_bg_hover / choice_border / choice_border_hover
```

## 选择列表全局样式 (selection_style)

标题菜单 / ESC 菜单 / 槽位界面共用：

```gal
selection_style
    width_ratio: 0.32 / width: 400 / height: 56 / gap: 14
    anchor_x: center / anchor_y: center
    button_bg / button_bg_hover / button_border / button_border_hover
    button_radius / text_size / dim_alpha
    button_image / button_image_hover / button_stretch / button_text
    text_color / text_color_hover / dialog_image
selection_style default   # 重置
```

## UI 主题素材 (ui 块)

九宫格切片，路径相对脚本目录；逗号=默认图,焦点图；分号=多组按按钮索引取图：

```gal
ui
    textbox: "materials/.../对话_adv对话框_llf.png"
    title_buttons: "默认.png, 焦点.png; 默认2.png, 焦点2.png"
    menu_buttons: "确认_按钮_默认_llf.png, 确认_按钮_焦点_llf.png"
    confirm_panel / confirm_button / slot_frame / slot_panel
```

style 图片键优先级更高；值为 `none` 禁用主题图。

## 设置系统

### 配置 (setting.gal)

```gal
settings
    title: "{@settings.title}"
    columns: 2
    bg: "panel.png"               # 面板背景图 (九宫格)
    # --- UI 图片键 (有图优先于纯色, 支持 {lang} 变体) ---
    item_image: "item.png"              # 条目背景图
    item_image_hover: "item_focus.png"  # 条目悬停图
    tab_image: "tab.png"                # 分栏图
    tab_image_hover: "tab_focus.png"    # 分栏激活/悬停图
    back_image: "back.png"              # 返回按钮图
    slider_track_image: "slider.png"    # 滑条轨道图
```

`title / label / section / options` 均支持 `{@key}`（切换语言即时生效）；内置设置项自带 `label_key`。

### 内置设置项

| key | 类型 | 说明 |
| --- | --- | --- |
| `bgm_volume` / `sfx_volume` / `voice_volume` | slider | 音乐/音效/语音音量 |
| `voice:<角色id>` | slider | 角色语音音量 (动态, 显示名自动为"角色名 语音") |
| `text_speed` | slider | 文字速度 (字符/秒) |
| `resolution` | cycle | 分辨率 (写 $res_w/$res_h) |
| `fullscreen` / `resizable` | checkbox | 全屏/可缩放 |
| `player_name` | cycle | 主角名字 ($player_name) |
| `language` | cycle | 语言 (显示名, 切换即时生效) |
| `key_up` ... `key_escape` | keybind | 键位 (主/副双槽) |

### 自定义设置项

```gal
    setting my_slider
        label: "{@settings.my_slider}"
        type: slider            # slider / checkbox / cycle / input / keybind / button
        var: my_val             # 绑定引擎变量, 自动读写
        min: 0 / max: 100 / step: 5
    setting my_input
        type: input             # 文本输入 (Enter 确认, ESC 取消)
        var: player_name
        default: "未命名"
```

插件注册：

```python
engine.settings.register(
    "my_setting", label="插件开关", kind="checkbox",
    getter=lambda: 取值, setter=lambda v: 应用,
    var="my_var", default="默认值",
    min=0, max=1, step=0.05, options=["a", "b"],
    section="分栏", on_click=lambda engine: ...,
    label_key="settings.my_setting",   # i18n 显示名
)
engine.settings.get("my_setting", False)
engine.settings.set("my_setting", True)
```

* 值存 `save/settings.json`（跨存档、可手动编辑）
* `read_settings`（脚本 start 首行）读取并赋值到变量、重新应用 window 配置
* 分栏 (tab) 显示名按 `settings.section.<值>` 翻译，未配置的自定义分栏原样显示

### 设置入口

标题菜单 / ESC 菜单 / bar 常驻栏均可打开（action: `settings_open`）。

## bar 常驻菜单栏

```gal
window
    menu_mode: "bar"             # popup (默认, ESC 弹窗) / bar (常驻)
    menu_bar_pos: "bottom"       # bottom / top

menu_bar
    bg: "#1a1a2e" / border: "#5a5a7a"
    align: center / gap: 12 / padding: 18 / height: 56 / btn_h: 38
    button_bg / button_bg_hover / button_border / button_border_hover
    button_radius / text_color / text_color_hover / text_size
    # --- UI 图片键 (图优先于纯色) ---
    bg_image: "bar.png"
    button_image: "btn.png" / button_image_hover: "btn_focus.png"
    button_image_active: "btn_active.png" / button_image_disabled: "btn_off.png"
menu_bar default   # 重置
```

* bar 复用 `menu system` 块的按钮定义（自动过滤无意义 continue；无定义用默认四项）
* 游戏过程中随时点击；ESC 不再弹窗（仅关闭覆盖层）；对话框自动上移让位
* 打开覆盖层时菜单栏被 dim 盖住，关闭后恢复
* 切换语言即时刷新按钮文案
