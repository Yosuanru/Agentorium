"""Shared design tokens and the single Qt stylesheet used by Agentorium."""

from __future__ import annotations

import re

from PySide6.QtGui import QColor, QPalette

from core.resources import resource_path
from core.theme_tokens import DARK_COLORS, LIGHT_COLORS

QSS_TEMPLATE = r"""
* {
    font-family: "Noto Sans SC", "思源黑体", "Microsoft YaHei UI", sans-serif;
    font-size: __FONT_SIZE__px;
    color: __TEXT__;
}
QMainWindow, QWidget#appRoot { background: __BG__; }
QWidget { background: transparent; }
QDialog { background: __BG__; }
QDialog#trashDialog { background: __BG__; color: __TEXT__; }

QWidget#primarySidebar {
    background: __PANEL__;
    border-right: none;      /* 三层底色已经分开了，不需要再画线 */
}
QLabel#brandTitle, QLabel#eyebrow {
    font-family: "Hanken Grotesk", "Inter", "Microsoft YaHei UI", sans-serif;
}
QLabel#pageTitle {
    font-family: "Noto Sans SC", "思源黑体", sans-serif;
    font-size: 17px;
    font-weight: 700;
}
QLabel#brandTitle { font-size: 16px; font-weight: 700; }
QLabel#brandSubtitle, QLabel#mutedLabel, QLabel#navHint {
    color: __MUTED__;
    font-size: __SMALL_FONT_SIZE__px;
}
QLabel#documentTitle, QLabel#sectionTitle {
    font-family: "Noto Serif SC", "思源宋体", sans-serif;
}
QLabel#documentTitle { font-size: 19px; font-weight: 700; }
QLabel#panelTitle { font-size: 14px; font-weight: 700; }
/* 原来这种「小号大写字距标签」是 AI 生成界面最常见的装饰。
   它对读者没有信息量——压成普通灰字，别抢正文。 */
QLabel#eyebrow {
    color: __MUTED__;
    font-size: __SMALL_FONT_SIZE__px;
    font-weight: 600;
}

QFrame#appHeader {
    background: __PANEL__;
    border-bottom: none;     /* 靠底色分层，不靠画线 */
}
QFrame#actionBar {
    background: __BG__;
    border-bottom: none;
}
QLabel#aiStatus, QLabel#aiStatusBusy {
    border: 1px solid __BORDER__;
    border-radius: 14px;
    padding: 5px 11px;
    font-size: __SMALL_FONT_SIZE__px;
    font-weight: 700;
}
QLabel#aiStatus { color: __GOOD__; background: __GOOD_BG__; }
QLabel#aiStatusBusy { color: __ACCENT__; background: __SELECTION__; }

QFrame#primaryNav { background: transparent; border: none; }
QPushButton#primaryNavButton, QPushButton#primaryNavActive {
    text-align: left;
    border: none;
    border-radius: 7px;
    padding: 10px 12px;
    min-height: 20px;
    font-weight: 650;
}
QPushButton#primaryNavButton { background: transparent; color: __MUTED__; }
QPushButton#primaryNavButton:hover { background: __HOVER__; color: __TEXT__; }
QPushButton#primaryNavActive {
    background: __SELECTION__;
    color: __ACCENT__;
    border-left: 3px solid __ACCENT__;
    padding-left: 9px;
}
QLabel#buttonIcon {
    font-family: "Material Symbols Outlined";
    font-size: 17px;
    color: __MUTED__;
}
QLabel#buttonText {
    font-family: "Microsoft YaHei UI", "Inter", sans-serif;
    font-size: __FONT_SIZE__px;
    font-weight: 600;
    color: __TEXT__;
}
QPushButton#primaryNavButton QLabel#buttonIcon { color: __MUTED__; }
QPushButton#primaryNavButton QLabel#buttonText { color: __MUTED__; }
QPushButton#primaryNavButton:hover QLabel#buttonIcon,
QPushButton#primaryNavButton:hover QLabel#buttonText { color: __TEXT__; }
QPushButton#primaryNavActive QLabel#buttonIcon,
QPushButton#primaryNavActive QLabel#buttonText { color: __ACCENT__; }
QPushButton#primaryNavActive QLabel#buttonText { font-weight: 700; }
QPushButton#accentButton QLabel#buttonIcon,
QPushButton#accentButton QLabel#buttonText { color: __ACCENT_TEXT__; }
QPushButton#smallAccentButton QLabel#buttonIcon,
QPushButton#smallAccentButton QLabel#buttonText { color: __ACCENT__; }
QFrame#projectCard {
    background: __FIELD__;
    border: 1px solid __BORDER__;
    border-radius: 9px;
}
QFrame#navDivider { background: __BORDER__; border: none; max-height: 1px; }
QLabel#projectCardName { font-weight: 700; }

QWidget#pageSurface, QWidget#dashboardPage, QWidget#reportsPage,
QWidget#exportPage, QWidget#settingsPage { background: __BG__; }
QScrollArea#pageScroll, QWidget#pageContent { background: transparent; border: none; }
QFrame#pageHeader, QFrame#sectionCard, QFrame#statCard, QFrame#emptyState,
QFrame#settingsSection, QFrame#reportSummaryCard, QFrame#reportIssueCard {
    background: __PANEL__;
    border: 1px solid __BORDER__;
    border-radius: 10px;
}
QFrame#pageHeader { border: none; background: transparent; }
QLabel#sectionTitle { font-size: 16px; font-weight: 750; }
QFrame#localInfoBar {
    background: transparent;
    border: none;
}
QLabel#localInfoIcon { color: __GOOD__; font-weight: 800; }
QLabel#dashboardChapterTitle { font-size: 18px; font-weight: 750; }
QLabel#dashboardPreview {
    color: __MUTED__;
    background: __FIELD__;
    border-left: 3px solid __ACCENT__;
    border-radius: 5px;
    padding: 11px 13px;
}
QLabel#dashboardReadinessValue { color: __ACCENT__; font-weight: 650; }
QFrame#dashboardReadinessRow {
    background: __FIELD__;
    border: 1px solid __BORDER__;
    border-radius: 7px;
}
QPushButton#readinessLinkButton {
    background: transparent;
    border: none;
    color: __ACCENT__;
    min-height: 20px;
    padding: 2px 3px;
}
QPushButton#readinessLinkButton:hover { background: __SELECTION__; }
QFrame#dashboardNextStep {
    background: __SELECTION__;
    border: 1px solid __BORDER__;
    border-radius: 8px;
}
QLabel#dashboardNextStepText { color: __TEXT__; }
QLabel#statValue {
    color: __ACCENT__;
    font-family: "JetBrains Mono", "Microsoft YaHei UI", monospace;
    font-size: 24px;
    font-weight: 800;
}
QLabel#statCaption { color: __MUTED__; font-size: __SMALL_FONT_SIZE__px; }
QLabel#emptyIcon { color: __ACCENT__; font-size: 28px; font-weight: 700; }

QWidget#navigationPanel, QWidget#inspectorPanel {
    background: __PANEL__;
}
QWidget#navigationPanel { border-right: 1px solid __BORDER__; }
QWidget#inspectorPanel { border-left: 1px solid __BORDER__; }
QLineEdit#navigationSearch {
    border-radius: 7px;
    padding: 9px 11px;
}
QTreeWidget#projectTree {
    background: transparent;
    border: none;
    outline: none;
    show-decoration-selected: 0;
    padding-top: 2px;
}
QTreeWidget#projectTree::item {
    min-height: __TREE_ITEM_HEIGHT__px;
    border-radius: 6px;
    padding: 2px 10px;
    margin: 2px 0;
}
QTreeWidget#projectTree::branch { background: transparent; }
QTreeWidget#projectTree::branch:has-children:!has-siblings:closed,
QTreeWidget#projectTree::branch:closed:has-children:has-siblings {
    border-image: none;
    image: url(__BRANCH_CLOSED__);
}
QTreeWidget#projectTree::branch:open:has-children:!has-siblings,
QTreeWidget#projectTree::branch:open:has-children:has-siblings {
    border-image: none;
    image: url(__BRANCH_OPEN__);
}
QTreeWidget#projectTree::item:hover { background: __HOVER__; }
QTreeWidget#projectTree::item:pressed { background: __SELECTION__; }
QTreeWidget#projectTree::item:selected,
QTreeWidget#projectTree::item:selected:active,
QTreeWidget#projectTree::item:selected:!active {
    background: __SELECTION__;
    color: __TEXT__;
    border: none;
}
QListWidget#chapterList, QListWidget#trashList {
    background: __FIELD__;
    border: 1px solid __BORDER__;
    border-radius: 8px;
    outline: none;
}
QListWidget#chapterList::item, QListWidget#trashList::item {
    min-height: __TREE_ITEM_HEIGHT__px;
    padding: 2px 8px;
    border-radius: 6px;
}
QListWidget#chapterList::item:hover, QListWidget#trashList::item:hover {
    background: __HOVER__;
}
QListWidget#chapterList::item:pressed, QListWidget#trashList::item:pressed {
    background: __SELECTION__;
}
QListWidget#chapterList::item:selected, QListWidget#trashList::item:selected {
    background: __SELECTION__;
    color: __TEXT__;
    border: none;
}
QListWidget#foreshadowingSelectionList {
    background: __FIELD__;
    color: __TEXT__;
    border: 1px solid __BORDER__;
    border-radius: 8px;
    outline: none;
    selection-background-color: transparent;
    selection-color: __TEXT__;
}
QListWidget#powerSelectionList {
    background: __FIELD__;
    color: __TEXT__;
    border: 1px solid __BORDER__;
    border-radius: 8px;
    outline: none;
    selection-background-color: transparent;
    selection-color: __TEXT__;
}
QListWidget#coreSystemSelectionList {
    background: __FIELD__;
    color: __TEXT__;
    border: 1px solid __BORDER__;
    border-radius: 8px;
    outline: none;
    selection-background-color: transparent;
    selection-color: __TEXT__;
}
QListWidget#foreshadowingSelectionList::item {
    min-height: __TREE_ITEM_HEIGHT__px;
    padding: 4px 12px;
    margin: 2px 4px;
    border-radius: 6px;
    background: __FIELD__;
    color: __TEXT__;
}
QListWidget#powerSelectionList::item {
    min-height: __TREE_ITEM_HEIGHT__px;
    padding: 4px 12px;
    margin: 2px 4px;
    border-radius: 6px;
    background: __FIELD__;
    color: __TEXT__;
}
QListWidget#coreSystemSelectionList::item {
    min-height: __TREE_ITEM_HEIGHT__px;
    padding: 4px 12px;
    margin: 2px 4px;
    border-radius: 6px;
    background: __FIELD__;
    color: __TEXT__;
}
QListWidget#foreshadowingSelectionList::item:hover {
    background: __HOVER__;
}
QListWidget#powerSelectionList::item:hover {
    background: __HOVER__;
}
QListWidget#coreSystemSelectionList::item:hover {
    background: __FIELD__;
}
QListWidget#foreshadowingSelectionList::item:selected {
    background: __FIELD__;
    color: __TEXT__;
    border: none;
}
QListWidget#powerSelectionList::item:selected {
    background: __FIELD__;
    color: __TEXT__;
    border: none;
}
QListWidget#coreSystemSelectionList::item:selected {
    background: __FIELD__;
    color: __TEXT__;
    border: none;
}
QToolButton#panelToggleButton {
    background: transparent;
    color: __MUTED__;
    border: 1px solid transparent;
    border-radius: 5px;
    min-width: 24px; max-width: 24px;
    min-height: 24px; max-height: 24px;
    padding: 0;
    font-size: 17px;
}
QToolButton#panelToggleButton:hover {
    background: __HOVER__;
    color: __TEXT__;
    border-color: __BORDER__;
}

QFrame#editorHeader, QFrame#editorFooter { border: none; }
QFrame#findBar {
    background: __PANEL__;
    border: 1px solid __BORDER__;
    border-radius: 10px;
}
/* 正文区就是「纸」。纸没有圆角、没有描边——它只是比周围亮一层。
   留白给足，行距靠字体本身撑开。chrome 全部退到桌面上。 */
QPlainTextEdit#writingEditor {
    background: __FIELD__;
    border: none;
    border-radius: 0;
    padding: 44px 56px;
    selection-background-color: __ACCENT__;
    selection-color: __ACCENT_TEXT__;
    font-family: "Noto Serif SC", "思源宋体", "Songti SC", "SimSun", serif;
    font-size: __EDITOR_FONT_SIZE__px;
}
QPlainTextEdit#writingEditor:focus { border: none; }
QFrame#outputContainer {
    background: __PANEL__;
    border-top: 1px solid __BORDER__;
}
QPlainTextEdit#outputPanel, QTextBrowser#inspectorBrowser, QTextBrowser#pageBrowser {
    background: __FIELD__;
    border: 1px solid __BORDER__;
    border-radius: 7px;
    padding: 10px;
    selection-background-color: __ACCENT__;
}
QPlainTextEdit#outputPanel { font-family: "JetBrains Mono", "Cascadia Mono", "Microsoft YaHei UI"; font-size: __SMALL_FONT_SIZE__px; }

QLabel#savedBadge, QLabel#dirtyBadge {
    padding: 4px 10px;
    border-radius: 10px;
    font-size: __SMALL_FONT_SIZE__px;
}
QLabel#savedBadge { color: __GOOD__; background: __GOOD_BG__; }
QLabel#dirtyBadge { color: __ACCENT__; background: __SELECTION__; }

/* ⚠️ 右内边距只给**下拉框**（它要放箭头）。
   以前这条基础规则统一写了 `padding-right: 34px`，等于给 QLineEdit/QSpinBox
   也白留了 34px —— 而 spinbox 的上下按钮**自己就占 26px**，两边一叠加，
   窄框里的数字就被挤没了（作者报的「能写进数字但看不见」）。 */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background: __FIELD__;
    border: 1px solid __BORDER__;
    border-radius: 7px;
    padding: 7px 9px;
    padding-right: 9px;
    selection-background-color: __ACCENT__;
}
QComboBox { padding-right: 34px; }
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus { border-color: __ACCENT__; }
/* 上下按钮已经占了右侧 26px，这里只留 4px 缝隙就够 —— 别再重复预留。
   文字可用宽 = 控件宽 − 38px（左 6 + 右 4 + 边框 2 + 按钮 26）。 */
QSpinBox, QDoubleSpinBox { padding-right: 4px; padding-left: 6px; }
QSpinBox::up-button, QDoubleSpinBox::up-button,
QSpinBox::down-button, QDoubleSpinBox::down-button {
    subcontrol-origin: border;
    width: 26px;
    height: 13px;
    border: none;
    background: transparent;
}
QSpinBox::up-button, QDoubleSpinBox::up-button {
    subcontrol-position: top right;
}
QSpinBox::down-button, QDoubleSpinBox::down-button {
    subcontrol-position: bottom right;
}
QSpinBox::up-button:hover, QSpinBox::down-button:hover,
QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover {
    background: __HOVER__;
}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {
    image: url("__SPIN_UP_ARROW__");
    width: 14px;
    height: 14px;
}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {
    image: url("__SPIN_DOWN_ARROW__");
    width: 14px;
    height: 14px;
}
QComboBox { combobox-popup: 0; }
QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 30px;
    border: none;
    background: transparent;
}
QComboBox::drop-down:hover { background: __HOVER__; border: none; }
QComboBox::down-arrow {
    image: url("__COMBO_ARROW__");
    width: 18px;
    height: 18px;
}
QComboBox QAbstractItemView {
    background: __PANEL__;
    color: __TEXT__;
    border: 1px solid __BORDER__;
    outline: none;
    padding: 4px;
    selection-background-color: __SELECTION__;
    selection-color: __TEXT__;
}
QCheckBox {
    spacing: 8px;
    min-height: 24px;
}
QCheckBox::indicator,
QListWidget#chapterList::indicator,
QListWidget#foreshadowingSelectionList::indicator,
QListWidget#powerSelectionList::indicator,
QListWidget#coreSystemSelectionList::indicator {
    width: 18px;
    height: 18px;
    border: 1px solid __CHECK_BORDER__;
    border-radius: 4px;
    background: __CHECK_BG__;
}
QCheckBox::indicator:hover,
QListWidget#chapterList::indicator:hover,
QListWidget#foreshadowingSelectionList::indicator:hover,
QListWidget#powerSelectionList::indicator:hover,
QListWidget#coreSystemSelectionList::indicator:hover {
    border-color: __ACCENT__;
    background: __HOVER__;
}
QCheckBox::indicator:checked,
QListWidget#chapterList::indicator:checked,
QListWidget#foreshadowingSelectionList::indicator:checked,
QListWidget#powerSelectionList::indicator:checked,
QListWidget#coreSystemSelectionList::indicator:checked {
    border-color: __ACCENT__;
    background: __ACCENT__;
    image: url("__CHECKMARK__");
}
QCheckBox::indicator:disabled,
QListWidget#chapterList::indicator:disabled,
QListWidget#foreshadowingSelectionList::indicator:disabled,
QListWidget#powerSelectionList::indicator:disabled,
QListWidget#coreSystemSelectionList::indicator:disabled {
    border-color: __BORDER__;
    background: __BG__;
}
QPushButton, QToolButton {
    background: __PANEL__;
    border: 1px solid __BORDER__;
    border-radius: 6px;
    padding: 6px 11px;
    min-height: 18px;
}
QPushButton:hover, QToolButton:hover { background: __HOVER__; border-color: __ACCENT__; }
QPushButton:pressed, QToolButton:pressed { background: __SELECTION__; }
QPushButton:disabled, QToolButton:disabled { color: __MUTED__; border-color: __BORDER__; }
QToolButton#accentButton, QPushButton#accentButton {
    background: __ACCENT__;
    color: __ACCENT_TEXT__;
    border-color: __ACCENT__;
    font-weight: 700;
    padding-left: 17px; padding-right: 17px;
}
QToolButton#accentButton:hover, QPushButton#accentButton:hover { background: __ACCENT_HOVER__; }
QToolButton#secondaryButton, QPushButton#secondaryButton { background: __FIELD__; }
QToolButton#ghostButton, QPushButton#ghostButton { background: transparent; border-color: transparent; }
QToolButton#ghostButton:hover, QPushButton#ghostButton:hover { background: __SELECTION__; }
/* 可勾选的那种（现在是「批注」）：开了必须一眼看出来。
   以前没有 :checked 规则，按下跟没按一个样，作者原话「看不出来到底是不是批注模式」。 */
QPushButton#ghostButton:checked { background: __ACCENT__; color: #FFFFFF; border-color: __ACCENT__; }
QPushButton#smallAccentButton {
    background: __SELECTION__;
    color: __ACCENT__;
    border-color: transparent;
    padding: 5px 9px;
}
QPushButton#focusExitButton {
    background: __SELECTION__;
    color: __ACCENT__;
    border: 1px solid __ACCENT__;
    border-radius: 9px;
    padding: 7px 13px;
}
QPushButton#focusExitButton:hover { background: __ACCENT__; color: __ACCENT_TEXT__; }
/* 上一章 / 下一章：只在专注模式里出现。描边不用底，跟"退出专注"区分开；
   到头顶或到底了，描边和字一起褪成灰的——一眼看得出"这条路到头了"。 */
QPushButton#focusNavButton {
    background: transparent;
    color: __ACCENT__;
    border: 1px solid __ACCENT__;
    border-radius: 9px;
    padding: 7px 13px;
}
QPushButton#focusNavButton:hover { background: __ACCENT__; color: __ACCENT_TEXT__; }
QPushButton#focusNavButton:disabled { color: __MUTED__; border-color: __MUTED__; }
QPushButton#dangerButton { color: __DANGER__; }
QPushButton#linkButton { background: transparent; border: none; color: __ACCENT__; text-align: left; }

QTabWidget::pane { border: none; background: transparent; top: -1px; }
QTabBar::tab {
    background: transparent;
    color: __MUTED__;
    border: none;
    border-bottom: 2px solid transparent;
    padding: 8px 10px;
}
QTabBar::tab:hover { color: __TEXT__; }
QTabBar::tab:selected { color: __ACCENT__; border-bottom-color: __ACCENT__; }
QGroupBox {
    border: 1px solid __BORDER__;
    border-radius: 10px;
    margin-top: 12px;
    padding: 15px 10px 10px 10px;
    font-weight: 700;
}
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; color: __ACCENT__; }
QDialogButtonBox QPushButton { min-width: 80px; }
QMessageBox {
    background: __PANEL__;
    color: __TEXT__;
    border: 1px solid __BORDER__;
}
QMessageBox QLabel {
    background: transparent;
    color: __TEXT__;
}
QMessageBox QPushButton {
    background: __FIELD__;
    color: __TEXT__;
    border: 1px solid __BORDER__;
    border-radius: 6px;
    padding: 7px 18px;
    min-width: 80px;
}
QMessageBox QPushButton:hover {
    background: __HOVER__;
    border-color: __ACCENT__;
}
QMessageBox QPushButton:default {
    background: __ACCENT__;
    color: __ACCENT_TEXT__;
    border-color: __ACCENT__;
}

QMenuBar { background: __PANEL__; border-bottom: 1px solid __BORDER__; padding: 2px 8px; }
QMenuBar::item { padding: 5px 9px; border-radius: 5px; }
QMenuBar::item:selected { background: __HOVER__; }
QMenu { background: __PANEL__; border: 1px solid __BORDER__; border-radius: 6px; padding: 6px; }
QMenu::item { padding: 7px 28px 7px 12px; border-radius: 5px; }
QMenu::item:selected { background: __SELECTION__; }
QStatusBar { background: __PANEL__; border-top: 1px solid __BORDER__; padding: 3px 10px; }
QStatusBar::item { border: none; }
QProgressBar { background: __FIELD__; border: none; border-radius: 4px; }
QProgressBar::chunk { background: __ACCENT__; border-radius: 4px; }
QSplitter::handle { background: __BORDER__; width: 1px; height: 1px; }
QSplitter::handle:hover { background: __ACCENT__; }
QSplitter#mainSplitter::handle { background: __BORDER__; width: 5px; }
QSplitter#mainSplitter::handle:hover { background: __ACCENT__; }
QSplitter#outerSplitter::handle { background: __BORDER__; height: 5px; }
QSplitter#outerSplitter::handle:hover { background: __ACCENT__; }
/* 滚动条：细、无箭头、两侧留空。
   纵横向统一 12px，把手比边框深一档——原来横向 9px、把手用的是边框色，
   在表格底下几乎看不见，作者说"底部的下滑栏做得不好"。 */
QScrollBar:vertical { background: transparent; width: 12px; margin: 2px; }
QScrollBar::handle:vertical {
    background: __MUTED__; border-radius: 5px; min-height: 36px; opacity: 0.55;
}
QScrollBar::handle:vertical:hover { background: __TEXT__; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal { background: transparent; height: 12px; margin: 2px; }
QScrollBar::handle:horizontal {
    background: __MUTED__; border-radius: 5px; min-width: 36px;
}
QScrollBar::handle:horizontal:hover { background: __TEXT__; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }

/* ── 对话栏 ───────────────────────────────────────────────
   原来的毛病：控件全裸奔——输入框没有边框、发送键是个灰块，
   作者找了半天不知道在哪儿打字。这里把「可以打字的地方」
   明确画出来：有底、有边、聚焦时描边变朱。
   朱色只出现在这一处关键交互上，不做装饰。 */
QWidget#chatPanel { background: transparent; }
QTextBrowser#chatTranscript {
    background: __FIELD__;
    border: 1px solid __BORDER__;
    border-radius: 9px;
    padding: 12px 14px;
}
QPlainTextEdit#chatInput {
    background: __PANEL__;
    border: 1px solid __BORDER__;
    border-radius: 9px;
    padding: 10px 12px;
    font-size: __FONT_SIZE__px;
}
QPlainTextEdit#chatInput:focus { border: 1px solid __ACCENT__; }
QPlainTextEdit#chatInput:disabled { background: __FIELD__; color: __MUTED__; }
QPushButton#chatSend {
    background: __ACCENT__;
    color: __ACCENT_TEXT__;
    border: none;
    border-radius: 9px;
    padding: 10px 14px;
    font-weight: 700;
}
QPushButton#chatSend:disabled { background: __BORDER__; color: __MUTED__; }
QPushButton#chatMic {
    background: __PANEL__;
    border: 1px solid __BORDER__;
    border-radius: 9px;
    color: __TEXT__;
    padding: 10px 6px;
}
QPushButton#chatMic:hover { border-color: __ACCENT__; color: __ACCENT__; }
QPushButton#chatMic:disabled { background: __SELECTION__; border-color: __ACCENT__; color: __ACCENT__; }
QPushButton#chatClear {
    background: transparent;
    border: 1px solid __BORDER__;
    border-radius: 7px;
    color: __MUTED__;
    padding: 4px 10px;
}
QPushButton#chatClear:hover { color: __TEXT__; border-color: __MUTED__; }
QLabel#chatStatus { color: __MUTED__; font-size: __SMALL_FONT_SIZE__px; }

/* ── 表格页 ───────────────────────────────────────────────
   原来表头走 Qt 默认，落在暖纸底上就是一整条黑，很突兀。
   这里让它跟主题一致：浅底、灰字、细分割线。 */
QTableView#tableView {
    background: __PANEL__;
    alternate-background-color: __FIELD__;
    border: 1px solid __BORDER__;
    border-radius: 9px;
    gridline-color: __BORDER__;
    selection-background-color: __SELECTION__;
    selection-color: __TEXT__;
}
QTableView#tableView QHeaderView::section {
    background: __FIELD__;
    color: __MUTED__;
    border: none;
    border-right: 1px solid __BORDER__;
    border-bottom: 1px solid __BORDER__;
    padding: 7px 10px;
    font-weight: 600;
}
QTableView#tableView QTableCornerButton::section { background: __FIELD__; border: none; }

/* ── 工作区浏览 ─────────────────────────────────────────── */
QTreeWidget#workspaceTree {
    background: __PANEL__;
    border: 1px solid __BORDER__;
    border-radius: 9px;
    padding: 6px;
}
QTreeWidget#workspaceTree::item { padding: 4px 2px; border-radius: 5px; }
QTreeWidget#workspaceTree::item:selected { background: __SELECTION__; color: __TEXT__; }
"""


