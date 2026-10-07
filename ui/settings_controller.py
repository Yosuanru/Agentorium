"""Application settings, theme and AI-engine connection-test coordination."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from core.config import normalize_config, save_config
from core.claude_client import ClaudeClient
from core.paths import workspace_root
from ui.ai_task_runner import AITask
from ui.ai_engine_controller import AIEngineController
from ui.document_controller import DocumentController
from ui.theme import apply_theme
from core.theme_tokens import DARK_COLORS, LIGHT_COLORS


class SettingsController(QObject):
    """Keep settings mutations in one place and expose UI-safe signals."""

    config_changed = Signal(object, str)
    connection_started = Signal()
    connection_succeeded = Signal(str)
    connection_failed = Signal(str)
    connection_finished = Signal()

    def __init__(
        self,
        config: dict,
        document_controller: DocumentController,
        engine_controller: AIEngineController | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._config = normalize_config(config)
        self._document_controller = document_controller
        self._engine_controller = engine_controller
        self._connection_task: AITask | None = None
        self._apply_runtime_settings()

    @property
    def config(self) -> dict:
        return dict(self._config)

    def synchronize(self, config: dict) -> None:
        """Adopt metadata persisted by another application controller."""
        self._config = normalize_config(config)

    def apply(self, config: dict, message: str = "设置已保存") -> dict:
        self._config = normalize_config(config)
        save_config(self._config)
        self._apply_runtime_settings()
        self.config_changed.emit(self.config, message)
        return self.config

    def toggle_theme(self) -> dict:
        next_theme = "dark" if self._config.get("theme", "light") == "light" else "light"
        updated = self.config
        updated["theme"] = next_theme
        updated.update(DARK_COLORS if next_theme == "dark" else LIGHT_COLORS)
        return self.apply(updated, message="主题已切换")

    def test_engine(self, config: dict | None = None) -> bool:
        if self._connection_task is not None and self._connection_task.isRunning():
            return False
        test_config = normalize_config(config or self._config)
        # 引擎早就换成本机 claude 了，这里却还在用 DSHClient——它会拼
        # `--profile headless`，而 claude CLI 没这个参数，于是「测试连接」**必然失败**，
        # 作者以为 AI 坏了，其实真实任务走的是 ClaudeClient、好好的。
        client = ClaudeClient(
            command=test_config["ai_command"],
            launcher_args=test_config["ai_launcher_args"],
            timeout=min(15, int(test_config["ai_timeout"])),
            extra_args=test_config["ai_extra_args"],
            # 「测试能不能连上」要拿**正在编辑的那份**去试——不然改了地址/密钥，
            # 点测试还是拿旧的连，看起来像"没生效"。
            api_base_url=test_config["api_base_url"],
            api_key=test_config["api_key"],
            api_model=test_config["api_model"],
        )
        client.set_working_directory(workspace_root())
        self._connection_task = AITask(
            lambda _cancel_event: client.generate("你是连通性自检。只回两个字：可以。", "在吗"),
            parent=self,
        )
        self._connection_task.success.connect(
            lambda result: self.connection_succeeded.emit(str(result))
        )
        self._connection_task.failed.connect(
            lambda error: self.connection_failed.emit(str(error))
        )
        self._connection_task.finished.connect(self._on_connection_finished)
        self.connection_started.emit()
        self._connection_task.start()
        return True

    def _apply_runtime_settings(self) -> None:
        self._document_controller.configure_auto_save(
            bool(self._config.get("auto_save", True)),
            int(self._config.get("auto_save_interval", 30)),
        )
        if self._engine_controller is not None:
            self._engine_controller.configure(self._config)
        app = QApplication.instance()
        if isinstance(app, QApplication):
            apply_theme(app, self._config)

    def _on_connection_finished(self) -> None:
        task = self._connection_task
        self._connection_task = None
        self.connection_finished.emit()
        if task is not None:
            task.deleteLater()
