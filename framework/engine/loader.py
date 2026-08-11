"""脚本加载器: 支持 import 语句递归展开, 把多个 .gal 文件合并为一个 Script。

用法 (脚本顶层)::

    import "ui.gal"          # 导入界面样式定义
    import "cast.gal"        # 导入角色/场景定义
    import "branches.gal"    # 导入分支标签

被导入文件可以包含: 标签块、window/style/char/scene/plugins/selection_style
等顶层声明。合并规则:

    * 顶层声明按 import 出现的位置顺序并入
    * 标签全部并入, 重复标签报错
    * 被导入文件的 ``start`` 标签会被忽略 (入口只属于主文件)
    * 循环导入会报错
"""

import os

from framework.engine import log
from framework.engine.parser import Script, Statement, parse_file


class ImportError_(Exception):
    pass


def load_script_with_imports(path: str) -> Script:
    """解析主脚本并递归展开 import, 返回合并后的 Script。"""
    labels = {}
    merged = Script(path=os.path.abspath(path))

    def load(path, stack):
        path = os.path.abspath(path)
        if path in stack:
            chain = " -> ".join(stack + [path])
            raise ImportError_(f"循环导入: {chain}")
        script = parse_file(path)
        if not stack:
            # 主文件元信息
            merged.meta = dict(script.meta)
            if script.name:
                merged.name = script.name
        for label, body in script.labels.items():
            if label == "start" and stack:
                continue          # 子文件不含入口
            if label in labels:
                raise ImportError_(
                    f"重复标签 {label!r} ({path} 与已有导入冲突)")
            labels[label] = body
        out = []
        base = os.path.dirname(path)
        for stmt in script.statements:
            if stmt.op == "import":
                target = stmt.args[0] if stmt.args else None
                if not target:
                    log.w("log.loader.import_no_path", line=stmt.line)
                    continue
                sub_path = os.path.join(base, str(target))
                if not os.path.isfile(sub_path):
                    raise ImportError_(
                        f"导入文件不存在: {sub_path} (第{stmt.line}行)")
                out.extend(load(sub_path, stack + [path]))
            else:
                out.append(stmt)
        return out

    merged.statements = load(path, [])
    merged.labels = labels
    return merged


def parse_file_with_imports(path: str) -> Script:
    """解析入口 (兼容 parse_file 签名)。"""
    return load_script_with_imports(path)
