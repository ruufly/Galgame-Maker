"""编辑器国际化 (P3): 轻量 i18n (zh-CN / en)。

- 语言文件: editor/lang/<code>.json
- 配置持久化: ~/.galmaker_editor.json (用户级)
- 切换: set_lang -> lang_changed 信号 -> UI 刷新
- 回退: en 缺失回退 zh-CN, 再回退 key 原文
"""

import json
import os

from PySide6.QtCore import QObject, Signal


class EditorI18n(QObject):
    lang_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._lang = "zh-CN"
        self._tables: dict = {}
        self._config_path = os.path.join(os.path.expanduser("~"),
                                         ".galmaker_editor.json")
        self._load_config()
        self._load_tables()

    # ---- 配置 ---------------------------------------------------------
    def _load_config(self):
        try:
            with open(self._config_path, encoding="utf-8") as f:
                cfg = json.load(f)
                self._lang = cfg.get("lang", "zh-CN")
        except (OSError, ValueError):
            pass

    def _save_config(self):
        try:
            with open(self._config_path, "w", encoding="utf-8") as f:
                json.dump({"lang": self._lang}, f)
        except OSError:
            pass

    # ---- 语言表 -------------------------------------------------------
    def _load_tables(self):
        here = os.path.dirname(os.path.abspath(__file__))
        lang_dir = os.path.join(here, "lang")
        for code in ("zh-CN", "en"):
            path = os.path.join(lang_dir, code + ".json")
            try:
                with open(path, encoding="utf-8") as f:
                    self._tables[code] = json.load(f)
            except (OSError, ValueError):
                self._tables[code] = {}

    # ---- 对外 ---------------------------------------------------------
    def set_lang(self, code: str) -> None:
        if code not in self._tables:
            code = "zh-CN"
        if code != self._lang:
            self._lang = code
            self._save_config()
            self.lang_changed.emit()

    def lang(self) -> str:
        return self._lang

    def t(self, key: str, **fmt) -> str:
        table = self._tables.get(self._lang, {})
        text = table.get(key)
        if text is None:
            text = self._tables.get("zh-CN", {}).get(key, key)
        if fmt and isinstance(text, str):
            try:
                text = text.format(**fmt)
            except (KeyError, IndexError):
                pass
        return text


_i18n = EditorI18n()


def t(key: str, **fmt) -> str:
    """全局翻译函数 (编辑器 UI 用)。"""
    return _i18n.t(key, **fmt)
