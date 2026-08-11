# 项目结构

## framework/ 目录

```
framework/
├── api/                      插件 API
│   ├── events.py             事件总线 (on/emit/off, 装饰器 @event_listener)
│   ├── commands.py           指令注册表 (按命名空间分组)
│   └── plugin.py             插件管理器 (发现/装载/实例化/卸载 + 文件解码)
├── engine/                   引擎核心
│   ├── core.py               GameEngine 主类 (主循环/窗口/动作/错误/编解码钩子/每帧钩子)
│   ├── parser.py             .gal DSL 解析器 (含 python:: 原始块)
│   ├── loader.py             import 递归展开合并
│   ├── runtime.py            脚本执行器 (指令/变量/命名空间/状态快照)
│   ├── display.py            渲染层 (含背景/立绘/文本渲染钩子)
│   ├── audio.py              BGM 状态机 / 音效 / 语音 (支持 file-like 解码)
│   ├── save.py               存档/读档 (编解码钩子)
│   ├── rich.py               富文本 + LaTeX
│   ├── ui.py                 UI 绘制原语
│   ├── error.py              错误处理
│   ├── styles.py             内置 5 套主题
│   ├── settings.py           设置注册表 + 设置界面 (支持图片键)
│   ├── keybind.py            快捷键注册表
│   └── i18n.py               多语言系统
├── lang/                     框架核心文案 (zh-CN.json / en.json)
├── plugins/                  内置插件
│   ├── lang/                 插件文案
│   ├── fx / notice / transitions_plus / custom_actions / debug_mode /
│   │   slot_thumbnails / gallery / auto_skip
├── tests/
│   └── smoke.py              冒烟测试 (779 项断言)
└── docs/                     本文档
```

## 游戏项目目录约定

```
mygame/
├── demo.gal            # 主脚本 (入口, 必为 start 标签)
├── ui.gal / cast.gal … # 通过 import 拆分的子脚本
├── lang/               # 游戏文本多语言 (<语言码>.json)
├── materials/          # 素材
│   ├── image/          # 背景/立绘/UI 切片
│   └── audio/          # BGM/音效/语音
├── fonts/              # 可选: 自定义字体
├── save/               # 运行时生成: 存档 (slot0-5.json / settings.json / global.json)
└── logs/               # 运行时生成: engine.log / errors.log
```

* 脚本内相对路径**相对脚本所在目录**解析（`engine.resolve_path`）
* `save/` 与 `logs/` 是运行产物，发布时排除；首次运行自动创建
* 素材路径支持 `{lang}` 语言变体（见 [i18n.md](i18n.md)）

## import 拆分

顶层用 `import` 合并多个文件：

```gal
import "ui.gal"          # 界面样式
import "cast.gal"        # 角色与场景
import "audio.gal"       # 声音
import "gallery.gal"     # 鉴赏
import "setting.gal"     # 设置
import "story.gal"       # 剧情
```

合并规则：
* 被导入文件的标签全部并入（重复标签报错），子文件的 `start` 标签忽略
* 顶层声明（window/style/char/scene/plugins/selection_style/sound/using/language）按 import 顺序并入
* 相对路径（相对 import 语句所在文件），支持链式 import，循环导入报错

demo 的拆分示例：
| 文件 | 内容 |
| --- | --- |
| demo.gal | 主流程: window/language/using/import + start (read_settings → title) |
| ui.gal | style / selection_style / ui 素材 / menu title / menu system |
| cast.gal | char producer / scene school |
| audio.gal | sound 注册 (sfx/music/voice) |
| gallery.gal | gallery 块 + CG 场景 (type: cg) |
| setting.gal | settings 块 (布局 + 条目) |
| story.gal | game_start 剧情流程 (game_start 标签) |
