"""拆文库里的「参考书」：按章读。

一本书进库时 `ingest.scan` 已经把章切好、把每章的行号写进了
`chapter_index.csv`，原文落在 `原文/原文.txt`。这里就是按那份行号把
某一章切出来——**章节边界只认 chapter_index.csv，不再猜第二次**。

界面要的是「一一对应」：左边列第 1 章到第 N 章，点哪章就是哪章。
"""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

from core.paths import workspace_root
from core.storage import atomic_write_text


def books_root() -> Path:
    return workspace_root() / "拆文库"


def discover_books() -> list[Path]:
    """拆文库下所有已入库（有 chapter_index.csv）的书目录。"""
    root = books_root()
    if not root.is_dir():
        return []
    return [entry for entry in sorted(root.iterdir(), key=lambda p: p.name)
            if entry.is_dir() and (entry / "chapter_index.csv").is_file()]


def sync_summaries_to_project(book_dir: Path, project_dir: Path) -> int:
    """把 `拆文库/{书}/章节/第N章_摘要.md` 送进项目的 `chapter_summaries.json`。

    拆书和面板本来是**两条断开的管道**：拆出来的摘要落在拆文库，
    而面板「故事记忆」页读的是项目里的 `chapter_summaries.json`。
    不接上，作者在面板里永远看不到自己拆出来的东西——
    原话是「拆了要用啊，拆了不用那不行啊」。

    只补缺的，已有内容一个字不覆盖。返回补了几条。
    """
    src = Path(book_dir) / "章节"
    target = Path(project_dir) / "memory" / "chapter_summaries.json"
    if not src.is_dir():
        return 0

    existing: dict = {}
    if target.exists():
        try:
            loaded = json.loads(target.read_text(encoding="utf-8"))
            existing = loaded if isinstance(loaded, dict) else {}
        except (OSError, ValueError):
            existing = {}

    added = 0
    for path in sorted(src.glob("第*章_摘要.md")):
        match = re.search(r"第(\d+)章", path.stem)
        if not match:
            continue
        # ⚠️ key 必须是 `chapter_07` 这种（core/project.py:chapter_number_from_id 只认它）。
        # 写成 `第7章` 的话，故事记忆页会多出一张打不开的卡片——数字解析不出来。
        key = "chapter_%02d" % int(match.group(1))
        if str(existing.get(key) or "").strip():
            continue                       # 已有的不动
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        # 去掉开头那行 HTML 注释（story-long-analyze 的投影标记）
        existing[key] = re.sub(r"^\s*<!--.*?-->\s*", "", text, flags=re.S).strip()
        added += 1

    if added:
        atomic_write_text(
            target, json.dumps(existing, ensure_ascii=False, indent=2) + "\n")
    return added


class Book:
    """一本入库的参考书。章节表与原文各读一次，之后按行号切片。"""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.name = self.path.name
        self._chapters: list[dict] | None = None
        self._lines: list[str] | None = None

    @property
    def chapters(self) -> list[dict]:
        if self._chapters is None:
            self._chapters = self._read_index()
        return self._chapters

    def _read_index(self) -> list[dict]:
        csv_path = self.path / "chapter_index.csv"
        if not csv_path.is_file():
            return []
        try:
            with open(csv_path, encoding="utf-8-sig", newline="") as fh:
                rows = list(csv.DictReader(fh))
        except (OSError, csv.Error):
            return []
        out: list[dict] = []
        for row in rows:
            try:
                out.append({
                    "chapter": int(row["chapter"]),
                    "title": (row.get("title") or "").strip(),
                    "start_line": int(row["start_line"]),
                    "end_line": int(row["end_line"]),
                    "char_count": int(row.get("char_count") or 0),
                    "status": (row.get("status") or "ok").strip(),
                })
            except (KeyError, TypeError, ValueError):
                continue
        return out

    def _source_lines(self) -> list[str]:
        if self._lines is None:
            src = self.path / "原文" / "原文.txt"
            try:
                self._lines = src.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                self._lines = []
        return self._lines

    def label(self, row: dict) -> str:
        title = row.get("title") or ""
        head = "第%d章" % row["chapter"]
        return "%s  %s" % (head, title) if title else head

    def chapter_text(self, chapter: int) -> str:
        row = next((r for r in self.chapters if r["chapter"] == chapter), None)
        if row is None:
            return ""
        lines = self._source_lines()
        start = max(0, row["start_line"] - 1)
        end = min(len(lines), row["end_line"])
        return "\n".join(lines[start:end])

    def total_chars(self) -> int:
        return sum(row["char_count"] for row in self.chapters)
