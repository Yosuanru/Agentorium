"""表格视图：把项目与拆文库里的结构摊成表。

设计取向：**正文逐字读，结构一眼扫。**
人物、伏笔、设定、线索轨迹、节奏曲线——这些东西在编辑器里是读不出来的，
摊成表才看得见。所以这一页不讲究，只求清楚：列宽合理、能排序、能导出。
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (QComboBox, QFileDialog, QHBoxLayout,
                               QLabel, QMessageBox, QPushButton, QTableView,
                               QTabWidget, QVBoxLayout, QWidget)

from core import tables


MAX_COL_WIDTH = 340          # 单列宽度上限，超过就省略


def _model(cols: list[str], rows: list[list[str]]) -> QStandardItemModel:
    m = QStandardItemModel()
    m.setHorizontalHeaderLabels(cols)
    for r in rows:
        items = [QStandardItem(str(c)) for c in r]
        for it in items:
            it.setEditable(False)
        m.appendRow(items)
    return m


class TablePage(QWidget):
    """一整页的表。数据来自 core/tables。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("pageSurface")
        self._project = None
        self._models: dict[str, QStandardItemModel] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 14)
        root.setSpacing(10)

        head = QHBoxLayout()
        title = QLabel("表格")
        title.setObjectName("pageTitle")
        head.addWidget(title)
        head.addSpacing(12)
        head.addWidget(QLabel("拆文库："))
        self.book_box = QComboBox()
        self.book_box.setMinimumWidth(160)
        self.book_box.currentTextChanged.connect(lambda _: self.refresh(self._project))
        head.addWidget(self.book_box)
        head.addStretch(1)
        # 「已同步至第 N 章」——和故事资料、故事记忆、分析页上是同一个数。
        self.synced_label = QLabel("尚未同步")
        self.synced_label.setObjectName("mutedLabel")
        head.addWidget(self.synced_label)
        self.hint = QLabel("")
        self.hint.setObjectName("mutedLabel")
        head.addWidget(self.hint)
        export = QPushButton("导出表格")
        export.setObjectName("secondaryButton")
        export.clicked.connect(self.export_current)
        head.addWidget(export)
        root.addLayout(head)

        self.tabs = QTabWidget()
        self.views: dict[str, QTableView] = {}
        for key, label in (("character", "人物"), ("foreshadow", "伏笔"),
                           ("canon", "设定"), ("thread", "线索轨迹"),
                           ("rhythm", "节奏曲线")):
            view = QTableView()
            view.setObjectName("tableView")
            view.setAlternatingRowColors(True)
            view.setSortingEnabled(True)
            view.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
            view.setWordWrap(False)
            view.setTextElideMode(Qt.TextElideMode.ElideRight)
            view.horizontalHeader().setStretchLastSection(False)
            view.verticalHeader().setVisible(False)
            self.views[key] = view
            self.tabs.addTab(view, label)
        root.addWidget(self.tabs, 1)

        self._reload_books()

    # ── 数据 ────────────────────────────────────────────────
    def _reload_books(self):
        books = tables.corpus_books()
        self.book_box.blockSignals(True)
        self.book_box.clear()
        self.book_box.addItems(books)
        self.book_box.blockSignals(False)

    def set_synced_text(self, text: str) -> None:
        self.synced_label.setText(text)

    def _source_root(self, project, book):
        """人物 / 伏笔 / 设定读谁的数据——**跟着「拆文库」下拉走**。

        下拉选的是哪本书，这几张表就摊哪本书的。拆解成果收尾时同步进
        `panel/projects/{书名}/`，所以按书名去那儿取。
        取不到同名项目就退回当前打开的项目——免得把作者自己在写的书
        （拆文库里没有同名的那本）的表顶成空的。
        """
        if project is not None and book == Path(project.root).name:
            return Path(project.root)
        root = tables.project_root(book)
        if root is not None:
            return root
        return Path(project.root) if project is not None else None

    def refresh(self, project=None):
        # 五张表都跟着「拆文库」下拉走：人物 / 伏笔 / 设定读那本书对应的项目
        # （见 `_source_root`），线索轨迹 / 节奏曲线直接从拆文库的原文算。
        # 只在**换了项目**时把下拉框拨到与项目同名的那本，免得出现
        # 「人在天不应、表里是龙族」这种串书；同一个项目里，作者自己在下拉框
        # 选了哪本就一直用哪本——否则每选一次都被拨回来，框等于锁死。
        # （关系图那边一直是这个写法，这里以前把它写成了每次 refresh 都强制拨。）
        changed_project = project is not self._project
        self._project = project
        if project is not None and changed_project:
            want = Path(project.root).name
            if want and self.book_box.findText(want) >= 0:
                self.book_box.blockSignals(True)
                self.book_box.setCurrentText(want)
                self.book_box.blockSignals(False)
        book = self.book_box.currentText()
        src = self._source_root(project, book)
        specs = {
            "character": tables.character_rows(src) if src else (["人物", "身份", "性格", "目标", "备注"], []),
            "foreshadow": tables.foreshadow_rows(src) if src else (["伏笔", "首现", "最近出现", "计划回收", "已回收", "状态", "说明"], []),
            "canon": tables.canon_rows(src) if src else (["类别", "条目", "字数", "前 40 字"], []),
            "thread": tables.thread_rows(book) if book else (["线索", "首现", "末现", "出现章数", "最大断档", "出现轨迹"], []),
            "rhythm": tables.rhythm_rows(book) if book else (["章节", "平均字数", "对话占比", "战斗词/万", "情绪词/万"], []),
        }
        for key, (cols, rows) in specs.items():
            self._models[key] = _model(cols, rows)
            view = self.views[key]
            view.setModel(self._models[key])
            view.resizeColumnsToContents()
            # 列宽封顶：不封的话「出现轨迹」那种长列会撑出上千像素，
            # 底下拖一条长得离谱的横向滚动条——作者说这栏做得不好。
            # 超宽就截断加省略号，鼠标停上去看全文。
            for c in range(self._models[key].columnCount()):
                if view.columnWidth(c) > MAX_COL_WIDTH:
                    view.setColumnWidth(c, MAX_COL_WIDTH)
        n = {k: v.rowCount() for k, v in self._models.items()}
        self.hint.setText("人物 %d · 伏笔 %d · 设定 %d · 线索 %d · 节奏 %d"
                          % (n["character"], n["foreshadow"], n["canon"],
                             n["thread"], n["rhythm"]))

    # ── 导出 ────────────────────────────────────────────────
    def export_current(self):
        idx = self.tabs.currentIndex()
        key = list(self.views)[idx]
        model = self._models.get(key)
        if model is None or model.rowCount() == 0:
            QMessageBox.information(self, "没有数据", "这张表现在是空的。")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "导出表格", str(Path.home() / ("%s.xlsx" % self.tabs.tabText(idx))),
            "Excel 工作簿 (*.xlsx);;CSV (*.csv)")
        if not path:
            return
        try:
            if path.lower().endswith(".csv"):
                self._write_csv(path, model)
            else:
                self._write_xlsx(path, key)
        except ImportError:
            QMessageBox.warning(self, "缺一个库",
                                "导出 xlsx 需要 openpyxl。\n"
                                "装上就行：python -m pip install openpyxl\n"
                                "或者改存 CSV。")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "导出失败", str(exc))
        else:
            QMessageBox.information(self, "导出好了", path)

    @staticmethod
    def _write_csv(path: str, model) -> None:
        import csv
        with open(path, "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.writer(fh)
            w.writerow([model.headerData(c, Qt.Orientation.Horizontal)
                        for c in range(model.columnCount())])
            for r in range(model.rowCount()):
                w.writerow([model.item(r, c).text() if model.item(r, c) else ""
                            for c in range(model.columnCount())])

    def _write_xlsx(self, path: str, key: str) -> None:
        """一个工作簿，每张表一个 sheet——把整页一次带走。"""
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font
        wb = Workbook()
        wb.remove(wb.active)
        for k, view in self.views.items():
            m = self._models.get(k)
            if m is None:
                continue
            ws = wb.create_sheet(self.tabs.tabText(list(self.views).index(k))[:28])
            ws.append([m.headerData(c, Qt.Orientation.Horizontal)
                       for c in range(m.columnCount())])
            for c in range(1, m.columnCount() + 1):
                ws.cell(row=1, column=c).font = Font(bold=True)
            for r in range(m.rowCount()):
                ws.append([m.item(r, c).text() if m.item(r, c) else ""
                           for c in range(m.columnCount())])
            for c in range(1, m.columnCount() + 1):
                ws.column_dimensions[ws.cell(row=1, column=c).column_letter].width = 18
            for row in ws.iter_rows(min_row=2):
                for cell in row:
                    cell.alignment = Alignment(vertical="top", wrap_text=False)
        wb.save(path)
