"""表格数据层：把「项目」和「拆文库」里的东西整理成一张张表。纯读，不碰界面。

从这个面板开始，「看数据」和「看正文」是两条路：
正文在编辑器里逐字读；结构性的东西（人物、伏笔、线索轨迹、节奏）
摊成表，一眼扫完。这里只管把数据摆成行与列。
"""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

from core.paths import app_home, workspace_root
from core.text_stats import body_char_count, strip_chapter_heading

WORKSPACE = workspace_root()          # 打包后也找得对，见 core/paths.py
CORPUS = WORKSPACE / "拆文库"
# ⚠️ 项目在**程序自己**那个目录下面，不在 workspace/panel/ 下面——
# 面板装在 <工作区>/panel/ 时两者正好一样，单独一个仓库时就不是了。
PROJECTS = app_home() / "projects"

FIELD_RE = re.compile(r"^\s*[-*]\s*(?P<key>[^：:]{1,12})[：:]\s*(?P<value>.+?)\s*$")


# ── 读文件的两把安全钳 ────────────────────────────────────────
# 这一层是**只读的展示层**：任何一个文件坏了、被占用了、编码不对，
# 都只应该让那一行变空，**不能让整页打不开**。
# （实测踩过：`memory/foreshadowing.json` 一旦不是合法 JSON，
#   分析页和表格页一起崩——而那个文件正是面板自己的 AI 会去写的。）
def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return ""


def _read_json_object(path: Path) -> dict:
    try:
        data = json.loads(_read_text(path) or "{}")
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def project_root(book: str) -> Path | None:
    """拆文库那本书对应的项目目录；没有同名的就返回 None。

    拆文库和项目管理的是同一本书的两份东西：**拆文库是原始产物，项目是面板里
    看得见的那一份**（拆完收尾时同步过去）。表格页按「拆文库」下拉选框走，
    所以人物 / 伏笔 / 设定也得取这本书对应的项目——以前它们固定读
    「当前打开的项目」，于是切下拉只有线索轨迹、节奏曲线会变，
    人物和伏笔纹丝不动（作者原话：切换成天不应没有用）。
    """
    if not book:
        return None
    p = PROJECTS / book
    return p if p.is_dir() else None


# ── 项目侧 ──────────────────────────────────────────────────
def character_rows(root) -> tuple[list[str], list[list[str]]]:
    """人物表：从 canon/characters/*.md 的字段里取。"""
    cols = ["人物", "身份", "性格", "目标", "备注"]
    rows = []
    d = Path(root) / "canon" / "characters"
    for p in sorted(d.glob("*.md")) if d.is_dir() else []:
        fields: dict[str, str] = {}
        for line in _read_text(p).splitlines():
            m = FIELD_RE.match(line)
            if m:
                fields.setdefault(m.group("key").strip(), m.group("value").strip())
        rows.append([
            p.stem,
            fields.get("身份", ""),
            fields.get("性格", ""),
            fields.get("目标", ""),
            fields.get("备注", ""),
        ])
    return cols, rows


def foreshadow_rows(root) -> tuple[list[str], list[list[str]]]:
    """伏笔表：memory/foreshadowing.json 的 items。

    键名以 `core/foreshadowing.py` 为准——原来是 `planned_resolution_chapter`，
    我一开始写成了 `planned_payoff_chapter`，那一列永远是空的
    （面板里的 AI 替我挑出来的）。
    """
    cols = ["伏笔", "首现", "最近出现", "计划回收", "已回收", "状态", "说明"]
    rows = []
    p = Path(root) / "memory" / "foreshadowing.json"
    if p.exists():
        data = _read_json_object(p)
        for it in data.get("items", []):
            if not isinstance(it, dict):
                continue
            rows.append([
                str(it.get("title") or ""),
                str(it.get("first_seen_chapter") or ""),
                str(it.get("recent_seen_chapter") or ""),
                str(it.get("planned_resolution_chapter") or "未计划"),
                str(it.get("resolved_chapter") or ""),
                str(it.get("status") or ""),
                str(it.get("note") or ""),
            ])
    return cols, rows


def canon_rows(root) -> tuple[list[str], list[list[str]]]:
    """设定表：canon/ 下所有 md 文件，一行一个文件。"""
    cols = ["类别", "条目", "字数", "前 40 字"]
    rows = []
    base = Path(root) / "canon"
    if base.is_dir():
        for p in sorted(base.rglob("*.md")):
            # 备份件不算设定条目——《天不应》的 canon/characters 下有一整个
            # `_backup-20261003-b/`，不挡的话这张表会平白多出十几行同名旧卡。
            if any(part.startswith("_backup") or ".bak-" in part for part in p.parts):
                continue
            text = _read_text(p).strip()
            head = re.sub(r"\s+", " ", text.replace("#", "").strip())[:40]
            rows.append([p.parent.name, p.stem, str(body_char_count(text)), head])
    return cols, rows


