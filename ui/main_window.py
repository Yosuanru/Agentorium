from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import (
    QAction,
    QCloseEvent,
    QDesktopServices,
    QKeySequence,
    QShortcut,
)
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QProgressDialog,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.config import load_config
from core.paths import app_home, workspace_root
from core.project import NovelProject
from core.project_data import ChapterIdConflictError, ProjectDataStore
from core.session import session_ending
from core.update_download_service import VerifiedUpdate
from core.update_install_service import (
    UpdateInstallLaunchError,
    automatic_install_unavailable_reason,
    launch_verified_update_install,
)
from core.update_service import UpdateCheckResult, UpdateInfo
from core.version import AppVersion, load_current_version
from ui.ai_controller import AIController
from ui.ai_engine_controller import AIEngineController
from ui.ai_task_runner import DSHTask
from ui.ai_task_view_controller import AITaskViewController
from ui.ai_workflow_controller import AIWorkflowController
from ui.appearance_controller import AppearanceController
from ui.document_controller import DocumentController
from ui.export_controller import ExportController
from ui.editor import Editor
from ui.icons import IconTextButton
from ui.inspector import Inspector
from ui.left_panel import LeftPanel
from ui.memory_page import StoryMemoryPage
from ui.navigation import PrimaryNavigation
from ui.pages import DashboardPage, ExportPage, ReportsPage, SettingsPage
from ui.analysis_page import AnalysisPage
from ui.relation_page import RelationPage
from ui.swimlane_page import SwimlanePage
from ui.table_page import TablePage
from ui.sharded_runner import ShardedTask, shard_ranges
from ui.workspace_page import WorkspacePage
from ui.project_session import ProjectSession
from ui.project_lifecycle_controller import ProjectLifecycleController, ProjectSwitchCancelled
from ui.project_setup_dialog import ProjectSetupDialog
from ui.settings_controller import SettingsController
from ui.story_navigation_controller import StoryNavigationController
from ui.trash_dialog import TrashDialog
from ui.update_controller import UpdateController
from ui.update_download_controller import UpdateDownloadController
from ui.update_dialog import UpdateDialog, no_update_notice
from ui.view_refresh_controller import ViewRefreshController
from ui.window_state_controller import WindowStateController


def fallback_chapter_after_delete(
    chapters: list[Path],
    deleted_index: int,
    current_deleted: bool,
) -> Path | None:
    """Choose a neighboring chapter only when the open chapter was deleted."""
    if not current_deleted:
        return None
    remaining = chapters[:deleted_index] + chapters[deleted_index + 1 :]
    if not remaining:
        return None
    return remaining[min(deleted_index, len(remaining) - 1)]


