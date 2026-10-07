"""工作区浏览：把 E 盘上的整个仓库连进面板。

面板原来只认「项目」——你新写的稿子。可真正在用的东西大半在项目外面：
拆文库、技法样本十册、refs 里的参考书……

两个标签页：

  · **参考书** —— 丢一本 TXT 进来，本地切好章、按章一一对应地打开、点一下就拆。
    作者的原话是「我随便丢个 TXT，能直接打开，章节分好就一一对应，然后让它拆书都行」。
  · **工作区文件** —— 整个仓库的目录树，找技法样本、翻规则用。

两页都**只读**，不在这里改稿——要改稿回写作台，要改规则改 CLAUDE.md。
这样不会出现「面板里改了一份、真身还是旧的」这种对不上的事。
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QComboBox, QFileDialog, QHBoxLayout, QLabel,
                               QListWidget, QListWidgetItem, QMessageBox,
                               QProgressBar, QPushButton, QSpinBox, QSplitter,
                               QTabWidget, QTextBrowser, QTreeWidget,
                               QTreeWidgetItem, QVBoxLayout, QWidget)

from core import ingest
from core.books import Book, discover_books
from core.paths import workspace_root
from ui.ai_task_runner import AITask

WORKSPACE = workspace_root()          # 打包后也找得对，见 core/paths.py

SKIP_DIRS = {".git", "__pycache__", ".venv", "node_modules", "corpus",
             "_analysis_cache", "playwright-mcp", "_downloads", "_scratch"}
SKIP_EXT = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".woff", ".woff2", ".ttf",
            ".otf", ".exe", ".dll", ".pyc", ".zip", ".tar", ".gz"}
MAX_BYTES = 400_000


class WorkspacePage(QWidget):
    ingest_requested = Signal(str, str, int, int, int)   # (书目录, 档位, 起始章, 结束章, 分几段)
    cancel_requested = Signal()                          # 「拆书/并册跑到一半想停」

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("pageSurface")
        self._book: Book | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 14)
        root.setSpacing(10)

        head = QHBoxLayout()
        title = QLabel("工作区")
        title.setObjectName("pageTitle")
        head.addWidget(title)
        head.addSpacing(12)
        hint = QLabel("%s —— 只读；要改稿回写作台，要改规则改 CLAUDE.md" % WORKSPACE)
        hint.setObjectName("mutedLabel")
        head.addWidget(hint, 1)
        # 「已同步至第 N 章」（当前项目）——和故事资料、故事记忆上是同一个数。
        self.synced_label = QLabel("尚未同步")
        self.synced_label.setObjectName("mutedLabel")
        head.addWidget(self.synced_label)
        root.addLayout(head)

        # 快捷入口：技法样本十三册在 style/ 下、拆文库在拆文库下、lore 六册在 lore/ 下，
        # 作者的原话是"没有你之前粗拆出来那些感情线……我没找到"——
        # 东西在，只是没有门。这里给几扇门。
        shortcuts = QHBoxLayout()
        shortcuts.setSpacing(6)
        shortcuts.addWidget(QLabel("直达："))
        for label, rel in (("技法样本（十三册）", "style/技法样本"),
                           ("lore 素材库", "lore"),
                           ("拆文库", "拆文库"),
                           ("参考书 refs", "refs/_inbox"),
                           ("项目规则", "")):
            btn = QPushButton(label)
            btn.setObjectName("ghostButton")
            btn.clicked.connect(lambda _c=False, r=rel: self._jump(r))
            shortcuts.addWidget(btn)
        shortcuts.addStretch(1)
        root.addLayout(shortcuts)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_books_tab(), "参考书")
        self.tabs.addTab(self._build_files_tab(), "工作区文件")
        # 切回「工作区文件」就重扫一遍——那棵树原本只在开面板时拍一张快照，
        # 之后往仓库里加的东西（新册、新样本、lore 那六册）不重扫就不出现。
        self.tabs.currentChanged.connect(self._on_tab_changed)
        root.addWidget(self.tabs, 1)

        self.refresh_books()

    # ── 参考书页 ────────────────────────────────────────────
    def _build_books_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 10, 0, 0)
        layout.setSpacing(8)

        tools = QHBoxLayout()
        tools.setSpacing(8)
        tools.addWidget(QLabel("参考书："))
        self.book_picker = QComboBox()
        self.book_picker.setMinimumWidth(220)   # 长书名不再截
        self.book_picker.currentIndexChanged.connect(self._on_book_changed)
        tools.addWidget(self.book_picker)
        self.import_btn = QPushButton("导入 TXT…")
        self.import_btn.setToolTip("选一个 txt，本地切好章、入库——这一档不花钱")
        self.import_btn.clicked.connect(self._import_txt)
        tools.addWidget(self.import_btn)
        tools.addStretch(1)
        self.run_btn = QPushButton("拆这本书")
        self.run_btn.setObjectName("accentButton")
        self.run_btn.clicked.connect(self._run_ingest)
        tools.addWidget(self.run_btn)

        # 以前拆书是"启动了就停不下来"——只能等每段各自撞到 600 秒超时。
        # 这个按钮只在忙的时候露出来。
        self.cancel_btn = QPushButton("停下来")
        self.cancel_btn.setObjectName("ghostButton")
        self.cancel_btn.setToolTip("中止这一轮拆书 / 并册（已经写完的产物会留着）")
        self.cancel_btn.clicked.connect(self.cancel_requested)
        self.cancel_btn.setVisible(False)
        tools.addWidget(self.cancel_btn)
        layout.addLayout(tools)

        # 范围 / 段数 / 拆法 **单独一行**。
        # 全塞在一行会把这一页的最小宽度顶到 990，而它是正文与对话栏之间
        # 那根分隔条的左半边——左半边不能再窄，分隔条就拖不动了（踩过）。
        scope = QHBoxLayout()
        scope.setSpacing(6)
        scope.addWidget(QLabel("范围：第"))
        self.range_from = QSpinBox()
        self.range_from.setRange(1, 99999)
        self.range_from.setMinimumWidth(84)
        scope.addWidget(self.range_from)
        scope.addWidget(QLabel("到"))
        self.range_to = QSpinBox()
        self.range_to.setRange(1, 99999)
        self.range_to.setMinimumWidth(84)
        scope.addWidget(self.range_to)
        scope.addWidget(QLabel("章"))
        scope.addSpacing(4)
        scope.addWidget(QLabel("分"))
        self.shards_spin = QSpinBox()
        self.shards_spin.setRange(1, 12)
        self.shards_spin.setValue(4)
        self.shards_spin.setMinimumWidth(74)   # 够放下 2 位数＋按钮，别学上次挤没
        self.shards_spin.setToolTip(
            "同时开几个 AI 干活（= 切成几段，几段并行）。\n"
            "开多了快，但机器和 token 都吃得狠——一般 4 个，别超过 6。")
        scope.addWidget(self.shards_spin)
        scope.addWidget(QLabel("段"))
        scope.addSpacing(6)
        scope.addWidget(QLabel("拆法："))
        self.tier = QComboBox()
        self.tier.addItem("轻量拆 · 要 AI", "light")
        self.tier.addItem("全本逐章 · 要 AI，很贵", "full")
        self.tier.setMinimumWidth(180)   # 「全本逐章 · 要 AI，很贵」要放得下
        self.tier.setToolTip(
            "轻量拆：前 5 章精读 + 每卷首尾 + 挑 10 个高能章——比全本便宜得多，\n"
            "适合先探这本书值不值得细拆。\n"
            "全本逐章：全书逐章摘要。像《天不应》这种 832 章的书，\n"
            "实测摊到每章约 1.5 万 token，全书约 1240 万（很贵，想清楚再点）。")
        scope.addWidget(self.tier)
        scope.addStretch(1)
        layout.addLayout(scope)

        # 上一轮的档位从三个变成两个，没写清为什么，作者问了。
        # 摊开说：第三档（只切章）现在就是「导入 TXT…」那一步，不在这里。
        self.tier_note = QLabel(
            "「导入 TXT…」= 本地切章、建章节表，免费；上面两档才是拿 AI 拆，要花钱。"
            "每档的说明把鼠标停在选项上就能看到。")
        self.tier_note.setObjectName("mutedLabel")
        layout.addWidget(self.tier_note)

        self.progress = QLabel("")
        self.progress.setObjectName("mutedLabel")
        layout.addWidget(self.progress)

        # 拆书是几段同时跑的，光一行小字看不出整体进度——给它一条。
        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("ingestProgress")
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%v / %m 段完成")
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        split = QSplitter(Qt.Orientation.Horizontal)
        split.setHandleWidth(5)
        split.setChildrenCollapsible(False)

        self.chapter_list = QListWidget()
        self.chapter_list.setObjectName("chapterList")
        self.chapter_list.setMinimumWidth(260)
        self.chapter_list.itemClicked.connect(self._open_chapter)
        split.addWidget(self.chapter_list)

        self.book_view = QTextBrowser()
        self.book_view.setObjectName("pageBrowser")
        split.addWidget(self.book_view)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setSizes([300, 900])
        layout.addWidget(split, 1)
        return page

    def set_synced_text(self, text: str) -> None:
        self.synced_label.setText(text)

    def refresh_books(self) -> None:
        """重扫拆文库，把已有书目填进下拉。

        顺手把控件从"忙碌"里救出来：万一哪次任务没走到收尾（报错/被掐/窗口没重开），
        `_busy(True)` 会把这一排控件全禁掉——作者再想改范围或段数就写不进去了。
        """
        self._busy(False, "")
        current = self._book.name if self._book else None
        self.book_picker.blockSignals(True)
        self.book_picker.clear()
        for path in discover_books():
            self.book_picker.addItem(path.name, str(path))
        self.book_picker.blockSignals(False)

        if self.book_picker.count() == 0:
            self._book = None
            self.chapter_list.clear()
            self.book_view.setPlainText(
                "还没有入库的书。\n\n"
                "点右上角「导入 TXT…」选一个 txt，本地给它切好章、做好章节表——"
                "这一档不调用模型，不花钱。")
            return

        index = self.book_picker.findText(current) if current else 0
        self.book_picker.setCurrentIndex(index if index >= 0 else 0)
        self._on_book_changed()

    def _on_book_changed(self) -> None:
        raw = self.book_picker.currentData()
        self._book = Book(Path(raw)) if raw else None
        self.chapter_list.clear()
        if self._book is None:
            return
        for row in self._book.chapters:
            item = QListWidgetItem(self._book.label(row))
            item.setData(Qt.ItemDataRole.UserRole, row["chapter"])
            self.chapter_list.addItem(item)
        total = len(self._book.chapters)
        self.progress.setText("《%s》：%d 章，约 %.1f 万字"
                              % (self._book.name, total,
                                 self._book.total_chars() / 10000.0))
        # 默认从「已经有逐章摘要的下一章」接着拆——省得每次手填。
        self.range_to.setValue(max(1, total))
        self.range_from.setValue(min(self._first_unsummarized(), max(1, total)))
        if self.chapter_list.count():
            self.chapter_list.setCurrentRow(0)
            self._open_chapter(self.chapter_list.item(0))

    def _first_unsummarized(self) -> int:
        """已有逐章摘要的下一章。拆文库里 章节/第N章_摘要.md 就是这件事的记录。"""
        top = 0
        folder = self._book.path / "章节" if self._book else None
        if folder is not None and folder.is_dir():
            for path in folder.glob("第*章_摘要.md"):
                digits = "".join(ch for ch in path.stem if ch.isdigit())
                if digits:
                    top = max(top, int(digits))
        return top + 1

    def _open_chapter(self, item: QListWidgetItem) -> None:
        if self._book is None or item is None:
            return
        chapter = int(item.data(Qt.ItemDataRole.UserRole))
        text = self._book.chapter_text(chapter)
        rule = "─" * 40
        self.book_view.setPlainText(
            "%s\n%s\n\n%s" % (item.text(), rule, text) if text
            else "%s\n%s\n\n（这一章是空的）" % (item.text(), rule))

    def _import_txt(self) -> None:
        inbox = WORKSPACE / "refs" / "_inbox"
        path, _ = QFileDialog.getOpenFileName(
            self, "选一本要入库的 txt", str(inbox) if inbox.is_dir() else str(WORKSPACE),
            "文本文件 (*.txt *.md);;所有文件 (*)")
        if not path:
            return
        src = Path(path)
        self._busy(True, "正在本地切章…（不调模型，不花钱）")
        task = AITask(lambda cancel: ingest.scan(src), parent=self)
        task.success.connect(self._import_done)
        task.failed.connect(self._failed)
        self._task = task
        task.start()

    def _import_done(self, result) -> None:
        self._busy(False, "")
        self.refresh_books()
        index = self.book_picker.findText(result["name"])
        if index >= 0:
            self.book_picker.setCurrentIndex(index)
        self.progress.setText(
            "导入完成：《%s》%d 章，约 %.1f 万字——左边一章一章点开看。"
            % (result["name"], result["chapters"], result["chars"] / 10000.0))

    # ── 拆书 ────────────────────────────────────────────────
    def _run_ingest(self) -> None:
        if self._book is None:
            QMessageBox.information(self, "先导入一本书",
                                    "点「导入 TXT…」选一个文本文件，"
                                    "本地切好章之后再来拆。")
            return
        # 要花钱的档交给主窗口（它手上有 AI 客户端）。
        # 发的是**书目录 + 章节范围**——主窗口据此切段、并发派出去。
        start, end = self.range_from.value(), self.range_to.value()
        if end < start:
            QMessageBox.information(self, "范围不对", "「到」比「从」小，改一下再点。")
            return
        self.ingest_requested.emit(
            str(self._book.path), self.tier.currentData(), start, end,
            self.shards_spin.value())

    # ── 工作区文件页 ────────────────────────────────────────
    def _build_files_tab(self) -> QWidget:
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(0, 10, 0, 0)
        root.setSpacing(10)

        # 这棵树是**打开面板那一刻**扫的一张快照，之后不再重读——往仓库里新加的东西
        # （新册、新样本、lore 六册）不重扫就永远不出现，作者会以为白干了（踩过两次）。
        # 所以给一个「刷新」，切回这一页也自动重扫一次。
        tools = QHBoxLayout()
        tools.setSpacing(8)
        self.refresh_tree_btn = QPushButton("刷新文件树")
        self.refresh_tree_btn.setObjectName("ghostButton")
        self.refresh_tree_btn.setToolTip("重扫整个仓库——新加的东西不用重开面板")
        self.refresh_tree_btn.clicked.connect(self.refresh_tree)
        tools.addWidget(self.refresh_tree_btn)
        note = QLabel("刚往仓库里加了东西？点一下刷新，或者重进这一页。")
        note.setObjectName("mutedLabel")
        tools.addWidget(note)
        tools.addStretch(1)
        root.addLayout(tools)

        split = QSplitter(Qt.Orientation.Horizontal)
        split.setHandleWidth(5)
        split.setChildrenCollapsible(False)

        self.tree = QTreeWidget()
        self.tree.setObjectName("workspaceTree")
        self.tree.setHeaderHidden(True)
        self.tree.setMinimumWidth(260)
        self.tree.itemClicked.connect(self._open_item)
        split.addWidget(self.tree)

        self.view = QTextBrowser()
        self.view.setObjectName("pageBrowser")
        split.addWidget(self.view)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setSizes([300, 900])
        root.addWidget(split, 1)

        self._fill(self.tree.invisibleRootItem(), WORKSPACE, depth=0)
        return page

    def _fill(self, parent, path: Path, depth: int) -> None:
        if depth > 4:
            return
        try:
            entries = sorted(path.iterdir(),
                             key=lambda p: (p.is_file(), p.name.lower()))
        except OSError:
            return
        for p in entries:
            if p.name.startswith(".") or p.name in SKIP_DIRS:
                continue
            if p.is_dir():
                node = QTreeWidgetItem(parent, [p.name + "/"])
                node.setData(0, Qt.ItemDataRole.UserRole, str(p))
                node.setForeground(0, self.palette().text())
                if p.name in ("style", "技法样本"):
                    node.setExpanded(True)
                self._fill(node, p, depth + 1)
            else:
                if p.suffix.lower() in SKIP_EXT:
                    continue
                node = QTreeWidgetItem(parent, [p.name])
                node.setData(0, Qt.ItemDataRole.UserRole, str(p))

    def _on_tab_changed(self, index: int) -> None:
        if index == 1:                        # 切到「工作区文件」就重扫
            self.refresh_tree()

    def refresh_tree(self) -> None:
        """重扫仓库、重建整棵树。展开的和选中的尽量留住，别让人每次重找。

        以前这棵树只在建页时扫一遍，之后再不动——`lore/` 六册就是这么"看不见"的。
        """
        current = self.tree.currentItem()
        keep = current.data(0, Qt.ItemDataRole.UserRole) if current else None
        expanded = self._expanded_paths()
        self.tree.clear()
        self._fill(self.tree.invisibleRootItem(), WORKSPACE, depth=0)
        if expanded:
            self._restore_expanded(expanded)
        if keep:
            self._locate(Path(keep))

    def _expanded_paths(self) -> set:
        out = set()

        def walk(item) -> None:
            raw = item.data(0, Qt.ItemDataRole.UserRole)
            if raw and item.isExpanded():
                out.add(raw)
            for i in range(item.childCount()):
                walk(item.child(i))

        for i in range(self.tree.topLevelItemCount()):
            walk(self.tree.topLevelItem(i))
        return out

    def _restore_expanded(self, paths: set) -> None:
        def walk(item) -> None:
            raw = item.data(0, Qt.ItemDataRole.UserRole)
            if raw in paths:
                item.setExpanded(True)
            for i in range(item.childCount()):
                walk(item.child(i))

        for i in range(self.tree.topLevelItemCount()):
            walk(self.tree.topLevelItem(i))

    def _open_item(self, item: QTreeWidgetItem, _col: int) -> None:
        raw = item.data(0, Qt.ItemDataRole.UserRole)
        if not raw:
            return
        p = Path(raw)
        if p.is_dir():
            item.setExpanded(not item.isExpanded())
            return
        try:
            if p.stat().st_size > MAX_BYTES:
                self.view.setPlainText("（文件太大，%d 字节，不在这里打开）" % p.stat().st_size)
                return
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            self.view.setPlainText("打不开：%s" % exc)
            return
        self.view.setPlainText("%s\n%s\n\n%s" % (p.name, "─" * 40, text))

    def _locate(self, target: Path) -> bool:
        """在树里找到 target 那个节点，选中、展开、滚到它，返回找没找到。"""

        def walk(item) -> bool:
            raw = item.data(0, Qt.ItemDataRole.UserRole)
            if raw and Path(raw) == target:
                self.tree.setCurrentItem(item)
                item.setExpanded(True)
                self.tree.scrollToItem(item)
                return True
            for i in range(item.childCount()):
                if walk(item.child(i)):
                    return True
            return False

        for i in range(self.tree.topLevelItemCount()):
            if walk(self.tree.topLevelItem(i)):
                return True
        return False

    def _jump(self, rel: str) -> None:
        """展开文件树并定位到某个目录；rel 为空则回根。"""
        self.tabs.setCurrentIndex(1)          # 定位去「工作区文件」页（会顺手重扫）
        if not rel:
            # 根目录本身没有节点（它是 invisibleRoot），直接展开它下面那一层
            for i in range(self.tree.topLevelItemCount()):
                self.tree.topLevelItem(i).setExpanded(True)
            return
        self._locate((WORKSPACE / rel).resolve())

    # ── 拆书进度（几段并行，得看得见） ──────────────────────
    def begin_shard_progress(self, name: str, start: int, end: int, total: int) -> None:
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, max(1, total))
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("%%v / %%m 段 · 《%s》%d–%d 章" % (name, start, end))

    def set_shard_progress(self, done: int, total: int, note: str = "") -> None:
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, max(1, total))
        self.progress_bar.setValue(done)
        # 这一页之外的人也得看得见进度——状态栏一并报一句。
        window = self.window()
        setter = getattr(window, "status_message", None)
        if setter is not None and hasattr(setter, "setText"):
            setter.setText("拆书中：%d / %d 段完成" % (done, total))
        # 这里**没有走 Python 的 % 运算**，所以不能写 `%%v`——Qt 只认 `%v`/`%m`，
        # 写成 `%%v` 会原样渲染成字面量「%2 / %4 段完成」。
        self.progress_bar.setFormat(
            "%v / %m 段完成 · 正在跑…" if done < total else "%v / %m 段完成")

    def finish_shard_progress(self, ok: int, bad: int) -> None:
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(1)
        self.progress_bar.setFormat("完成：%d 段成功，%d 段失败" % (ok, bad))

    # ── 状态 ────────────────────────────────────────────────
    def _busy(self, on: bool, note: str = "") -> None:
        # 跑起来就把**所有**能改这一轮的入口都锁上。只锁按钮、不锁选择器的话，
        # 作者中途换书名/改范围会以为改了就生效，其实这一轮已按老参数在跑了。
        for widget in (self.run_btn, self.tier, self.import_btn,
                       self.book_picker, self.range_from, self.range_to,
                       self.shards_spin):
            widget.setEnabled(not on)
        self.cancel_btn.setVisible(on)
        if note:
            self.progress.setText(note)

    def _failed(self, err: str) -> None:
        self._busy(False, "出错了")
        QMessageBox.critical(self, "拆书失败", str(err))

    # 给主窗口回报 AI 档的进度用
    def report(self, text: str) -> None:
        self.progress.setText(text)

    def set_busy(self, on: bool) -> None:
        self._busy(on, "")