# ── 拆文库侧（这是这个面板自己的东西）────────────────────────
def corpus_books() -> list[str]:
    if not CORPUS.is_dir():
        return []
    return sorted(d.name for d in CORPUS.iterdir()
                  if d.is_dir() and (d / "chapter_index.csv").exists())


def _thread_words(book: str) -> list[str]:
    """线索词表：放在拆文目录下的「线索词表.txt」，一行一个。

    不用自动发现——试过，按"名词最大断档"扫出来全是噪声（石像、马肉、烧刀子），
    因为"线索"是有语义的，得先知道哪条线重要才追得动。
    """
    p = CORPUS / book / "线索词表.txt"
    if not p.exists():
        return []
    return [w.strip() for w in p.read_text(encoding="utf-8").splitlines()
            if w.strip() and not w.startswith("#")]


def _load_book(book: str):
    """读一本拆文库的书。**读不了就返回空的**——表格页显示空表，不是报错。

    ⚠️ 顺手修了个句柄泄漏：原来 `csv.DictReader(open(...))` 没有 close，
    Windows 上被占着的文件删不掉。
    """
    d = CORPUS / book
    rows: list[dict] = []
    try:
        with open(d / "chapter_index.csv", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
    except (OSError, UnicodeError, csv.Error):
        rows = []
    lines = _read_text(d / "原文" / "原文.txt").split("\n")
    return rows, lines


def _chapter_texts(ch_rows, lines) -> list[tuple[str, str]]:
    """按章节表把原文切成一章一段，返回 `[(章号, 正文), ...]`。

    **列缺了就跳过那一章**，不猜、不抛——表坏了顶多少几行，不该让整页打不开。
    章号也一并带出来，省得调用方再按下标去对 `ch_rows`（跳过坏行之后就对不上了）。
    """
    out: list[tuple[str, str]] = []
    for row in ch_rows:
        try:
            start = int(row.get("start_line"))
            end = int(row.get("end_line"))
        except (TypeError, ValueError):
            continue
        out.append((str(row.get("source_chapter") or ""), "\n".join(lines[start - 1:end])))
    return out


def thread_rows(book: str) -> tuple[list[str], list[list[str]]]:
    """线索轨迹：每条线索出现在哪几章，压缩成区间。"""
    cols = ["线索", "首现", "末现", "出现章数", "最大断档", "出现轨迹"]
    rows = _load_book(book) if (CORPUS / book).exists() else ([], [])
    ch_rows, lines = rows
    if not ch_rows:
        return cols, []
    texts = [text for _label, text in _chapter_texts(ch_rows, lines)]
    if not texts:
        return cols, []

    out = []
    for w in _thread_words(book):
        hits = [i + 1 for i, t in enumerate(texts) if w in t]
        if not hits:
            continue
        segs, a, b = [], hits[0], hits[0]
        for c in hits[1:]:
            if c - b <= 3:
                b = c
            else:
                segs.append((a, b))
                a = b = c
        segs.append((a, b))
        gap = max((hits[i + 1] - hits[i], hits[i], hits[i + 1])
                  for i in range(len(hits) - 1)) if len(hits) > 1 else (0, 0, 0)
        trace = ",".join(str(x) if x == y else "%d-%d" % (x, y) for x, y in segs)
        out.append([w, str(hits[0]), str(hits[-1]), str(len(hits)),
                    str(gap[0]), trace])
    out.sort(key=lambda r: -int(r[3]))
    return cols, out


def rhythm_rows(book: str, window: int = 40) -> tuple[list[str], list[list[str]]]:
    """节奏曲线：每 window 章一段，看字数、对话占比、战斗/情绪词密度。

    字数口径跟面板别处一致（见 `core.text_stats`）：**只算正文、含标点、不含空白**——
    所以每章块开头那行「第N章 标题」先摘掉再数。
    """
    cols = ["章节", "平均字数", "对话占比", "战斗词/万", "情绪词/万"]
    ch_rows, lines = _load_book(book)
    pairs = _chapter_texts(ch_rows, lines)
    if not pairs:
        return cols, []
    labels = [label for label, _text in pairs]
    texts = [strip_chapter_heading(text) for _label, text in pairs]

    BATTLE = "刀剑血斩杀弩箭尸拳掌招"
    EMO = "心恨痛怕笑哭叹怒悲喜"
    DIAL = re.compile(r"[“「][^”」\n]*[”」]")

    out = []
    for i in range(0, len(texts), window):
        chunk = texts[i:i + window]
        flat = re.sub(r"\s", "", "\n".join(chunk))
        if not flat:
            continue
        d = sum(len(re.sub(r"\s", "", x)) for x in DIAL.findall("\n".join(chunk)))
        lo = labels[i]
        hi = labels[min(i + window - 1, len(labels) - 1)]
        out.append([
            "%s-%s" % (lo, hi),
            "%d" % (len(flat) / len(chunk)),
            "%.1f%%" % (d / len(flat) * 100),
            "%.1f" % (sum(flat.count(c) for c in BATTLE) / len(flat) * 10000),
            "%.1f" % (sum(flat.count(c) for c in EMO) / len(flat) * 10000),
        ])
    return cols, out
