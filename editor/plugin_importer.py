"""插件导入 (P4): 安装 .galpkg 标准插件包。

.galpkg = zip, 结构::

    my_plugin.galpkg
    ├── main.yml          # name/author/description/version/date/copyright
    │                     # + framework/editor 文件映射
    ├── gal_impl.py       # -> framework/plugins/<name>.py (引擎侧实现)
    └── ed_impl.py        # -> editor/plugins/<name>.py (编辑器接口, 可选)

main.yml 示例::

    name: my_plugin
    author: "xx"
    description: "自定义插件"
    version: 1.0
    date: 2026-08-12
    copyright: "xx 2026"
    framework: gal_impl.py
    editor: ed_impl.py

纯逻辑 import_plugin_package 可测试。
"""

import os
import re
import shutil
import zipfile

import yaml

_NAME_RE = re.compile(r"^[A-Za-z0-9_]+$")


def _read_yaml(zf: zipfile.ZipFile, name: str) -> dict:
    data = yaml.safe_load(zf.read(name).decode("utf-8"))
    return data if isinstance(data, dict) else {}


def import_plugin_package(zip_path: str, editor_plugins_dir: str,
                          framework_plugins_dir: str) -> dict:
    """导入插件包, 返回 {"name", "framework_file", "editor_file"}。

    写入位置: framework/plugins/<name>.py + editor/plugins/<name>.py
    (framework/plugins 为子模块目录, 写入后子模块会变脏, 由用户管理)
    """
    zip_path = os.path.abspath(zip_path)
    if not os.path.isfile(zip_path):
        raise FileNotFoundError("插件包不存在: %s" % zip_path)
    with zipfile.ZipFile(zip_path, "r") as zf:
        names = set(zf.namelist())
        if "main.yml" not in names:
            raise ValueError("插件包缺少 main.yml")
        meta = _read_yaml(zf, "main.yml")
        name = str(meta.get("name", "")).strip()
        if not _NAME_RE.match(name):
            raise ValueError("插件名非法 (仅 字母/数字/下划线): %r" % name)

        fw_src = str(meta.get("framework", "") or "").strip()
        ed_src = str(meta.get("editor", "") or "").strip()
        result = {"name": name, "framework_file": "", "editor_file": "",
                  "meta": meta}

        # 引擎侧实现 -> framework/plugins/<name>.py
        if fw_src:
            if fw_src not in names:
                raise ValueError("main.yml 声明的 framework 文件不存在: %s"
                                 % fw_src)
            os.makedirs(framework_plugins_dir, exist_ok=True)
            dst = os.path.join(framework_plugins_dir, name + ".py")
            with zf.open(fw_src) as src, open(dst, "wb") as out:
                shutil.copyfileobj(src, out)
            result["framework_file"] = dst

        # 编辑器接口 -> editor/plugins/<name>.py
        if ed_src:
            if ed_src not in names:
                raise ValueError("main.yml 声明的 editor 文件不存在: %s"
                                 % ed_src)
            os.makedirs(editor_plugins_dir, exist_ok=True)
            dst = os.path.join(editor_plugins_dir, name + ".py")
            with zf.open(ed_src) as src, open(dst, "wb") as out:
                shutil.copyfileobj(src, out)
            result["editor_file"] = dst
    return result


def load_plugin_editor_file(path: str, meta: dict | None = None) -> str | None:
    """导入后立即加载单个编辑器接口文件, 返回插件名或 None。

    meta: main.yml 元信息 —— 作为权威元数据合并进注册
    (插件 setup 内的 meta 仅作补充, main.yml 为准)
    """
    from editor.plugins_api import registry, load_editor_plugins
    name = os.path.splitext(os.path.basename(path))[0]
    before = set(registry.plugins())
    load_editor_plugins(os.path.dirname(path))
    added = set(registry.plugins()) - before
    if name in added and meta:
        registry.register_plugin(name, meta=meta)
    return name if name in added else None
