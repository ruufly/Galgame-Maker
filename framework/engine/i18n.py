"""多语言系统 (i18n): 框架 / 插件 / 游戏文本 三层翻译。

* **框架文案**: ``framework/lang/<code>.json`` (日志/提示/内置 UI 文案),
  引擎构造时自动加载;
* **插件文案**: ``plugins/lang/<code>.json`` (key 建议带插件名前缀,
  如 "gallery.button"), 插件装载时自动加载;
* **游戏文本**: 项目目录 ``lang/<code>.json``, 脚本中用 ``{@key}``
  占位符引用 (额外文件保存文本, DSL 保持简洁); 检测到项目 lang/
  目录即启用。

API::

    engine.i18n.set_lang("en")          # 切换语言 (全局生效)
    engine.i18n.t("menu.quit")          # 取当前语言文本 (回退默认语言/原文)
    engine.i18n.resolve("你好 {@name}")  # 替换 { @key } 占位符
    engine.i18n.langs()                 # 可用语言列表
"""
import glob
import os
import re

from framework.engine import log

_REF_RE = re.compile(r"\{@([\w.:-]+)\}")


class I18n:
    """翻译表管理器。"""

    def __init__(self, engine, default_lang="zh-CN") -> None:
        self.engine = engine
        self.default_lang = default_lang
        self.current = default_lang
        self._tables = {}        # ns -> {code: {key: text}}
        self._order = []         # 语言加载顺序 (首加载为默认)
        self._lang_names = None  # language 块: code -> 显示名
        # 加载框架核心文案
        core_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "lang")
        self.load_dir(core_dir, ns="core")

    # ------------------------------------------------------------------
    # language 块配置 (项目主文件声明)
    # ------------------------------------------------------------------
    def configure_language(self, cfg, lang_dir=None) -> None:
        """按主文件 language 块配置语言系统。

        cfg: {"default": "en", "en": "English", "zh-CN": "简体中文", ...}
        - default: 默认语言 (当前语言缺翻译时回退)
        - 其他键: 语言码 -> 设置中显示的名字
        - 游戏语言文件只从列出的语言中加载 (lang/<code>.json)
        """
        names = {}
        for code, name in cfg.items():
            if code == "default":
                continue
            if isinstance(name, (str, int, float)):
                names[str(code)] = str(name)
        if "default" in cfg:
            self.default_lang = str(cfg["default"])
        self._lang_names = names or None
        # 只加载列出的语言文件 (游戏文本 {@key} 均在其中查找)
        if lang_dir and names:
            for code in names:
                p = os.path.join(lang_dir, f"{code}.json")
                if os.path.isfile(p):
                    self.load_file(p, ns="game")
        # 当前语言切到默认语言 (主文件静态声明, 游戏启动即生效)
        self.current = self.default_lang
        try:
            self.engine.set_var("lang", self.current)
            self.engine.set_var("language", self.current)
        except Exception:
            pass
        # 设置页"语言"项刷新为显示名
        try:
            self.engine.settings.refresh_language_item()
        except Exception:
            pass
        # 广播 lang_change: 引擎据此刷新对话框/菜单文案、显示中界面
        try:
            self.engine.emit("lang_change", lang=self.current)
        except Exception:
            pass

    def lang_name(self, code: str) -> str:
        """语言显示名 (language 块配置; 未配置时用内置名表)。"""
        if self._lang_names and code in self._lang_names:
            return self._lang_names[code]
        builtin = {"zh-CN": "简体中文", "en": "English", "ja": "日本語",
                   "ko": "한국어", "fr": "Français", "de": "Deutsch"}
        return builtin.get(code, code)

    def code_by_name(self, name: str) -> str:
        """显示名 -> 语言码 (language 块配置; 找不到时原样返回)。"""
        if self._lang_names:
            for k, v in self._lang_names.items():
                if v == name:
                    return k
        if name in self.langs():
            return name
        return name

    def lang_options(self) -> list:
        """设置"语言"项选项: [(显示名, 语言码), ...]。

        language 块已配置时仅列出支持的语言; 否则列出全部已加载语言。
        """
        if self._lang_names:
            return [(v, k) for k, v in self._lang_names.items()]
        return [(self.lang_name(c), c) for c in self.langs()]

    # ------------------------------------------------------------------
    # 加载
    # ------------------------------------------------------------------
    def load_file(self, path, ns="core") -> None:
        """加载一个 JSON 语言文件: {code: {key: text}} 或直接 {key: text}。

        单语言文件 (仅 {key: text}) 时, 语言码取文件名 (如 en.json -> en)。
        """
        if not path or not os.path.isfile(path):
            return
        try:
            import json
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as exc:
            log.w("log.i18n.load_failed", path=path, exc=exc)
            return
        if not isinstance(data, dict):
            return
        # 多语言表 {code: {...}} vs 单语言 {key: text}
        has_code = any(isinstance(v, dict) for v in data.values())
        if has_code:
            for code, table in data.items():
                self._merge(ns, str(code), table)
        else:
            code = os.path.splitext(os.path.basename(path))[0]
            self._merge(ns, code, data)

    def load_dir(self, directory, ns="core") -> list:
        """加载目录下所有 *.json (文件名=语言码)。返回加载的语言码列表。"""
        codes = []
        if not directory or not os.path.isdir(directory):
            return codes
        for path in sorted(glob.glob(os.path.join(directory, "*.json"))):
            code = os.path.splitext(os.path.basename(path))[0]
            self.load_file(path, ns=ns)
            if code not in codes:
                codes.append(code)
        return codes

    def _merge(self, ns, code, table: dict) -> None:
        t = self._tables.setdefault(ns, {})
        t.setdefault(code, {}).update(table)
        if code not in self._order:
            self._order.append(code)

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------
    def langs(self) -> list:
        """可用语言列表 (核心/插件/游戏已加载语言的并集)。"""
        codes = []
        for t in self._tables.values():
            for code in t:
                if code not in codes:
                    codes.append(code)
        return codes

    def t(self, key: str, ns: str = "core", default=None, **fmt) -> str:
        """取当前语言文本; 当前语言缺 key 回退默认语言, 再回退原文 key。

        fmt 支持 {name} 占位替换。
        """
        table = self._tables.get(ns, {})
        text = None
        for code in (self.current, self.default_lang):
            if code in table and key in table[code]:
                text = table[code][key]
                break
        if text is None:
            text = key if default is None else default
        if fmt:
            try:
                text = str(text).format(**fmt)
            except (KeyError, IndexError, ValueError):
                pass
        return str(text)

    def set_lang(self, code: str) -> None:
        """切换当前语言 (需已加载; 未加载则忽略)。

        写入 $lang / $language 变量并广播 lang_change
        (引擎刷新所有显示中的界面文案/图片)。
        """
        if code in self.langs():
            self.current = code
            try:
                self.engine.set_var("lang", code)
                self.engine.set_var("language", code)
            except Exception:
                pass
            self.engine.emit("lang_change", lang=code)
            log.i("log.lang_switched", lang=code)

    # ------------------------------------------------------------------
    # 游戏文本占位符 { @key }
    # ------------------------------------------------------------------
    def resolve(self, text) -> str:
        """替换文本中的 ``{@key}`` 占位符 (游戏语言表, ns="game")。

        查找顺序: 游戏表 (ns="game") -> 核心表 (ns="core", 便于脚本直接
        引用框架文案, 如 ``{@dialog.quit.text}``) -> 保留原文 (便于调试)。
        支持 ``{@key}`` 嵌套变量插值 (文本中的 $var 由调用方另行处理)。
        """
        if not text or "{@" not in str(text):
            return str(text)

        def repl(m):
            key = m.group(1)
            return self.t(key, ns="game",
                          default=self.t(key, ns="core", default=m.group(0)))
        return _REF_RE.sub(repl, str(text))
