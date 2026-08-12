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
from editor.preview import PreviewPanel
from editor.i18n import t, _i18n
from editor.project_wizard import NewProjectDialog
from editor.project_settings import ProjectSettingsDialog
from editor.definitions import DefinitionsPanel
from editor.flow_editor import FlowEditor
from editor.assets import AssetPanel
from editor.styles_editor import StylesEditor
from editor.build import BuildPanel
from editor.plugins_panel import PluginsPanel

_RUNTIME_DIRS = {"save", "logs", "__pycache__", "nowfiletmp", "fonts"}


def _placeholder(title: str, desc: str) -> QWidget:
    """工作区占位页。"""
    w = QWidget()
    layout = QVBoxLayout(w)
    label = QLabel(title)
    label.setStyleSheet("font-size:20px; font-weight:600; padding:24px 8px 4px 8px;")
    hint = QLabel(desc)
    hint.setWordWrap(True)
    hint.setStyleSheet("color:#666; padding:0 8px;")
    layout.addWidget(label)
    layout.addWidget(hint)
    layout.addStretch(1)
    return w


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(t("app.title"))
        self.resize(1280, 800)
        self.project: Project | None = None

        # 预览面板先建 (菜单动作需要引用)
        self.preview = PreviewPanel()
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
        self.act_preview.triggered.connect(self.preview.start)

        self.act_stop = QAction(t("act.stop"), self)
        self.act_stop.setShortcut("Shift+F5")
        self.act_stop.triggered.connect(self.preview.stop)

        self.act_about = QAction(t("act.about"), self)
        self.act_about.triggered.connect(self._about)

    def _build_menus(self):
        self.menu_file = self.menuBar().addMenu(t("menu.file"))
        self.menu_file.addAction(self.act_new)
        self.menu_file.addAction(self.act_open)
        self.menu_file.addSeparator()
        self.menu_file.addAction(self.act_settings)
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

        # 右: 属性 (占位)
        prop = QLabel("属性面板 (P2 实现)\n\n选中节点/素材后\n在此编辑属性")
        prop.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        prop.setWordWrap(True)
        prop.setStyleSheet("color:#666; padding:8px;")
        self._dock_prop = self._make_dock("dock.props", prop, Qt.RightDockWidgetArea)

        # 下: 输出 + 预览 (并排; 16:9 画面需要宽度)
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setMaximumBlockCount(2000)
        self._dock_out = self._make_dock("dock.output", self.output,
                                         Qt.BottomDockWidgetArea)
        self._dock_preview = self._make_dock("dock.preview", self.preview,
                                             Qt.BottomDockWidgetArea)

    def showEvent(self, event):
        """首次显示、布局就绪后分配 dock 尺寸 (build 阶段调用无效)。"""
        super().showEvent(event)
        if self._dock_sized:
            return
        self._dock_sized = True
        # 预览宽 / 输出窄
        self.resizeDocks([self._dock_out, self._dock_preview],
                         [300, 900], Qt.Horizontal)
        # 底部区域加高, 让 16:9 画面更舒展
        self.resizeDocks([self._dock_preview], [400], Qt.Vertical)

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
        self.tabs.addTab(self.flow, t("tab.logic"))
        self._tab_keys.append((2, "tab.logic"))
        # 样式: 可视化配色编辑 (P3)
        self.styles = StylesEditor()
        self.tabs.addTab(self.styles, t("tab.styles"))
        self._tab_keys.append((3, "tab.styles"))
        # 插件: 能力总览 + 装载配置 (P3)
        self.plugins_panel = PluginsPanel()
        self.plugins_panel.log.connect(self._log)
        self.tabs.addTab(self.plugins_panel, t("tab.plugins"))
        self._tab_keys.append((4, "tab.plugins"))
        # 编译: 校验/导出/打包 (P3)
        self.build = BuildPanel()
        self.build.log.connect(self._log)
        self.tabs.addTab(self.build, t("tab.build"))
        self._tab_keys.append((5, "tab.build"))
        self.setCentralWidget(self.tabs)

    def _new_project(self) -> None:
        """新建项目向导: 创建成功 -> 直接打开。"""
        dlg = NewProjectDialog(self)
        if dlg.exec() == NewProjectDialog.Accepted:
            path = dlg.result_path()
            self._log("新项目已创建: %s" % path)
            self.open_project(path)

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
        main = self.project.main_script()
        if main is not None:
            self.preview.set_script(os.path.join(self.project.root,
                                                 self.project.main))
            self.setWindowTitle("Galgame Maker 编辑器 — %s" % path)
            self._log("项目已打开: %s (%d 个脚本)" % (path, len(self.project.scripts)))
            self._log("预览脚本: %s" % self.project.main)
        else:
            self._log("警告: 目录中未找到主脚本 %s" % self.project.main)

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
        if text.endswith(".gal"):
            self._log("打开脚本编辑器: %s (P2 实现)" % text)

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
        self.preview.apply_lang()
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
                          "编辑器版本: 0.2 (P1 骨架)")

    def _todo(self, name: str):
        def _f(*_a):
            self._log("尚未实现: %s" % name)
        return _f

    def closeEvent(self, event):
        self.preview.stop()
        if self.preview._thread is not None:
            self.preview._thread.wait(5000)
        super().closeEvent(event)