class MainWindow(QMainWindow):
    ROUTES = ("dashboard", "writing", "analysis", "canon", "memory", "reports",
              "export", "settings")
    DELETE_CHAPTER_SHORTCUT = "Ctrl+Shift+Delete"
    ACTION_ICONS = {
        "new_chapter": "add",
        "delete_chapter": "delete",
        "open_project": "folder_open",
        "save": "save",
        "export": "ios_share",
        "focus": "center_focus_strong",
        "check": "fact_check",
        "memory": "psychology",
        "continue": "auto_awesome",
    }

    def __init__(self, parent=None, config: dict | None = None):
        super().__init__(parent)
        self.project_session = ProjectSession(self)
        self.ai_controller = AIController(self)
        self.config = dict(config) if config is not None else load_config()
        self._action_icon_buttons: dict[str, IconTextButton] = {}
        self.project_setup_dialog: ProjectSetupDialog | None = None
        self.update_dialog: UpdateDialog | None = None
        self.update_download_progress: QProgressDialog | None = None
        self._pending_update_install: VerifiedUpdate | None = None
        self.ai_engine_controller = AIEngineController(
            self.config,
            self.ai_controller.is_running,
            self,
        )

        self.setWindowTitle("Agentorium")
        self.setMinimumSize(1100, 720)
        self._build_actions()
        self._build_ui()
        self.document_controller = DocumentController(
            self.editor,
            self.project_session,
            self,
        )
        self.project_lifecycle_controller = ProjectLifecycleController(
            project_session=self.project_session,
            config=self.config,
            is_task_running=self.ai_controller.is_running,
            save_if_dirty=self._save_if_dirty,
            parent=self,
        )
        self.settings_controller = SettingsController(
            self.config,
            self.document_controller,
            self.ai_engine_controller,
            self,
        )
        self.update_controller = UpdateController(self.config, self)
        self.update_download_controller = UpdateDownloadController(self)
        self.export_controller = ExportController(self.project_session, self)
        self.export_page.set_export_controller(self.export_controller)
        self.view_refresh_controller = ViewRefreshController(
            self.project_session,
            self.editor,
            self.left_panel,
            self.inspector,
            self.dashboard_page,
            self.memory_page,
            self.reports_page,
            self.export_page,
            self,
        )
        self.window_state_controller = WindowStateController(
            primary_nav=self.primary_nav,
            page_stack=self.page_stack,
            pages={
                "dashboard": self.dashboard_page,
                "analysis": self.analysis_page,
                "memory": self.memory_page,
                "reports": self.reports_page,
                "export": self.export_page,
                "settings": self.settings_page,
            },
            writing_page=self.writing_page,
            action_bar=self.action_bar,
            app_header=self.app_header,
            menu_bar=self.menuBar(),
            status_bar=self.statusBar(),
            left_panel=self.left_panel,
            inspector=self.inspector,
            editor=self.editor,
            output_container=self.output_container,
            main_splitter=self.main_splitter,
            outer_splitter=self.outer_splitter,
            focus_action=self.actions["focus"],
            exit_focus_button=self.editor.exit_focus_button,
            parent=self,
        )
        self.story_navigation_controller = StoryNavigationController(
            project_session=self.project_session,
            editor=self.editor,
            left_panel=self.left_panel,
            show_route=lambda route: self._show_route(route),
            parent=self,
        )
        self.appearance_controller = AppearanceController(
            root=self,
            inspector=self.inspector,
            left_panel=self.left_panel,
            settings_page=self.settings_page,
            theme_button=self.theme_button,
            action_icon_buttons=self._action_icon_buttons,
            relation_page=self.relation_page,
            swimlane_page=self.swimlane_page,
            parent=self,
        )
        self.main_splitter.splitterMoved.connect(
            self.window_state_controller.remember_panel_sizes
        )
        self.appearance_controller.apply(self.config)
        self._build_menus()
        self._build_statusbar()
        self.ai_task_view_controller = AITaskViewController(
            ai_controller=self.ai_controller,
            ai_engine_controller=self.ai_engine_controller,
            actions=self.actions,
            task_progress=self.task_progress,
            cancel_button=self.cancel_task_button,
            ai_indicator=self.ai_indicator,
            status_message=self.status_message,
            memory_page=self.memory_page,
            output_panel=self.output_panel,
            window_state_controller=self.window_state_controller,
            parent=self,
        )
        self.ai_workflow_controller = AIWorkflowController(
            config=self.config,
            project_session=self.project_session,
            editor=self.editor,
            document_controller=self.document_controller,
            ai_controller=self.ai_controller,
            ai_engine_controller=self.ai_engine_controller,
            inspector=self.inspector,
            reports_page=self.reports_page,
            go_to_writing=lambda: self._show_route("writing"),
            save_if_dirty=self._save_if_dirty,
            left_panel=self.left_panel,
            parent=self,
        )
        self.ai_workflow_controller.output_requested.connect(
            self.ai_task_view_controller.append_output
        )
        # 所有功能的产出**也**回到同一个对话栏。
        # 作者的原话：「都是同一个那个侧栏的 AI，这样才是合理的」——
        # 不管点的是哪一项（检查设定 / 更新记忆 / 扩写 / 修复），结果都该落在同一个地方。
        self.ai_workflow_controller.output_requested.connect(
            lambda text: self.inspector.chat_panel.append("它", str(text))
        )
        self.ai_workflow_controller.status_requested.connect(
            self.ai_task_view_controller.set_status
        )
        self._connect_signals()
        self.project_session.project_changed.connect(self._on_project_changed)
        self._show_route("dashboard")

        self.exit_focus_shortcut = QShortcut(QKeySequence("Esc"), self)
        self.exit_focus_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
        self.exit_focus_shortcut.activated.connect(self._exit_focus_mode)
        self.f11_focus_shortcut = QShortcut(QKeySequence("F11"), self)
        self.f11_focus_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
        self.f11_focus_shortcut.activated.connect(self.toggle_focus_mode)

        self._refresh_auto_save_timer()
        QTimer.singleShot(80, self._restore_last_project)
        QTimer.singleShot(1500, self.update_controller.check_automatically)

    @property
    def project(self) -> NovelProject | None:
        return self.project_session.project

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------
    def _build_actions(self) -> None:
        self.actions: dict[str, QAction] = {}

        def action(key: str, text: str, slot, shortcut: str | None = None) -> QAction:
            item = QAction(text, self)
            item.triggered.connect(slot)
            if shortcut:
                item.setShortcut(QKeySequence(shortcut))
            self.actions[key] = item
            return item

        action("new_project", "新建项目…", self.new_project, "Ctrl+Shift+N")
        action("open_project", "打开项目…", self.open_project, "Ctrl+Shift+O")
        action("save", "保存", self.save_current_file, "Ctrl+S")
        action("export", "导出作品", lambda: self._show_route("export"), "Ctrl+Shift+E")
        action("trash", "回收站…", self.open_trash)
        self.actions["trash"].setEnabled(False)
        action("settings", "设置", lambda: self._show_route("settings"), "Ctrl+,")
        action("quit", "退出", self.close, "Ctrl+Q")
        action("new_chapter", "新建章节", self.new_chapter, "Ctrl+N")
        action(
            "delete_chapter",
            "移入回收站",
            self.delete_current_chapter,
            self.DELETE_CHAPTER_SHORTCUT,
        )
        self.actions["delete_chapter"].setEnabled(False)
        action("new_character", "新建角色", self.new_character, "Ctrl+Alt+C")
        action("new_world", "新建世界观条目", self.new_world_entry)
        action("new_power", "新建体系设定", self.new_power_entry)
        action("new_timeline", "新建时间线", self.new_timeline)
        action("undo", "撤销", lambda: self.editor.text_edit.undo(), "Ctrl+Z")
        action("redo", "重做", lambda: self.editor.text_edit.redo(), "Ctrl+Y")
        action("find", "查找与替换", lambda: self.editor.show_find(), "Ctrl+F")
        action("focus", "专注模式", self.toggle_focus_mode, "Ctrl+K")
        action("navigation", "显示/隐藏资料面板", self.toggle_navigation_panel, "Ctrl+Shift+L")
        action("inspector", "显示/隐藏故事雷达", self.toggle_inspector, "Ctrl+Shift+I")
        action("output", "显示/隐藏 AI 记录", self.toggle_output, "Ctrl+J")
        action("continue", "AI 扩写", self.expand_chapter, "Ctrl+Enter")
        action("check", "一致性检查", self.check_consistency, "Ctrl+Shift+C")
        action("memory", "更新记忆", self.update_memory, "Ctrl+Shift+M")
        action("check_updates", "检查更新…", self.check_for_updates)
        action("about", "关于 Agentorium", self.show_about)

    def _build_ui(self) -> None:
        central = QWidget(self)
        central.setObjectName("appRoot")
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.primary_nav = PrimaryNavigation()
        root.addWidget(self.primary_nav)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        root.addWidget(content, 1)

        self.app_header = QFrame()
        self.app_header.setObjectName("appHeader")
        header_layout = QHBoxLayout(self.app_header)
        header_layout.setContentsMargins(20, 13, 20, 13)
        header_layout.setSpacing(10)
        title_box = QVBoxLayout()
        title_box.setSpacing(1)
        self.page_title = QLabel("项目")
        self.page_title.setObjectName("pageTitle")
        self.page_subtitle = QLabel("项目概览与最近创作")
        self.page_subtitle.setObjectName("mutedLabel")
        title_box.addWidget(self.page_title)
        title_box.addWidget(self.page_subtitle)
        header_layout.addLayout(title_box, 1)
        # 原来这里挂着一个「● DSH 空闲中」的徽标：引擎都换成 claude 了，
        # 名字是错的，状态也没人看——作者说不要，就收起来。
        # 对象保留（控制器还在往里写状态），只是不显示。
        self.ai_indicator = QLabel("")
        self.ai_indicator.setObjectName("aiStatus")
        self.ai_indicator.hide()
        header_layout.addWidget(self.ai_indicator)
        self.theme_button = QPushButton()
        self.theme_button.setObjectName("ghostButton")
        self.theme_button.setProperty("material_icon", "dark_mode")
        self.theme_button.setProperty("material_icon_size", 17)
        self.theme_button.clicked.connect(self.toggle_theme)
        header_layout.addWidget(self.theme_button)
        settings_button = IconTextButton("settings", "设置", centered=True)
        settings_button.setObjectName("ghostButton")
        settings_button.setToolTip("打开设置")
        settings_button.clicked.connect(lambda: self._show_route("settings"))
        header_layout.addWidget(settings_button)
        content_layout.addWidget(self.app_header)

        self.action_bar = QFrame()
        self.action_bar.setObjectName("actionBar")
        action_layout = QHBoxLayout(self.action_bar)
        action_layout.setContentsMargins(14, 8, 14, 8)
        action_layout.setSpacing(7)
        action_layout.addWidget(self._action_button("new_chapter", "新章节"))
        action_layout.addWidget(self._action_button("open_project", "打开项目"))
        action_layout.addWidget(self._action_button("save", "保存"))
        action_layout.addWidget(self._action_button("export", "导出"))
        action_layout.addStretch(1)
        # 刷新：作者的原话「我需要的不是先把应用叉掉、再打开」。拆完书、
        # 同步完、或在别处改了文件，点一下就把最新的读进来。
        refresh_button = IconTextButton("sync", "刷新", centered=True)
        refresh_button.setObjectName("ghostButton")
        refresh_button.setToolTip(
            "重新读一遍项目文件。\n"
            "拆完书、补完同步、或在别处改了文件之后点一下——不用关掉应用再打开。")
        refresh_button.clicked.connect(self.refresh_everything)
        action_layout.addWidget(refresh_button)

        focus_button = self._action_button("focus", "专注模式")
        focus_button.setObjectName("ghostButton")
        focus_button.style().unpolish(focus_button)
        focus_button.style().polish(focus_button)
        action_layout.addWidget(focus_button)

        # 批注开关：默认关着（正文就是干净成稿），点开才把伏笔和待改落在字上。
        self.anno_button = QPushButton("批注")
        self.anno_button.setObjectName("ghostButton")
        self.anno_button.setCheckable(True)
        self.anno_button.setToolTip("打开后伏笔与待改会标在正文上；关掉就是干净成稿")
        self.anno_button.toggled.connect(self._toggle_annotations)
        action_layout.addWidget(self.anno_button)

        check_button = self._action_button("check", "检查设定")
        check_button.setObjectName("secondaryButton")
        action_layout.addWidget(check_button)
        memory_button = self._action_button("memory", "更新记忆")
        memory_button.setObjectName("secondaryButton")
        action_layout.addWidget(memory_button)
        continue_button = self._action_button("continue", "AI 扩写")
        continue_button.setObjectName("accentButton")
        action_layout.addWidget(continue_button)
        content_layout.addWidget(self.action_bar)

        self.page_stack = QStackedWidget()
        self.page_stack.setObjectName("pageStack")
        # 右侧栏在这里先建出来，好让它和 page_stack 并排、不属于任何一页。
        self.inspector = Inspector()
        self.dashboard_page = DashboardPage()
        self.writing_page = self._build_writing_page()
        self.memory_page = StoryMemoryPage()
        self.reports_page = ReportsPage()
        self.export_page = ExportPage()
        self.table_page = TablePage()
        self.relation_page = RelationPage()
        self.swimlane_page = SwimlanePage()
        self.workspace_page = WorkspacePage()
        self.analysis_page = AnalysisPage(self.table_page, self.relation_page,
                                          self.workspace_page, self.swimlane_page)
        self.settings_page = SettingsPage(self.config)
        for page in (
            self.dashboard_page,
            self.writing_page,
            self.analysis_page,
            self.memory_page,
            self.reports_page,
            self.export_page,
            self.settings_page,
        ):
            self.page_stack.addWidget(page)

        # 常驻右栏：和 page_stack 并排，而不是塞在某一张页里。
        # 原来它挂在「写作台」页上，于是仪表盘／故事资料／设置这些页
        # 整个看不到它——「打开面板就能跟它说话」这条也就落不了地。
        self.workbench_row = QSplitter(Qt.Orientation.Horizontal)
        self.workbench_row.setObjectName("workbenchRow")
        self.workbench_row.setHandleWidth(5)
        self.workbench_row.setChildrenCollapsible(False)
        self.workbench_row.addWidget(self.page_stack)
        self.workbench_row.addWidget(self.inspector)
        # ⚠️ 必须显式给小值。QSplitter 的默认下限是各页的 minimumSizeHint，
        # 而检查报告页那种宽内容的页会报到 769——比整个容器还大。
        # 装不下时 QSplitter 会失控：把左页撑到 769，把右边的对话栏顶到窗口外
        # （作者的原话："点一下就迅速扩大，把旁边页面挤到屏幕外面去"）。
        self.page_stack.setMinimumWidth(320)
        self.inspector.setMinimumWidth(220)
        self.workbench_row.setStretchFactor(0, 1)
        self.workbench_row.setStretchFactor(1, 0)
        self.workbench_row.setSizes([1180, 340])
        self.workbench_row.setCollapsible(0, False)
        self.workbench_row.setCollapsible(1, False)
        content_layout.addWidget(self.workbench_row, 1)

    def _build_writing_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("pageSurface")
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(0)

        self.outer_splitter = QSplitter(Qt.Orientation.Vertical)
        self.outer_splitter.setObjectName("outerSplitter")
        self.outer_splitter.setHandleWidth(5)
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.setObjectName("mainSplitter")
        self.main_splitter.setHandleWidth(5)
        self.main_splitter.setChildrenCollapsible(False)
        self.left_panel = LeftPanel()
        self.editor = Editor()
        self.main_splitter.addWidget(self.left_panel)
        self.main_splitter.addWidget(self.editor)
        self.main_splitter.setStretchFactor(0, 0)
        self.main_splitter.setStretchFactor(1, 1)
        self.main_splitter.setSizes([270, 1080])
        for index in range(2):
            self.main_splitter.setCollapsible(index, False)
        self.output_container = QFrame()
        self.output_container.setObjectName("outputContainer")
        output_layout = QVBoxLayout(self.output_container)
        output_layout.setContentsMargins(14, 8, 14, 10)
        output_layout.setSpacing(6)
        output_header = QHBoxLayout()
        output_title = QLabel("AI 工作记录")
        output_title.setObjectName("panelTitle")
        copy_button = QPushButton("复制")
        copy_button.setObjectName("ghostButton")
        copy_button.clicked.connect(lambda: self.ai_task_view_controller.copy_output())
        clear_button = QPushButton("清空")
        clear_button.setObjectName("ghostButton")
        clear_button.clicked.connect(lambda: self.ai_task_view_controller.clear_output())
        close_button = QPushButton("收起")
        close_button.setObjectName("ghostButton")
        close_button.clicked.connect(self.toggle_output)
        output_header.addWidget(output_title)
        output_header.addStretch(1)
        output_header.addWidget(copy_button)
        output_header.addWidget(clear_button)
        output_header.addWidget(close_button)
        output_layout.addLayout(output_header)
        self.output_panel = QPlainTextEdit()
        self.output_panel.setObjectName("outputPanel")
        self.output_panel.setReadOnly(True)
        self.output_panel.setPlaceholderText("AI 扩写、设定检查和记忆更新的过程会记录在这里。")
        output_layout.addWidget(self.output_panel, 1)
        self.output_container.hide()

        self.outer_splitter.addWidget(self.main_splitter)
        self.outer_splitter.addWidget(self.output_container)
        self.outer_splitter.setStretchFactor(0, 1)
        self.outer_splitter.setStretchFactor(1, 0)
        self.outer_splitter.setSizes([720, 170])
        page_layout.addWidget(self.outer_splitter, 1)
        return page

    # 光有名字不够——作者的反馈是"这些功能我都不知道咋用"。
    # 每个按钮鼠标停上去都说清楚：干什么、要不要花钱。
    ACTION_HINTS = {
        "new_chapter": "在最后加一章空白的，这一章你自己写",
        "open_project": "打开一个已有的小说项目目录",
        "save": "把当前这一章存盘（Ctrl+S）",
        "export": "把整本书导出成文件——Markdown 或纯文本",
        "focus": "专注模式：只留正文，侧栏和工具条全收起来",
        "check": "让 AI 拿这一章跟设定比一遍，找前后矛盾（会花钱）",
        "memory": "让 AI 读完这一章，更新摘要和伏笔记录（会花钱）",
        "continue": "让 AI 接着往下写（会花钱，按字数计）",
    }

    def _action_button(self, key: str, text: str) -> IconTextButton:
        icon_name = self.ACTION_ICONS.get(key)
        button = IconTextButton(icon_name, text, centered=True) if icon_name else IconTextButton("circle", text, centered=True)
        if not icon_name:
            button.findChild(QLabel, "buttonIcon").hide()
        action = self.actions[key]
        button.setToolTip(self.ACTION_HINTS.get(key) or action.text())
        button.setEnabled(action.isEnabled())
        button.clicked.connect(action.trigger)
        action.changed.connect(lambda item=action, target=button: self._sync_action_button(item, target))
        self._action_icon_buttons[key] = button
        return button

    @staticmethod
    def _sync_action_button(action: QAction, button: IconTextButton) -> None:
        button.setEnabled(action.isEnabled())
        button.setToolTip(action.text())
        button.set_label(action.text())

    def _build_menus(self) -> None:
        file_menu = self.menuBar().addMenu("文件")
        file_menu.addAction(self.actions["new_project"])
        file_menu.addAction(self.actions["open_project"])
        self.recent_menu = QMenu("最近项目", self)
        file_menu.addMenu(self.recent_menu)
        self._refresh_recent_menu()
        file_menu.addSeparator()
        file_menu.addAction(self.actions["save"])
        file_menu.addAction(self.actions["export"])
        file_menu.addAction(self.actions["trash"])
        file_menu.addSeparator()
        file_menu.addAction(self.actions["settings"])
        file_menu.addAction(self.actions["quit"])

        edit_menu = self.menuBar().addMenu("编辑")
        edit_menu.addAction(self.actions["undo"])
        edit_menu.addAction(self.actions["redo"])
        edit_menu.addSeparator()
        edit_menu.addAction(self.actions["find"])

        create_menu = self.menuBar().addMenu("创作")
        create_menu.addAction(self.actions["new_chapter"])
        create_menu.addAction(self.actions["delete_chapter"])
        create_menu.addAction(self.actions["new_character"])
        create_menu.addAction(self.actions["new_world"])
        create_menu.addAction(self.actions["new_power"])
        create_menu.addAction(self.actions["new_timeline"])
        create_menu.addSeparator()
        create_menu.addAction(self.actions["continue"])
        create_menu.addAction(self.actions["check"])
        create_menu.addAction(self.actions["memory"])

        view_menu = self.menuBar().addMenu("视图")
        view_menu.addAction(self.actions["focus"])
        view_menu.addAction(self.actions["navigation"])
        view_menu.addAction(self.actions["inspector"])
        view_menu.addAction(self.actions["output"])

        help_menu = self.menuBar().addMenu("帮助")
        help_menu.addAction(self.actions["check_updates"])
        help_menu.addSeparator()
        help_menu.addAction(self.actions["about"])

    def _build_statusbar(self) -> None:
        self.status_message = QLabel("打开或创建一个项目，开始今天的写作")
        self.status_message.setObjectName("mutedLabel")
        self.task_progress = QProgressBar()
        self.task_progress.setRange(0, 0)
        self.task_progress.setFixedSize(110, 8)
        self.task_progress.hide()
        self.cancel_task_button = QPushButton("取消 AI")
        self.cancel_task_button.setObjectName("ghostButton")
        self.cancel_task_button.setAutoDefault(False)
        self.cancel_task_button.clicked.connect(self.cancel_ai_task)
        self.cancel_task_button.hide()
        self.auto_save_status = QLabel("自动保存已开启")
        self.auto_save_status.setObjectName("mutedLabel")
        self.statusBar().addWidget(self.status_message, 1)
        self.statusBar().addPermanentWidget(self.task_progress)
        self.statusBar().addPermanentWidget(self.cancel_task_button)
        self.statusBar().addPermanentWidget(self.auto_save_status)

    def _connect_signals(self) -> None:
        self.inspector.chat_send_requested.connect(self._on_chat_send)
        self.inspector.chat_apply_requested.connect(self._on_chat_apply)
        self.workspace_page.ingest_requested.connect(self._on_ingest_requested)
        self.workspace_page.cancel_requested.connect(self._on_ingest_cancel)
        self.primary_nav.route_requested.connect(self._show_route)
        self.primary_nav.new_project_requested.connect(self.new_project)
        self.primary_nav.trash_requested.connect(self.open_trash)
        self.dashboard_page.new_project_requested.connect(self.new_project)
        self.dashboard_page.open_project_requested.connect(self.open_project)
        self.dashboard_page.import_requested.connect(self._import_markdown_chapters)
        self.dashboard_page.continue_requested.connect(lambda: self._show_route("writing"))
        self.dashboard_page.recent_chapter_requested.connect(
            self._open_memory_chapter
        )
        self.dashboard_page.new_chapter_requested.connect(self.new_chapter)
        self.dashboard_page.outline_requested.connect(self._open_dashboard_main_arc)
        self.dashboard_page.memory_requested.connect(lambda: self._show_route("memory"))
        self.dashboard_page.canon_requested.connect(lambda: self._show_route("canon"))
        self.left_panel.file_selected.connect(self._on_file_selected)
        self.left_panel.new_chapter_requested.connect(self.new_chapter)
        self.left_panel.new_canon_requested.connect(self.new_canon_entry)
        self.left_panel.system_importance_requested.connect(self.set_system_importance)
        self.left_panel.delete_chapter_requested.connect(self.delete_chapter_by_path)
        self.left_panel.delete_character_requested.connect(self.delete_character_by_path)
        self.left_panel.delete_canon_requested.connect(self.delete_canon_by_path)
        self.left_panel.new_timeline_requested.connect(self.new_timeline)
        self.left_panel.toggle_requested.connect(self.toggle_navigation_panel)
        # 右边那个 ✕ 原来没接上——点了没反应。接起来：收起后正文能占满整宽。
        self.inspector.toggle_requested.connect(self.toggle_inspector)
        self.memory_page.sync_requested.connect(self.update_memory)
        self.memory_page.sync_all_requested.connect(self.update_memory_batch)
        self.memory_page.chapter_requested.connect(self._open_memory_chapter)
        # 框架图上点一段 → 跳到那一章。走的是跟"故事记忆"同一个入口。
        self.swimlane_page.chapter_requested.connect(self._open_memory_chapter)
        self.memory_page.foreshadowing_changed.connect(self.project_session.notify_data_changed)
        self.reports_page.run_requested.connect(
            self.ai_workflow_controller.check_from_reports
        )
        self.reports_page.jump_requested.connect(self.ai_workflow_controller.jump_to_issue)
        self.reports_page.repair_requested.connect(self.ai_workflow_controller.repair_issue)
        self.export_page.export_requested.connect(self.export_manuscript)
        self.settings_page.save_requested.connect(self._apply_settings)
        self.settings_page.test_requested.connect(self._test_dsh)
        self.settings_controller.config_changed.connect(self._on_settings_changed)
        self.settings_controller.connection_started.connect(self._on_dsh_test_started)
        self.settings_controller.connection_succeeded.connect(self._on_dsh_test_succeeded)
        self.settings_controller.connection_failed.connect(self._on_dsh_test_failed)
        self.settings_controller.connection_finished.connect(self._on_dsh_test_finished)
        self.update_controller.started.connect(self._on_update_check_started)
        self.update_controller.result_ready.connect(self._on_update_check_result)
        self.update_controller.failed.connect(self._on_update_check_failed)
        self.update_controller.finished.connect(self._on_update_check_finished)
        self.update_controller.config_changed.connect(self._on_update_config_changed)
        self.update_download_controller.started.connect(self._on_update_download_started)
        self.update_download_controller.progress_changed.connect(
            self._on_update_download_progress
        )
        self.update_download_controller.succeeded.connect(
            self._on_update_download_succeeded
        )
        self.update_download_controller.failed.connect(self._on_update_download_failed)
        self.update_download_controller.cancelled.connect(
            self._on_update_download_cancelled
        )
        self.update_download_controller.finished.connect(
            self._on_update_download_finished
        )
        self.editor.dirty_changed.connect(self._on_dirty_changed)
        self.ai_controller.started.connect(self._on_ai_started)
        self.ai_controller.finished.connect(self._on_ai_finished)
        self.document_controller.auto_saved.connect(self._on_auto_saved)
        self.document_controller.save_conflict_detected.connect(
            self._on_save_conflict_detected
        )
        self.editor.exit_focus_button.clicked.connect(self._exit_focus_mode)

    def _open_dashboard_main_arc(self) -> None:
        project = self.project
        if project is None or not self._show_route("canon"):
            return
        self.left_panel.select_path(project.outline_dir / "main_arc.md")

    # ------------------------------------------------------------------
    # Routing and shared shell
    # ------------------------------------------------------------------
    def _show_route(self, route: str) -> bool:
        if route not in self.ROUTES:
            route = "dashboard"
        # 表格页不需要项目也能看——拆文库那几张表（线索轨迹、节奏曲线）
        # 跟当前项目无关，不该被"先打开项目"挡住。
        if route not in {"dashboard", "settings", "analysis"} and not self._require_project():
            self.primary_nav.set_active(self.window_state_controller.current_route)
            return False
        if (
            route != self.window_state_controller.current_route
            and self.editor.is_dirty()
            and not self._save_if_dirty()
        ):
            self.primary_nav.set_active(self.window_state_controller.current_route)
            return False

        if route != "settings":
            self.view_refresh_controller.refresh_route(route)
        else:
            self.settings_page.set_config(self.config)
        self.window_state_controller.activate_route(route)
        if route == "analysis":
            self.analysis_page.refresh(self.project)
        if route == "canon":
            self.story_navigation_controller.select_default_canon()

        self._update_page_header(route)
        self._update_window_title()
        return True

    def _update_page_header(self, route: str) -> None:
        labels = {
            "dashboard": ("项目", "项目概览与最近创作"),
            "writing": ("写作台", "章节正文、故事雷达与 AI 辅助"),
            "analysis": ("分析", "表格 · 关系图 · 工作区 —— 看数据，不是写正文"),
            "workspace": ("工作区", "整个仓库 —— 拆文库、技法样本、参考书、脚本"),
            "canon": ("故事资料", "集中维护会被正文和 AI 引用的故事事实"),
            "memory": ("故事记忆", "章节摘要、人物状态与长期线索"),
            "reports": ("检查报告", "集中查看设定一致性风险"),
            "export": ("导出", "确认章节范围并生成本地文件"),
            "settings": ("设置", "写作体验、AI 引擎与外观"),
        }
        title, subtitle = labels[route]
        self.page_title.setText(title)
        self.page_subtitle.setText(subtitle if not self.project else f"{self.project.name} · {subtitle}")
        self.theme_button.setText("深色" if self.config.get("theme") == "light" else "浅色")

    # ------------------------------------------------------------------
    # Projects and documents
    # ------------------------------------------------------------------
    def open_project(self) -> None:
        start = self.project.root if self.project else Path.cwd() / "projects"
        path = QFileDialog.getExistingDirectory(self, "选择小说项目目录", str(start))
        if path:
            self._load_project(Path(path))

    def _load_project(self, path: Path, quiet: bool = False) -> bool:
        try:
            project = self.project_lifecycle_controller.load(path)
        except ProjectSwitchCancelled:
            return False
        except Exception as exc:  # noqa: BLE001
            if not quiet:
                QMessageBox.critical(self, "加载失败", str(exc))
            return False

        chapters = project.list_chapters()
        if chapters:
            self.left_panel.select_path(chapters[0])
            # 有章节就直接进写作台：右栏的「对话」在那一页上，
            # 别再让人打开项目后自己多点一步去找它。
            self._show_route("writing")
        else:
            self._show_route("dashboard")
        return True

    def _on_project_changed(self, project: NovelProject | None) -> None:
        """Update shell state after the view refresh controller switches projects."""
        self.primary_nav.set_project(project.name if project else None)
        if hasattr(self, "ai_task_view_controller"):
            self.ai_task_view_controller.clear_output()
        else:
            self.output_panel.clear()
        self.status_message.setText(
            f"已打开 · {project.name}" if project else "尚未打开项目"
        )
        self._refresh_delete_action()
        self._refresh_trash_access()
        self._update_page_header(self.window_state_controller.current_route)
        self.refresh_synced_labels()
        # 对话记录跟着项目走：打开哪本就读回哪本的，不是每次都从空白开始。
        # （作者原话：「不然每次重新写章，它会割裂的吧？就像你一样有个长期固化的记忆。」）
        self.inspector.chat_panel.attach_project(project.root if project else None)

    def _on_ai_started(self, _token) -> None:
        self.reports_page.set_check_running(True)
        self._refresh_delete_action()
        self.primary_nav.set_trash_enabled(False)
        self.actions["trash"].setEnabled(False)

    def _on_ai_finished(self, _token) -> None:
        self.reports_page.set_check_running(False)
        self._refresh_delete_action()
        self._refresh_trash_access()

    def _refresh_trash_access(self) -> None:
        enabled = self.project is not None and not self.ai_controller.is_running()
        self.primary_nav.set_trash_enabled(enabled)
        self.actions["trash"].setEnabled(enabled)

    def new_project(self) -> None:
        parent_dir = QFileDialog.getExistingDirectory(self, "选择新项目存放目录")
        if not parent_dir:
            return
        name, ok = QInputDialog.getText(self, "创建新的故事", "作品名称：", text="我的小说")
        if not ok or not name.strip():
            return
        try:
            project = self.project_lifecycle_controller.create_and_load(
                Path(parent_dir), name.strip()
            )
        except FileExistsError as exc:
            QMessageBox.warning(self, "项目已存在", f"目标目录已经存在，请换一个作品名称：\n{exc}")
            return
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "创建失败", str(exc))
            return
        if project is not None:
            self._show_route("canon")
            self._show_project_setup(project)

    def save_current_file(self, notify: bool = True) -> bool:
        if not self.editor.current_path():
            if notify:
                QMessageBox.information(self, "保存", "请先打开一份可编辑的故事资料。")
            return False
        if not self.document_controller.save():
            if self.document_controller.save_conflict_path is not None:
                return self._resolve_save_conflict()
            if notify:
                QMessageBox.warning(self, "保存失败", "文件未能保存，请检查写入权限。")
            return False
        if notify:
            self.status_message.setText("已保存")
        self._update_window_title()
        return True

    def _resolve_save_conflict(self) -> bool:
        path = self.document_controller.save_conflict_path
        if path is None:
            return False
        choice = QMessageBox(self)
        choice.setIcon(QMessageBox.Icon.Warning)
        choice.setWindowTitle("文件已被外部修改")
        choice.setText(f"当前文件在编辑期间发生了外部修改：\n{path.name}")
        choice.setInformativeText(
            "重新加载会放弃当前未保存内容；覆盖保存会用编辑器中的内容替换磁盘文件。"
        )
        reload_button = choice.addButton(
            "重新加载外部版本", QMessageBox.ButtonRole.DestructiveRole
        )
        overwrite_button = choice.addButton(
            "覆盖外部修改", QMessageBox.ButtonRole.AcceptRole
        )
        choice.addButton("取消", QMessageBox.ButtonRole.RejectRole)
        choice.exec()
        if choice.clickedButton() is reload_button:
            return self.document_controller.reload_current_file()
        if choice.clickedButton() is overwrite_button:
            return self.document_controller.save(force=True)
        return False

    def new_chapter(self) -> None:
        if not self._require_project():
            return
        assert self.project is not None
        default_id = self.document_controller.next_chapter_id()
        title, ok = QInputDialog.getText(self, "新建章节", "章节标题：", text="新章节")
        if not ok or not title.strip():
            return
        chapter_id, ok = QInputDialog.getText(self, "新建章节", "文件标识（建议保留默认值）：", text=default_id)
        if not ok:
            return
        chapter_id = chapter_id.strip()
        if not chapter_id:
            return
        try:
            path = self.document_controller.create_chapter(title, chapter_id)
        except ChapterIdConflictError as exc:
            answer = QMessageBox.question(
                self,
                "章节 ID 已存在",
                f"章节 ID“{exc.chapter_id}”已经存在。\n\n是否改用可用 ID“{exc.suggested_id}”？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            try:
                path = self.document_controller.create_chapter(title, exc.suggested_id)
            except (OSError, ValueError, FileExistsError) as retry_exc:
                QMessageBox.warning(self, "创建失败", str(retry_exc))
                return
        except FileExistsError:
            QMessageBox.warning(self, "章节已存在", f"请换一个文件标识：{chapter_id}")
            return
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "创建失败", str(exc))
            return
        self._show_route("writing")
        self.left_panel.select_path(path)
        self.status_message.setText(f"已创建 · {title.strip()}")

    def open_trash(self) -> None:
        project = self.project
        if project is None:
            QMessageBox.information(self, "尚未打开项目", "请先打开或新建一个小说项目。")
            return
        if self.ai_controller.is_running():
            QMessageBox.information(self, "AI 正在工作", "当前 AI 任务完成后才能管理回收站。")
            return
        dialog = TrashDialog(self.project_session.require_data_store(), self)
        dialog.changed.connect(self.project_session.notify_data_changed)
        dialog.exec()

    def delete_current_chapter(self) -> None:
        category = self.editor.current_category()
        if category == "角色":
            current = self.editor.current_path()
            self._delete_character(Path(current) if current else None)
            return
        if category in {"世界观", "体系设定", "时间线"}:
            current = self.editor.current_path()
            self._delete_canon(category, Path(current) if current else None)
            return
        chapter_id = self.editor.current_chapter_id()
        if chapter_id is None:
            QMessageBox.information(self, "需要章节", "请先打开要删除的章节。")
            return
        self._delete_chapter(chapter_id)

    def delete_chapter_by_path(self, path_str: str) -> None:
        project = self.project
        if project is None:
            return
        path = Path(path_str)
        try:
            if path.resolve().parent != project.chapters_dir.resolve():
                raise ValueError
        except (OSError, ValueError):
            QMessageBox.warning(self, "删除失败", "只能删除当前项目中的章节文件。")
            return
        self._delete_chapter(path.stem)

    def _delete_chapter(self, chapter_id: str) -> None:
        project = self.project
        if project is None:
            return
        if self.ai_controller.is_running():
            QMessageBox.information(self, "AI 正在工作", "当前 AI 任务完成后才能删除章节。")
            return

        target = project.chapters_dir / f"{chapter_id}.md"
        if not target.is_file():
            QMessageBox.warning(self, "删除失败", "目标章节不存在，项目资料可能已经发生变化。")
            self.project_session.notify_data_changed()
            return

        chapters = self.project_session.require_data_store().list_chapters()
        try:
            deleted_index = next(
                index
                for index, path in enumerate(chapters)
                if path.resolve() == target.resolve()
            )
        except StopIteration:
            QMessageBox.warning(self, "删除失败", "目标章节不在当前项目章节目录内。")
            return

        current_path = self.editor.current_path()
        is_current = bool(current_path and Path(current_path).resolve() == target.resolve())
        chapter_title = project.load_chapter(chapter_id).title
        answer = QMessageBox.question(
            self,
            "移入回收站",
            f"确定将《{chapter_title}》移入回收站吗？\n\n"
            "章节文件和对应摘要将移入回收站，之后仍可恢复。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        discard_current_changes = False
        if is_current and self.editor.is_dirty():
            choice = QMessageBox(self)
            choice.setIcon(QMessageBox.Icon.Warning)
            choice.setWindowTitle("章节尚未保存")
            choice.setText("当前章节有未保存修改，删除前如何处理？")
            save_button = choice.addButton("保存后删除", QMessageBox.ButtonRole.AcceptRole)
            discard_button = choice.addButton(
                "放弃修改并删除", QMessageBox.ButtonRole.DestructiveRole
            )
            choice.addButton("取消", QMessageBox.ButtonRole.RejectRole)
            choice.exec()
            if choice.clickedButton() is save_button:
                if not self.document_controller.save():
                    QMessageBox.warning(self, "删除失败", "当前章节保存失败，已取消删除。")
                    return
            elif choice.clickedButton() is discard_button:
                discard_current_changes = True
            else:
                return

        fallback = fallback_chapter_after_delete(chapters, deleted_index, is_current)
        try:
            self.document_controller.delete_chapter(
                chapter_id,
                discard_current_changes=discard_current_changes,
            )
        except (OSError, RuntimeError, ValueError) as exc:
            QMessageBox.critical(self, "删除失败", str(exc))
            return

        if fallback is not None:
            self._show_route("writing")
            self.left_panel.select_path(fallback)
        self.status_message.setText(f"已移入回收站 · {chapter_title}")
        self._refresh_delete_action()

    def delete_character_by_path(self, path_str: str) -> None:
        project = self.project
        if project is None:
            return
        path = Path(path_str)
        characters_dir = project.canon_dir / "characters"
        try:
            if path.resolve().parent != characters_dir.resolve():
                raise ValueError
        except (OSError, ValueError):
            QMessageBox.warning(self, "删除失败", "只能删除当前项目中的角色卡文件。")
            return
        self._delete_character(path)

    def _delete_character(self, path_or_id: Path | str | None) -> None:
        project = self.project
        if project is None or path_or_id is None:
            return
        target = (
            Path(path_or_id)
            if isinstance(path_or_id, Path)
            else project.canon_dir / "characters" / f"{str(path_or_id).strip()}.md"
        )
        characters_dir = project.canon_dir / "characters"
        try:
            if target.resolve().parent != characters_dir.resolve():
                raise ValueError
        except (OSError, ValueError):
            QMessageBox.warning(self, "删除失败", "只能删除当前项目中的角色卡文件。")
            return
        if not target.is_file():
            QMessageBox.warning(self, "删除失败", "目标角色卡不存在，项目资料可能已经发生变化。")
            self.project_session.notify_data_changed()
            return
        if self.ai_controller.is_running():
            QMessageBox.information(self, "AI 正在工作", "当前 AI 任务完成后才能删除角色卡。")
            return

        store = self.project_session.require_data_store()
        character_title = store.chapter_display_name(target)
        answer = QMessageBox.question(
            self,
            "移入回收站",
            f"确定将角色卡“{character_title}”移入回收站吗？\n\n"
            "角色卡文件之后仍可恢复，故事记忆中的角色追踪数据会保留。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        current_path = self.editor.current_path()
        is_current = bool(current_path and Path(current_path).resolve() == target.resolve())
        discard_current_changes = False
        if is_current and self.editor.is_dirty():
            choice = QMessageBox(self)
            choice.setIcon(QMessageBox.Icon.Warning)
            choice.setWindowTitle("角色卡尚未保存")
            choice.setText("当前角色卡有未保存修改，删除前如何处理？")
            save_button = choice.addButton("保存后删除", QMessageBox.ButtonRole.AcceptRole)
            discard_button = choice.addButton(
                "放弃修改并删除", QMessageBox.ButtonRole.DestructiveRole
            )
            choice.addButton("取消", QMessageBox.ButtonRole.RejectRole)
            choice.exec()
            if choice.clickedButton() is save_button:
                if not self.document_controller.save():
                    QMessageBox.warning(self, "删除失败", "当前角色卡保存失败，已取消删除。")
                    return
            elif choice.clickedButton() is discard_button:
                discard_current_changes = True
            else:
                return

        try:
            self.document_controller.delete_character(
                target.stem,
                discard_current_changes=discard_current_changes,
            )
        except (OSError, RuntimeError, ValueError) as exc:
            QMessageBox.critical(self, "删除失败", str(exc))
            return
        self.status_message.setText(f"已移入角色卡回收站 · {character_title}")
        self._show_route("canon")
        self._refresh_delete_action()

    def delete_canon_by_path(self, category: str, path_str: str) -> None:
        kind_map = {
            "世界观": "world",
            "world": "world",
            "体系设定": "power",
            "power": "power",
            "时间线": "timeline",
            "timeline": "timeline",
        }
        kind = kind_map.get(str(category or ""))
        if kind is None:
            return
        display = {"world": "世界观", "power": "体系设定", "timeline": "时间线"}[kind]
        self._delete_canon(display, Path(path_str))

    def _delete_canon(self, category: str, path: Path | None) -> None:
        project = self.project
        if project is None or path is None:
            return
        kind_map = {"世界观": "world", "体系设定": "power", "时间线": "timeline"}
        kind = kind_map.get(str(category or ""))
        if kind is None:
            return
        target = Path(path)
        if not target.is_absolute():
            target = project.root / target
        expected_parent = {
            "world": project.canon_dir / "world",
            "power": project.canon_dir / "power",
            "timeline": project.canon_dir,
        }[kind]
        try:
            resolved = target.resolve()
            if resolved.parent != expected_parent.resolve():
                raise ValueError
            if kind == "timeline" and resolved.name != "timeline.md":
                raise ValueError
            if target.suffix.casefold() != ".md":
                raise ValueError
        except (OSError, ValueError):
            QMessageBox.warning(self, "删除失败", "只能删除当前项目中的故事资料文件。")
            return
        store = self.project_session.require_data_store()
        if kind == "power" and store.is_core_power_path(target):
            QMessageBox.information(
                self,
                "核心规则不可删除",
                "核心规则是项目常驻资料，如需修改请直接编辑该文件。",
            )
            return
        if not target.is_file():
            QMessageBox.warning(self, "删除失败", "目标故事资料不存在，项目资料可能已经发生变化。")
            self.project_session.notify_data_changed()
            return
        if self.ai_controller.is_running():
            QMessageBox.information(self, "AI 正在工作", "当前 AI 任务完成后才能删除故事资料。")
            return

        title = store.chapter_display_name(target)
        if kind == "timeline":
            detail = "整份时间线文档之后仍可在回收站恢复；永久删除后可重新创建空白时间线。"
        elif kind == "power":
            detail = "体系的 AI 加载策略会一并保存，故事正文和故事记忆不会被修改。"
        else:
            detail = "该条目之后仍可在回收站恢复。"
        answer = QMessageBox.question(
            self,
            "移入回收站",
            f"确定将{category}“{title}”移入回收站吗？\n\n{detail}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        current_path = self.editor.current_path()
        is_current = bool(current_path and Path(current_path).resolve() == target.resolve())
        discard_current_changes = False
        if is_current and self.editor.is_dirty():
            choice = QMessageBox(self)
            choice.setIcon(QMessageBox.Icon.Warning)
            choice.setWindowTitle("故事资料尚未保存")
            choice.setText(f"当前{category}有未保存修改，删除前如何处理？")
            save_button = choice.addButton("保存后删除", QMessageBox.ButtonRole.AcceptRole)
            discard_button = choice.addButton(
                "放弃修改并删除", QMessageBox.ButtonRole.DestructiveRole
            )
            choice.addButton("取消", QMessageBox.ButtonRole.RejectRole)
            choice.exec()
            if choice.clickedButton() is save_button:
                if not self.document_controller.save():
                    QMessageBox.warning(self, "删除失败", "当前故事资料保存失败，已取消删除。")
                    return
            elif choice.clickedButton() is discard_button:
                discard_current_changes = True
            else:
                return

        try:
            self.document_controller.delete_canon_entry(
                kind,
                target,
                discard_current_changes=discard_current_changes,
            )
        except (OSError, RuntimeError, ValueError) as exc:
            QMessageBox.critical(self, "删除失败", str(exc))
            return
        self.status_message.setText(f"已移入回收站 · {title}")
        self._show_route("canon")
        self._refresh_delete_action()

    def new_character(self) -> None:
        self.new_canon_entry("character")

    def new_world_entry(self) -> None:
        self.new_canon_entry("world")

    def new_power_entry(self) -> None:
        self.new_canon_entry("power")

    def new_timeline(self) -> None:
        if not self._require_project():
            return
        try:
            path = self.document_controller.create_timeline()
        except FileExistsError:
            QMessageBox.information(self, "时间线已存在", "当前项目已经有一份时间线。")
            return
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "创建失败", str(exc))
            return
        self._show_route("canon")
        self.left_panel.select_path(path)
        self.status_message.setText("已创建 · 时间线")

    def new_canon_entry(self, kind: str) -> None:
        if kind == "timeline":
            self.new_timeline()
            return
        if not self._require_project():
            return
        labels = {
            "character": ("角色", "角色姓名：", "新角色", "角色已存在", "同名角色卡已经存在。"),
            "world": ("世界观条目", "条目名称：", "新设定", "条目已存在", "同名世界观条目已经存在。"),
            "power": ("体系设定", "体系名称：", "新体系", "条目已存在", "同名体系设定已经存在。"),
        }
        title_data = labels.get(kind)
        if title_data is None:
            QMessageBox.warning(self, "创建失败", "不支持的故事资料类型。")
            return
        dialog_title, prompt, default, conflict_title, conflict_message = title_data
        title, ok = QInputDialog.getText(self, f"新建{dialog_title}", prompt, text=default)
        if not ok or not title.strip():
            return
        try:
            path = self.document_controller.create_canon_entry(kind, title)
        except FileExistsError:
            QMessageBox.warning(self, conflict_title, conflict_message)
            return
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "创建失败", str(exc))
            return
        self._show_route("canon")
        self.left_panel.select_path(path)
        if self.project_setup_dialog is not None:
            self.project_setup_dialog.refresh(self.project)

    def set_system_importance(self, path_str: str, importance: str) -> None:
        project = self.project
        if project is None:
            return
        path = Path(path_str)
        if not path.is_absolute():
            project_path = project.root / path
            path = project_path if project_path.exists() else path.resolve()
        path = path.resolve()
        try:
            store = ProjectDataStore(project)
            current = store.system_metadata(path).get("importance", "non_core")
            if current == importance:
                label = "核心 · 自动加载" if importance == "core" else "非核心加载"
                self.status_message.setText(f"“{path.stem}”当前已使用{label}")
                return
            store.set_system_importance(path, importance)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "设置体系重要性失败", str(exc))
            return
        self.project_session.notify_data_changed(
            [store.system_registry_path], kind="system_importance"
        )
        if importance == "core":
            message = f"已将“{path.stem}”设为核心 · 后续 AI 任务将自动加载"
        else:
            message = f"已将“{path.stem}”设为非核心 · 可在 AI 扩写时手动选择"
        core_count = len(store.list_core_systems())
        if core_count >= 8:
            message += f"（当前 {core_count} 项核心体系，可能占用较多上下文）"
        self.status_message.setText(message)

    def _show_project_setup(self, project: NovelProject) -> None:
        if self.project_setup_dialog is not None:
            self.project_setup_dialog.close()
        dialog = ProjectSetupDialog(project, self)
        dialog.new_entry_requested.connect(self.new_canon_entry)
        dialog.entry_open_requested.connect(self._open_setup_entry)
        dialog.done_requested.connect(lambda: self._finish_project_setup(dialog))
        dialog.finished.connect(lambda _result: self._clear_project_setup(dialog))
        self.project_setup_dialog = dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _clear_project_setup(self, dialog: ProjectSetupDialog) -> None:
        if self.project_setup_dialog is dialog:
            self.project_setup_dialog = None

    def _finish_project_setup(self, dialog: ProjectSetupDialog) -> None:
        if self.project_setup_dialog is not dialog:
            return
        dialog.close()
        self._show_route("writing")
        self.status_message.setText("初始化资料完成，可以开始写作")

    def _open_setup_entry(self, path_str: str) -> None:
        project = self.project
        if project is None:
            return
        path = Path(path_str)
        if not path.is_file() or project.canon_dir.resolve() not in path.resolve().parents:
            return
        self._show_route("canon")
        self.left_panel.select_path(path)

    def _on_file_selected(self, category: str, path_str: str) -> None:
        current = self.editor.current_path()
        if current and Path(current) == Path(path_str):
            return
        opened = self.document_controller.open_file(category, path_str)
        if not opened and self.document_controller.save_conflict_path is not None:
            if self._resolve_save_conflict():
                opened = self.document_controller.open_file(category, path_str)
        if opened and self.project:
            self.view_refresh_controller.refresh_inspector(self.project)
            self._show_route(
                self.story_navigation_controller.route_for_category(category)
            )
        self._refresh_delete_action()
        self._update_window_title()

    def _open_memory_chapter(self, chapter_id: str) -> None:
        self.story_navigation_controller.open_memory_chapter(chapter_id)

    def _import_markdown_chapters(self) -> None:
        if not self._require_project():
            return
        assert self.project is not None
        files, _ = QFileDialog.getOpenFileNames(
            self, "导入 Markdown 章节", str(Path.cwd()), "Markdown 文档 (*.md *.markdown);;文本文件 (*.txt)"
        )
        if not files:
            return
        try:
            imported = self.document_controller.import_markdown(files)
        except (OSError, UnicodeError, RuntimeError) as exc:
            QMessageBox.critical(self, "导入失败", str(exc))
            return
        if imported:
            self._show_route("writing")
            self.left_panel.select_path(imported[0])
            self.status_message.setText(f"已导入 {len(imported)} 个章节")

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------
    def export_manuscript(self, options: object = None) -> None:
        if not self._require_project():
            return
        if not isinstance(options, dict):
            self._show_route("export")
            return
        assert self.project is not None
        if not self._save_if_dirty():
            return
        try:
            chapters = self.export_controller.selected_chapters(options)
        except (RuntimeError, ValueError) as exc:
            QMessageBox.information(self, "无法导出", str(exc))
            return
        if not chapters:
            QMessageBox.information(self, "无法导出", "请至少选择一个章节。")
            return
        export_format = "txt" if options.get("format") == "txt" else "md"
        suggested = self.export_controller.suggested_path(options)
        filters = "纯文本 (*.txt);;Markdown 文档 (*.md)" if export_format == "txt" else "Markdown 文档 (*.md);;纯文本 (*.txt)"
        output, selected_filter = QFileDialog.getSaveFileName(self, "导出全书", str(suggested), filters)
        if not output:
            return
        plain_text = output.lower().endswith(".txt") or "纯文本" in selected_filter
        # 丢到后台：几百章要重读一遍全文再加起来，在主线程做界面会冻住几秒到十几秒。
        self.status_message.setText("正在导出…（界面不会卡，导完会告诉你）")

        def work(_cancel_event):
            return self.export_controller.export(
                options, Path(output), format_name="txt" if plain_text else "md")

        task = DSHTask(work, parent=self)
        task.success.connect(self._on_export_done)
        task.failed.connect(
            lambda error: QMessageBox.critical(self, "导出失败", str(error)))
        task.finished.connect(task.deleteLater)
        self._export_task = task
        task.start()

    def _on_export_done(self, result) -> None:
        self.status_message.setText(f"已导出 {result.chapter_count} 章 · {result.path.name}")
        # 结果回对话栏，不再弹窗（作者嫌弹窗丑）。
        self.inspector.chat_panel.append(
            "它", "全书已导出到：%s（%d 章）" % (result.path, result.chapter_count))

    # ------------------------------------------------------------------
    # Focus, panels and preferences
    # ------------------------------------------------------------------
    def toggle_focus_mode(self) -> None:
        if self.window_state_controller.current_route not in {"writing", "canon"}:
            self._show_route("writing")
        self.window_state_controller.toggle_focus_mode()

    def _exit_focus_mode(self) -> None:
        self.window_state_controller.exit_focus_mode()

    def toggle_navigation_panel(self) -> None:
        self.window_state_controller.toggle_navigation_panel()

    # ── 对话面板 ────────────────────────────────────────────
    # 只带两样东西进上下文：创作内核 + 当前章节正文。
    # 带多了反而稀释——这一条是实测过的。

    @staticmethod
    def _workspace_root() -> Path:
        # 走 core/paths.py：源码运行指向仓库根，打包后指向 exe 旁边，
        # 不会因为 __file__ 落在 bundle 里而找不到 CLAUDE.md 和技法样本。
        return workspace_root()

    def _workspace_caveat(self) -> str:
        """本机没有配套素材库时，先给 AI 一句提醒。

        ⚠️ `style/技法样本/` `lore/` `拆文库/` `CLAUDE.md` 这些，是**本项目的可选搭档**，
        不是这个程序的一部分——别人把仓库单独拉下来跑，这些目录一个都不存在。
        不提醒的话，它会照着系统提示词里的清单一个个去找、然后落空。
        （本机有素材库时返回空串，跟以前完全一样。）
        """
        root = self._workspace_root()
        if (root / "style" / "技法样本").is_dir() or (root / "拆文库").is_dir():
            return ""
        return (
            "# ⚠️ 先看这一条\n"
            "**这台机器上没有 `style/技法样本/`、`lore/`、`拆文库/`、`CLAUDE.md` 这些目录**——\n"
            "它们是本项目的**可选配套资料**（写作素材库、拆书产物），不是这个程序的一部分。\n"
            "下面提到它们的地方，**找不到就跳过**：别照着清单一个个去找，**更别凭印象编**。\n"
            "你手上真正有的，是「当前作品」那一段里那个项目目录。")

    def _read_kernel(self) -> str:
        try:
            md = (self._workspace_root() / "CLAUDE.md").read_text(encoding="utf-8")
        except OSError:
            return ""
        i = md.find("# 创作内核")
        if i < 0:
            return ""
        rest = md[i:]
        j = rest.find("\n# ", 1)
        return rest if j < 0 else rest[:j]

    def _build_chat_system(self) -> str:
        root = self._workspace_root()
        parts = [
            "你是这本小说的写作搭档。作者和你一起写这本书——你出稿，他判。",

            "# 怎么说话\n"
            "- 像人一样说。**不要动不动列 bullet、不要写小标题、不要「首先其次最后」。**\n"
            "- 作者问什么答什么，不铺垫、不总结、不客套。\n"
            "- 要改稿就**直接给改后的正文**：把改后的完整正文放进一个 ```正文 块里。\n"
            "  **作者已放权：你可以直接改文件。** 但两条底线——\n"
            "  ① 改之前先看清要动哪儿，改完在对话里说清你动了什么；\n"
            "  ② 一次只做一件事，别一口气改一大片（他才退得回来）。\n"
            "  想让他先过目也行：把改后的正文放进「正文」块，他会看到「应用到正文」按钮。\n"
            "  块外面用一两句说你动了哪儿。**别只讲思路、别让作者自己复制粘贴。**",

            self._workspace_caveat(),

            "# 这个应用怎么运转（**你自己就是它的一部分，这些必须门儿清**）\n"
            "面板叫 Agentorium。一本书 = `%s/projects/{书名}/` 下的一个目录，\n"
            "一个项目一个区，互不干扰：\n\n"
            "```\n"
            "{书名}/\n"
            "  project.json                    书的身份\n"
            "  outline/chapters/chapter_NN.md   正文（一章一个文件，`## 正文` 段是正文）\n"
            "  outline/main_arc.md              主线\n"
            "  outline/future_plan.md           后续规划\n"
            "  canon/characters/*.md            角色卡\n"
            "  canon/world/*.md                 世界观\n"
            "  canon/power/*.md                 体系设定\n"
            "  canon/timeline.md                时间线\n"
            "  canon/relation.json              关系图数据（分析页那张网读它）\n"
            "  memory/chapter_summaries.json    逐章摘要（key 用 `chapter_07` 这种格式！）\n"
            "  memory/story_state.json          故事状态：当前位置/时间/在场角色\n"
            "  memory/foreshadowing.json        伏笔\n"
            "  memory/sync_log.json             哪几章已同步（**别手改**）\n"
            "  memory/对话记录.md               你和作者在这个项目里的往次对话\n"
            "  memory/角色索引.md               谁在第几章干了什么（查来龙去脉用它，别 grep 一本）\n"
            "  writing/style_guide.md           这本书的文风\n"
            "```\n\n"
            "**每种活写到哪，照这个来，别自己另起炉灶：**\n\n"
            "| 干什么 | 写到哪 |\n"
            "|---|---|\n"
            "| 写/改正文 | `outline/chapters/chapter_NN.md` 的 `## 正文` 段 |\n"
            "| 改文风 | `writing/style_guide.md` |\n"
            "| 沉淀一章 | `memory/chapter_summaries.json`（**摘要**）＋ `memory/story_state.json`（状态） |\n"
            "| 记伏笔 | `memory/foreshadowing.json` |\n"
            "| 建角色 | `canon/characters/{名字}.md` |\n"
            "| 补关系 | `canon/relation.json` |\n"
            "| 接时间线 | `canon/timeline.md` |\n"
            "| 拆书 | `拆文库/{书名}/`（摘要进 `章节/`，条目进 `_analysis_cache/`，最后并进 `style/技法样本/`）|\n"
            "| 取神话民俗素材（造设定/怪物/规矩） | 先扫 `lore/_调用索引.md`，按指针读 `lore/{册}.md` 的那几条；"
            "照「可搬」那一步造自己的东西，不照抄原型 |\n"
            "| 拆完收尾 | 照 `_拆书流程.md` 第 7 步：**面板上看得见的每一项**都补到最新章——"
            "人物/伏笔/设定/线索词表/关系图/总大纲/后续规划/文风指南/世界观/体系设定/时间线/摘要/状态/角色索引 |\n\n"
            "**界面上的事你也得知道**：\n"
            "- 「分析」页的**表格**里，**节奏曲线**扫的是原文和 `chapter_index.csv`，不用同步；\n"
            "  但**线索轨迹**不是——它读 `拆文库/{书名}/线索词表.txt`，收尾必须手填，空着表就是空的。\n"
            "- 「故事记忆」页有个「补同步全部」，读 `memory/sync_log.json` 算待办。\n"
            "- ⚠️ `sync_log.json` **别手改**；**在终端改完记忆、面板还显示旧章号时，跑 "
            "`py scripts/同步面板.py {书名}`**（重算同步标记 ＋ 顺带自检伏笔/状态/摘要/大纲**面板读不读得出**）。\n"
            "- 分析页、故事资料、故事记忆、表格页 —— 四处都显示「**已同步至第 N 章**」，同步完自己会涨。\n\n"
            "**每次动手前先问自己三句**：这件事的产物该落到哪个文件？已有内容会不会被我盖掉？\n"
            "我依据的是原文/摘要，还是我自己想象出来的？\n\n"
            "# 三条长期合作规矩（2026-10-03 定）\n\n"
            "**一、裁定要留痕。** 作者推翻自己的时候（某个角色死不死、某条伏笔收不收、\n"
            "某张地图怎么画、时间怎么推），**把这次裁定记一行**到 `projects/{书}/decision-log.md`：\n"
            "`- 第N章｜推翻了什么｜新定的是什么｜为什么`。\n"
            "你要不要维护这个文件不用问他——**他只需要拍板，你负责落笔**。\n"
            "⚠️ 不记的后果：到几百章他会反复推翻自己，同一场争论用同样的话术再来一遍，\n"
            "他说「我是不是说过这个」，而记录里没有。\n\n"
            "**二、有效性的判定归作者，你只负责记录。** 技法样本每条有「有效性」字段\n"
            "（高价值/易漏/无效/未验）。**哪条真起作用只有他能说。**\n"
            "你觉得某条起了作用，就说出来给他认；**别自己落笔改那个字段**。\n\n"
            "**三、角色不能失联。** `story_state` 只列当前在场的人，配角可能几百章不露面。\n"
            "写到某一章要用到谁的时候，**先查 `memory/角色索引.md`**（每人在每章干了什么，\n"
            "一句一行）——别拿 grep 去翻一本，命中的全是噪音。\n\n"
            "**四、别把上一次的话丢了。** 你和作者在这个项目里的往次对话记在\n"
            "`memory/对话记录.md`。**接着上次往下干之前，先扫一眼最近几条**——\n"
            "他说过什么要求、你许过什么，都在里头。长连载最怕的就是每次从空白开始。\n"
            "（界面里也会把最近 30 条读回来。）\n\n"
            "**五、这个应用的大部分功能，本质是「帮你把提示词组织好」。**\n"
            "写到某一章要用到谁的时候，**先查他上次出现是哪章、当时在干什么**；\n"
            "查完发现确实很久没提（超过 100 章），提一句「某某已经 N 章没露面了」给作者。\n\n"
            "# 你手上有什么（都在 %s 里，用 Read/Glob/Grep 自己取，别凭印象）\n"
            "- `工作逻辑.md` —— **怎么干活**：扫书的五层（机械扫描→定位→专题精读→结构归纳→并库）、\n"
            "  写作时的取用顺序、什么时候该停下来问作者。**开工前先读这一份。**\n"
            "- `CLAUDE.md` —— **创作内核五条** + 项目规则。写任何东西之前先读它。\n"
            "- `PROJECT.md` —— 项目宪章：硬约束、禁区、书稿怎么存。\n"
            "- `style/技法样本/` —— **十三册写法样本**，按本章要写什么读对应的：\n"
            "    `01-情感与心理` 情绪怎么呈现、心绪托在什么上、留白留到哪\n"
            "    `02-对话` 对话承担信息、潜台词、问答节奏、怎么收\n"
            "    `03-场面与切换` 换场标记、切前切后怎么写、时间怎么跳\n"
            "    `04-结构与伏笔` 伏笔埋多久、什么时候收、章尾落在哪\n"
            "    `05-多线并行` 线能停多久、怎么断、怎么接回来\n"
            "    `06-战斗` 打戏怎么起手、招式怎么处理、怎么压缩\n"
            "    `07-日常与过场` 什么都不发生的段落怎么不流水账\n"
            "    `08-长弧怎么撑` 一场戏拆十几二十章靠什么不塌\n"
            "    `09-别学的地方` **每次写完查这一册**\n"
            "    `10-男女主感情线` 不说破的暗线怎么写\n"
            "    `11-人物塑造` 一个人从出场到立住：人设怎么分批抖、缺点什么时候给、久不露面怎么接回来\n"
            "    `12-世界与设定` 设定什么时候揭、揭多少、留什么；规则怎么让人看懂又不倒豆子\n"
            "    `13-全书结构` 一本怎么拱上去、卷与卷怎么接、主线怎么隔几百章还咬得住\n"
            "  形态是「**要写「什么处境」→ 原句 + 可搬的做法**」——照那个格式取用。\n"
            "  ⚠️ **写正文前先扫 `_调用索引.md`**（894 条触发条件的总表，13 册）：勾出本章要用的 3–8 条，\n"
            "  再按指针（`01#12 · L84`）去册里读那几条。按「本章是什么类型」挑册，会漏掉跨册的同处境条目。\n"
            "  ⚠️ `01`–`10` 这十册只管「**一个场景怎么落笔**」；`11`–`13` 三册管「**一个人 / 一套设定 /\n"
            "  一整本怎么走完全程**」。精拆产出的**全局材料**（角色卡 / 世界观 / 体系设定 /\n"
            "  总大纲 / 逐章摘要 / 伏笔表 / 角色索引 / 文风指南，都在 `projects/{书}/`）\n"
            "  **也要按「本章要干什么」翻**：立人物→`11` + 角色卡；揭设定→`12` + 体系设定＋世界观；\n"
            "  铺/收线、卷与卷接续→`13` + 总大纲＋伏笔表；接一个久未露面的人→角色索引＋章节摘要；\n"
            "  定手感→ `writing/style_guide.md`。\n"
            "- `lore/` —— **神话民俗素材库：这层管「写什么」**（`style/技法样本/` 管「怎么写」，两张是一对）。\n"
            "  六册：`01-希腊神话`（权力与宿命的结构）· `02-中国神话`（天庭/地府/劫数的体系气）·\n"
            "  `03-星宿与天象`（境界名/宗派名/称号/纪年的命名库）· `04-民俗与节令`（现实底下那一层）·\n"
            "  `05-民间诡异`（横死/替身/纸人/走阴/尸变这些现成故事形态）· `06-北欧神话`（代价与宿命，《龙族》底子）。\n"
            "  ⚠️ **造设定 / 写正文前先扫 `lore/_调用索引.md`**（218 条「要造什么」的总表）：勾出本章要造的几条，\n"
            "  再按指针（`05#12 · L84`）去册里读那几条。**条目落点是「可搬」——照那一步在书里造自己的东西，\n"
            "  不要照抄原型。** 写情感、对话这些「怎么写」翻 `style/技法样本/`；造世界、造怪物、造规矩这些\n"
            "  「写什么」翻这儿。\n"
            "- `style/技法样本/_拆书流程.md` —— 拆一本书的完整流程（含踩过的坑）。\n"
            "  **拆完必须照它的「第 7 步 · 收尾」把产物同步进项目**——\n"
            "  **面板上看得见的每一项**都要补到最新章：人物 / 伏笔 / 设定 / 线索词表 /\n"
            "  关系图 / 总大纲 / 后续剧情规划 / 文风指南 / 世界观 / 体系设定 / 时间线 /\n"
            "  章节摘要 / 故事状态 / 角色索引 / 章节文件，落到 `projects/{书}/` 对应文件里。\n"
            "  **拆到哪章就同步到哪章。**「分析」页里只有**节奏曲线**是自动的，不用同步；\n"
            "  **线索轨迹不是**——它要 `拆文库/{书}/线索词表.txt`，收尾必须手填，空着表就是空的。\n"
            "  ⚠️ 收尾时**拿不准的自己定、做完再说**，不许先甩一份待办清单给作者。\n"
            "  ⚠️ **粗拆和精拆是两套规矩，别混**：粗拆按**主题**跳着读（只有条目，不产出逐章摘要）；\n"
            "  精拆按**章节**一章一章读完（逐章摘要必须有）。作者点哪个档位就照哪套走。\n"
            "- `style/probes/` —— **这一场试出来的实证**：\n"
            "    `试笔-黄金三章.md` 六稿演进与每稿的实测数据（哪一稿指标全达标却评价最差）\n"
            "    `差距报告-我vs天不应.md` 我和原著逐项量出来的差距\n"
            "    `天不应-试笔.md` 三段试笔\n"
            "  **写之前扫一眼，能少踩别人踩过的坑。**\n"
            "- `.claude/rules/` —— 叙事与格式的硬规则（story-format / story-narrative 等）。\n"
            "- `拆文库/{书名}/` —— 拆过的书：`chapter_index.csv`（章节表）、\n"
            "  `作品分析.md`、`线索词表.txt`、`拆解小结.md`、`原文/原文.txt`、\n"
            "  `章节/第N章_摘要.md`。**可以直接读原文。**\n"
            "- 你自己的书在 `projects/{项目}/`：`canon/`（设定）、`outline/`（大纲）、\n"
            "  `memory/`（记忆与伏笔）、`writing/style_guide.md`（文风）。" % (app_home(), root),

            "# 不要做的\n"
            "- **不凭空造设定。**推理链的每一环都要能在前文找到出处。\n"
            "- 不写心理总结句；情绪落在具体动作和物件上。**但克制只对主角成立**，"
            "配角、反派、过场可以直接报情绪。\n"
            "- 不留白到读者看不懂：藏的是「这意味着什么」，不是「发生了什么」。",
        ]
        kernel = self._read_kernel()
        if kernel:
            parts.append("# 创作内核（原文）\n" + kernel)
        project = self.project_session.project
        if project is not None:
            parts.append("# 当前作品\n《%s》" % project.name)
            brief = self._project_memory_brief(
                project, self.editor.current_chapter_id())
            if brief:
                parts.append(brief)
        # 上次聊到哪——后台带最近 30 条，**不上屏**（作者要的是"界面干净、AI 知道"）。
        # 要看更早的，它自己去 Read `memory/对话记录.md`，那里是全量。
        digest = self.inspector.chat_panel.history_digest()
        if digest:
            parts.append(
                "# 上次你们聊到哪（最近 30 句）\n"
                "**这是后台带上的，作者屏幕上并没有显示这些**——别以为他刚说过。\n"
                "要翻更早的，去读 `projects/{书}/memory/对话记录.md`（那里是全量）。\n\n"
                + digest)
        text = self.editor.text_edit.toPlainText().strip()
        if text:
            parts.append(
                "# 当前章节正文\n"
                "**这是作者此刻屏幕上的实时版本，以它为准。**\n"
                "⚠️ 磁盘上的文件可能还是旧的——作者改了不一定存过。"
                "要引用正文、要判断写到哪儿了，都用下面这一段，不要再去读文件。\n\n"
                + text[:6000])
        # 空段（比如没有素材库时的提醒）不参与拼接，免得留一串光秃秃的分隔线。
        return "\n\n---\n\n".join(part for part in parts if part)

    def _project_memory_brief(self, project, chapter_id: str | None = None) -> str:
        """这本书现在的样子——**每次说话都自动摆在它眼前**。

        作者的原话：「他每次写东西的时候也都会考虑到这些东西……不是调用知识库。」
        —— 伏笔和人物状态不能等他问，得每次都带到，不然写着写着就写飞了。

        2026-10-04 作者又点了一句：「我们写作的时候也会参考上下文，参考我们之前
        列出来的东西，毕竟都是花 token 的。」所以这里不止人物和伏笔——**该书这一路
        攒下来的统筹件按「写的时候用得着」摆进来**：本章规划、总大纲/后续规划节选、
        伏笔的紧急度、记忆铺到第几章。角色卡/世界观/体系设定那种大块头仍是**按需去读**
        （把全书设定每轮都灌进来会把正文挤没，这条是他自己踩过的）。
        """
        from core.project_data import ProjectDataStore
        store = ProjectDataStore(project)
        lines: list[str] = []

        try:
            state = store.load_story_state() or {}
        except (OSError, ValueError):
            state = {}
        where = state.get("current_location") or ""
        when = state.get("current_time") or ""
        if where or when:
            lines.append("**人在哪**：%s%s" % (where, (" · " + when) if when else ""))
        characters = state.get("characters")
        # ⚠️ 类型要挡。AI 写坏或旧数据里 characters 可能是 list/str，
        # 直接 .items() 会抛 AttributeError —— 而这一抛会把对话栏永久卡在「它正在想…」
        # （_on_chat_send 已经 set_busy(True) 了，任务却根本没建起来）。
        if isinstance(characters, dict) and characters:
            brief = "；".join(
                "%s（%s）" % (name, str(detail.get("state") or "").strip()[:40])
                for name, detail in list(characters.items())[:8]
                if isinstance(detail, dict))
            if brief:
                lines.append("**他们的状态**：" + brief)

        try:
            open_notes = [n for n in store.load_foreshadowing()
                          if str(n.get("status") or "") == "open"]
        except (OSError, ValueError):
            open_notes = []
        if open_notes:
            # 「该管了」的排前面，红标跟作者自己勾选时看到的那份用同一套判断
            # （core/foreshadowing.py）——不然他看到的顺序会和 AI 收到的对不上。
            from core.foreshadowing import foreshadowing_urgency, urgency_label
            from core.project import chapter_number_from_id
            current_number = chapter_number_from_id(chapter_id) if chapter_id else None
            open_notes = sorted(
                open_notes,
                key=lambda n: foreshadowing_urgency(n, current_number))
            rows = []
            for note in open_notes[:15]:
                plan = str(note.get("planned_resolution_chapter") or "").strip()
                label = urgency_label(foreshadowing_urgency(note, current_number))
                rows.append("· %s%s%s" % (
                    note.get("title") or "未命名",
                    ("（计划第 %s 章收）" % plan) if plan else "",
                    (" " + label) if label else ""))
            lines.append("**还没收的伏笔**（写的时候留神，别写飞；⚠️ 是已经该管的）：\n"
                         + "\n".join(rows))

        # **本章规划**：正文只带 `## 正文` 那一段，规划（大纲 / 剧情简写）不摆出来的话，
        # 它写的时候看不见这一章要干什么，只能凭前文猜。
        if chapter_id:
            try:
                chapter = store.load_chapter(chapter_id)
            except (OSError, ValueError):
                chapter = None
            if chapter is not None:
                plan = "\n".join(
                    part for part in (
                        str(getattr(chapter, "outline", "") or "").strip(),
                        str(getattr(chapter, "plot_brief", "") or "").strip(),
                    ) if part)
                if plan:
                    lines.append("**本章规划**：\n" + plan[:500])

        # **总大纲 / 后续规划**（各取开头一段）：作者点名要带——那是花 token 攒的，
        # 写正文时摆出来才知道这一章在大盘上走到哪儿了。整篇太长，只截开头。
        for caption, loader in (("总大纲", store.load_main_arc),
                                ("后续规划", store.load_future_plan)):
            try:
                body = " ".join(str(loader() or "").split())
            except (OSError, ValueError):
                body = ""
            if body:
                lines.append("**%s**（节选）：%s" % (caption, body[:300]))

        # **进度**：记忆铺到哪一章。不摆出来的话，摘要只到第 N 章，
        # 后面几章它其实没见过，却会当成「没发生」。
        try:
            total = len(project.list_chapters())
        except OSError:
            total = 0
        if total:
            from core import sync_state
            try:
                synced = sync_state.synced_upto(project)
                waiting = len(sync_state.pending(project))
            except OSError:
                synced, waiting = 0, 0
            line = "**进度**：全书 %d 章" % total
            line += ("，记忆已同步至第 %d 章" % synced) if synced else "，记忆尚未同步"
            if waiting:
                line += "（还有 %d 章没同步，那些章的事还没进摘要——别当成没发生）" % waiting
            lines.append(line)

        # **前文**：作者的原话「写后文要参前文」——光有状态和伏笔不够，
        # 还得让他知道前面几章实际写到哪儿了。伏笔/人物都是**这本书自己的**，
        # 跨项目共享的只有技法样本那层（「怎么写」），两码事。
        try:
            summaries = store.load_chapter_summaries() or {}
        except (OSError, ValueError):
            summaries = {}
        if summaries:
            from core.project import chapter_sort_key
            recent = sorted(summaries, key=chapter_sort_key)[-5:]
            rows = []
            for chapter_id in recent:
                body = " ".join(str(summaries[chapter_id]).split())
                rows.append("· %s：%s" % (chapter_id, body[:120]))
            if rows:
                lines.append("**前文写到哪了**（最近 5 章）：\n" + "\n".join(rows))

        if not lines:
            return ""
        return "# 这本书现在什么样（**动手之前先看一眼**）\n" + "\n".join(lines)

    def _on_chat_send(self, message: str) -> None:
        panel = self.inspector.chat_panel
        client = self.ai_engine_controller.client
        if client is None:
            panel.append("它", "AI 引擎还没准备好，先到偏好设置里确认一下命令。")
            return
        panel.append("你", message)
        panel.set_busy(True)
        # 作者要是**圈了一段**再说话，就记下来：等一下只改那一段，别动整章。
        # （他要的是"能圈选几行让它动"，不是每次都全篇重写。）
        cursor = self.editor.text_edit.textCursor()
        if cursor.hasSelection():
            whole = self.editor.text_edit.toPlainText()
            start, end = sorted((cursor.selectionStart(), cursor.selectionEnd()))
            picked = whole[start:end]
            if picked.strip():
                self._chat_selection = {"start": start, "end": end, "text": picked}
                message = (
                    "作者**只选中了下面这一段**，请**只改这一段**，别的地方一个字都别动。\n"
                    "把改后的那一段放进 ```正文 块——**只放这一段，不要给整章**。\n\n"
                    "选中的原文：\n" + picked + "\n\n要求：" + message)
            else:
                self._chat_selection = None
        else:
            self._chat_selection = None
        system = self._build_chat_system()

        def work(cancel_event):
            return client.generate(system, message, cancel_event=cancel_event)

        self._chat_task = DSHTask(work, parent=self)
        self._chat_task.success.connect(self._on_chat_reply)
        self._chat_task.failed.connect(self._on_chat_failed)
        self._chat_task.cancelled.connect(lambda: panel.set_busy(False, "已取消"))
        self._chat_task.finished.connect(self._chat_task.deleteLater)
        self._chat_task.start()

    # ── 批注模式 ────────────────────────────────────────────
    def _toggle_annotations(self, on: bool) -> None:
        self.editor.set_annotation_mode(on)
        # 光靠按钮变色还不够——文字也换，扫一眼就知道在不在批注模式。
        self.anno_button.setText("批注 · 开" if on else "批注")
        if not on:
            self.status_message.setText("批注已关：正文回到干净成稿。")
            return
        items = self._collect_annotations()
        self.editor.set_annotations(items)
        if items:
            self.status_message.setText(
                "批注已开：正文里标了 %d 处——朱红＝伏笔，墨绿＝待改。再点一下「批注 · 开」关掉。"
                % len(items))
        else:
            self.status_message.setText(
                "批注已开，但这本书还没有可标的东西：伏笔要先生成（点「更新记忆」），"
                "待改要写进 writing/notes.json。")

    def _collect_annotations(self):
        """批注从哪来：项目里的伏笔 + 作者自己写的待改。

        伏笔取 memory/foreshadowing.json 的标题词；待改取 writing/notes.json：
            [{"text": "正文里的原句", "note": "为什么标它", "kind": "待改"}]
        """
        out = []
        project = self.project_session.project
        if project is None:
            return out
        root = Path(project.root)
        try:
            data = json.loads((root / "memory" / "foreshadowing.json")
                              .read_text(encoding="utf-8") or "{}")
            for it in data.get("items", []):
                title = str(it.get("title") or "").strip()
                if len(title) >= 2:
                    out.append({"text": title, "kind": "伏笔",
                                "note": it.get("note") or "尚未回收的伏笔"})
        except (OSError, ValueError):
            pass
        try:
            notes = json.loads((root / "writing" / "notes.json")
                               .read_text(encoding="utf-8") or "[]")
            for it in notes if isinstance(notes, list) else []:
                if it.get("text"):
                    out.append({"text": str(it["text"]),
                                "kind": str(it.get("kind") or "待改"),
                                "note": str(it.get("note") or "")})
        except (OSError, ValueError):
            pass
        return out

    # ── 拆书（要花钱的两档）──────────────────────────────────
    def _on_ingest_requested(self, book_dir: str, mode: str,
                             start: int, end: int, shards_wanted: int = 4) -> None:
        """点「拆这本书」= **把提示词放进右边输入框**，不开任务。

        作者的原话：「我在点拆这本书之后，不是应该给我生成提示词，然后我点发送，
        然后让旁边的侧栏指派任务吗？为啥它直接拆了呀？」

        他要的是：**看得见、能改、点发送才跑**。所以这里只生成提示词——
        真正的执行由他点「发送」之后，交给侧栏那个 AI 自己派代理去做。
        """
        from core.ingest import build_ingest_prompt
        prompt = build_ingest_prompt(
            Path(book_dir).name, mode, start, end, shards_wanted)
        self.inspector.tabs.setCurrentIndex(0)
        editor = self.inspector.chat_panel.editor
        editor.setPlainText(prompt)
        editor.setFocus()
        self.status_message.setText("拆书提示词已生成 —— 看一眼，改完点「发送」就开始。")

    def _run_ingest_shards(self, book_dir: str, mode: str,
                           start: int, end: int, shards_wanted: int = 4) -> None:
        """把拆书交给 AI——按章节切段，**几段同时跑**。

        为什么并发：拆书流程（style/技法样本/_拆书流程.md 第 3 步）写的就是
        「一个专题一个代理、可以并行」。单进程跑 363 章太慢（实测每章约 1.5 万 token）。

        ⚠️ 写并发的红线：**每片只写自己那一段**。
           逐章摘要写 章节/；技法条目写 _analysis_cache/片段-{lo}-{hi}.md。
           「并进 style/技法样本 那几册」是最后单独一步——**不在这里做**，
           几片同时写同一册就是抢文件，这台机器上反复出过的故障源。
        """
        client = self.ai_engine_controller.client
        if client is None:
            QMessageBox.information(self, "AI 引擎没起来",
                                    "先到「设置」里确认一下命令。")
            return
        root = self._workspace_root()
        book = Path(book_dir)
        name = book.name
        tier = {"light": "轻量拆：前 5 章精读 + 每卷首尾 + 挑 10 个高能章",
                "full": "全本逐章拆：逐章摘要"}.get(mode, mode)

        # 分几段由作者定（界面上那个「分 N 段」），不再写死。
        count = max(1, min(12, int(shards_wanted or 4)))
        span = end - start + 1
        size = max(1, (span + count - 1) // count)
        shards = shard_ranges(start, end, size)
        self._last_ingest_book = str(book)

        system = ("你是拆书流水线的执行者。严格按给定的流程文档做，不要自创流程，"
                  "也不要为了凑数编造原文里没有的东西。"
                  "你只负责分配给你的那一段章节，不要去动别人负责的段。")

        def make_prompt(lo: int, hi: int) -> str:
            # 粗拆和精拆是两套规矩：粗拆按主题跳着读、不产出逐章摘要；
            # 精拆按章节一章一章读完、摘要必须有。
            if mode == "light":
                how = ("这一趟是**粗拆**（按主题）：**跳着读**，不用逐章过。\n"
                       "  产出：技法条目写 `_analysis_cache/片段-%d-%d.md`。**逐章摘要不用写。**" % (lo, hi))
            else:
                how = ("这一趟是**精拆**（按章节）：**一章一章读完**，一章不跳。\n"
                       "  产出：逐章摘要写 `章节/第N章_摘要.md`（一章不能少）；\n"
                       "  技法条目写 `_analysis_cache/片段-%d-%d.md`。" % (lo, hi))
            return (
                "按 `%s/style/技法样本/_拆书流程.md` 的流程，拆《%s》第 %d–%d 章（档位：%s）。\n\n"
                "原文：%s\n"
                "章节表：%s\n"
                "产出目录：%s\n\n"
                "要求：\n"
                "1. 本地扫描**已经做过了**（章节表和规范化原文都在），别再扫，从精读开始。\n"
                "2. 用章节表里这几章的起止行号直接从原文取——**别在全书里自己找章节**。\n"
                "3. 输出格式严格照流程第 4 步，**「要写「X」」那一行必须在最前面**。\n"
                "4. **只写你这一段**：%s\n"
                "   ⚠️ **不要动 style/技法样本/ 里的册子**——并册是最后单独一步的事，"
                "几片同时写同一册会抢文件。\n"
                "5. **不许新造设定**，推理链每一环都要能在原文找到出处。\n"
                "6. 按题材归册，**不预设哪一类不学**（打斗进 06，写坏的进 09）。\n\n"
                "做完回一段白话：拆了哪几章、哪几条最值得学。"
                % (root, name, lo, hi, tier,
                   book / "原文" / "原文.txt", book / "chapter_index.csv", book, how))

        def worker(shard, cancel_event):
            lo, hi = shard
            return client.generate(system, make_prompt(lo, hi), cancel_event=cancel_event)

        task = ShardedTask(shards, worker, self)
        task.progress.connect(self.workspace_page.set_shard_progress)
        task.succeeded.connect(self._on_ingest_shards_done)
        self._ingest_task = task
        self.workspace_page.set_busy(True)
        self.workspace_page.begin_shard_progress(name, start, end, len(shards))
        self.workspace_page.report(
            "正在拆《%s》第 %d–%d 章：切成 %d 段，同时开跑…（跑完前按钮都按不动）"
            % (name, start, end, len(shards)))
        # 点了按钮就当作者说要干这个——写进对话栏，跑完的结果也回那儿。
        self.inspector.tabs.setCurrentIndex(0)
        self.inspector.chat_panel.append(
            "你", "拆《%s》第 %d–%d 章 · 分 %d 段并行 · %s"
            % (name, start, end, len(shards), tier))
        task.start()

    def _on_ingest_shards_done(self, results: list, errors: list) -> None:
        """几段都跑完了。成功/失败分别报——不粉饰。

        ⚠️ 这里**先不放开按钮**：若接着要并册，并册没写完之前作者再点一次
        拆书或导入，就会和正在写册子的并册抢同一个文件。
        放开交给 _start_merge_pass 收尾时做（没有并册时才在这儿放开）。
        """
        self.workspace_page.finish_shard_progress(len(results), len(errors))
        self.workspace_page.report("拆书结束：%d 段成功，%d 段失败"
                                   % (len(results), len(errors)))
        panel = self.inspector.chat_panel
        self.inspector.tabs.setCurrentIndex(0)
        # 别按 enumerate 打「第 N 段」——结果是**按完成顺序**回来的，
        # 和真实的段号对不上，写出来是误导。
        for text in results:
            panel.append("它", "【一段完成】%s" % str(text))
        for index, text in enumerate(errors, 1):
            panel.append("它", "【第 %d 段失败】%s" % (index, str(text)))
        book_dir = getattr(self, "_last_ingest_book", None)
        if not errors and results and book_dir:
            panel.append("它", "各段产物已落盘。接着**并册**——这一步串行做，"
                              "几片同时写同一册会抢文件。")
            self._start_merge_pass(book_dir)      # 跑完由它放开按钮
        else:
            self.workspace_page.set_busy(False)

    def _on_ingest_cancel(self) -> None:
        """中止这一轮拆书/并册。**已经写完的产物留着，不删**——
        半成品总比没有强，作者自己看着办。"""
        stopped = []
        for label, task in (("拆书", getattr(self, "_ingest_task", None)),
                            ("并册", getattr(self, "_merge_task", None))):
            if task is None:
                continue
            try:
                running = (task.is_running() if hasattr(task, "is_running")
                           else task.isRunning())
            except RuntimeError:
                continue        # 已经跑完并被回收了，不用取消
            if running:
                task.cancel()
                stopped.append(label)
        self.workspace_page.report(
            "已让它停下：%s（已经写好的产物会留着）" % "、".join(stopped)
            if stopped else "现在没有在跑的活。")

    def refresh_character_index(self) -> None:
        """重建「角色索引.md」——把某某人在第几章干了什么串成一条线。

        搭档的原话：查一个角色，"grep 给的是噪音不是答案"（阿水命中 215 次）。
        角色卡是快照，这张索引是来龙去脉。失败不该惊动人。
        """
        project = self.project_session.project
        if project is None:
            return
        try:
            from core.character_index import write
            write(project)
        except (OSError, ValueError):
            pass

    def _sync_summaries_to_project(self, book_dir: str) -> None:
        """拆完的书，把逐章摘要送进**同名项目**的「故事记忆」。

        拆书产出落在 拆文库/，面板「故事记忆」读的是 项目/memory/chapter_summaries.json——
        不接上，作者在面板里看不到自己拆出来的东西。
        """
        from core.books import sync_summaries_to_project
        name = Path(book_dir).name
        project_dir = app_home() / "projects" / name
        if not project_dir.is_dir():
            return
        try:
            added = sync_summaries_to_project(Path(book_dir), project_dir)
        except OSError as exc:
            self.inspector.chat_panel.append("它", "摘要同步没成功：%s" % exc)
            return
        if added:
            self.inspector.chat_panel.append(
                "它", "顺手把 %d 条逐章摘要同步进了项目《%s》的「故事记忆」页。"
                      % (added, name))

    def _start_merge_pass(self, book_dir: str) -> None:
        """各段跑完后的**收尾**：并册 + 把记忆与设定同步进项目。

        **必须串行**：并册要往 `style/技法样本/` 那几册里写，
        而刚才那几段是并行的——几片同时写同一册就是抢文件。

        作者的原话：「我以后拆书，拆到哪章它就自动同步了这些东西，全部的所有。」
        —— 所以收尾不只并册，还要把**记忆、伏笔、角色、时间线**一起补到最新章。
        """
        client = self.ai_engine_controller.client
        if client is None:
            # 拿不到引擎也要把工作区放开——不然所有控件一直禁用着，「停下来」按钮还露在外面。
            self.workspace_page.set_busy(False)
            self.inspector.chat_panel.append(
                "它", "拆完了，但 AI 引擎这会儿不可用，收尾（并册＋同步）没做。"
                      "去设置里确认一下，然后手动补一次。")
            return
        book = Path(book_dir)
        root = self._workspace_root()
        project_dir = app_home() / "projects" / book.name
        system = ("你是拆书流水线的收尾者。只做收尾（并册 + 把拆出来的东西"
                  "同步进项目），不要重拆，也不要去改原文。")
        prompt = (
            "《%s》各段已经拆完，逐章摘要落在 `%s/章节/`，"
            "技法条目落在 `%s/_analysis_cache/片段-*.md`。\n\n"
            "收尾做两件事。\n\n"
            "## 一、并册\n"
            "按 `%s/style/技法样本/_拆书流程.md` 第 5 步，把片段条目并进 `style/技法样本/` 对应那几册：\n"
            "- 按「写什么」归档，不按书；\n"
            "- 同一条目下挂多本书的例子时，把《%s》的例子并进去，别另开一条；\n"
            "- 格式照第 4 步，一个字别改；\n"
            "- **不留副本**——同一台机器上重复文件是反复出过的故障源。\n\n"
            "## 二、把拆出来的东西同步进项目\n"
            "项目在 `%s/`（若不存在就跳过这一节，在汇报里说明）。逐章摘要那一项"
            "面板已经自己同步了，**你不用再写 chapter_summaries.json**。\n"
            "**清单按「面板上看得见的每一项」来定——不是只补五样，是全部：**\n"
            "- 分析·表格「人物」／故事资料「角色」—— `canon/characters/`：\n"
            "  新出场、以后还会用到的角色，**照现有角色卡的格式**各建一份；\n"
            "  老角色有重大变化的（境界/立场/身份/关系）补进去。\n"
            "- 分析·表格「伏笔」／故事记忆「伏笔」—— `memory/foreshadowing.json`：\n"
            "  新埋的补进去（**沿用现有条目的字段和 id 规则**）；这批里回收掉的改成已回收。\n"
            "- 分析·表格「设定」／故事资料「世界观」—— `canon/world/*.md`：\n"
            "  这一批读到的地理、势力、社会、历史，一条一个文件。\n"
            "- 故事资料「体系设定」—— `canon/power/*.md`：能力、等级、规则、代价。\n"
            "- 分析·表格「线索轨迹」—— `%s/线索词表.txt`：\n"
            "  **按你读到的线索手填，一行一个词**（面板拿它扫全书画轨迹）。**不许留空模板。**\n"
            "- 故事资料「总大纲」—— `outline/main_arc.md`：全书主线，读到哪写到哪。\n"
            "- 故事资料「后续剧情规划」—— `outline/future_plan.md`：走向判断；\n"
            "  已完本的书就写明「已完本，无后续」，拿不准的写「待考」，**别编**。\n"
            "- 故事资料「写作风格指南」—— `writing/style_guide.md`：\n"
            "  这本书的文风（总体气质／叙事视角／句式节奏／对话风格／描写偏好／避免事项），\n"
            "  按你读到的填，**不许把空模板原样留着**。\n"
            "- 故事记忆「当前状态」—— `memory/story_state.json`：推进到**最新一章**：\n"
            "  current_chapter / current_location / current_time，以及每个在场角色最新的 location、state。\n"
            "- 故事资料「时间线」—— `canon/timeline.md`：这一批的关键节点接上。\n"
            "- 写作台「章节列表」—— `outline/chapters/chapter_NN.md`：\n"
            "  按摘要给每章落一份章文件（大纲／关键事件／因果／涉及／章尾钩子），照现有格式。\n"
            "- 「来龙去脉」—— `memory/角色索引.md`：每人在每章干了什么，一句一行。\n"
            "- **关系图** —— `%s/人物关系.json` 和项目的 `canon/relation.json` 都要补上"
            "这一批新出现/变化的关系（沿用现有格式：\n"
            '  {"nodes":[{"id","name","role"}],'
            '"edges":[{"from","to","relation","from_chapter","because"}]}）。\n'
            "  「分析」页的关系图直接读这两份，不补的话图上还是老样子。\n"
            "（「分析」页的「节奏曲线」不用管——它扫原文和 chapter_index.csv，本来就是全量。）\n\n"
            "规矩：\n"
            "- **只依据原文和摘要，不许新造**——每处都要能在原文找到出处；\n"
            "- 已有内容是**续写和更新**，不是推倒重写；\n"
            "- **拿不准的自己定，做完再说**——作者要的是拆完就有，不是先看一份待办。\n"
            "  时间对不齐就写「冬季，具体年月待考」；没正面出场但重要的照样建卡；\n"
            "  这批里死了的、以后用不到的就不建。定完在汇报里说明你怎么定的即可。\n\n"
            "做完回一段白话：并了哪几册各加几条、项目里改了哪几个文件、"
            "角色加了几张、伏笔加了几条、时间线接了几条，以及你没敢定的地方。"
            % (book.name, book, book, root, book.name, project_dir, book, book))

        def work(cancel_event):
            return client.generate(system, prompt, cancel_event=cancel_event)

        def _done(reply) -> None:
            self.workspace_page.set_busy(False)
            self.inspector.chat_panel.append("它", "【并册完成】%s" % str(reply))
            self._sync_summaries_to_project(book_dir)

        def _failed(error) -> None:
            self.workspace_page.set_busy(False)
            self.inspector.chat_panel.append("它", "【并册失败】%s" % str(error))

        def _cancelled() -> None:
            # 并册被「停下来」掐断也要放开工作区——不接这个信号的话，
            # 按钮一直禁用着、「停下来」也一直露在外面，等于卡死。
            self.workspace_page.set_busy(False)
            self.inspector.chat_panel.append("它", "并册已停。已经并进去的条目留着，没并的还在片段文件里。")

        task = DSHTask(work, parent=self)
        task.success.connect(_done)
        task.failed.connect(_failed)
        task.cancelled.connect(_cancelled)
        task.finished.connect(task.deleteLater)
        self._merge_task = task
        task.start()

    def _on_ingest_failed(self, error: str) -> None:
        self.workspace_page.set_busy(False)
        self.workspace_page.report("拆书失败")
        QMessageBox.critical(self, "拆书失败", str(error))

    def _on_chat_reply(self, reply: object) -> None:
        panel = self.inspector.chat_panel
        panel.append("它", str(reply))
        panel.set_busy(False)

    def _on_chat_failed(self, error: str) -> None:
        panel = self.inspector.chat_panel
        panel.append("它", "出错了：" + str(error))
        panel.set_busy(False, "出错了")

    def _on_chat_apply(self, text: str) -> None:
        """作者点了「应用到正文」——把 AI 改好的正文写进当前章节。

        这是**只在作者按按钮时**才走的路径，不自动改稿。
        写入只替换「## 正文」那一段，后面自定义的小节不动；
        走 QTextCursor，作者不满意可以 Ctrl+Z 退回去。
        """
        panel = self.inspector.chat_panel
        if not self.editor.current_path():
            panel.append("它", "现在没打开任何章节，没法写。先在左边点开一章。")
            return
        if self.editor.current_chapter_id() is None:
            panel.append("它", "现在打开的是故事资料，不是章节——改后的正文只能写进章节。")
            return
        # 圈选改：只动选中的那一段（且要选区内容还跟发出去时一模一样才写——
        # 作者中途改了的话，宁可退回去整章替换，也不能往错位置塞）。
        selection = getattr(self, "_chat_selection", None)
        if selection and self.editor.replace_range_if_matches(
                selection["start"], selection["end"], selection["text"], text):
            self._chat_selection = None
            if self._save_if_dirty():
                panel.append("它", "已替换你圈中的那一段，也存好了。不满意按 Ctrl+Z 退回去。")
            else:
                panel.append("它", "已替换圈中的那一段，但**保存没成功**——记得手动存一下。")
            return
        self._chat_selection = None
        self.editor.replace_chapter_body(text)
        if self._save_if_dirty():
            panel.append("它", "已写进这一章的「正文」段，也存好了。"
                              "不满意按 Ctrl+Z 能退回改之前。")
        else:
            panel.append("它", "已经写进去了，但**保存没成功**——记得手动存一下，别丢了。")

    def toggle_inspector(self) -> None:
        self.window_state_controller.toggle_inspector()

    def toggle_output(self) -> None:
        self.window_state_controller.toggle_output()

    def toggle_theme(self) -> None:
        self.settings_controller.toggle_theme()

    def _apply_settings(self, config: object, message: str = "设置已保存") -> None:
        if not isinstance(config, dict):
            return
        self.settings_controller.apply(config, message=message)

    def _on_settings_changed(self, config: dict, message: str) -> None:
        self.config = dict(config)
        self.update_controller.set_config(self.config)
        self.project_lifecycle_controller.set_config(self.config)
        self.ai_workflow_controller.set_config(self.config)
        self.appearance_controller.apply(self.config)
        self._update_page_header(self.window_state_controller.current_route)
        self.status_message.setText(message)

    def _test_dsh(self, config: object) -> None:
        if not isinstance(config, dict):
            return
        self.settings_controller.test_dsh(config)

    def _on_dsh_test_started(self) -> None:
        self.settings_page.set_test_status("正在检查 AI 引擎…")
        self.settings_page.test_button.setEnabled(False)

    def _on_dsh_test_succeeded(self, result: str) -> None:
        self.settings_page.set_test_status(str(result))

    def _on_dsh_test_failed(self, error: str) -> None:
        self.settings_page.set_test_status(f"检查失败：{error}")

    def _on_dsh_test_finished(self) -> None:
        self.settings_page.test_button.setEnabled(True)

    def check_for_updates(self) -> None:
        if (
            not self.update_controller.check(manual=True)
            and self.update_controller.is_running()
        ):
            self.status_message.setText("更新检查已在进行中")

    def show_about(self) -> None:
        try:
            version = load_current_version()
            version_text = f"v{version}"
        except ValueError:
            version_text = "版本未知"
        QMessageBox.information(
            self,
            "关于 Agentorium",
            f"Agentorium {version_text}\n\n"
            "本地优先的长篇小说创作工具。\n"
            "项目主页：https://github.com/xiauho/agentorium",
        )

    def _on_update_check_started(self, manual: bool) -> None:
        self.actions["check_updates"].setEnabled(False)
        if manual:
            self.status_message.setText("正在检查 Agentorium 更新…")

    def _on_update_check_result(
        self,
        result: UpdateCheckResult,
        manual: bool,
    ) -> None:
        if self.update_controller.should_present(result, manual=manual):
            if self.update_dialog is not None:
                self.update_dialog.show()
                self.update_dialog.raise_()
                self.update_dialog.activateWindow()
                return
            if result.latest is None:
                return
            dialog = UpdateDialog(result, self)
            self.update_dialog = dialog
            dialog.finished.connect(
                lambda choice,
                release=result.latest,
                current=result.current_version: self._handle_update_choice(
                    choice, release, current
                )
            )
            dialog.finished.connect(
                lambda _choice, target=dialog: self._clear_update_dialog(target)
            )
            dialog.open()
            self.status_message.setText(f"发现新版本 {result.latest.tag_name}")
            return
        if manual:
            notice_title, notice_message = no_update_notice(result)
            QMessageBox.information(
                self,
                notice_title,
                notice_message,
            )
            self.status_message.setText("更新检查完成")

    def _handle_update_choice(
        self,
        choice: int,
        release: UpdateInfo,
        current_version: AppVersion,
    ) -> None:
        if choice == UpdateDialog.OPEN_RELEASE:
            QDesktopServices.openUrl(QUrl(release.release_url))
        elif choice == UpdateDialog.SKIP_VERSION:
            self.update_controller.skip_version(release.tag_name)
            self.status_message.setText(f"已忽略 {release.tag_name}")
        elif choice == UpdateDialog.DOWNLOAD_UPDATE:
            if not self.update_download_controller.download(release, current_version):
                self.status_message.setText("更新下载已在进行中")

    def _on_update_download_started(self, release: UpdateInfo) -> None:
        dialog = QProgressDialog("正在准备安全下载…", "取消下载", 0, 1000, self)
        dialog.setWindowTitle(f"下载 {release.tag_name}")
        dialog.setWindowModality(Qt.WindowModality.WindowModal)
        dialog.setMinimumDuration(0)
        dialog.setAutoClose(False)
        dialog.setAutoReset(False)
        dialog.canceled.connect(self.update_download_controller.cancel)
        dialog.show()
        self.update_download_progress = dialog
        self.actions["check_updates"].setEnabled(False)
        self.status_message.setText(f"正在安全下载 {release.tag_name}…")

    def _on_update_download_progress(self, downloaded: int, total: int) -> None:
        dialog = self.update_download_progress
        if dialog is None:
            return
        ratio = min(1000, int(downloaded * 1000 / total)) if total > 0 else 0
        dialog.setValue(ratio)
        dialog.setLabelText(
            f"正在下载并校验… {downloaded / 1048576:.1f} / "
            f"{total / 1048576:.1f} MiB"
        )

    def _on_update_download_succeeded(self, result: VerifiedUpdate) -> None:
        self._close_update_download_progress()
        unavailable = automatic_install_unavailable_reason()
        message = QMessageBox(self)
        message.setIcon(QMessageBox.Icon.Information)
        message.setWindowTitle("更新包已安全下载")
        message.setText(
            f"{result.release.tag_name} 已通过大小、SHA-256 和 ZIP 安全检查。"
        )
        details = f"缓存位置：\n{result.archive_path}"
        if unavailable:
            details += f"\n\n{unavailable}"
        else:
            details += (
                "\n\n可立即退出 Agentorium，由独立更新器备份并替换受管程序文件；"
                "新版启动自检失败时会自动恢复当前版本。"
            )
        message.setInformativeText(details)
        message.addButton("稍后", QMessageBox.ButtonRole.RejectRole)
        open_folder = message.addButton(
            "打开缓存目录",
            QMessageBox.ButtonRole.ActionRole,
        )
        install_now = None
        if not unavailable:
            install_now = message.addButton(
                "立即重启并安装",
                QMessageBox.ButtonRole.AcceptRole,
            )
            message.setDefaultButton(install_now)
        message.exec()
        clicked = message.clickedButton()
        if clicked is open_folder:
            QDesktopServices.openUrl(
                QUrl.fromLocalFile(str(result.archive_path.parent))
            )
        elif install_now is not None and clicked is install_now:
            self._pending_update_install = result
            self.status_message.setText(
                f"{result.release.tag_name} 已验证，正在准备自动安装…"
            )
            return
        self.status_message.setText(f"{result.release.tag_name} 已下载并验证")

    def _on_update_download_failed(self, message: str) -> None:
        self._close_update_download_progress()
        QMessageBox.warning(self, "更新下载失败", str(message))
        self.status_message.setText("更新下载或安全校验失败")

    def _on_update_download_cancelled(self) -> None:
        self._close_update_download_progress()
        self.status_message.setText("更新下载已取消")

    def _on_update_download_finished(self) -> None:
        self.actions["check_updates"].setEnabled(True)
        if self._pending_update_install is not None:
            QTimer.singleShot(0, self._launch_pending_update_install)

    def _launch_pending_update_install(self) -> None:
        result = self._pending_update_install
        self._pending_update_install = None
        if result is None:
            return
        if self.ai_controller.is_running():
            QMessageBox.warning(
                self,
                "暂时无法安装更新",
                "AI 任务仍在进行，请等待任务完成后重新检查更新并安装。",
            )
            return
        if self.editor.is_dirty() and not self.save_current_file(notify=False):
            QMessageBox.warning(
                self,
                "暂时无法安装更新",
                "当前文档未能安全保存，已取消自动安装。更新包仍保留在缓存中。",
            )
            return
        try:
            launch = launch_verified_update_install(
                result,
                load_current_version(),
            )
        except (UpdateInstallLaunchError, OSError, ValueError) as exc:
            QMessageBox.warning(self, "无法启动自动安装", str(exc))
            QDesktopServices.openUrl(
                QUrl.fromLocalFile(str(result.archive_path.parent))
            )
            self.status_message.setText("自动安装未启动，可改用手动安装")
            return
        self.status_message.setText(f"正在退出并安装 v{launch.target_version}…")
        self.ai_engine_controller.cleanup()
        app = QApplication.instance()
        if app is not None:
            app.quit()

    def _close_update_download_progress(self) -> None:
        dialog = self.update_download_progress
        self.update_download_progress = None
        if dialog is not None:
            dialog.close()
            dialog.deleteLater()

    def _clear_update_dialog(self, dialog: UpdateDialog) -> None:
        if self.update_dialog is dialog:
            self.update_dialog = None
        dialog.deleteLater()

    def _on_update_check_failed(self, message: str, manual: bool) -> None:
        if manual:
            QMessageBox.warning(self, "检查更新失败", str(message))
            self.status_message.setText("更新检查失败")

    def _on_update_check_finished(self, _manual: bool) -> None:
        self.actions["check_updates"].setEnabled(True)

    def _on_update_config_changed(self, config: dict) -> None:
        self.config = dict(config)
        self.settings_controller.synchronize(self.config)
        self.settings_page.synchronize_update_metadata(self.config)

    # ------------------------------------------------------------------
    # Auto-save and AI tasks
    # ------------------------------------------------------------------
    def _refresh_auto_save_timer(self) -> None:
        enabled = bool(self.config.get("auto_save", True))
        seconds = max(5, int(self.config.get("auto_save_interval", 30) or 30))
        self.document_controller.configure_auto_save(enabled, seconds)
        self.auto_save_status.setText("自动保存已开启" if enabled else "自动保存已关闭")

    def _on_auto_saved(self, _path: str) -> None:
        self.auto_save_status.setText("刚刚自动保存")

    def _on_save_conflict_detected(self, path: str) -> None:
        self.auto_save_status.setText("检测到外部修改，尚未覆盖")
        self.status_message.setText(f"文件已被外部修改：{Path(path).name}")

    def _on_dirty_changed(self, _dirty: bool) -> None:
        self._update_window_title()

    def _refresh_delete_action(self) -> None:
        action = self.actions.get("delete_chapter")
        if action is None:
            return
        enabled = (
            self.project is not None
            and self.editor.current_category()
            in {"章节", "角色", "世界观", "体系设定", "时间线"}
            and self.editor.current_path() is not None
            and not self.ai_controller.is_running()
        )
        if enabled and self.editor.current_category() == "体系设定":
            enabled = not ProjectDataStore(self.project).is_core_power_path(
                Path(self.editor.current_path())
            )
        action.setEnabled(enabled)

    def _save_if_dirty(self) -> bool:
        # Opening the first project normally has no current document yet. In
        # that state there is nothing to save, so project switching must be
        # allowed to continue.
        if not self.editor.is_dirty():
            return True
        return self.save_current_file(notify=False)

    def expand_chapter(self) -> None:
        self._with_confirm(
            "要让 AI 接着往下写",
            "AI 会读这一章的规划、上文和记忆，接着写一段完整的正文。\n"
            "写完你还能改、还能不用。\n\n**会花钱，按字数计。**",
            self.ai_workflow_controller.expand)

    def continue_writing(self) -> None:
        """Backward-compatible entry point for older shortcuts or callers."""
        self.expand_chapter()

    def _with_confirm(self, title: str, body: str, run) -> None:
        """**花钱的动作统一走这里**：先在对话栏出一份说明，作者点「开始」才跑。

        作者的原话：「生成一份提示词，我点发送，它就开始拆书了……
        不是说的其他的几个功能也都是这么做的吗？」
        —— 他要的是**先看见要花什么、干什么，再点头**，不是按钮一点就闷头跑。
        """
        panel = self.inspector.chat_panel
        self.inspector.tabs.setCurrentIndex(0)
        from ui.chat_panel import ask_in_panel
        if ask_in_panel(panel, title, body + "\n\n（点「确认写入」＝开始，点「不要」＝算了）"):
            run()

    def update_memory(self) -> None:
        self._with_confirm(
            "要更新这一章的记忆",
            "AI 会读当前章的正文，提炼出：\n"
            "· 这一章发生了什么（摘要）\n"
            "· 人物现在在哪、什么状态\n"
            "· 有没有新埋伏笔\n\n**会花钱。**",
            self.ai_workflow_controller.update_memory)

    def update_memory_batch(self) -> None:
        """「补同步全部」：把没同步的章节一次跑完。

        这条**最花钱**（一次几章到几百章），以前却是唯一零确认的入口——
        与「花钱的动作统一先出说明」自相矛盾。补上。
        """
        from core import sync_state
        waiting = sync_state.pending(self.project_session.project)
        if not waiting:
            self.status_message.setText("没有待同步的章节——记忆是最新的。")
            return
        self._with_confirm(
            "要补同步 %d 章" % len(waiting),
            "AI 会**逐章读一遍**，给这 %d 章各生成摘要和状态：\n%s\n\n"
            "**这是最花钱的一条**（每章一次调用）。"
            % (len(waiting), "、".join(waiting[:10]) + ("…" if len(waiting) > 10 else "")),
            self.ai_workflow_controller.update_memory_batch)

    def check_consistency(self) -> None:
        self._with_confirm(
            "要检查这一章的设定",
            "AI 会把当前章的正文，跟「故事资料」里的角色卡、世界观、体系设定比一遍，\n"
            "把对不上的地方列出来（人物记错事、用了没解锁的能力、前后时间对不上……）。\n\n"
            "**会花钱。**",
            self.ai_workflow_controller.check_consistency)

    def refresh_everything(self) -> None:
        """把项目文件重读一遍：拆完书 / 同步完 / 在别处改了文件之后点这个。

        作者的原话：「我需要的不是那种，先把应用叉掉、再打开，然后出现的」。
        """
        self.project_session.notify_data_changed()
        self.refresh_synced_labels()
        try:
            self.workspace_page.refresh_books()
        except (OSError, AttributeError):
            pass
        self.status_message.setText("已刷新——项目文件重新读过了。")

    def refresh_synced_labels(self) -> None:
        """把「已同步至第 N 章」刷到四个地方：工作区、左栏、故事记忆、表格。"""
        from core import sync_state
        text = sync_state.synced_label(self.project_session.project)
        for widget in (self.workspace_page, self.left_panel,
                       getattr(self, "memory_page", None),
                       getattr(self, "table_page", None)):
            setter = getattr(widget, "set_synced_text", None)
            if callable(setter):
                setter(text)

    def cancel_ai_task(self) -> None:
        self.ai_task_view_controller.cancel()

    # ------------------------------------------------------------------
    # Helpers and lifecycle
    # ------------------------------------------------------------------
    def _require_project(self) -> bool:
        if self.project is None:
            QMessageBox.information(self, "尚未打开项目", "请先打开或新建一个小说项目。")
            return False
        return True

    def _refresh_recent_menu(self) -> None:
        if not hasattr(self, "recent_menu"):
            return
        self.recent_menu.clear()
        paths = self.project_lifecycle_controller.recent_projects()

        if not paths:
            empty = self.recent_menu.addAction("暂无最近项目")
            empty.setEnabled(False)
            return
        for path in paths:
            item = self.recent_menu.addAction(path.name)
            item.setToolTip(str(path))
            item.triggered.connect(lambda _checked=False, p=path: self._load_project(p))

    def _restore_last_project(self) -> None:
        last = self.project_lifecycle_controller.safe_project_path(
            self.config.get("last_project")
        )
        if last is not None:
            self._load_project(last, quiet=True)

    def _update_window_title(self) -> None:
        self.setWindowTitle("Agentorium")

    @staticmethod
    def _safe_name(value: str) -> str:
        return ProjectLifecycleController.safe_name(value)

    @staticmethod
    def _safe_project_path(value: object) -> Path | None:
        """Return a readable Agentorium project path without leaking OS errors."""
        return ProjectLifecycleController.safe_project_path(value)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.editor.is_dirty() and not self.save_current_file(notify=False):
            answer = QMessageBox.question(
                self,
                "文件尚未保存",
                "当前内容保存失败，仍要退出吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        if self.ai_controller.is_running():
            QMessageBox.information(self, "AI 任务仍在进行", "请等待当前 AI 任务完成后再退出，以免丢失生成结果。")
            event.ignore()
            return
        if self.update_controller.is_running():
            self.status_message.setText("更新检查仍在进行，请稍候再退出")
            event.ignore()
            return
        if self.update_download_controller.is_running():
            self.status_message.setText("更新下载仍在进行，请先取消或等待完成")
            event.ignore()
            return
        # 拆书（几段并行）、并册、对话、本地扫描都是**独立的**任务，
        # 不在 ai_controller 里，上面那层拦不住它们。
        # 不拦的后果：窗口关了，claude 子进程还在写 拆文库/、style/技法样本/，
        # 留下一堆半成品（已确证）。
        for label, task in (
            ("拆书", getattr(self, "_ingest_task", None)),
            ("并册", getattr(self, "_merge_task", None)),
            ("对话", getattr(self, "_chat_task", None)),
            ("导出", getattr(self, "_export_task", None)),
            ("本地扫描", getattr(self.workspace_page, "_task", None)),
        ):
            if task is None:
                continue
            try:
                running = (task.is_running() if hasattr(task, "is_running")
                           else task.isRunning())
            except RuntimeError:
                # 任务跑完就已经 deleteLater 了，C++ 对象没了。
                # 不兜住的话关窗口时这一下会抛异常，event.accept() 走不到 —— 窗口关不掉。
                continue
            if running:
                QMessageBox.information(
                    self, "%s 还在进行" % label,
                    "%s 还没跑完。现在退出，它会继续在后台写文件，"
                    "留下一堆半成品。等它跑完再退出。" % label)
                event.ignore()
                return
        # 退出前给所有项目做一次时间戳快照（保留 5 份轮转）。
        # PROJECT.md 承诺的三层备份里，git 那层现在是空的——
        # 先把不依赖 git、也不用你记得点的那层做出来。失败不该拦着退出。
        try:
            from core.backup import rotate_all
            made = rotate_all()
            if made:
                self.status_message.setText("已备份 %d 个项目" % len(made))
        except Exception:  # noqa: BLE001 - 备份失败绝不能拦着退出
            pass

        name = self.project_session.project.name if self.project_session.project else "书稿"
        if session_ending():
            # 关机/注销：此刻**绝不能起 git.exe**。会话拆除中它连 DLL 都初始化不完，
            # Windows 会弹「git.exe - 应用程序无法正常启动(0xc0000142)」的模态框，
            # 而模态框顶住注销（2026-10-06：事件 26 弹框 + 事件 1073 关闭失败）。
            # 那个框拦不住，只能不起——改留条子，下次启动补交（main.py）。
            try:
                from core.autocommit import mark_pending
                mark_pending(self._workspace_root(),
                             "本地自动提交：%s（关机跳过，启动补交）" % name)
            except Exception:  # noqa: BLE001 - 留条失败也不能拦着退出
                pass
        else:
            # 本地 git 提交一次（不推远端）。作者要的是"退得回来"，
            # 而全局规矩是"只在用户要求时提交"——不补这层，真出事时无路可退。
            try:
                from core.autocommit import commit_projects
                commit_projects(self._workspace_root(), "本地自动提交：%s（退出时）" % name)
            except Exception:  # noqa: BLE001 - 提交失败也不能拦着退出
                pass
        self.ai_engine_controller.cleanup()
        event.accept()
