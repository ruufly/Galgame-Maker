"""编辑器数据模型 (P0: 轻量封装)。

P0 阶段: 模型直接复用 framework.engine.parser 的 Script / Statement 树
作为单一事实来源; Project 负责管理一组脚本文件 + 项目元数据。

后续 P1+ 在此之上加类型化访问器 (Scene / Character / Sound / Menu /
Style / Setting / StoryNode ...), 不变式: 所有 .gal 文本均由模型
序列化生成, 导入 = 解析回模型 (Editor-first)。
"""

import os
from typing import Dict, List, Optional

from framework.engine.parser import Script, Statement, parse_file


class Project:
    """一个游戏项目 = 一个标准目录 (与 framework 运行约定一致)。

    目录约定 (与 test/engine_demo 相同)::

        MyGame/
        ├── demo.gal            # 主脚本 (window/language/plugins/title + import)
        ├── ui.gal / cast.gal / audio.gal / gallery.gal / setting.gal / story.gal
        ├── materials/          # 素材 (image/audio/...)
        ├── lang/               # i18n JSON
        ├── fonts/
        └── save/ logs/         # 运行时产物
    """

    def __init__(self, root: str, main: str = "demo.gal"):
        self.root = os.path.abspath(root)
        self.main = main
        self.scripts: Dict[str, Script] = {}   # 相对路径 -> Script

    # ---- 加载 / 保存 -------------------------------------------------
    def load(self) -> "Project":
        """扫描目录内全部 .gal 并解析进模型。"""
        self.scripts.clear()
        for dirpath, _dirs, files in os.walk(self.root):
            # 跳过运行时产物目录
            parts = set(os.path.relpath(dirpath, self.root).split(os.sep))
            if parts & {"save", "logs", "__pycache__"}:
                continue
            for f in sorted(files):
                if f.endswith(".gal"):
                    p = os.path.join(dirpath, f)
                    rel = os.path.relpath(p, self.root)
                    self.scripts[rel] = parse_file(p)
        return self

    def add_script(self, rel: str, script: Script) -> None:
        self.scripts[rel] = script

    def remove_script(self, rel: str) -> None:
        self.scripts.pop(rel, None)

    def get(self, rel: str) -> Optional[Script]:
        return self.scripts.get(rel)

    def main_script(self) -> Optional[Script]:
        return self.scripts.get(self.main)

    # ---- 查询 (P0 用通用遍历, P1 加类型化访问) -----------------------
    def statements_of(self, rel: str, op: str) -> List[Statement]:
        """取某脚本中所有顶层 op 语句 (递归 block 不展开)。"""
        script = self.scripts.get(rel)
        if script is None:
            return []
        return [s for s in script.statements if s.op == op]

    def all_top_statements(self) -> List[Statement]:
        """全部脚本的顶层语句 (import 合并语义近似)。"""
        out: List[Statement] = []
        for script in self.scripts.values():
            out.extend(script.statements)
        return out

    def find_label(self, label: str) -> Optional[Statement]:
        """在所有脚本中查找标签 (返回其首条语句, 无则 None)。"""
        for script in self.scripts.values():
            if label in script.labels:
                body = script.labels[label]
                return body[0] if body else None
        return None

    def __repr__(self):
        return f"<Project {self.root} ({len(self.scripts)} scripts)>"
