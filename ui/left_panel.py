from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (
    QFrame,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QTreeWidget,
    QTreeWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from core.project import NovelProject, loose_chapter_number
from core.project_data import ProjectDataStore
from core.volumes import group_chapters, load_volumes, volumes_path
from ui.icons import IconTextButton, material_icon, set_button_icon
from ui.theme import colors_for


class LeftPanel(QWidget):
    """Project-local navigation used by the writing and canon routes."""

    file_selected = Signal(str, str)
    new_chapter_requested = Signal()
    new_canon_requested = Signal(str)
    system_importance_requested = Signal(str, str)
    delete_chapter_requested = Signal(str)
    delete_character_requested = Signal(str)
    delete_canon_requested = Signal(str, str)
    new_timeline_requested = Signal()
    toggle_requested = Signal()

    PATH_ROLE = int(Qt.ItemDataRole.UserRole)
    CATEGORY_ROLE = PATH_ROLE + 1
    ICON_ROLE = PATH_ROLE + 2
    IMPORTANCE_ROLE = PATH_ROLE + 3
    SECTION_ROLE = PATH_ROLE + 4  # 「卷 / 幕」的分节行（不是文件，也不是顶级分组）
    STATUS_COLUMN_WIDTH = 94
    COMPACT_TREE_WIDTH = 300
    IMPORTANCE_LABELS = {
        "core": "核心",
        "non_core": "非核心",
        "always": "常驻",
    }
    IMPORTANCE_TOOLTIPS = {
        "core": "核心体系：后续 AI 任务会自动作为重点上下文加载。点击可修改。",
        "non_core": "非核心体系：平时作为背景，AI 扩写时可手动选择。点击可修改。",
        "always": "常驻：始终生效，不参与核心/非核心分级。",
    }
    GROUP_ICONS = {
        "总大纲": "account_tree",
        "写作风格": "stylus",
        "章节": "auto_stories",
        "角色": "group",
        "世界观": "public",
        "体系设定": "bolt",
        "时间线": "schedule",
    }
    # 分组名保持原样，只是不再带 `01 / 02` 这种编号——
    # 编号是模板腔，而且侧栏只有 204 宽，白占地方。
    # 内部标识（label、GROUP_ICONS 的键、CATEGORY_ROLE 的值）一律不动，
    # 免得牵动树的过滤、图标和体系分级逻辑。

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("navigationPanel")
        self.setMinimumWidth(230)
        self._project: NovelProject | None = None
        self._scope = "all"
        self._selected_path: str | None = None
        self._icon_color = "#63748A"
        self._accent_color = "#2F80ED"
        self._muted_color = "#63748A"
        self._compact_mode = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 16, 10, 12)
        layout.setSpacing(10)

        # 标题一行。
        header = QFrame()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        title_box = QVBoxLayout()
        title_box.setSpacing(1)
        title = QLabel("项目资料")
        title.setObjectName("panelTitle")
        self.project_label = QLabel("尚未打开项目")
        self.project_label.setObjectName("mutedLabel")
        title_box.addWidget(title)
        title_box.addWidget(self.project_label)
        # 「已同步至第 N 章」——挂在项目名底下，一眼看见同步到哪了。
        self.synced_label = QLabel("尚未同步")
        self.synced_label.setObjectName("mutedLabel")
        title_box.addWidget(self.synced_label)
        header_layout.addLayout(title_box, 1)

        toggle_btn = QToolButton()
        toggle_btn.setObjectName("panelToggleButton")
        set_button_icon(toggle_btn, "close", size=17)
        toggle_btn.setToolTip("收起整个资料栏（Ctrl+Shift+L 可恢复）")
        toggle_btn.clicked.connect(self.toggle_requested)
        header_layout.addWidget(toggle_btn)
        layout.addWidget(header)

        # 两个「新建」单独一行。原来它们跟标题、✕ 挤在一行里，
        # 侧栏只有 204 宽，「+ 章节」被压得只剩半个字。
        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(6)

        add_btn = IconTextButton("add", "章节")
        add_btn.setObjectName("smallAccentButton")
        add_btn.setToolTip("新建章节")
        add_btn.setMinimumWidth(96)
        add_btn.clicked.connect(self.new_chapter_requested)
        actions.addWidget(add_btn, 1)

        canon_add_btn = QToolButton()
        canon_add_btn.setObjectName("smallAccentButton")
        canon_add_btn.setText("新建资料")
        canon_add_btn.setToolTip("新建角色、世界观、体系设定或时间线")
        canon_add_btn.setMinimumWidth(96)
        canon_menu = QMenu(canon_add_btn)
        for kind, label in (
            ("character", "新建角色"),
            ("world", "新建世界观条目"),
            ("power", "新建体系设定"),
            ("timeline", "新建时间线"),
        ):
            action = canon_menu.addAction(label)
            action.triggered.connect(
                lambda _checked=False, entry_kind=kind: self.new_canon_requested.emit(
                    entry_kind
                )
            )
        canon_add_btn.setMenu(canon_menu)
        canon_add_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        actions.addWidget(canon_add_btn, 1)
        layout.addLayout(actions)

        # 搜索 + 一键收起。
        # 分组一展开就是 87 章、15 个人物，翻起来要命——给一个总开关。
        self.search = QLineEdit()
        self.search.setObjectName("navigationSearch")
        self.search.setPlaceholderText("搜索章节、角色或设定")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter_tree)

        self.fold_btn = QToolButton()
        self.fold_btn.setObjectName("smallAccentButton")
        self.fold_btn.setText("全收起")
        self.fold_btn.setToolTip("把所有分组收起来（再点一次全部展开）")
        self.fold_btn.setMinimumWidth(58)
        self.fold_btn.clicked.connect(self._toggle_all_groups)

        search_row = QHBoxLayout()
        search_row.setContentsMargins(0, 0, 0, 0)
        search_row.setSpacing(6)
        search_row.addWidget(self.search, 1)
        search_row.addWidget(self.fold_btn)
        layout.addLayout(search_row)

        self.tree = QTreeWidget()
        self.tree.setObjectName("projectTree")
        self.tree.setHeaderHidden(True)
        self.tree.setColumnCount(2)
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.tree.setColumnWidth(1, self.STATUS_COLUMN_WIDTH)
        # 展开逻辑：点那个倒三角，单击即可；单击整行是选中。
        # 原来 setRootIsDecorated(False) 把箭头藏了，只能双击展开——
        # 作者要的是点三角、而且过渡自然。setAnimated 让展开/收起是滑开的，不是跳开。
        self.tree.setIndentation(14)
        self.tree.setRootIsDecorated(True)
        self.tree.setAnimated(True)
        self.tree.setExpandsOnDoubleClick(False)
        self.tree.setIconSize(QSize(18, 18))
        self.tree.setAnimated(True)
        self.tree.setUniformRowHeights(True)
        self.tree.itemClicked.connect(self._on_item_clicked)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._show_context_menu)
        layout.addWidget(self.tree, 1)

        self._nav_hint = QLabel("单击打开 · 点击体系状态可设置加载策略")
        self._nav_hint.setObjectName("navHint")
        self._nav_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._nav_hint)
        self._update_tree_layout()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_tree_layout()

    def _toggle_all_groups(self) -> None:
        """一键收 / 放所有分组。

        作者的原话："它在总章节下面 87，那我就得翻 87 下；
        它那个人物有 15 个，那我就得一直往下翻。" —— 分组一多，树就失控了。
        """
        items = [item for item in self._iter_items() if item.childCount()]
        any_open = any(item.isExpanded() for item in items)
        for item in items:
            item.setExpanded(not any_open)
        self.fold_btn.setText("全展开" if any_open else "全收起")

    def _update_tree_layout(self) -> None:
        """Give document titles the full row when the navigation is narrow."""
        if not hasattr(self, "tree"):
            return
        compact = self.tree.width() < self.COMPACT_TREE_WIDTH
        if compact == self._compact_mode:
            return
        self._compact_mode = compact
        self.tree.setColumnHidden(1, compact)
        if not compact:
            self.tree.setColumnWidth(1, self.STATUS_COLUMN_WIDTH)
        if hasattr(self, "_nav_hint"):
            self._nav_hint.setText(
                "单击打开 · 右键体系设定可设置加载策略"
                if compact
                else "单击打开 · 点击体系状态可设置加载策略"
            )

    def set_scope(self, scope: str) -> None:
        """左栏显示哪几组。

        原来只有 all / canon 两档，canon 只是"去掉章节组"——于是
        「写作台」和「故事资料」是同一个页面、只差一个分组，作者看着就是重复。
        现在分清楚：
          · writing —— 只有章节。这一页是写稿的地方。
          · canon   —— 只有资料（大纲 / 文风 / 角色 / 世界观 / 体系 / 时间线）。
          · all     —— 全给（给"我全都要"的场合）。
        """
        self._scope = scope if scope in {"all", "writing", "canon"} else "all"
        self.set_project(self._project)

    def set_theme(self, config: dict | None = None) -> None:
        colors = colors_for(config)
        self._icon_color = colors["muted_text_color"]
        self._accent_color = colors["accent_color"]
        self._muted_color = colors["muted_text_color"]
        for item in self._iter_items():
            if item.data(0, self.PATH_ROLE):
                item.setIcon(0, material_icon("description", self._icon_color, 18))
                if item.data(0, self.CATEGORY_ROLE) == "体系设定":
                    self._apply_importance_appearance(item)
                continue
            icon_name = item.data(0, self.ICON_ROLE) or "folder"
            item.setIcon(0, material_icon(str(icon_name), self._icon_color, 18))
            if item.data(0, self.SECTION_ROLE):
                item.setForeground(0, QBrush(QColor(self._muted_color)))

    def set_synced_text(self, text: str) -> None:
        self.synced_label.setText(text)

    def set_project(self, project: NovelProject | None) -> None:
        same_project = bool(
            self._project
            and project
            and self._project.root.resolve() == project.root.resolve()
        )
        selected_path = self._selected_path if same_project else None
        self._project = project
        self._selected_path = selected_path
        # 重建树之前，把「哪些分组是展开的」和「滚到哪了」都记下来。
        # 不记的后果：组全收起 + 滚动归零 —— 你点开第 23 章，看到的却是最上面 1–9 章。
        # 作者的原话：「切到 23 章，它就会自动滚到 1~9 章的列表，这个真的很烦。」
        expanded_groups: dict[str, bool] = {}
        for item in self._iter_items():
            if item.childCount():
                expanded_groups[self._group_key(item)] = item.isExpanded()
        scroll_position = self.tree.verticalScrollBar().value()
        self.tree.clear()
        self.project_label.setText(project.name if project else "尚未打开项目")
        if project is None:
            return

        store = ProjectDataStore(project)
        groups: list[tuple[str, list[Path]]] = [
            (
                "总大纲",
                [
                    project.outline_dir / "main_arc.md",
                    project.outline_dir / "future_plan.md",
                ],
            ),
            ("写作风格", [store.style_guide_path]),
            ("章节", store.list_chapters()),
            ("角色", store.list_characters()),
            ("世界观", store.list_world()),
            ("体系设定", store.list_power()),
            ("时间线", [project.canon_dir / "timeline.md"]),
        ]
        if self._scope == "writing":
            groups = [groups[2]]                       # 只留「章节」
        elif self._scope == "canon":
            groups = [groups[index] for index in (0, 1, 3, 4, 5, 6)]
        category_map = {"体系设定": "体系设定"}
        for label, paths in groups:
            existing = [path for path in paths if path.exists()]
            core_count = (
                len(store.list_core_systems()) if label == "体系设定" else 0
            )
            suffix = f" · 核心 {core_count}" if label == "体系设定" else ""
            group_text = self._group_title(label, len(existing), suffix)
            group = QTreeWidgetItem([group_text, ""])
            group.setData(0, self.CATEGORY_ROLE, category_map.get(label, label))
            group.setData(0, self.ICON_ROLE, self.GROUP_ICONS.get(label, "folder"))
            group.setFlags(group.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            group.setFirstColumnSpanned(True)
            group_font = group.font(0)
            group_font.setWeight(QFont.Weight.DemiBold)
            group.setFont(0, group_font)
            group.setIcon(0, material_icon(self.GROUP_ICONS.get(label, "folder"), self._icon_color, 18))
            self.tree.addTopLevelItem(group)
            if label == "章节":
                self._fill_chapter_nodes(group, store, existing, expanded_groups)
            else:
                for path in existing:
                    child = self._add_document_item(group, store, path, label, category_map)
                    if child.data(0, self.IMPORTANCE_ROLE):
                        self._apply_importance_appearance(child)
            # 展开状态照刷新前恢复；第一次建树才默认收起
            # （一展开就是 150 章、19 个人物，全摊开等于没法用）。
            group_key = group.data(0, self.CATEGORY_ROLE) or ""
            group.setExpanded(bool(expanded_groups.get(group_key, False)))
        self._filter_tree(self.search.text())
        self._restore_selection()
        self._update_tree_layout()
        # 滚动位置必须**等布局算完**再设：clear() 之后 maximum 还是 0，
        # 当场 setValue 会被钳成 0 —— 这就是上一版没修好的原因。
        QTimer.singleShot(
            0, lambda pos=scroll_position: self.tree.verticalScrollBar().setValue(pos))
        if hasattr(self, "fold_btn"):
            self.fold_btn.setText("全展开")

    # ---- 卷 / 幕（`outline/volumes.json`）---------------------------------

    def _iter_items(self):
        """深度优先走一遍整棵树：顶级分组 → 卷 → 幕 → 章。"""

        def walk(parent):
            for index in range(parent.childCount()):
                child = parent.child(index)
                yield child
                yield from walk(child)

        return walk(self.tree.invisibleRootItem())

    def _group_key(self, item: QTreeWidgetItem) -> str:
        return item.data(0, self.CATEGORY_ROLE) or item.text(0)

    def _add_section_item(
        self, parent: QTreeWidgetItem, label: str, note: str, key: str, icon: str
    ) -> QTreeWidgetItem:
        """卷 / 幕 的分节行：不可选、加粗、颜色压暗。"""
        item = QTreeWidgetItem([label, ""])
        item.setData(0, self.CATEGORY_ROLE, key)
        item.setData(0, self.SECTION_ROLE, True)
        item.setData(0, self.ICON_ROLE, icon)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
        item.setFirstColumnSpanned(True)
        font = item.font(0)
        font.setWeight(QFont.Weight.Medium)
        item.setFont(0, font)
        item.setForeground(0, QBrush(QColor(self._muted_color)))
        if note:
            item.setToolTip(0, note)
        item.setIcon(0, material_icon(icon, self._icon_color, 18))
        parent.addChild(item)
        return item

    def _add_document_item(
        self, parent: QTreeWidgetItem, store: ProjectDataStore, path: Path,
        label: str, category_map: dict | None = None,
    ) -> QTreeWidgetItem:
        """一个文件条目（章 / 人物 / 设定 / 大纲…都走它）。"""
        category_map = category_map or {}
        display_name = store.chapter_display_name(path)
        status = ""
        importance = ""
        if label == "体系设定":
            if store.is_core_power_path(path):
                importance = "always"
            else:
                importance = store.system_metadata(path).get("importance")
            status = self.IMPORTANCE_LABELS.get(importance, "非核心")
        child = QTreeWidgetItem([display_name, status])
        child.setTextAlignment(
            0,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        )
        child.setTextAlignment(
            1,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        )
        child.setToolTip(0, str(path))
        child.setData(0, self.PATH_ROLE, str(path))
        child.setData(0, self.CATEGORY_ROLE, category_map.get(label, label))
        if importance:
            child.setData(0, self.IMPORTANCE_ROLE, importance)
        child.setIcon(0, material_icon("description", self._icon_color, 18))
        parent.addChild(child)
        return child

    def _fill_chapter_nodes(
        self, group: QTreeWidgetItem, store: ProjectDataStore,
        chapters: list[Path], expanded_groups: dict[str, bool],
    ) -> None:
        """「章节」组：有卷幕表就分成 卷 → 幕 → 章；**没有就照旧扁平**。"""
        project = self._project
        volumes = load_volumes(volumes_path(project.outline_dir)) if project else []
        blocks = group_chapters(
            volumes, chapters, lambda path: loose_chapter_number(Path(path).stem)
        )
        for index, (volume, acts) in enumerate(blocks):
            if volume is None:
                # 没有卷幕表 → 照旧平铺（老项目一行都不用改）；
                # 有卷幕表但这一块落在表外 → 置顶的那块（作品简介这类）照旧平铺，
                # 末尾那块（新写的、表还没跟上）挂一个「未分卷」。
                parent = group
                if volumes and index > 0:
                    loose_key = "章节/__unassigned__"
                    parent = self._add_section_item(
                        group, "未分卷", "", loose_key, "folder"
                    )
                    parent.setExpanded(bool(expanded_groups.get(loose_key, True)))
                for _, paths in acts:
                    for path in paths:
                        self._add_document_item(parent, store, path, "章节")
                continue
            volume_key = f"章节/{volume.id}"
            volume_item = self._add_section_item(
                group, volume.label, volume.note, volume_key, "auto_stories"
            )
            volume_item.setExpanded(bool(expanded_groups.get(volume_key, index == 0)))
            if volume.epigraph or volume.epigraph_file:
                # 卷首语（扉页）——⭐ 做成"一页"：**点得开、看得到完整**
                # （作者 2026-10-05：原来那行又小又淡，看不清；要"单独做成一页正文"。）
                epi_path = None
                if volume.epigraph_file:
                    candidate = project.root / volume.epigraph_file
                    if candidate.is_file():
                        epi_path = candidate
                text = volume.epigraph or "扉页"
                item = QTreeWidgetItem([text, ""])
                item.setFirstColumnSpanned(True)
                item.setIcon(0, material_icon("format_quote", self._icon_color, 18))
                item.setToolTip(0, text)
                if epi_path is not None:
                    item.setData(0, self.PATH_ROLE, str(epi_path))
                    item.setData(0, self.CATEGORY_ROLE, "章节")
                    item.setToolTip(0, text + "\n\n" + str(epi_path))
                parent = volume_item
                parent.addChild(item)
            for act, paths in acts:
                parent = volume_item
                if act is not None:
                    act_key = f"章节/{volume.id}/{act.id}"
                    parent = self._add_section_item(
                        volume_item, act.label, act.note, act_key, "folder"
                    )
                    parent.setExpanded(bool(expanded_groups.get(act_key, True)))
                for path in paths:
                    self._add_document_item(parent, store, path, "章节")

    def select_path(self, path: Path) -> None:
        target = str(Path(path))
        self._selected_path = target
        for item in self._iter_items():
            if item.data(0, self.PATH_ROLE) == target:
                self.tree.setCurrentItem(item)
                self.tree.scrollToItem(item)
                self._on_item_clicked(item, 0)
                return

    def reveal_path(self, path: Path | str) -> bool:
        """Select and scroll to a file without emitting a new open request."""
        target = str(Path(path))
        self._selected_path = target
        for item in self._iter_items():
            if item.data(0, self.PATH_ROLE) == target:
                self.tree.setCurrentItem(item)
                self.tree.scrollToItem(item)
                return True
        return False

    def _restore_selection(self) -> None:
        if not self._selected_path:
            return
        target = self._selected_path
        for item in self._iter_items():
            if item.data(0, self.PATH_ROLE) == target and not item.isHidden():
                # 只设选中，**不要滚**。这里是「刷新之后把选中恢复回去」，
                # 一滚整个列表就滑一下——作者报的原话：「点第二章，整个列表都会滑动一下」。
                self.tree.setCurrentItem(item)
                return

    def _on_item_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        path_str = item.data(0, self.PATH_ROLE)
        if path_str:
            self._selected_path = str(path_str)
            category = item.data(0, self.CATEGORY_ROLE) or ""
            if (
                category == "体系设定"
                and column == 1
                and not self._compact_mode
            ):
                if item.data(0, self.IMPORTANCE_ROLE) == "always":
                    return
                position = self.tree.viewport().mapToGlobal(
                    self.tree.visualItemRect(item).bottomRight()
                )
                self._show_importance_menu(item, position)
                return
            self.file_selected.emit(category, path_str)

    def _show_context_menu(self, position) -> None:
        item = self.tree.itemAt(position)
        if item is None:
            return
        path_str = item.data(0, self.PATH_ROLE)
        category = item.data(0, self.CATEGORY_ROLE) or ""
        if not path_str and category in {"角色", "世界观", "体系设定", "时间线"}:
            menu = QMenu(self.tree)
            labels = {
                "角色": "character",
                "世界观": "world",
                "体系设定": "power",
                "时间线": "timeline",
            }
            new_action = menu.addAction(
                "新建时间线" if category == "时间线" else f"新建{category}条目"
            )
            new_action.triggered.connect(
                lambda _checked=False, entry_kind=labels[category]: (
                    self.new_timeline_requested.emit()
                    if entry_kind == "timeline"
                    else self.new_canon_requested.emit(entry_kind)
                )
            )
            menu.exec(self.tree.viewport().mapToGlobal(position))
            return
        if path_str and category == "体系设定":
            self._show_importance_menu(
                item, self.tree.viewport().mapToGlobal(position)
            )
            return
        if not path_str or category not in {"章节", "角色", "世界观", "时间线"}:
            return
        menu = QMenu(self.tree)
        delete_action = menu.addAction("移入回收站")
        if category == "章节":
            delete_action.triggered.connect(
                lambda _checked=False, path=str(path_str): self.delete_chapter_requested.emit(path)
            )
        else:
            if category == "角色":
                delete_action.triggered.connect(
                    lambda _checked=False, path=str(path_str): self.delete_character_requested.emit(path)
                )
            else:
                delete_action.triggered.connect(
                    lambda _checked=False, path=str(path_str), value=category: self.delete_canon_requested.emit(
                        value, path
                    )
                )
        menu.exec(self.tree.viewport().mapToGlobal(position))

    def _show_importance_menu(self, item: QTreeWidgetItem, global_position) -> None:
        """Show explicit loading choices instead of silently flipping state."""
        path_str = item.data(0, self.PATH_ROLE)
        if not path_str:
            return
        menu = QMenu(self.tree)
        current = item.data(0, self.IMPORTANCE_ROLE) or "non_core"
        if current == "always":
            fixed = menu.addAction("常驻规则 · 始终加载")
            fixed.setEnabled(False)
            menu.exec(global_position)
            return

        title = menu.addAction("AI 加载策略")
        title.setEnabled(False)
        menu.addSeparator()
        core_action = menu.addAction("核心 · 自动作为重点上下文加载")
        optional_action = menu.addAction("非核心 · 扩写时手动选择")
        for action, importance in (
            (core_action, "core"),
            (optional_action, "non_core"),
        ):
            action.setCheckable(True)
            action.setChecked(current == importance)
            action.triggered.connect(
                lambda _checked=False, path=str(path_str), value=importance: self._emit_system_importance(
                    path, value
                )
            )
        menu.addSeparator()
        delete_action = menu.addAction("移入回收站")
        delete_action.triggered.connect(
            lambda _checked=False, path=str(path_str): self.delete_canon_requested.emit(
                "体系设定", path
            )
        )
        menu.exec(global_position)

    def refresh_system_importance(self) -> None:
        """Refresh only system badges and counts while preserving tree state."""
        if self._project is None:
            return
        store = ProjectDataStore(self._project)
        root = self.tree.invisibleRootItem()
        for index in range(root.childCount()):
            group = root.child(index)
            if group.data(0, self.CATEGORY_ROLE) != "体系设定":
                continue
            for child_index in range(group.childCount()):
                child = group.child(child_index)
                path_str = child.data(0, self.PATH_ROLE)
                if not path_str:
                    continue
                path = Path(path_str)
                importance = (
                    "always"
                    if store.is_core_power_path(path)
                    else store.system_metadata(path).get("importance", "non_core")
                )
                child.setData(0, self.IMPORTANCE_ROLE, importance)
                child.setText(1, self.IMPORTANCE_LABELS.get(importance, "非核心"))
                self._apply_importance_appearance(child)
            self._update_system_group_label(group)

    @staticmethod
    def _group_title(label: str, count: int, suffix: str = "") -> str:
        """分组的显示标题：名字 + 数量，不带编号。"""
        return f"{label}   {count}{suffix}"

    def _update_system_group_label(self, group: QTreeWidgetItem) -> None:
        core_count = sum(
            group.child(index).data(0, self.IMPORTANCE_ROLE) == "core"
            for index in range(group.childCount())
        )
        group.setText(
            0,
            self._group_title("体系设定", group.childCount(), f" · 核心 {core_count}"),
        )

    def _apply_importance_appearance(self, item: QTreeWidgetItem) -> None:
        importance = item.data(0, self.IMPORTANCE_ROLE) or "non_core"
        is_emphasized = importance in {"core", "always"}
        color = self._accent_color if is_emphasized else self._muted_color
        item.setForeground(1, QBrush(QColor(color)))
        item.setToolTip(1, self.IMPORTANCE_TOOLTIPS.get(importance, ""))
        # Keep status metrics identical to the title column.  A bold status
        # changes the font ascent and makes the right column appear to float
        # above the document title, especially in compact rows.
        font = item.font(0)
        font.setWeight(QFont.Weight.Normal)
        item.setFont(1, font)

    def _emit_system_importance(self, path_str: str, importance: str) -> None:
        """Emit a canonical path so the receiving window can persist reliably."""
        path = Path(path_str)
        if self._project is not None and not path.is_absolute():
            project_path = self._project.root / path
            path = project_path if project_path.exists() else path.resolve()
        self.system_importance_requested.emit(str(path), importance)

    def _filter_tree(self, query: str) -> None:
        needle = query.strip().casefold()

        def visit(item: QTreeWidgetItem) -> int:
            """返回这一支底下有多少条可见的**文件**条目（分组 / 卷 / 幕 为 0 就整支藏起来）。"""
            if item.data(0, self.PATH_ROLE):
                visible = not needle or needle in item.text(0).casefold()
                item.setHidden(not visible)
                return int(visible)
            visible_children = 0
            for index in range(item.childCount()):
                visible_children += visit(item.child(index))
            item.setHidden(bool(needle) and visible_children == 0)
            if needle and visible_children:
                item.setExpanded(True)
            return visible_children

        root = self.tree.invisibleRootItem()
        for index in range(root.childCount()):
            visit(root.child(index))
        self._restore_selection()
