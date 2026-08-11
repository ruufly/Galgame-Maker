"""快捷键注册表 (核心): 归并所有键盘事件, 插件可注册自定义快捷键。

每个快捷键命令含 **主键 (primary) 与 副键 (alt)** 两个槽位
(每个槽位绑定一个键, 可留空), 设置界面同一命令的主副键显示在同一行。

用法::

    engine.keybinds.register("auto_toggle", "自动模式",
                             callback=my_fn, primary="a", alt="ctrl")

* 注册后自动生成对应设置项 (keybind 类型, "按键"分栏),
  开发者可在 setting.gal 引用调整 (setting <注册名>);
* 值持久化在 save/settings.json (settings 系统统一保存);
* 绑定冲突自动处理: 新键占用其他绑定时提示并自动让位。
"""

import pygame

from framework.engine import log

_SLOTS = ("primary", "alt")


class KeyBindManager:
    """快捷键注册表: name -> {label, primary, alt, callback}。"""

    def __init__(self, engine) -> None:
        self.engine = engine
        self.bindings = {}          # name -> {"label","primary","alt","callback"}
        self._order = []            # 注册顺序 (设置项顺序)
        self._register_core()

    # ------------------------------------------------------------------
    # 注册 / 查询
    # ------------------------------------------------------------------
    def register(self, name: str, label: str, callback,
                 primary=None, alt=None, section="按键",
                 label_key=None) -> str:
        """插件 API: 注册快捷键 (主键 primary + 副键 alt 两个槽位)。

        name: 唯一名 (也是设置项 key, setting.gal 可引用)。
        callback(key) -> bool (返回 False 表示不消费该按键)。
        primary/alt: 键常量或键名串 ("up"/pygame.K_UP), 可留空。
        label_key: i18n 语言表 key (设置界面显示名走翻译, 即时生效);
            不传则用 label 原文。
        """
        self.bindings[name] = {
            "label": label,
            "primary": self._norm_key(primary),
            "alt": self._norm_key(alt),
            "callback": callback,
            "section": section,
        }
        if name not in self._order:
            self._order.append(name)
        # 自动生成设置项 (keybind 类型, 双槽显示由设置界面处理)
        self.engine.settings.register(
            name, label, "keybind",
            getter=lambda n=name: self._keys_to_str(self.get_keys(n)),
            setter=lambda v, n=name: self.set_keys(n, self.parse_keys(v)),
            section=section, label_key=label_key)
        self.engine.emit("keybind_register", name=name, label=label)
        log.i("log.keybind.registered", name=name, label=label)
        return name

    def set_key(self, name: str, slot: str, key) -> None:
        """设置某槽位 (primary/alt) 的按键 (None=清空); 自动处理冲突。"""
        if slot not in _SLOTS:
            return
        key = self._norm_key(key)
        conflicts = self.conflicts(name, key)
        for other in conflicts:
            b = self.bindings.get(other)
            if b:
                for s in _SLOTS:
                    if b[s] == key:
                        b[s] = None
                self._sync_core(other)
        self.bindings[name][slot] = key
        self._sync_core(name)
        if conflicts:
            self.engine.display.show_notice(
                self.engine.i18n.t("keybind.conflict",
                                   names="/".join(conflicts)), 1.8)
        self.engine.emit("keybind_change", name=name, slot=slot, key=key)

    def set_keys(self, name: str, keys) -> None:
        """兼容: 按键列表设置 (前两个分别为主/副)。"""
        keys = self._norm_keys(keys)
        self.set_key(name, "primary", keys[0] if keys else None)
        self.set_key(name, "alt", keys[1] if len(keys) > 1 else None)

    def get_key(self, name: str, slot: str):
        b = self.bindings.get(name)
        return b.get(slot) if b else None

    def get_keys(self, name: str) -> list:
        """主副合并列表 (兼容旧代码/显示用)。"""
        b = self.bindings.get(name)
        if not b:
            return []
        return [k for k in (b.get("primary"), b.get("alt")) if k]

    def conflicts(self, name: str, key) -> list:
        """返回占用 key 的其他绑定名列表 (key 为空则不冲突)。"""
        if not key:
            return []
        out = []
        for other, b in self.bindings.items():
            if other == name:
                continue
            if key in (b.get("primary"), b.get("alt")):
                out.append(other)
        return out

    # ------------------------------------------------------------------
    # 按键分发
    # ------------------------------------------------------------------
    def press(self, key) -> bool:
        """按下一个键: 命中绑定 (主/副) 则触发回调; 返回 True=已处理。"""
        for name, b in self.bindings.items():
            if key in (b.get("primary"), b.get("alt")):
                try:
                    result = b["callback"](key)
                except Exception as exc:
                    log.w("log.keybind.callback_failed", name=name, exc=exc)
                    result = True
                return result is not False
        return False

    # ------------------------------------------------------------------
    # 工具
    # ------------------------------------------------------------------
    def _norm_key(self, key):
        """键常量 / 键名串 -> 键常量 (None/空 -> None)。"""
        if key is None:
            return None
        if isinstance(key, str):
            keys = self.parse_keys(key)
            return keys[0] if keys else None
        return key

    def _norm_keys(self, keys) -> list:
        if keys is None:
            return []
        if isinstance(keys, str):
            return self.parse_keys(keys)
        out = []
        for k in keys:
            if isinstance(k, str):
                out.extend(self.parse_keys(k))
            elif k not in out:
                out.append(k)
        return out

    def parse_keys(self, s) -> list:
        """键名串 -> 键常量列表 ("up, w" -> [K_UP, K_w]; 空 -> [])。"""
        if not s or not str(s).strip():
            return []
        out = []
        for part in str(s).split(","):
            name = part.strip().lower()
            if not name:
                continue
            k = self.engine._KEY_NAMES.get(name)
            if k is None and len(name) == 1 and name.isalnum():
                k = getattr(pygame, f"K_{name}", None)
            if k is None:
                # 功能键/大写键名 (f9 -> K_F9, ctrl -> K_CTRL)
                k = getattr(pygame, f"K_{name.upper()}", None)
            if k is not None and k not in out:
                out.append(k)
        return out

    def _keys_to_str(self, keys) -> str:
        return ", ".join(pygame.key.name(k) for k in keys)

    def _sync_core(self, name) -> None:
        """同步到旧版 engine.key_* 属性 (兼容旧代码/插件)。"""
        if name in ("key_up", "key_down", "key_confirm",
                    "key_left", "key_right"):
            setattr(self.engine, name, self.get_keys(name))

    # ------------------------------------------------------------------
    # 核心绑定 (原键盘导航行为; 主/副两槽)
    # ------------------------------------------------------------------
    def _register_core(self) -> None:
        eng = self.engine
        d = lambda: eng.display
        # 核心键位: 显示名走 i18n (label_key), 中文 label 作未配置时兜底
        self.register("key_up", "上移键",
                      lambda key: d().move_active(-1),
                      primary="up", alt="w",
                      label_key="keybind.key_up")
        self.register("key_down", "下移键",
                      lambda key: d().move_active(1),
                      primary="down", alt="s",
                      label_key="keybind.key_down")
        self.register("key_left", "左移键",
                      lambda key: d().move_active(-1),
                      primary="left", alt="a",
                      label_key="keybind.key_left")
        self.register("key_right", "右移键",
                      lambda key: d().move_active(1),
                      primary="right", alt="d",
                      label_key="keybind.key_right")
        self.register("key_confirm", "确认键",
                      eng._key_confirm_action,
                      primary="return", alt="space",
                      label_key="keybind.key_confirm")
        self.register("key_escape", "菜单键(ESC)",
                      lambda key: eng.on_escape(),
                      primary="esc",
                      label_key="keybind.key_escape")
