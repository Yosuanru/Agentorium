"""书稿的本地 git 自动提交。

作者 2026-10-03：「Git 存本地就可以了」——不推远端，但**得能退回来**。
而全局规矩是「只在用户要求时提交」，等于平时没人 commit，真出事时无路可退。

所以这里补一层：**动完书稿就本地提交一次**，message 用中文说书的话。
只在有改动时提交；提交失败绝不拦着退出（书还在，备份也在）。
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path


def _git(repo: Path, *args: str, timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout,
        # 无控制台打包的 GUI：不设这个，每提交一次闪一个黑窗
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def commit_projects(repo_root: Path, message: str) -> bool:
    """把书稿的改动提交一次。返回是否真的提交了。"""
    repo_root = Path(repo_root)
    if not (repo_root / ".git").exists():
        return False
    target = "panel/projects"
    try:
        status = _git(repo_root, "status", "--porcelain", "--", target)
        if status.returncode != 0 or not status.stdout.strip():
            return False                      # 没改动，别造空提交
        _git(repo_root, "add", "--", target)
        done = _git(repo_root, "commit", "-m", message, "--", target)
        return done.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _pending_path() -> Path:
    """关机跳过的提交，条子放哪。跟着工作区走，不往 C 盘用户目录丢。"""
    from core.paths import app_home
    return app_home() / "_scratch" / ".autocommit-pending.json"


def _remove_pending(path: Path) -> None:
    try:
        path.unlink()
    except OSError:
        pass


def mark_pending(repo_root: Path, message: str) -> None:
    """关机/注销时**不启动 git**，留张条子，下次启动补一次。

    条子写不进去也无所谓——最坏是这次改动不落提交，而它会在**下一次正常退出**时
    被一起提交（commit_projects 提交的是整个 panel/projects，不是单次改动）。
    """
    path = _pending_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"repo": str(repo_root), "message": message}, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError:
        pass


def run_pending() -> bool:
    """启动时补交一次「关机跳过」的提交。没有条子就什么也不做。

    条子只补一次就删：它不是重试队列，漏掉的东西下次正常退出照样会被一起提交。
    """
    path = _pending_path()
    try:
        if not path.is_file():
            return False
        data = json.loads(path.read_text(encoding="utf-8"))
        repo_root = Path(str(data["repo"]))
        message = str(data["message"])
    except (OSError, ValueError, KeyError):
        _remove_pending(path)
        return False

    try:
        done = commit_projects(repo_root, message)
    except (OSError, subprocess.SubprocessError):
        done = False
    _remove_pending(path)
    return done
