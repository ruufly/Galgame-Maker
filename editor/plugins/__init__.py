"""editor 插件包: framework/plugins 各插件的编辑器接口。

约定: 每个文件对应 framework/plugins/<同名>.py 的**编辑器侧接口**,
在 setup(registry) 中主动注册能力 (责任在插件侧, 编辑器不分析源码)。
"""

import os

from editor.plugins_api import registry, load_editor_plugins

__all__ = ["registry", "load_editor_plugins"]

# 启动时加载本目录全部接口文件
_HERE = os.path.dirname(os.path.abspath(__file__))
_loaded = load_editor_plugins(_HERE)
