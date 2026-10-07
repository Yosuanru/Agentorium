"""Synchronize theme and appearance changes across the desktop shell."""

from __future__ import annotations

from PySide6.QtCore import QObject
from PySide6.QtWidgets import QApplication

from ui.icons import refresh_button_icons, set_button_icon
from ui.theme import apply_theme, colors_for


class AppearanceController(QObject):
    """Apply settings-driven appearance changes to all theme-aware widgets."""

    def __init__(
        self,
        *,
        root,
        inspector,
        left_panel,
        settings_page,
        theme_button,
        action_icon_buttons: dict,
        relation_page=None,
        swimlane_page=None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.root = root
        self.inspector = inspector
        self.left_panel = left_panel
        self.settings_page = settings_page
        self.theme_button = theme_button
        self.action_icon_buttons = action_icon_buttons
        # 关系图是自绘图元，不吃 QSS——换主题得单独通知它，
        # 否则深色下还是黑字画在黑底上。
        self.relation_page = relation_page
        # 框架图也是自绘图元，同一条道理：换主题得单独通知。
        self.swimlane_page = swimlane_page
        self.parent = parent
        self.config: dict = {}

    def apply(self, config: dict) -> None:
        self.config = dict(config)
        app = QApplication.instance()
        if isinstance(app, QApplication):
            apply_theme(app, self.config)
        self.inspector.set_theme(self.config)
        self.left_panel.set_theme(self.config)
        self.settings_page.set_config(self.config)
        if self.relation_page is not None:
            self.relation_page.set_theme(self.config)
        if self.swimlane_page is not None:
            self.swimlane_page.set_theme(self.config)
        self.refresh_icons()

    def refresh_icons(self) -> None:
        palette = colors_for(self.config)
        muted = palette["muted_text_color"]
        refresh_button_icons(self.root, muted)
        for button in self.action_icon_buttons.values():
            color = "#FFFFFF" if button.objectName() == "accentButton" else muted
            button.set_icon_color(color)
        theme_icon = "dark_mode" if self.config.get("theme") == "light" else "light_mode"
        set_button_icon(self.theme_button, theme_icon, muted, 17)