def _color(config: dict, key: str, default: str) -> str:
    value = config.get(key)
    if isinstance(value, str) and re.fullmatch(r"#[0-9A-Fa-f]{6}", value):
        return value.upper()
    return default


def _mix(hex_color: str, target: str, amount: float) -> str:
    def rgb(value: str) -> tuple[int, int, int]:
        value = value.lstrip("#")
        return tuple(int(value[index:index + 2], 16) for index in (0, 2, 4))

    first, second = rgb(hex_color), rgb(target)
    mixed = tuple(round(a + (b - a) * amount) for a, b in zip(first, second))
    return "#" + "".join(f"{channel:02X}" for channel in mixed)


def colors_for(config: dict | None = None) -> dict[str, str]:
    config = config or {}
    light = config.get("theme", "light") == "light"
    preset = LIGHT_COLORS if light else DARK_COLORS
    return {key: _color(config, key, value) for key, value in preset.items()}


def build_qss(config: dict | None = None) -> str:
    config = config or {}
    light = config.get("theme", "light") == "light"
    colors = colors_for(config)
    try:
        font_size = max(10, min(26, int(config.get("ui_font_size", 14) or 14)))
    except (TypeError, ValueError):
        font_size = 14
    try:
        editor_size = max(12, min(36, int(config.get("editor_font_size", 16) or 16)))
    except (TypeError, ValueError):
        editor_size = 16
    accent_text = "#FFFFFF" if light else "#08111E"
    asset_root = resource_path("assets")
    replacements = {
        "__FONT_SIZE__": str(font_size),
        "__SMALL_FONT_SIZE__": str(max(10, font_size - 2)),
        "__EDITOR_FONT_SIZE__": str(editor_size),
        "__TREE_ITEM_HEIGHT__": str(max(30, font_size + 15)),
        "__BG__": colors["background_color"],
        "__PANEL__": colors["panel_color"],
        "__FIELD__": colors["field_color"],
        "__BORDER__": colors["border_color"],
        "__TEXT__": colors["text_color"],
        "__MUTED__": colors["muted_text_color"],
        "__ACCENT__": colors["accent_color"],
        "__SELECTION__": colors["selection_color"],
        "__HOVER__": colors["hover_color"],
        "__ACCENT_TEXT__": accent_text,
        "__ACCENT_HOVER__": _mix(colors["accent_color"], "#FFFFFF" if light else "#000000", 0.12),
        "__GOOD__": "#278457" if light else "#7BD39B",
        "__GOOD_BG__": _mix(colors["panel_color"], "#278457", 0.13),
        "__DANGER__": "#C13D49" if light else "#FF8D98",
        "__CHECK_BORDER__": colors["text_color"],
        "__CHECK_BG__": colors["panel_color"] if light else colors["field_color"],
        "__CHECKMARK__": str(asset_root / "checkmark.svg").replace("\\", "/"),
        "__COMBO_ARROW__": str(
            asset_root
            / ("chevron-down-light.svg" if light else "chevron-down-dark.svg")
        ).replace("\\", "/"),
        "__SPIN_UP_ARROW__": str(
            asset_root
            / ("chevron-up-light.svg" if light else "chevron-up-dark.svg")
        ).replace("\\", "/"),
        "__SPIN_DOWN_ARROW__": str(
            asset_root
            / ("chevron-down-light.svg" if light else "chevron-down-dark.svg")
        ).replace("\\", "/"),
        # 树的展开三角：收起 ▶ / 展开 ▼。
        # 原来 setRootIsDecorated(False) 把箭头整个藏了，只能双击展开——
        # 作者要的是「点倒三角」，所以这里把箭头放回来。
        "__BRANCH_CLOSED__": str(
            asset_root
            / ("branch-closed-light.svg" if light else "branch-closed-dark.svg")
        ).replace("\\", "/"),
        "__BRANCH_OPEN__": str(
            asset_root
            / ("branch-open-light.svg" if light else "branch-open-dark.svg")
        ).replace("\\", "/"),
    }
    qss = QSS_TEMPLATE
    for token, value in replacements.items():
        qss = qss.replace(token, value)
    return qss


