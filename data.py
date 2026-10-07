# -*- coding: utf-8 -*-
"""面板的数据层：只负责读磁盘，不碰界面。

**面板不复制内容，它读磁盘。** 这一层永远只读，改文件 = 改面板显示。
换界面（终端 → Qt）时这一层原样复用。
"""
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL_DIR = ROOT / "style" / "技法样本"
BOOK_DIR = ROOT / "拆文库"


def read(p, default=""):
    try:
        return Path(p).read_text(encoding="utf-8")
    except Exception:
        return default


def section(text, marker):
    """取某个一级标题（`# X`）到下一个一级标题之间的内容。二级标题不算边界。"""
    i = text.find(marker)
    if i < 0:
        return ""
    rest = text[i:]
    j = rest.find("\n# ", 1)
    return rest if j < 0 else rest[:j]


# ── 有哪些书 ────────────────────────────────────────────────
def books():
    """拆文库里已经拆过的书。"""
    if not BOOK_DIR.exists():
        return []
    return sorted(d.name for d in BOOK_DIR.iterdir()
                  if d.is_dir() and (d / "chapter_index.csv").exists())


# ── 读一本书 ────────────────────────────────────────────────
class Book:
    """一本已拆的书。原文和章节表都在手上，按需取章。"""

    def __init__(self, name):
        self.name = name
        self.dir = BOOK_DIR / name
        self.rows = list(csv.DictReader(
            open(self.dir / "chapter_index.csv", encoding="utf-8-sig")))
        self.lines = read(self.dir / "原文" / "原文.txt").split("\n")

    def __len__(self):
        return len(self.rows)

    def chapter(self, i):
        r = self.rows[i]
        s, e = int(r["start_line"]), int(r["end_line"])
        return "\n".join(self.lines[s:e])

    def title(self, i):
        return "第%s章 %s" % (self.rows[i]["source_chapter"], self.rows[i]["title"])

    def groups(self, size=50):
        """把章分成组，目录树用。有些书真分了卷，就用卷。"""
        vols = {}
        for i, r in enumerate(self.rows):
            v = (r.get("volume") or "").strip()
            vols.setdefault(v, []).append(i)
        if len(vols) > 1:
            return [(v or "正文", idxs) for v, idxs in vols.items()]
        out = []
        for g in range(0, len(self.rows), size):
            idxs = list(range(g, min(g + size, len(self.rows))))
            out.append(("第 %d–%d 章" % (g + 1, idxs[-1] + 1), idxs))
        return out

    def outline(self, path):
        return read(self.dir / path)


# ── 材料：右边随时能翻的东西 ────────────────────────────────
def materials(book_name=None):
    m = {
        "创作内核": lambda: section(read(ROOT / "CLAUDE.md"), "# 创作内核"),
        "拆书流程": lambda: read(SKILL_DIR / "_拆书流程.md"),
        "项目宪章": lambda: read(ROOT / "PROJECT.md"),
    }
    for p in sorted(SKILL_DIR.glob("[0-9]*.md")):
        m["样本·" + p.stem.split("-", 1)[1]] = (lambda q=p: read(q))
    if book_name:
        d = BOOK_DIR / book_name
        for f, label in (("作品分析.md", "作品分析"),
                         ("概要.md", "全书概要"),
                         ("快速预览.md", "快速预览"),
                         ("原书章号对照.md", "章号对照")):
            if (d / f).exists():
                m[label] = (lambda q=d / f: read(q))
    return m


# ── 稿子：写作台那一块 ──────────────────────────────────────
DRAFT = ROOT / "panel" / "draft.md"


def draft():
    return read(DRAFT)


def save_draft(text):
    DRAFT.write_text(text, encoding="utf-8", newline="\n")
