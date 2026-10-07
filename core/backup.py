"""项目备份：时间戳轮转副本。

`PROJECT.md` 第七节承诺"备份三层：git 本地提交 ＋ 时间戳轮转副本 ＋ 推远端"。

**2026-10-03 起这三层都有了下限**：
- git 本地提交 → `core/autocommit.py`（退出时自动提交）＋ `.gitignore` 已放行 `projects/`
- 时间戳轮转副本 → **本文件**（学 Scrivener：保留 N 份，覆盖最旧的）
- 推远端 → **不做**（作者拍板：「Git 存本地就可以了」）

本文件这一层不依赖 git，也不需要你记得点——面板退出时自动跑一次。

**只备份书本身**（`projects/{书}/`），不备份 `dist/`、`_build/`、`.venv` 这些。
"""
from __future__ import annotations

import shutil
import time
from pathlib import Path

KEEP = 5                      # 轮转保留几份
STAMP = "%Y%m%d-%H%M%S"


def _backup_root() -> Path:
    """备份放哪。跟着工作区走，不往 C 盘用户目录丢。"""
    from core.paths import app_home
    return app_home() / "_backups"


def rotate(project_dir: Path, *, keep: int = KEEP) -> Path | None:
    """给一个项目做一次时间戳快照，并轮转掉最旧的几份。

    返回本次快照的路径；项目不存在或空目录则返回 None（静默跳过）。
    """
    project_dir = Path(project_dir)
    if not project_dir.is_dir():
        return None
    # 空项目（只剩 project.json）不值得占一份备份位
    files = [p for p in project_dir.rglob("*") if p.is_file()]
    if len(files) <= 1:
        return None

    root = _backup_root() / project_dir.name
    root.mkdir(parents=True, exist_ok=True)
    target = root / time.strftime(STAMP)
    if target.exists():
        # 同一秒内重复调用：不重复拷，**也不当成一次新备份**
        # （返回 None，否则关窗时那句「已备份 N 个项目」会虚高）。
        return None
    shutil.copytree(project_dir, target)

    snapshots = sorted(p for p in root.iterdir() if p.is_dir())
    for old in snapshots[:-keep]:
        shutil.rmtree(old, ignore_errors=True)
    return target


def rotate_all(*, keep: int = KEEP) -> list[Path]:
    """给所有项目各做一次快照。面板退出时调它。"""
    from core.paths import app_home
    projects = app_home() / "projects"
    if not projects.is_dir():
        return []
    out: list[Path] = []
    for entry in sorted(projects.iterdir()):
        if not entry.is_dir():
            continue
        snapshot = rotate(entry, keep=keep)
        if snapshot is not None:
            out.append(snapshot)
    return out
