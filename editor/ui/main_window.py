"""Galgame Maker 编辑器主窗口 (P1 骨架)。

布局:
- 菜单/工具栏: 项目 / 校验 / 预览
- 左 Dock: 项目浏览器 (脚本 + 素材目录)
- 右 Dock: 属性面板 (占位)
- 右下 Dock: 引擎实时预览 (嵌入式无头渲染)
- 下 Dock: 输出日志
- 中央: 四工作区 Tab (素材 / 样式 / 逻辑 / 编译, 占位)

P1 已通: 打开项目 -> 校验 (序列化往返) -> 内嵌预览。
P2+: 四工作区逐个实现 (素材库 / 样式可视化 / 流程节点编辑器 / 打包)。
"""

import os
import time

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (QDockWidget, QFileDialog, QLabel, QMainWindow,
                               QMessageBox, QPlainTextEdit, QTabWidget,
                               QToolBar, QTreeWidget, QTreeWidgetItem,
                               QVBoxLayout, QWidget)

from framework.engine.loader import load_script_with_imports
from framework.engine.parser import parse

from editor.compare import norm_script, roundtrip_ok
from editor.model import Project
from editor.preview_window import PreviewWindow
from editor.i18n import t, _i18n
import editor.plugins  # noqa: F401  (加载内置插件编辑器接口)
from editor.project_wizard import NewProjectDialog
from editor.project_settings import ProjectSettingsDialog
from editor.definitions import DefinitionsPanel
from editor.flow_editor import FlowEditor
from editor.assets import AssetPanel
from editor.styles_editor import StylesEditor
from editor.build import BuildPanel
from editor.plugins_panel import PluginsPanel
from editor.localization_panel import LocalizationPanel
from editor.property_panel import PropertyPanel

_RUNTIME_DIRS = {"save", "logs", "__pycache__", "nowfiletmp", "fonts"}