def document_css(config: dict | None = None) -> str:
    """Return a theme-aware stylesheet for QTextBrowser documents."""
    colors = colors_for(config)
    is_light = not config or config.get("theme", "light") == "light"
    bubbles = (
        # 对话记录里的「你 / 它」两种气泡。作者的话靠朱色左边线认出来，
        # AI 的话用描边卡片——一眼分得清谁说的。
        ".who{font-size:11px;color:%s;margin:0 0 4px 0;}"
        ".body{line-height:1.8;margin:0;}"
        ".msg-user{background:%s;border-left:3px solid %s;border-radius:0 8px 8px 0;"
        "padding:10px 12px;margin:14px 0;}"
        ".msg-ai{background:%s;border:1px solid %s;border-radius:8px;"
        "padding:10px 12px;margin:14px 0;}"
    ) % (
        colors["muted_text_color"], colors["selection_color"], colors["accent_color"],
        colors["panel_color"], colors["border_color"],
    )
    return bubbles + (
        "body{font-family:'Noto Serif SC','思源宋体','Microsoft YaHei UI';color:%s;background:%s;line-height:1.75;}"
        "h2{font-family:'Microsoft YaHei UI','Hanken Grotesk';font-size:18px;margin:5px 0 10px;color:%s;}"
        "h3{font-size:14px;margin:16px 0 7px;color:%s;}"
        ".eyebrow{font-size:11px;color:%s;letter-spacing:1px;}"
        ".muted{color:%s;}.good{color:%s;}"
        ".card{background:%s;border:1px solid %s;border-radius:8px;padding:9px;margin:5px 0;}"
        ".chip{background:%s;color:%s;border-radius:8px;padding:3px 7px;margin-right:4px;}"
        ".metric{display:inline-block;background:%s;border:1px solid %s;padding:7px;margin:3px;}"
        ".metric b{font-size:17px;color:%s;}.metric span{font-size:10px;color:%s;margin-left:4px;}"
        ".report{line-height:1.75;}li{margin-bottom:5px;}"
    ) % (
        colors["text_color"], colors["field_color"], colors["text_color"],
        colors["text_color"], colors["accent_color"], colors["muted_text_color"],
        "#278457" if is_light else "#7BD39B",
        colors["panel_color"], colors["border_color"], colors["selection_color"],
        colors["accent_color"], colors["panel_color"], colors["border_color"],
        colors["accent_color"], colors["muted_text_color"],
    )


