# Galgame Maker Framework — 文档

运行时视觉小说引擎 (Python 3.10 + pygame) 的完整使用文档。

## 阅读路径

**第一次接触 / 只想跑起来**
- [快速开始](getting-started.md) — 环境、运行 demo、最小项目、操作键位

**写游戏脚本 (.gal)**
- [项目结构](project-structure.md) — 目录约定、import 拆分、素材/存档/日志
- [DSL 语法全参考](script-dsl.md) — 表达式、流程、背景/立绘/对话/声音/菜单/样式…全部指令

**配置界面与表现**
- [样式 / 设置 / bar 菜单](styles-settings.md) — 主题、UI 素材、设置项、常驻菜单栏
- [多语言系统](i18n.md) — 三层语言、{@key}、设置/角色名/结局名、日志翻译

**引擎内部**
- [引擎核心](engine-core.md) — 主循环、事件、动作、存档、渲染、音频、窗口、快捷键、错误处理

**做插件 / 扩展**
- [插件开发指南](plugin-dev.md) — 生命周期、API、事件表、全部扩展点、示例插件

**上线与加固**
- [高级主题](advanced.md) — 文件加密、DRM 策略、Steam、打包发行、测试、常见坑

## 快速导航

| 想做什么 | 看这里 |
| --- | --- |
| 跑起 demo | [getting-started.md](getting-started.md) |
| 写第一段剧情 | [script-dsl.md](script-dsl.md#对话与语音) |
| 自定义 UI 样式 | [styles-settings.md](styles-settings.md) |
| 做多语言版本 | [i18n.md](i18n.md) |
| 注册自定义 DSL 指令 | [plugin-dev.md](plugin-dev.md#指令) |
| 播放视频 / 嵌 Live2D | [plugin-dev.md](plugin-dev.md#渲染钩子) |
| 加密资源 / 存档 | [advanced.md](advanced.md#文件编解码钩子) |
| 打包发布 | [advanced.md](advanced.md#打包发行) |

> 核心交接文档（开发历史、设计动机、变更日志）见 `framework/README.md`。
> 本 docs/ 是面向使用者的功能文档；README 是面向接手者的交接文档。
