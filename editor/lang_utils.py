"""项目游戏文本 (多语言) 管理 — 纯逻辑, 可测试。

与编辑器 UI i18n (editor/i18n.py) 区分: 本模块管理**游戏项目**的
``lang/<code>.json`` 与脚本中的 ``{@key}`` 占位符, 让开发者在
编辑器里看到的是当前语言下的实际显示文本, 而不是占位符。

规则 (与引擎一致):
- ``{@key}`` 占位符: 文本取自 lang/<当前语言>.json; 缺失回退
  默认语言, 再回退原文 (key 原样显示, 便于开发调试)
- 富文本标记 ({c=..}/{b}/{m}..{/m}) 原样保留, 不与 {@key} 混淆
- 语言列表来自主脚本 language 块 (default + 语言码); 无 language
  块时扫描 lang/ 目录下的 JSON 文件
"""

import json
import os
import re

PLACEHOLDER_RE = re.compile(r"\{@([^{}]+)\}")


class GameLang:
    """一个游戏项目的多语言文本表。"""

    def __init__(self, root_dir: str, main_script=None):
        self.root = os.path.abspath(root_dir)
        self.lang_dir = os.path.join(self.root, "lang")
        self.default = "zh-CN"
        self.langs: list = []          # 语言码列表 (保持声明顺序)
        self._tables: dict = {}        # 语言码 -> {key: text}
        self.current = "zh-CN"         # 编辑器当前编辑语言
        self._parse_language_block(main_script)
        self._load()

    # ---- 加载 ---------------------------------------------------------
    def _parse_language_block(self, main_script) -> None:
        """从主脚本 language 块读取: default + 语言列表。"""
        if main_script is None:
            return
        for stmt in main_script.statements:
            if stmt.op == "language":
                dflt = stmt.kwargs.get("default", "zh-CN")
                if dflt:
                    self.default = dflt
                codes = [k for k in stmt.kwargs.keys() if k != "default"]
                if codes:
                    self.langs = codes
                return

    def _load(self) -> None:
        if not self.langs:
            self.langs = self._scan_lang_dir()
        for code in self.langs:
            self._tables[code] = self._read(code)
        if self.langs:
            # default 必须在语言列表内: 无 language 块时取第一个
            if self.default not in self.langs:
                self.default = self.langs[0]
            self.current = self.default

    def _scan_lang_dir(self) -> list:
        out = []
        if os.path.isdir(self.lang_dir):
            for f in sorted(os.listdir(self.lang_dir)):
                if f.endswith(".json"):
                    out.append(f[:-5])
        return out or [self.default]

    def _read(self, code: str) -> dict:
        path = self.path_for(code)
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def path_for(self, code: str) -> str:
        return os.path.join(self.lang_dir, code + ".json")

    # ---- 查询 ---------------------------------------------------------
    def text(self, key: str, lang: str | None = None) -> str:
        """取某语言文本 (缺失回退默认语言, 再回退 key 原文)。"""
        lang = lang or self.current
        table = self._tables.get(lang, {})
        val = table.get(key)
        if val is not None:
            return val
        if lang != self.default:
            dflt = self._tables.get(self.default, {}).get(key)
            if dflt is not None:
                return dflt
        return key

    def has_key(self, key: str) -> bool:
        return any(key in t for t in self._tables.values())

    def keys(self) -> list:
        seen: dict = {}
        for t in self._tables.values():
            for k in t:
                seen.setdefault(k, True)
        return sorted(seen)

    def resolve(self, text: str, lang: str | None = None) -> str:
        """替换文本中的全部 {@key} 为当前语言实际文本。

        富文本标记 ({c=..} 等) 原样保留; 未找到的 key 回退
        默认语言, 再回退原文 (保留 {@key} 便于定位)。
        """
        def _repl(m):
            key = m.group(1)
            lang2 = lang or self.current
            table = self._tables.get(lang2, {})
            val = table.get(key)
            if val is None and lang2 != self.default:
                val = self._tables.get(self.default, {}).get(key)
            return val if val is not None else m.group(0)
        return PLACEHOLDER_RE.sub(_repl, text)

    def key_of(self, text: str) -> str | None:
        """若文本整体是单个占位符, 返回其 key; 否则 None。"""
        m = PLACEHOLDER_RE.fullmatch(text.strip())
        return m.group(1) if m else None

    # ---- 编辑 ---------------------------------------------------------
    def set_text(self, key: str, lang: str, value: str) -> None:
        table = self._tables.setdefault(lang, {})
        if value:
            table[key] = value
        else:
            table.pop(key, None)

    def ensure_key(self, text: str, lang: str | None = None) -> str:
        """把无占位符的文本转为 {@key} 引用 (写入当前语言, 其它语言留空)。

        返回替换后的文本 (含 {@key}); 文本已是占位符则原样返回。
        """
        stripped = text.strip()
        if not stripped:
            return text
        if self.key_of(stripped) is not None:
            return stripped
        key = self._next_key()
        lang = lang or self.current
        self.set_text(key, lang, stripped)
        return "{@%s}" % key

    def _next_key(self) -> str:
        n = 1
        while True:
            key = "t%d" % n
            if not self.has_key(key):
                return key
            n += 1

    # ---- 保存 ---------------------------------------------------------
    def save(self) -> None:
        """写回 lang/<code>.json (全部语言)。"""
        os.makedirs(self.lang_dir, exist_ok=True)
        for code, table in self._tables.items():
            path = self.path_for(code)
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(table, fh, ensure_ascii=False, indent=2)
            os.replace(tmp, path)

    def __repr__(self):
        return "<GameLang %s langs=%s current=%s keys=%d>" % (
            self.root, self.langs, self.current, len(self.keys()))
