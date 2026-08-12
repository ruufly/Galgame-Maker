# Galgame Maker 编辑器

可视化制作 `.gal` 视觉小说的桌面编辑器（Python 3.10 + PySide6），
与 `framework/` 子模块（运行时引擎）深度对接。零基础友好：全程
所见即所得，不强制接触脚本；产出项目可直接被引擎运行。

- **引擎**：framework 子模块（Python 3.10 + pygame，.gal DSL）
- **编辑器**：本目录（PySide6 6.x，中英双语）
- **核心原则**：单一事实来源 —— 编辑器模型 = 引擎解析器的
  Script/Statement 树；所有 `.gal` 文本由模型序列化生成（Editor-first）

---

## 一、快速开始

```powershell
# 环境 (与引擎一致)
py -3.10 -m pip install PySide6 pygame pyyaml pillow

# 打开编辑器
py -3.10 editor/app.py                       # 空编辑器
py -3.10 editor/app.py test/engine_demo      # 打开 demo 项目

# 常用快捷键
Ctrl+Shift+N   新建项目        Ctrl+,   项目设置
F5             运行预览        Shift+F5 停止预览
F7             校验项目        视图→语言 切换中/英
```

编辑器内流程：**文件→新建项目（向导）→ 素材 Tab 拖入素材 → 定义 Tab
建角色/场景/声音 → 逻辑 Tab 编排剧情 → 样式 Tab 配色 → 校验 → 预览 →
编译 Tab 导出 zip / PyInstaller 打包**。

## 二、工作区布局

| 区域 | 内容 |
|---|---|
| 中央 Tab | 素材 / 定义 / 逻辑 / 样式 / 插件 / 编译 |
| 左 Dock | 项目树（脚本 + 素材目录） |
| 右 Dock | 属性（占位） |
| 底 Dock | 输出日志 + **真实引擎内嵌预览**（无头渲染取帧） |
| 菜单 | 文件 / 视图（语言）/ 工具 / 帮助 |

## 三、功能清单

### 1. 新建项目向导（project_wizard.py）
- 从 engine_demo 复制骨架 + 复制 fonts/（自包含）+ 身份替换
  （项目名→window 标题/meta/main.yml，语言→language 块）
- 分辨率 / 默认语言 / 是否复制演示素材；创建即打开

### 2. 素材库（assets.py）
- 分类浏览（图片/音频/字体/其他）、图片缩略图、扩展名色块
- 按钮导入 + 系统文件**拖拽导入**，自动归类、重名自动改名

### 3. 定义管理器（definitions.py）
- **角色**（显示名/默认立绘/表情表/语音音量/描述/CV）、
  **场景**（normal/cg/默认背景/背景表）、**声音**（类型/文件/音量）
- 约定：char/scene→cast.gal，sound→audio.gal

### 11. 项目设置（project_settings.py）
- window 块表单：标题/分辨率/帧率/图标/全屏/缩放/存档槽位/
  BGM 淡入淡出/UI 音效 + 确认框 + 键盘导航 + 菜单文案
- 保存即改模型并落盘（`{@key}` 占位符保留）

### 11. 流程节点编辑器（flow.py + flow_editor.py）—— 核心创作面
- **节点类型**：对话 / 选择支（每选项端口）/ 跳转（call 可选）/
  结局 / 标签 / **场景 stage** / 动作（兜底保留任意语句）/ 代码块
- **场景分镜**：背景（场景定义下拉+过渡效果）+ 立绘动作表 +
  **背景缩略图** + **引擎真实帧预览** + **立绘拖放排布**（生成 move）
  + **音频轨横向时间轴**（秒刻度标尺 + 块宽∝时长 + 起始时间标签，双击编辑、拖拽排序）
- **交互**：端口拖线连线、右键删除连线（悬停高亮）、目标 id 标注、
  Ctrl+Z 撤销 / Ctrl+Shift+Z 重做、Delete 删节点、框选多选移动、
  自动布局 / 适配视图、缩放百分比状态行
- **action 参数提示**：双击动作节点按指令类型弹参数表单
  （候选来自内核 + 插件能力，见第五节）
- 导入 story.gal 无损失（对话链合并 + 块尾 jump 折叠 + 幂等）

### 11. 样式可视化编辑器（styles_editor.py）
- 17 个样式字段（对话框/台词/名字框/选择支配色、字号、字体）
- Qt 自绘实时样例预览，改即见；保存进 ui.gal style 块

### 11. 插件生态（plugins_api.py + plugins_panel.py + plugin_importer.py）—— 见第五节

### 11. 编译与打包（build.py）
- 校验（往返 + import 合并加载）→ 导出项目 zip（排除运行时产物）
- PyInstaller 打包（QProcess 实时输出，参数化 README 引擎侧方案）

