"""存档模块: 以 JSON 形式读写槽位文件。"""

import json
import os
import time

from framework.engine import log


class SaveManager:
    """存档管理器。槽位文件保存在项目目录的 ``save/`` 下。

    目录在每次存取时按 ``engine.project_dir`` 现算,
    因此切换项目后存档会自动落到新项目目录。
    """

    def __init__(self, engine) -> None:
        self.engine = engine

    def _path(self, slot: int) -> str:
        d = os.path.join(self.engine.project_dir, "save")
        os.makedirs(d, exist_ok=True)
        return os.path.join(d, f"slot{int(slot)}.json")

    def save(self, slot: int, data: dict) -> str:
        """写入存档, 返回存档文件路径。"""
        data = dict(data)
        data["_saved_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        path = self._path(slot)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        self.engine.emit("save", slot=slot, path=path)
        log.i("log.save_written", path=path)
        return path

    def load(self, slot: int) -> dict:
        """读取存档, 不存在或损坏时返回 None。"""
        path = self._path(slot)
        if not os.path.isfile(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.engine.emit("load", slot=slot, path=path)
            return data
        except Exception as exc:
            log.w("log.save.load_failed", path=path, exc=exc)
            return None

    def _global_path(self) -> str:
        """全局进度文件 (结局/CG 收集等跨存档记录)。"""
        d = os.path.join(self.engine.project_dir, "save")
        os.makedirs(d, exist_ok=True)
        return os.path.join(d, "global.json")

    def get_global(self, key: str, default=None):
        """读取全局进度 (跨存档, 如已达成结局 / 已解锁 CG)。"""
        try:
            with open(self._global_path(), "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get(key, default)
        except Exception:
            return default

    def set_global(self, key: str, value) -> None:
        """写入全局进度。"""
        data = {}
        if os.path.isfile(self._global_path()):
            try:
                with open(self._global_path(), "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = {}
        data[key] = value
        with open(self._global_path(), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _settings_path(self) -> str:
        d = os.path.join(self.engine.project_dir, "save")
        os.makedirs(d, exist_ok=True)
        return os.path.join(d, "settings.json")

    def get_settings(self, default=None):
        """读取全局设置 (跨存档, 音量/键位/主角名等)。"""
        try:
            with open(self._settings_path(), "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default

    def set_settings(self, data: dict) -> None:
        """写入全局设置。"""
        try:
            with open(self._settings_path(), "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as exc:
            log.w("log.save.settings_write_failed", exc=exc)

    def set_meta(self, slot: int, key: str, value) -> None:
        """写入存档元数据 (如快照路径), 不覆盖游戏状态。"""
        data = self.load(slot)
        if data is None:
            return
        data[key] = value
        data["_saved_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(self._path(slot), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def get_meta(self, slot: int, key: str, default=None):
        """读取存档元数据。"""
        data = self.load(slot)
        if data is None:
            return default
        return data.get(key, default)

    def meta_path(self, slot: int, rel: str) -> str:
        """把存档元数据里的相对路径解析为绝对路径 (基于存档目录)。"""
        if not rel:
            return None
        if os.path.isabs(rel):
            return rel
        return os.path.join(os.path.dirname(self._path(slot)), rel)

    def _read_raw(self, slot: int) -> dict:
        """直接读取槽位文件 (不发 load 事件, 供列表展示用)。"""
        path = self._path(slot)
        if not os.path.isfile(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def list_slots(self, count: int = 6) -> list:
        """列出前 count 个槽位的信息, 供存档选择界面展示。

        每项: {"slot": 索引, "time": 存档时间, "label": 所在标签,
               "preview": 进度摘要, "empty": 是否空槽}
        """
        out = []
        for slot in range(count):
            data = self._read_raw(slot)
            if data is None:
                out.append({"slot": slot, "empty": True})
                continue
            preview = data.get("text") or data.get("label") or ""
            out.append({
                "slot": slot,
                "time": data.get("_saved_at", ""),
                "label": data.get("label") or "",
                "preview": str(preview)[:24],
                "screenshot": data.get("screenshot") or "",
                "empty": False,
            })
        return out

    def slots(self) -> list:
        d = os.path.join(self.engine.project_dir, "save")
        out = []
        if not os.path.isdir(d):
            return out
        for name in sorted(os.listdir(d)):
            if name.startswith("slot") and name.endswith(".json"):
                out.append(name)
        return out
