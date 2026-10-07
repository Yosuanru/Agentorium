"""Lifecycle management for the configured AI engine client.

本项目把引擎从 `dsh` 换成了本机的 `claude`（见 `core/claude_client.py`）。
配置里的键名仍沿用 `dsh_*`，避免改动设置界面与旧配置——值默认已是 `claude`。
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QObject

from core.claude_client import ClaudeClient
from core.config import normalize_config
from core.paths import workspace_root


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
        self._client: ClaudeClient | None = None
        self._retired_clients: list[ClaudeClient] = []
        self.configure(config)

    @property
    def client(self) -> ClaudeClient | None:
        return self._client

    def configure(self, config: dict) -> ClaudeClient:
        """Replace the active client, deferring cleanup while a task runs."""
        normalized = normalize_config(config)
        previous = self._client
        if previous is not None:
            if self._is_task_running():
                self._retired_clients.append(previous)
            else:
                previous.cleanup()

        client = ClaudeClient(
            command=normalized["dsh_command"],
            launcher_args=normalized["dsh_launcher_args"],
            timeout=normalized["dsh_timeout"],
            extra_args=normalized["dsh_extra_args"],
            api_base_url=normalized["api_base_url"],
            api_key=normalized["api_key"],
            api_model=normalized["api_model"],
        )
        # 不给它空目录——空目录会让它去找文件而不是读内联上下文。
        # 指向整个仓库根，它才读得到 E 盘上的拆文库、技法样本这些真东西。
        #
        # ⚠️ 必须走 workspace_root()：`Path(__file__).resolve().parents[2]` 在源码里
        # 是对的，但**打包后 `__file__` 在 bundle 内部**，会算成 `dist/Agentorium`——
        # 于是 exe 里的 AI 读不到 CLAUDE.md 和技法样本十册，等于变瞎。
        # core/paths.py 就是为这个写的，别再退回写死 parents[i]。
        client.set_working_directory(workspace_root())
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