class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(t("app.title"))
        self.resize(1280, 800)
        self.project: Project | None = None

        # 独立预览窗口 (单例, 首次点击预览时创建)
        self._preview_window: PreviewWindow | None = None
        self._preview_script: str = ""
        self._dock_sized = False
        self._tab_keys: list = []
        self._dock_keys: list = []

        self._build_actions()
        self._build_menus()
        self._build_toolbar()
        self._build_docks()
        self._build_central()
        self.statusBar().showMessage(t("status.ready"))
        _i18n.lang_changed.connect(self._apply_lang)

    # ==================================================================
    # UI 构建
    # ==================================================================
    def _build_actions(self):
        self.act_open = QAction(t("act.open"), self)
        self.act_open.setShortcut(QKeySequence.Open)
        self.act_open.triggered.connect(lambda: self.open_project())

        self.act_new = QAction(t("act.new"), self)
        self.act_new.setShortcut("Ctrl+Shift+N")
        self.act_new.triggered.connect(self._new_project)

        self.act_settings = QAction(t("act.settings"), self)
        self.act_settings.setShortcut("Ctrl+,")
        self.act_settings.triggered.connect(self._project_settings)

        self.act_validate = QAction(t("act.validate"), self)
        self.act_validate.setShortcut("F7")
        self.act_validate.triggered.connect(self.validate)

        self.act_preview = QAction(t("act.preview"), self)
        self.act_preview.setShortcut("F5")
        self.act_preview.triggered.connect(self._open_preview)

        self.act_stop = QAction(t("act.stop"), self)
        self.act_stop.setShortcut("Shift+F5")
        self.act_stop.triggered.connect(self._stop_preview)

        self.act_about = QAction(t("act.about"), self)
        self.act_about.triggered.connect(self._about)

    def _build_menus(self):
        self.menu_file = self.menuBar().addMenu(t("menu.file"))
        self.menu_file.addAction(self.act_new)
        self.menu_file.addAction(self.act_open)
        self.menu_file.addSeparator()
        self.menu_file.addAction(self.act_settings)
        self.menu_file.addSeparator()
        self.act_import_plugin = QAction("导入插件 (.galpkg)…", self)
        self.act_import_plugin.triggered.connect(self._import_plugin)
        self.menu_file.addAction(self.act_import_plugin)
        self.menu_file.addSeparator()
        self.menu_file.addAction(t("act.exit"), self.close, QKeySequence.Quit)

        self.menu_view = self.menuBar().addMenu(t("menu.view"))
        m_lang = self.menu_view.addMenu(t("menu.language"))
        act_zh = m_lang.addAction("简体中文")
        act_zh.triggered.connect(lambda: _i18n.set_lang("zh-CN"))
        act_en = m_lang.addAction("English")
        act_en.triggered.connect(lambda: _i18n.set_lang("en"))

        self.menu_tool = self.menuBar().addMenu(t("menu.tools"))
        self.menu_tool.addAction(self.act_validate)
        self.menu_tool.addAction(self.act_preview)
        self.menu_tool.addAction(self.act_stop)

        self.menu_help = self.menuBar().addMenu(t("menu.help"))
        self.menu_help.addAction(self.act_about)

    def _build_toolbar(self):
        tb = QToolBar("主工具栏", self)
        tb.setMovable(False)
        tb.addAction(self.act_open)
        tb.addSeparator()
        tb.addAction(self.act_validate)
        tb.addAction(self.act_preview)
        tb.addAction(self.act_stop)
        self.addToolBar(tb)

    def _build_docks(self):
        # 左: 项目浏览器
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["项目内容"])
        self.tree.itemDoubleClicked.connect(self._on_tree_double)
        self._dock_tree = self._make_dock("dock.project", self.tree, Qt.LeftDockWidgetArea)

        # 右: 属性面板 (P4: 流程节点等选中对象的快捷编辑)
        self.props = PropertyPanel()
        self._dock_prop = self._make_dock("dock.props", self.props,
                                          Qt.RightDockWidgetArea)

        # 下: 输出日志
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setMaximumBlockCount(2000)
        self._dock_out = self._make_dock("dock.output", self.output,
                                         Qt.BottomDockWidgetArea)

    def showEvent(self, event):
        """首次显示、布局就绪后分配 dock 尺寸 (build 阶段调用无效)。"""
        super().showEvent(event)
        if self._dock_sized:
            return
        self._dock_sized = True
        # 底部输出日志: 默认高度即可, 不再为预览预留大块空间
        self.resizeDocks([self._dock_out], [180], Qt.Vertical)

    def _make_dock(self, key: str, widget: QWidget, area) -> QDockWidget:
        dock = QDockWidget(t(key), self)
        dock.setWidget(widget)
        dock.setAllowedAreas(Qt.AllDockWidgetAreas)
        self.addDockWidget(area, dock)
        self._dock_keys.append((dock, key))
        return dock

    def _build_central(self):
        self.tabs = QTabWidget()
        # 素材: 可用的素材库面板 (P2)
        self.assets = AssetPanel()
        self.assets.status.connect(self._log)
        self.tabs.addTab(self.assets, t("tab.material"))
        self._tab_keys.append((0, "tab.material"))
        # 定义: 角色/场景/声音 类型化编辑 (P2)
        self.defs = DefinitionsPanel()
        self.tabs.addTab(self.defs, t("tab.defs"))
        self._tab_keys.append((1, "tab.defs"))
        # 逻辑: 流程节点画布 (P2)
        self.flow = FlowEditor()
        self.flow.log.connect(self._log)
        self.flow.locate_key.connect(self._locate_key)
        self.tabs.addTab(self.flow, t("tab.logic"))
        self._tab_keys.append((2, "tab.logic"))
        # 多语言: 全项目占位符条目大列表 (P4)
        self.localization = LocalizationPanel()
        self.tabs.addTab(self.localization, t("tab.local"))
        self._tab_keys.append((3, "tab.local"))
        # 样式: 可视化配色编辑 (P3/P4: 多样式源 + 插件字段)
        self.styles = StylesEditor()
        self.styles.log.connect(self._log)
        self.tabs.addTab(self.styles, t("tab.styles"))
        self._tab_keys.append((4, "tab.styles"))
        # 插件: 能力总览 + 装载配置 (P3)
        self.plugins_panel = PluginsPanel()
        self.plugins_panel.log.connect(self._log)
        self.tabs.addTab(self.plugins_panel, t("tab.plugins"))
        self._tab_keys.append((5, "tab.plugins"))
        # 编译: 校验/导出/打包 (P3)
        self.build = BuildPanel()
        self.build.log.connect(self._log)
        self.tabs.addTab(self.build, t("tab.build"))
        self._tab_keys.append((6, "tab.build"))
        self.setCentralWidget(self.tabs)
        # 流程画布选中节点 -> 属性面板
        self.flow.node_selected.connect(self.props.show_flow_node)

    def _locate_key(self, key: str) -> None:
        """切到多语言面板并定位指定 key (来自画布/定义等跳转)。"""
        self.localization.refresh()
        self.tabs.setCurrentWidget(self.localization)
        self.localization.locate(key)

    def _new_project(self) -> None:
        """新建项目向导: 创建成功 -> 直接打开。"""
        dlg = NewProjectDialog(self)
        if dlg.exec() == NewProjectDialog.Accepted:
            path = dlg.result_path()
            self._log("新项目已创建: %s" % path)
            self.open_project(path)

    def _import_plugin(self) -> None:
        """导入 .galpkg 插件包: main.yml + framework/editor 双 py。"""
        f, _ = QFileDialog.getOpenFileName(
            self, "导入插件", "", "Galgame 插件包 (*.galpkg)")
        if not f:
            return
        from editor.plugin_importer import (import_plugin_package,
                                            load_plugin_editor_file)
        _ROOT2 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        try:
            result = import_plugin_package(
                f,
                editor_plugins_dir=os.path.join(_ROOT2, "plugins"),
                framework_plugins_dir=os.path.join(_ROOT2, "framework",
                                                   "plugins"))
        except Exception as exc:
            QMessageBox.critical(self, "导入失败", str(exc))
            return
        name = result["name"]
        msgs = ["插件已导入: %s" % name]
        if result.get("framework_file"):
            msgs.append("引擎侧: %s" % result["framework_file"])
        if result.get("editor_file"):
            loaded = load_plugin_editor_file(result["editor_file"])
            msgs.append("编辑器接口: %s%s" % (
                result["editor_file"],
                " (已注册)" if loaded else " (未注册 setup)"))
        self._log(" | ".join(msgs))
        if result.get("editor_file"):
            self.plugins_panel.refresh()
        self._log("注意: framework/plugins 为子模块, 变更后需自行管理 git 状态")

    def _project_settings(self) -> None:
        """项目设置: window 块表单, 保存后写回模型并落盘。"""
        if self.project is None:
            self._log("请先打开项目")
            return
        dlg = ProjectSettingsDialog(self.project, self)
        if dlg.exec() == ProjectSettingsDialog.Accepted:
            self._log("项目设置已保存 (window 块已更新)")
            self._log("提示: 重新运行预览以应用窗口配置")
            self.project.load()   # 重新加载模型 (内容已变)

    def open_project(self, path: str | None = None) -> None:
        if path is None:
            path = QFileDialog.getExistingDirectory(self, "选择 Galgame 项目目录")
        if not path:
            return
        try:
            self.project = Project(path)
            self.project.load()
        except Exception as exc:
            QMessageBox.critical(self, "打开失败", str(exc))
            return
        self._populate_tree()
        self.assets.set_project(self.project)
        self.defs.set_project(self.project)
        self.flow.set_project(self.project)
        self.styles.set_project(self.project)
        self.plugins_panel.set_project(self.project)
        self.build.set_project(self.project)
        self.localization.set_project(self.project)
        from editor.lang_utils import GameLang
        self.props.set_lang(GameLang(self.project.root,
                                     self.project.main_script()))
        self.props.set_flow_scene(self.flow.scene)
        self.props.show_message(t("props.empty"))
        main = self.project.main_script()
        if main is not None:
            self._preview_script = os.path.join(self.project.root,
                                                self.project.main)
            if self._preview_window is not None:
                self._preview_window.set_script(self._preview_script)
            self.setWindowTitle("Galgame Maker 编辑器 — %s" % path)
            self._log("项目已打开: %s (%d 个脚本)" % (path, len(self.project.scripts)))
            self._log("预览脚本: %s" % self.project.main)
        else:
            self._log("警告: 目录中未找到主脚本 %s" % self.project.main)

    def _open_preview(self) -> None:
        """打开独立预览窗口 (真实进程运行游戏 + 调试控制台)。"""
        if not self._preview_script:
            self._log("请先打开项目")
            return
        if self._preview_window is None:
            self._preview_window = PreviewWindow(self)
            self._preview_window.destroyed.connect(
                lambda: setattr(self, "_preview_window", None))
        self._preview_window.set_script(self._preview_script)
        self._preview_window.show()
        self._preview_window.raise_()
        self._preview_window.activateWindow()
        self._preview_window.start()

    def _stop_preview(self) -> None:
        """停止当前预览 (若窗口已打开)。"""
        if self._preview_window is not None:
            self._preview_window.stop()

    def _populate_tree(self) -> None:
        self.tree.clear()
        root_item = QTreeWidgetItem([os.path.basename(self.project.root)])
        root_item.setToolTip(0, self.project.root)

        scripts_item = QTreeWidgetItem(["脚本 (.gal)"])
        for rel in sorted(self.project.scripts):
            QTreeWidgetItem(scripts_item, [rel])
        root_item.addChild(scripts_item)

        mats_item = QTreeWidgetItem(["素材目录"])
        for name in sorted(os.listdir(self.project.root)):
            full = os.path.join(self.project.root, name)
            if os.path.isdir(full) and name not in _RUNTIME_DIRS:
                QTreeWidgetItem(mats_item, [name + "/"])
        root_item.addChild(mats_item)

        self.tree.addTopLevelItem(root_item)
        root_item.setExpanded(True)
        scripts_item.setExpanded(True)

    def _on_tree_double(self, item: QTreeWidgetItem, _col: int) -> None:
        text = item.text(0)
        if text.endswith(".gal") and self.project is not None:
            from editor.script_editor import ScriptEditorDialog
            dlg = ScriptEditorDialog(self.project, text, self)
            if dlg.exec() == ScriptEditorDialog.Accepted:
                self._reload_project_panels()
                self._log("脚本已保存并重新解析: %s" % text)

    def _reload_project_panels(self) -> None:
        """脚本被文本编辑后: 重载模型并刷新全部面板。"""
        if self.project is None:
            return
        self.project.load()
        for panel in (self.assets, self.defs, self.flow, self.styles,
                      self.plugins_panel, self.build, self.localization):
            fn = getattr(panel, "set_project", None)
            if fn is not None:
                fn(self.project)
        self._populate_tree()

    # ==================================================================
    # 校验与日志
    # ==================================================================
    def validate(self) -> None:
        if self.project is None:
            self._log("请先打开项目")
            return
        t0 = time.time()
        ok, bad = 0, []
        for rel, script in self.project.scripts.items():
            if roundtrip_ok(script):
                ok += 1
            else:
                bad.append(rel)
        msg = "校验完成: %d/%d 通过" % (ok, len(self.project.scripts))
        if bad:
            msg += " | 往返失败: %s" % ", ".join(bad)
        msg += " (%.2fs)" % (time.time() - t0)
        self._log(msg)

        # 集成校验: 主脚本 import 合并加载
        try:
            main = os.path.join(self.project.root, self.project.main)
            merged = load_script_with_imports(main)
            self._log("合并加载 OK: %d 顶层语句, %d 标签"
                      % (len(merged.statements), len(merged.labels)))
        except Exception as exc:
            self._log("合并加载失败: %s" % exc)

    def _log(self, msg: str) -> None:
        self.output.appendPlainText("[%s] %s" % (
            time.strftime("%H:%M:%S"), msg))

    # ==================================================================
    def _apply_lang(self):
        """语言切换后刷新全部 UI 文本。"""
        self.setWindowTitle(t("app.title"))
        self.menu_file.setTitle(t("menu.file"))
        self.menu_view.setTitle(t("menu.view"))
        self.menu_tool.setTitle(t("menu.tools"))
        self.menu_help.setTitle(t("menu.help"))
        self.act_new.setText(t("act.new"))
        self.act_open.setText(t("act.open"))
        self.act_settings.setText(t("act.settings"))
        self.act_validate.setText(t("act.validate"))
        self.act_preview.setText(t("act.preview"))
        self.act_stop.setText(t("act.stop"))
        self.act_about.setText(t("act.about"))
        for idx, key in self._tab_keys:
            self.tabs.setTabText(idx, t(key))
        for dock, key in self._dock_keys:
            dock.setWindowTitle(t(key))
        self.tree.setHeaderLabels([t("tree.project")])
        self.statusBar().showMessage(t("status.ready"))
        if self._preview_window is not None:
            self._preview_window.apply_lang()
        for panel in (self.assets, self.defs, self.flow, self.styles,
                      self.build):
            fn = getattr(panel, "apply_lang", None)
            if fn is not None:
                fn()

    def _about(self):
        QMessageBox.about(self, "关于 Galgame Maker 编辑器",
                          "Galgame Maker 编辑器\n\n"
                          "可视化制作 .gal 视觉小说, 零基础友好。\n"
                          "引擎: framework 子模块 (Python 3.10 + pygame)\n"
                          "编辑器版本: 0.4 (P0-P3 + 独立预览调试 / 多语言可视化 / 脚本编辑器)")


    def closeEvent(self, event):
        if self._preview_window is not None:
            self._preview_window.close()
        super().closeEvent(event)