### 11. 国际化（i18n.py + lang/）
- zh-CN / en 双语；配置存 ~/.galmaker_editor.json；切换即时全 UI 刷新
- 已覆盖：主窗口 + 全部工作区面板

## 四、架构与数据流

```
编辑器模型 (Project / Script / Statement 树)
   │  serialize() 纯函数          parser (引擎复用)
   ▼                              ▲
.gal 文本  ──────────── 导入（解析回模型）
   │
   ▼
标准项目目录 (demo.gal + ui.gal + cast.gal + audio.gal + story.gal
             + materials/ + fonts/ + lang/)
   │ gamelauncher.py
   ▼
framework 引擎 (真实运行/无头预览)
```

- **往返保证**：`parse(serialize(parse(t)))` 与 `parse(t)` 结构等价
  （roundtrip_test 覆盖 engine_demo 全部文件 + 合成样例 + 合并加载）
- **幂等**：story.gal 导入→导出→再导入，节点结构稳定
- **Editor-first**：一切编辑 = 改模型 → 序列化落盘

## 五、插件生态（责任反转：插件主动注册，编辑器不分析插件源码）

### 设计原则
- 编辑器只提供**注册点**（PluginRegistry），不扫描/分析插件源码
- 插件在 `editor/plugins/<名>.py` 中调用 API 主动声明能力
  （指令参数表单 / 动作候选 / 文字模式 / 设置项 / 元信息）
- 编辑器 UI（action 参数提示 / 插件面板 / 设置项生成）只查询注册中心
- framework/plugins 的每个插件在 editor/plugins 有对应接口文件（内置 8 个）
- 能力来源区分：**引擎内核（KERNEL_* 固定清单）** vs **插件（注册中心）**

### editor/plugins 内置接口（与 framework/plugins 一一对应）

| 接口文件 | 注册内容 |
|---|---|
| fx.py | 6 指令参数表单（shake 时长+幅度 / flash / blackflash / strobe / tint 颜色+时长 / pulse） |
| custom_actions.py | do_action 指令 + 4 动作 + 6 立绘效果 + 5 文字模式 |
| transitions_plus.py | 7 种扩展过渡 |
| debug_mode.py | debug_toggle 快捷键 |
| gallery.py | gallery_open 动作 + script_block 事件 |
| auto_skip.py | auto_toggle / skip_once 动作 + 菜单按钮 |
| notice.py / slot_thumbnails.py | 元信息 + 事件（无注册项） |

### 插件 API（editor/plugins_api.py）

```python
from editor.plugins_api import registry

def setup(reg):                       # 编辑器加载时自动调用
    p = reg.register_plugin("my_plugin", meta={"name": "my_plugin",
                                               "description": "..."})
    p.add_command("my_fx", params=[("强度", "number", "1"),
                                   ("颜色", "color", "255,0,0")])
    p.add_action("my_action")
    p.add_text_mode("my_mode")
    p.add_setting("my_speed", "速度", kind="slider",
                  min=0.1, max=5.0, step=0.1, section="游戏")
    p.add_keybind("my_toggle", "我的开关")
    p.add_transition("my_trans")
    p.add_sprite_effect("my_effect")
    p.add_event("my_event")
```

### 插件导入（.galpkg 标准包，文件→导入插件）

包结构（zip）：

```
my_plugin.galpkg
├── main.yml          # name/author/description/version/date/copyright
│                     # + framework/editor 文件映射
├── gal_impl.py       # -> framework/plugins/<name>.py (引擎侧实现)
└── ed_impl.py        # -> editor/plugins/<name>.py (编辑器接口)
```

main.yml：

```yaml
name: my_plugin
author: "xx"
description: "自定义插件"
version: 1.0
date: 2026-08-12
copyright: "xx 2026"
framework: gal_impl.py
editor: ed_impl.py
```

导入流程：校验 main.yml → 引擎侧写入 framework/plugins → 编辑器接口写入
editor/plugins → 立即加载注册（**main.yml 元信息为权威**，setup 内 meta 仅补充）
→ 插件面板刷新。注意：framework/plugins 为子模块，写入后需自行管理 git。

### 配置闭环

- **plugins 块**（only/except）：插件面板配置 → 保存进主脚本
- **设置项**：插件 `add_setting` → 一键生成 setting.gal 子块 → 游戏内设置界面出现
- **指令参数表单**：插件 `add_command(params=...)` → 流程画布双击该指令弹逐参表单
- **动作/文字模式候选**：插件 `add_action` / `add_text_mode` → do_action / typing 下拉自动包含

## 六、测试清单（18 项，全绿）

