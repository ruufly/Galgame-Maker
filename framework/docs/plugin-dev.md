# 插件开发指南

插件是 `framework/plugins/` 下的 `.py` 文件（下划线开头忽略），引擎启动自动发现。**命名空间 = 插件文件名**（如 `gm_plugin_fx.py` → 命名空间 `fx`）。

## 两种写法

### 1. 装饰器写法（推荐，模块级）

```python
# my_plugin.py
from framework.api import command, event_listener

@command("mycmd")                       # 自定义 DSL 指令 -> my_plugin::mycmd
def mycmd(engine, stmt, **kw):
    engine.show_notice("指令被调用!")
    return None                          # 返回 "block" 可阻塞等外部事件

@event_listener("bg_change")            # 订阅事件 (engine 参数自动注入)
def on_bg(path, engine, **kw):
    print("背景切换到", path)
```

### 2. 类写法（生命周期管理）

```python
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

    def on_unload(self):                 # 卸载时清理
        pass
```

## 生命周期与装载

* 引擎 `run()` 时 discover 插件（在脚本加载前）→ `on_load` 注册一切
* 脚本的 `plugins` 块可控制装载：`only: "fx, notice"` / `except: "debug_mode"`
* 运行时：`plugin load/unload/list`（DSL 语句）
* 卸载清理：类实例 `on_unload` + 模块级指令/事件/订阅

## 命名空间

| 域 | 内容 |
| --- | --- |
| `builtin::` | 引擎内置指令/变量 |
| `main::` | 项目文件变量（`set love = 1` 归此域） |
| `<插件名>::` | 插件注册的指令/变量 |

无命名空间解析：变量 `main::` → `builtin::`；指令 `builtin::` → `main::` → 已 using 的插件 → 报错并提示所在命名空间。

```gal
using my_plugin        # 之后 mycmd 可裸名调用
```

## 事件参考

事件自动附带 `engine`；处理器返回 `False` 可标记"阻止默认行为"（如消费点击）。

| 事件 | 载荷 |
| --- | --- |
| engine_start / engine_quit | engine |
| script_load / script_start / script_end | path / name |
| script_block (静态扫描属性块) | op, stmt |
| label_enter | label |
| statement | stmt, label |
| text_show / text_advance / text_complete | text, speaker |
| choice_prepare (显示前, 可改写) | options (可变列表) |
| choice_show / choice_made | choices / index, label, text |
| bg_change | path, effect |
| scene_change | id, name, background, pose |
| sprite_show / sprite_hide | id, path |
| sprite_effect_complete | id, direction |
| var_set | name, value |
| using | namespaces |
| sound_register | name, type |
| music_play / pause / resume / stop | name, path, loop, fade |
| voice_play / voice_stop | path |
| save / load | slot, path |
| confirm_show / confirm_choice | text / index |
| action | type, params, source |
| draw_overlay (每帧) | surface |
| error / error_dismiss | exc / level |

## 扩展点大全

### DSL 指令

```python
@command("mycmd")          # 注册到 <插件名>:: 命名空间
def mycmd(engine, stmt, **kw):
    return None            # "block" = 阻塞脚本, 之后 engine.runtime.release("...") + advance() 继续
```

```python
engine.commands.register("x", fn, ns="main")
engine.commands.call("x", stmt, ns="plugin") / has / get / find / unregister
```

### 选择列表动作

```python
engine.register_action("explode", fn)   # fn(engine, params, source) -> bool
# 脚本: do_action explode duration=0.5
```

### 菜单按钮

```python
engine.register_menu_button("title", "文本", {"type": "gallery_open"},
                            cfg={"enabled": False, "name": "gallery"})
engine.set_menu_button_state("title", key, enabled)      # key=name/原始文本/索引
engine.set_menu_button_cfg("title", key, {"image": ...})
```

### 渲染钩子

```python
# 背景过渡 (Transition 子类, draw_bg + 可选 draw_overlay)
display.register_transition("name", cls)

# 立绘登场/退场动画
display.register_sprite_effect("wobble", fn, dur)

# 文字显示模式
display.register_text_mode("wave", {"reset": fn, "update": fn(display, dt)})

# 槽位缩略图
display.register_slot_thumbnail_provider(fn)   # fn(slot, info) -> Surface|None

# 动态背景渲染器 (视频帧/程序背景)
display.register_bg_renderer(fn)    # fn(display) -> Surface|None, None=取消

# 立绘动态渲染器 (Live2D)
display.register_sprite_renderer(sid, fn)  # fn(display, sprite) -> Surface|None
# sid=None 注册全局兜底; fn=None 取消

# 全屏特效覆盖层 (最上层)
display.register_effect_overlay(fn)  # fn(surface) -> surface|None
```

### 每帧与文本钩子

```python
# 每帧无条件调用 (Steam 回调/轮询/心跳; 暂停菜单时也执行)
engine.register_frame_hook(fn)      # fn(dt: float)

# 文本输出钩子 (打字音效/字幕高亮)
display.register_text_char_hook(fn) # fn(display, start_idx, count)
```

### 状态快照 / 回滚

```python
snap = engine.snapshot_state()      # 内存快照 (与存档同构)
engine.restore_state(snap)          # 静默恢复到快照点
```

### 文件编解码钩子（加密）

```python
engine.register_file_codec("save", decode=dec, encode=enc)
# scope: save / resource / lang / script / plugin
# decode/encode: fn(bytes)->bytes, None=原样; 返回旧 codec
```

详见 [advanced.md](advanced.md#文件编解码钩子)。

### 设置项 / 快捷键

```python
engine.settings.register("my_setting", label="...", kind="slider", ...)
engine.keybinds.register("my_key", "显示名", callback, primary="f9", label_key="...")
```

### 嵌入 Python（脚本侧）

```gal
python::
    import random
    engine.set_var("luck", random.randint(1, 100))
```

插件可注册自己的 raw 块处理：parser 对 `xxx::` 生成 `Statement(op="xxx", kwargs={"code": 原文})`，插件 `@command("xxx")` 处理即可。

### 全局数据 / 存档

```python
engine.save.get_global(key, default) / set_global(key, value)   # 跨存档
engine.save.set_meta(slot, key, value) / get_meta(...)          # 槽位元数据
engine.get_var(name) / set_var(name, value)                     # 引擎变量
```

## 插件语言（i18n）

插件文案放 `framework/plugins/lang/<code>.json`（key 带插件前缀），取用：

```python
engine.i18n.t("gallery.button", ns="plugin", default="鉴赏")
```

## 完整示例插件（"通知 BGM" 的最小实现）

```python
"""bgm_tip 插件: 播放 BGM 时右下角提示曲名。"""
from framework.api import event_listener

@event_listener("music_play")
def on_music(engine, name, path, loop, fade, **kw):
    label = name or path.split("/")[-1]
    engine.display.show_notice(
        engine.i18n.t("bgm_tip.playing", ns="plugin",
                      default="♪ {label}", label=label),
        2.0, pos="top-right")
```

```json
// framework/plugins/lang/zh-CN.json
{ "bgm_tip.playing": "♪ 正在播放: {label}" }
```

## 插件加载失败排查

* 插件文件语法错误（注意 **Python 3.10 f-string 不支持表达式内嵌嵌套字符串字面量**——3.12 的写法在 3.10 会 SyntaxError，见 README §13 坑位 17）
* 未 `using` 就裸名调用指令 → 报错提示所在命名空间
* 需要第三方库的插件：`pip install` 后**打包时**要一并配置（见 [advanced.md](advanced.md#打包发行)）
