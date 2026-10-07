"""Lifecycle management for the configured AI engine client.

本项目把引擎从 `dsh` 换成了本机的 `claude`（见 `core/claude_client.py`）。
配置键名历史上是 `dsh_*`，现在叫 `ai_*`（旧键由 core/config.py 自动搬过来）。
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QObject

from core.engine import EngineClient, create_engine
from core.config import normalize_config


class AIEngineController(QObject):
    """Create, rotate and release AI clients independently of AI tasks."""

    def __init__(
        self,
        config: dict,
        is_task_running: Callable[[], bool],
        parent=None,
    ):
        super().__init__(parent)
        self._is_task_running = is_task_running
        self._client: EngineClient | None = None
        self._retired_clients: list[EngineClient] = []
        self.configure(config)

    @property
    def client(self) -> EngineClient | None:
        return self._client

    def configure(self, config: dict):
        """Replace the active client, deferring cleanup while a task runs."""
        normalized = normalize_config(config)
        previous = self._client
        if previous is not None:
            if self._is_task_running():
                self._retired_clients.append(previous)
            else:
                previous.cleanup()

        # 走哪个后端（本机 claude 命令 / 直连 API）由 core/engine.py 挑，
        # 两个都实现同一套接口，这里不关心是哪个。
        client = create_engine(normalized)
        self._client = client
        return client

    def cleanup_retired(self) -> None:
        for client in self._retired_clients:
            client.cleanup()
        self._retired_clients.clear()

    def cleanup(self) -> None:
        if self._client is not None:
            self._client.cleanup()
            self._client = None
        self.cleanup_retired()