| 测试 | 覆盖 |
|---|---|
| roundtrip_test | 序列化往返 + 合并加载 |
| headless_spike | 无头渲染取帧 |
| qt_embed_spike | Qt 内嵌引擎帧 (1280x720) |
| ui_smoke | 主窗口/校验/预览 |
| p2_wizard_test | 新建项目向导 (13 断言) |
| p2_assets_test | 素材导入/分类/重名 |
| p2_settings_test | window 块读写 |
| p2_definitions_test | 定义增删改/文件约定 |
| p2_flow_test | 流程模型 (含 stage/moves/audio 幂等) |
| p2_flow_ui_test | 画布 UI/撤销/连线删除 |
| p3_styles_test | 样式块读写 |
| p3_build_test | 导出 zip 排除规则 |
| p3_plugins_test | 插件注册中心 (API 注册/查询/装卸, 15 断言) |
| p4_plugin_import_test | .galpkg 导入/注册/错误处理 (8 断言) |
| p3_stage_preview_test | 场景脚本生成 + 真实渲染 |
| p3_i18n_test | 语言切换/回退 |
| p3_plugin_settings_test | 设置项提取/生成 (13 断言) |
| p3_action_hint_test | 参数提示 (API 驱动, 21 断言) |
| p3_audio_timeline_test | 时间线数据/排序 (9 断言) |

```powershell
# 单跑
py -3.10 editor/tests/<测试名>.py
# 全量 (PowerShell)
$tests = Get-ChildItem editor\tests\*_test.py | % BaseName
foreach ($t in $tests) { py -3.10 "editor\tests\$t.py"; "EXIT=$LASTEXITCODE" }
```

> 注：测试入口统一 `os._exit`，跳过 pygame/SDL atexit 清理竞态
> （否则退出码偶发非 0，功能不受影响）。

## 七、开发流程（里程碑演进）

整个编辑器按 P0→P3 四阶段增量开发，每阶段以"可测试的闭环"收尾：

| 阶段 | 内容 | 验收标准 |
|---|---|---|
| **P0 地基** | 序列化器往返测试（模型↔.gal）；无头渲染取帧验证；修复十六进制颜色被注释截断 bug | engine_demo 全部文件往返等价 + 合并加载一致 |
| **P1 骨架** | PySide6 主窗口 + Qt 内嵌引擎预览（帧→QImage→控件，~50fps）；项目树/校验/预览闭环 | ui_smoke 通过 |
| **P2 创作** | 新建向导 / 素材库 / 项目设置 / 定义管理器 / **流程节点画布**（节点图模型 + 导入导出幂等）；顺带修复自动 id 冲突、块尾 jump 折叠 | 全程可视化完成 demo 级剧情 |
| **P3 完整化** | 样式实时预览 / 插件能力注册表 + 面板 / 设置项生成 / 引擎帧场景预览 / 立绘排布 / 音频轨时间线 / action 参数提示 / 双语 / 编译打包 / 连线标注 | 18 项测试全绿 |

**关键开发纪律**（贯穿始终）：
1. **纯逻辑与 UI 分离**：序列化、模型、插件扫描、参数候选全部抽成可测纯函数；UI 只做薄封装
2. **模型优先**：先让数据（model + serializer）闭环，再画界面
3. **每个特性配测试**：修 bug 先写失败用例（往返/幂等/解析断言）
4. **截图验证 UI**：对话框/画布用 grab 截图核对（无头环境可自动化）

## 八、踩坑经历（交接备忘，血泪教训）

### 1. PySide6 6.11 自定义 QGraphicsItem 渲染段错误（最严重）
- **现象**：给连线 QGraphicsPathItem 加 paint/contextMenuEvent 覆盖后，画布一渲染就 Segmentation Fault（pygame parachute 打印）；连"普通矩形+自绘边"的纯 Qt 场景也崩
- **排查**：逐步二分（空场景✓ / 仅节点✓ / 加边✗ / 剥离特性…），隔离出 item 子类 + 事件覆盖的渲染链问题；同代码在测试类里却不崩（环境级怪癖），最终放弃追底层
- **决策**：**图形对象一律自绘**——连线改纯数据 + QGraphicsScene.drawForeground；立绘画布/时间线用 QWidget.paintEvent；不覆盖 QGraphicsItem 事件方法。此后零崩溃
- **教训**：PySide6 的 QGraphicsItem 子类覆盖是高风险区，能用 scene 前景/自绘 QWidget 就不碰 item

### 2. 字符串替换事故：main_window 方法块重复
- 批量替换时区间计算错误，showEvent/_make_dock/_build_central 出现两份副本且 addTab 括号被吃 → 语法错误
- **教训**：大范围文本替换前先打印锚点位置/区间长度；改完立即 py_compile + 全量测试

