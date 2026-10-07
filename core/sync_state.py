"""哪几章还没同步进记忆。

作者选的是「攒着跑」：写稿是连着写的，每保存一次就跑一次 AI 太烧钱。
所以这里只记**「上次同步第 N 章是什么时候」**——章节文件比它新，就是待同步。

判断只看 mtime，不存正文副本：同一台机器上重复存一份正文是反复出过的故障源，
而且章节文件本身就是唯一真相，没必要再抄一遍。
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from core.storage import atomic_write_text

FILENAME = "sync_log.json"


def _path(project) -> Path:
    return Path(project.root) / "memory" / FILENAME


def load(project) -> dict:
    try:
        data = json.loads(_path(project).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def mark_synced(project, chapter_id: str) -> None:
    """记下「这一章刚同步过」。"""
    log = load(project)
    log[str(chapter_id)] = time.time()
    atomic_write_text(_path(project), json.dumps(log, ensure_ascii=False, indent=2) + "\n")


def mark_many_synced(project, chapter_ids) -> None:
    log = load(project)
    now = time.time()
    for chapter_id in chapter_ids:
        log[str(chapter_id)] = now
    atomic_write_text(_path(project), json.dumps(log, ensure_ascii=False, indent=2) + "\n")


def _ensure_initialized(project) -> dict:
    """第一次用时，把「已经有摘要的章节」按当前时间记进去。

    不这么做的话，拆书带进来的那批（摘要早就有了）会整本显示成「待同步」，
    作者一看 150 章待办就懵了 —— 那些不是待办，是已经同步过的。
    """
    path = _path(project)
    if path.exists():
        return load(project)
    try:
        summaries = project.load_chapter_summaries()
    except (OSError, ValueError):
        summaries = {}
    fresh: dict[str, float] = {}
    try:
        paths = list(project.list_chapters())
    except OSError:
        paths = []
    for item in paths:
        chapter_id = Path(item).stem
        if not str(summaries.get(chapter_id) or "").strip():
            continue
        try:
            fresh[chapter_id] = Path(item).stat().st_mtime
        except OSError:
            continue
    if fresh:
        try:
            atomic_write_text(path, json.dumps(fresh, ensure_ascii=False, indent=2) + "\n")
        except OSError:
            # 只读项目目录 / 磁盘满：这只是个快照文件，写不进去不该让界面崩。
            # 下次照样按 mtime 算，只是在写出成功前「已同步」那个数会一直是 0。
            pass
    return fresh


def synced_upto(project) -> int:
    """已经同步到第几章：有记录、且章节文件之后没再改过的，取最大章号。

    分析页、故事资料、故事记忆三处都显示这个数，每次同步完自动涨。
    """
    if project is None:
        return 0
    from core.project import chapter_number_from_id
    log = _ensure_initialized(project)
    best = 0
    try:
        paths = list(project.list_chapters())
    except OSError:
        return 0
    for item in paths:
        chapter_id = Path(item).stem
        number = chapter_number_from_id(chapter_id)
        if not number:
            continue
        try:
            mtime = Path(item).stat().st_mtime
        except OSError:
            continue
        if mtime <= float(log.get(chapter_id) or 0) and number > best:
            best = number
    return best


def synced_label(project) -> str:
    """给界面用的一句话。"""
    number = synced_upto(project)
    return "已同步至第 %d 章" % number if number else "尚未同步"


def pending(project) -> list[str]:
    """还没同步（或同步之后又改过）的章节，按章号排。"""
    if project is None:
        return []
    from core.project import chapter_sort_key
    log = _ensure_initialized(project)
    out: list[str] = []
    try:
        paths = list(project.list_chapters())
    except OSError:
        return []
    for item in paths:
        chapter_id = Path(item).stem
        try:
            mtime = Path(item).stat().st_mtime
        except OSError:
            continue
        if mtime > float(log.get(chapter_id) or 0):
            out.append(chapter_id)
    return sorted(out, key=chapter_sort_key)
