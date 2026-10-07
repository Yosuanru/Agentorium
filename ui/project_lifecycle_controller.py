"""Project creation, loading, restoration, and recent-project state."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject

from core.config import save_config
from core.project import NovelProject
from core.project_data import sanitize_filename


class ProjectSwitchCancelled(Exception):
    """Raised when the current document could not be safely saved."""


class ProjectLifecycleController(QObject):
    """Keep project lifecycle rules separate from window dialogs and routing."""

    def __init__(
        self,
        *,
        project_session,
        config: dict,
        is_task_running: Callable[[], bool],
        save_if_dirty: Callable[[], bool],
        persist_config: Callable[[dict], None] = save_config,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.project_session = project_session
        self.config = config
        self.is_task_running = is_task_running
        self.save_if_dirty = save_if_dirty
        self.persist_config = persist_config

    def set_config(self, config: dict) -> None:
        self.config = config

    def load(self, path: Path):
        """Validate, save, load, activate, and remember a project."""
        path = Path(path)
        if self.is_task_running():
            raise RuntimeError("AI 任务仍在进行，请等待当前任务完成后再切换项目。")
        if not self.is_project_path(path):
            raise ValueError(f"该目录不是有效的 Agentorium 创作项目：\n{path}")
        if not self.save_if_dirty():
            raise ProjectSwitchCancelled()
        project = self.project_session.load(path)
        self.remember_project(project.root)
        return project

    def create_and_load(self, parent_dir: Path, name: str):
        root = Path(parent_dir) / sanitize_filename(name)
        if root.exists():
            raise FileExistsError(root)
        NovelProject.create(root, name=name.strip())
        return self.load(root)

    def restore_last(self):
        path = self.safe_project_path(self.config.get("last_project"))
        return self.load(path) if path is not None else None

    def remember_project(self, path: Path) -> None:
        resolved = str(Path(path).resolve())
        recent = [
            str(item)
            for item in self.config.get("recent_projects", [])
            if str(item) != resolved
        ]
        self.config["recent_projects"] = [resolved] + recent[:7]
        self.config["last_project"] = resolved
        self.persist_config(self.config)

    def remember_chapter(self, project_root, chapter_id: str) -> None:
        """记住这本书上次读到哪一章——下次打开直接回到那儿。

        ⚠️ **按项目分开记**：几本书各有各的位置，不能共用一个章号。
        ⚠️ 每切一次章就写一次盘，所以值没变时直接跳过，别白写。
        """
        chapter_id = str(chapter_id or "").strip()
        if not chapter_id:
            return
        resolved = str(Path(project_root).resolve())
        table = self.config.get("last_chapters")
        table = dict(table) if isinstance(table, dict) else {}
        if table.get(resolved) == chapter_id:
            return
        table[resolved] = chapter_id
        self.config["last_chapters"] = table
        self.persist_config(self.config)

    def last_chapter_for(self, project_root) -> str:
        """这本书上次读到哪一章。没记过就返回空串。"""
        table = self.config.get("last_chapters")
        if not isinstance(table, dict):
            return ""
        return str(table.get(str(Path(project_root).resolve())) or "")

    def recent_projects(self) -> list[Path]:
        """Return valid, deduplicated recent projects and clean stale entries."""
        raw_paths = self.config.get("recent_projects", [])
        if not isinstance(raw_paths, list):
            raw_paths = []
        paths: list[Path] = []
        seen: set[str] = set()
        for raw_path in raw_paths:
            path = self.safe_project_path(raw_path)
            if path is None:
                continue
            key = str(path).casefold()
            if key in seen:
                continue
            seen.add(key)
            paths.append(path)

        cleaned_paths = [str(path) for path in paths]
        if cleaned_paths != [str(path) for path in raw_paths]:
            self.config["recent_projects"] = cleaned_paths
            if self.safe_project_path(self.config.get("last_project")) is None:
                self.config["last_project"] = ""
            self.persist_config(self.config)
        return paths

    @staticmethod
    def safe_name(value: str) -> str:
        return sanitize_filename(value)

    @classmethod
    def safe_project_path(cls, value: object) -> Path | None:
        if not value:
            return None
        try:
            path = Path(str(value)).expanduser()
            return path.resolve() if cls.is_project_path(path) else None
        except (OSError, TypeError, ValueError):
            return None

    @staticmethod
    def is_project_path(path: Path) -> bool:
        try:
            return path.is_dir() and NovelProject.is_project(path)
        except OSError:
            return False