### 3. 责任反转：AST 静态扫描方案弃用
- 初版"编辑器自动扫描插件源码"虽能工作（含常量传播），但把插件支持的
  责任压在编辑器：新插件能力（参数语义等）必须由编辑器解析推断
- 重构为**插件主动注册**（editor/plugins API）：编辑器只提供注册点，
  插件自己声明参数表单/候选/设置项；framework/plugins 各插件在
  editor/plugins 有对应接口文件；自定义插件经 .galpkg 导入
- **教训**：平台（编辑器）的责任是提供稳定接口，而不是理解每个插件内部

### 11. `_call_name` 不支持 Call 节点（docstring 约定失效）
- 装饰器 `@command("x")` 的 AST 节点是 Call，`_call_name(dec)` 返回空串 → 指令注册分支静默失效（但 Call 段的重复处理让 commands 看似正常，掩盖了 docstring 参数提取的缺失）
- 调试打印 `dec name: ''` 才暴露；改为 `_call_name(dec.func)`
- **教训**：AST 工具函数要对 Name/Attribute/Call 全覆盖；同名功能重复出现时警惕"假正常"

### 11. `setFlags(0)` 类型错误（PySide6 严格枚举）
- 空态占位 item 用 `setFlags(0)`，Python 下 int 0 报 TypeError；此前从未走到空态分支所以测试全过
- 修：`Qt.NoItemFlags`；**教训**：PySide6 严格类型检查，枚举别用整数

### 11. pygame/SDL atexit 清理竞态
- 测试/脚本退出码偶发非 0（SDL dummy 驱动在解释器关闭时清理问题）
- 修：测试入口统一 `os._exit(main())` 跳过 atexit；引擎线程内显式 pygame.quit()
- **教训**：GUI 测试的"退出阶段"也要验证，否则 CI 时灵时不灵

### 11. 工具链转义：`\n` 被写进文件变成真实换行
- 通过文件工具写含 `\n` 的字符串时被转义为换行 → SyntaxError
- 修：改用 `chr(10)` 拼接或三引号；**教训**：写代码生成工具时避免依赖转义序列

### 11. parser 上游保真限制（序列化器无法找回）
- 注释/空行丢失；`choice` 行内参数被引擎 parser 丢弃；键值行 `" #"` 被当注释（十六进制颜色裸写被吞空）→ 序列化器强制 `#` 开头值加引号
- **教训**：与上游 parser 对接时先做"最小意外测试"（把 demo 全文件往返跑一遍），限制会自己浮出来

### 11. 幂等陷阱：块尾 jump 折叠
- 导入→导出→再导入时，块尾 jump 语句每轮多生成一个节点（15→11→…）
- 修：块尾 jump（目标已存在、prev 非 choice）折叠回 next 连线；自动 id 生成器跳过已占用名
- **教训**：任何"图↔文本"转换都要有幂等断言，否则一轮轮退化

### 11. 默认值省略（loop=1）
- `music x loop 1` 导出省略默认 loop → 测试断言过严报错；语义等价即可
- **教训**：测试断言要区分"结构等价"与"语义等价"

### 11. 测试隔离：用户配置污染
- i18n 测试断言默认中文，却被上一次截图脚本持久化的 en 配置污染 → 用临时配置路径隔离
- **教训**：涉及用户级配置的测试必须隔离

## 十、已知限制与兼容策略

### PySide6 渲染兼容（重要）
PySide6 6.11 对本环境的自定义 `QGraphicsItem` 子类（覆盖
paint/contextMenuEvent 等）渲染会**段错误**（已多次二分定位）。
编辑器统一策略：**图形对象尽量自绘**（QWidget.paintEvent /
QGraphicsScene.drawForeground）——
- 连线 = 纯数据对象 + 场景前景绘制（含标注/悬停/右键命中）
- 立绘排布画布 / 音频时间线 = 自绘 QWidget
- 不覆盖 QGraphicsItem 的事件方法

### parser 保真限制（序列化器无法找回）
- 注释与空行；普通语句参数引号信息（按安全规则重引号，语义不变）
- `choice` 行内参数（ui_click 等）被引擎 parser 丢弃
- 键值行值含 `" #"` 会被当行内注释截断 —— 序列化器已规避
  （`#` 开头值强制加引号）

### 其他
- 音频/图片缺失仅告警（引擎行为）；面板内部对话框文案部分未 t 化
- 编辑器自身打包（PyInstaller）暂缓（用户决定）

## 十一、下一步方向

- 更多 action 指令参数化（按 docstring 约定扩展）
- 音乐轨时间线升级为横向时间轴（带时长/淡入淡出可视化）
- 编辑器自身 PyInstaller 发行
- 面板内剩余对话框文案双语化
