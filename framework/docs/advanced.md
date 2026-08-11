# 高级主题

## 文件编解码钩子（资源/存档/语言加密）

```python
engine.register_file_codec(
    "save",                          # scope: save / resource / lang / script / plugin
    decode=my_decrypt,               # fn(bytes)->bytes 读取时解码 (None=原样)
    encode=my_encrypt,               # fn(bytes)->bytes 写入时编码 (None=原样)
)
```

覆盖范围：

| scope | 接入点 |
| --- | --- |
| `save` | 槽位存档 / settings.json / global.json 全部 JSON 读写 |
| `resource` | 图片 (`display.load_image`) / BGM / 音效 / 语音 / 字体（pygame 以 file-like 加载解密结果） |
| `lang` | `i18n.load_file` 语言文件 |
| `script` | `.gal` 脚本（引擎构造时绑定解析器模块级解码器） |
| `plugin` | 插件源码（解密后经 importlib 加载，临时文件自动清理） |

特性：
* 未注册 scope 读写**完全原样**；编解码异常记录日志并回退原数据
* 密钥可运行时从服务器获取：插件 `on_load`（早于一切资源加载）拉取并缓存，注册的闭包直接使用

## DRM / 版权保护策略

* **前提**：内容型作品防不住录屏/截图；目标是提高拆包门槛 + 建立证据链（水印）
* 分层：法律（EULA/水印）→ 代码/资产（pyd 化核心 + file codec 加密 + PyArmor 混淆）→ 许可证（离线激活：服务器 RSA 签发 + 机器指纹 + 本地公钥验证）→ 平台（Steam/商店自带 DRM）
* **关键**：密钥/校验逻辑放 pyd，别放纯 Python（否则读源码即得密钥）
* 防逆向首选 `pyd`（C 扩展，平台/CPython 版本绑定）；业务插件可用加密 `.py`
* 服务器密钥分发：`on_load` 同步拉取缓存；服务器不可达降级策略由插件自定

## Steam 集成（成就/云存档/身份）

全部**纯插件**实现（无需动内核）：

| 功能 | 接入点 |
| --- | --- |
| 初始化 | 插件 `on_load`（窗口已建、主循环未开始） |
| 每帧回调 | `engine.register_frame_hook(lambda dt: SteamAPI.RunCallbacks())` |
| 成就 | DSL 指令 → `SetAchievement` |
| 云存档 | `engine_start` 下载 + `save` 事件上传 + `engine_quit` 同步 |
| 身份 | `engine_start` 后 `GetSteamID` 等，写入变量 |
| DLC 授权 | 联动文件编解码钩子（按授权注入密钥） |

注意：无 Steam 环境必须优雅降级（开发机 demo 照常跑）；库选型 `steamworks`；打包配 `steam_api64.dll` 与 appid。

## 打包发行 (PyInstaller)

```powershell
# 全部产物输出到 test/release, 不污染项目根
py -3.10 -m PyInstaller --noconfirm --onedir --name GalgameMaker ^
  --distpath test/release --workpath test/release/build ^
  --specpath test/release ^
  --add-data "C:\<项目绝对路径>\framework\plugins;framework\plugins" ^
  --add-data "C:\<项目绝对路径>\framework\lang;framework\lang" ^
  gamelauncher.py

# 复制 demo 数据与字体到发行目录 (排除 save/logs/__pycache__)
robocopy test\engine_demo test\release\GalgameMaker\test\engine_demo /E /XD save logs __pycache__
robocopy fonts test\release\GalgameMaker\test\engine_demo\fonts /E
```

要点：
* **`framework/lang` 必须打包**（否则核心语言文件缺失，日志/UI 显示 key 名）——README §19 老命令漏了它
* frozen 环境项目根基于 exe 所在目录；demo/字体为外部文件便于替换
* 第三方库（opencv/live2d/steamworks 等）用 `--hidden-import` 或随包放置

## 测试

```powershell
py -3.10 framework/tests/smoke.py    # 779 项断言, dummy 驱动无窗口
```

覆盖：解析器/运行时/交互/样式/selection/存档/过渡/角色/场景/对话框/菜单/动作/立绘效果/文字模式/插件/命名空间/音频/快照/LaTeX/语音音量/窗口缩放/菜单栏/鉴赏/自动跳过/设置/confirm/keybind/日志/i18n/插件扩展等。

## 性能与常见坑

* **Python 3.10 f-string**：表达式内嵌嵌套字符串字面量会 SyntaxError（PEP 701 到 3.12 才放开）——先算好再拼接
* 主循环单线程：网络请求/长任务放后台线程，用 `register_frame_hook` 轮询结果；阻塞型指令返回 `"block"` + 完成后 `release` + `advance`
* 立绘重开消失：`clear_sprites` 清 `sprite_order` 但保留 `sprites` 字典，`show_sprite` 用 `sid not in sprite_order` 判断入序
* 立绘首帧闪现：`show ... with 效果` 启动后立即应用 t=0 起始状态
* BGM 存档存**注册名**（非路径）；`ending`/开始游戏自动淡出停止 BGM
* 存档快照用 `engine.get_last_game_frame()`（纯游戏帧），别截当前画面
* 表达式禁止函数调用是安全设计；`python::` 与插件拥有完整解释器权限，仅在可信脚本使用
