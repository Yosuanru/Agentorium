"""卷 / 幕 分界表（`outline/volumes.json`）。

左栏的「章节」组按这份表分成 **卷 → 幕 → 章**。
**没有这份文件、或者它读不通，一切照旧**——章节组仍然是今天那样的扁平列表，
所以老项目一行都不用改。

文件长这样（字段都可省，只写 name 和 from/to 也能用）::

    {
      "volumes": [
        {"id": "v1", "name": "卷一", "title": "守拙", "from": 1, "to": 100,
         "epigraph": "……",
         "acts": [
           {"id": "v1a1", "name": "第一幕", "title": "落", "from": 1, "to": 10}
         ]}
      ]
    }

`epigraph` 是**卷首语（扉页那一句）**，可省；有的话面板会**在卷名下面显示成一行**。

章号用**闭区间** `[from, to]`；`to` 允许大于已写到的章数（表示"这一卷还没写完"）。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

VOLUMES_FILENAME = "volumes.json"


@dataclass(frozen=True)
class Act:
    """一幕。"""

    id: str
    label: str
    start: int
    end: int
    note: str = ""


@dataclass(frozen=True)
class Volume:
    """一卷。"""

    id: str
    label: str
    start: int
    end: int
    acts: tuple[Act, ...] = ()
    note: str = ""
    epigraph: str = ""  # 卷首语（扉页那一句）；面板在卷下面显示成一行
    epigraph_file: str = ""  # ⭐ 扉页那一页的正文文件（相对项目根）；有它就能点开看完整


def volumes_path(outline_dir: Path | str) -> Path:
    return Path(outline_dir) / VOLUMES_FILENAME


def _as_int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _label(entry: dict, fallback: str) -> str:
    """`name` ＋ `title` 拼成显示名：「卷一 守拙」/「第四幕 入局」。"""
    name = str(entry.get("name") or fallback).strip()
    title = str(entry.get("title") or "").strip()
    if not name:
        return title or fallback
    return f"{name} {title}".strip() if title else name


def load_volumes(path: Path | str) -> list[Volume]:
    """读出卷幕表。**读不出来一律返回空列表**——调用方据此退回扁平列表。"""
    path = Path(path)
    try:
        if not path.is_file():
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []

    if isinstance(data, list):
        entries = data
    elif isinstance(data, dict):
        entries = data.get("volumes")
    else:
        return []
    if not isinstance(entries, list):
        return []

    volumes: list[Volume] = []
    for index, raw in enumerate(entries, start=1):
        if not isinstance(raw, dict):
            continue
        start = _as_int(raw.get("from"))
        end = _as_int(raw.get("to"))
        if start is None and end is None:
            continue
        start = 1 if start is None else start
        end = start if end is None else end
        if end < start:
            start, end = end, start

        acts: list[Act] = []
        for act_index, act_raw in enumerate(raw.get("acts") or [], start=1):
            if not isinstance(act_raw, dict):
                continue
            act_start = _as_int(act_raw.get("from"))
            act_end = _as_int(act_raw.get("to"))
            if act_start is None and act_end is None:
                continue
            act_start = start if act_start is None else act_start
            act_end = act_start if act_end is None else act_end
            if act_end < act_start:
                act_start, act_end = act_end, act_start
            acts.append(
                Act(
                    id=str(act_raw.get("id") or f"v{index}a{act_index}"),
                    label=_label(act_raw, f"第{act_index}幕"),
                    start=act_start,
                    end=act_end,
                    note=str(act_raw.get("note") or ""),
                )
            )

        volumes.append(
            Volume(
                id=str(raw.get("id") or f"v{index}"),
                label=_label(raw, f"第{index}卷"),
                start=start,
                end=end,
                acts=tuple(acts),
                note=str(raw.get("note") or ""),
                epigraph=str(raw.get("epigraph") or "").strip(),
                epigraph_file=str(raw.get("epigraph_file") or "").strip(),
            )
        )
    return volumes


def group_chapters(volumes, chapters, number_of):
    """把章节按卷 / 幕分块。

    返回 ``[(volume, [(act, [chapter, ...]), ...]), ...]``：

    - `volumes` 为空 → ``[(None, [(None, chapters)])]``：**就是今天的扁平列表**；
    - 卷 / 幕按**表里声明的顺序**排（不是按章号先后），空块不出现；
    - 落在所有区间之外的章 → 单收一块 `volume=None`：
      **章号在第一卷之前的**（作品简介这类前置内容）放**最前**，
      **其余的**（新写的、表还没跟上的）放**最后**。

    `number_of` 是取章号的回调（拿不到就返回 None）。
    """
    chapters = list(chapters)
    if not volumes:
        return [(None, [(None, chapters)])]

    by_number: dict[int, object] = {}
    leftover: list = []
    for chapter in chapters:
        number = number_of(chapter)
        if number is None or number in by_number:
            leftover.append(chapter)
            continue
        by_number[number] = chapter

    blocks: list = []
    claimed: set[int] = set()
    first_start = volumes[0].start

    def take(start: int, end: int) -> list:
        picked = []
        for number in range(start, end + 1):
            chapter = by_number.get(number)
            if chapter is not None and number not in claimed:
                claimed.add(number)
                picked.append(chapter)
        return picked

    # 第一卷之前的内容（作品简介、序章这类）—— 放最前，别掉到卷后面去
    leading = [by_number[n] for n in sorted(by_number) if n < first_start]
    if leading:
        for n in sorted(by_number):
            if n < first_start:
                claimed.add(n)
        blocks.append((None, [(None, leading)]))

    for volume in volumes:
        acts: list = []
        for act in volume.acts:
            picked = take(act.start, act.end)
            if picked:
                acts.append((act, picked))
        # 落在卷内、但没落进任何一幕的章：直接挂在卷下（不硬塞进某一幕）
        loose = take(volume.start, volume.end)
        if loose:
            acts.insert(0, (None, loose))
        if acts:
            blocks.append((volume, acts))

    rest = [by_number[number] for number in sorted(by_number) if number not in claimed]
    rest.extend(leftover)
    if rest:
        blocks.append((None, [(None, rest)]))
    return blocks