def chat_css(config: dict | None = None) -> str:
    """对话区的样式：**无衬线**。

    正文（编辑器）用宋体——读长句舒服。但对话是个交互界面，
    宋体落在窄栏里显得笨重，作者的原话是"看着不舒服"。
    这里换回黑体，行距放宽一点，气泡之间留够气口。
    """
    c = colors_for(config)
    return (
        "body{font-family:'Noto Sans SC','思源黑体','Microsoft YaHei UI';"
        "color:%s;background:%s;line-height:1.85;font-size:13.5px;}"
        ".who{font-size:11px;color:%s;margin:0 0 5px 0;font-weight:600;}"
        ".body{line-height:1.85;margin:0;}"
        ".msg-user{background:%s;border-left:3px solid %s;border-radius:0 8px 8px 0;"
        "padding:11px 13px;margin:4px 0 16px 0;}"
        ".msg-ai{background:%s;border:1px solid %s;border-radius:8px;"
        "padding:11px 13px;margin:4px 0 16px 0;}"
        ".eyebrow{color:%s;font-size:11px;font-weight:600;}"
        ".muted{color:%s;}"
        ".applyRow{margin-top:9px;}"
        ".applyLink{color:%s;text-decoration:none;font-weight:600;font-size:12.5px;}"
    ) % (
        c["text_color"], c["field_color"], c["muted_text_color"],
        c["selection_color"], c["accent_color"],
        c["panel_color"], c["border_color"],
        c["muted_text_color"], c["muted_text_color"],
        c["accent_color"],
    )


def apply_theme(app, config: dict | None = None) -> None:
    colors = colors_for(config)
    light = (config or {}).get("theme", "light") == "light"
    palette = app.palette()
    palette.setColor(QPalette.ColorRole.Window, QColor(colors["background_color"]))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(colors["text_color"]))
    palette.setColor(QPalette.ColorRole.Base, QColor(colors["field_color"]))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(colors["panel_color"]))
    palette.setColor(QPalette.ColorRole.Text, QColor(colors["text_color"]))
    palette.setColor(QPalette.ColorRole.Button, QColor(colors["field_color"]))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(colors["text_color"]))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(colors["accent_color"]))
    palette.setColor(
        QPalette.ColorRole.HighlightedText,
        QColor("#FFFFFF" if light else "#08111E"),
    )
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(colors["panel_color"]))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(colors["text_color"]))
    app.setPalette(palette)
    app.setStyleSheet(build_qss(config))
