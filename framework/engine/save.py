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
        log.info(f"已存档: {path}")
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
            log.warning(f"读档失败 {path}: {exc}")
            return None

    def slots(self) -> list:
        d = os.path.join(self.engine.project_dir, "save")
        out = []
        if not os.path.isdir(d):
            return out
        for name in sorted(os.listdir(d)):
            if name.startswith("slot") and name.endswith(".json"):
                out.append(name)
        return out
