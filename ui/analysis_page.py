"""分析：把「表格 / 关系图 / 框架图 / 工作区」几样收在一页里。

为什么要收：它们本来各占侧栏一项，加上原有的六项，侧栏成了一条十项长单，
**看不出层次**——作者说"摸不清这个面板能干什么"。
这几样是一类东西（都是"看数据、看结构"，不是"写正文"），合成一页，
侧栏短了，含义也清楚了。

**框架图**（2026-10-04 加）就放在「关系图」旁边：关系图看**人跟人的网**，
框架图看**线跟时间的路**——两条挨着看，一个是横向的、一个是纵向的。
"""
from __future__ import annotations

from PySide6.QtWidgets import QTabWidget, QVBoxLayout, QWidget


class AnalysisPage(QWidget):
    def __init__(self, table_page, relation_page, workspace_page,
                 swimlane_page=None, parent=None):
        super().__init__(parent)
        self.setObjectName("pageSurface")
        self.table_page = table_page
        self.relation_page = relation_page
        self.workspace_page = workspace_page
        self.swimlane_page = swimlane_page

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 10, 8, 10)
        root.setSpacing(0)
        self.tabs = QTabWidget()
        self.tabs.setObjectName("analysisTabs")
        self.tabs.addTab(table_page, "表格")
        self.tabs.addTab(relation_page, "关系图")
        if swimlane_page is not None:
            self.tabs.addTab(swimlane_page, "框架图")
        self.tabs.addTab(workspace_page, "工作区")
        root.addWidget(self.tabs, 1)

    def refresh(self, project=None) -> None:
        """进这一页时把几样都刷新一遍——都在手上，刷齐了再切最省事。"""
        self.table_page.refresh(project)
        self.relation_page.refresh(project)
        if self.swimlane_page is not None:
            self.swimlane_page.refresh(project)
