"""框架图数据（`outline/swimlanes.json`）——**把整卷的线铺在同一条时间轴上**。

跟 `core/volumes.py` 是一对：
- `volumes.json` 管**「哪一章属于哪一卷哪一幕」**（左栏那棵树的骨架）；
- `swimlanes.json` 管**「每一章每一幕是在讲哪条线、到哪儿亮、到哪儿断」**（框架图的骨架）。

**没有这份文件，框架图页签只是一句提示**，不报错、不影响别的页面。

文件长这样（字段大多可省）::

    {
      "title": "卷一《守拙》", "from": 1, "to": 100,
      "acts":  [{"name": "第一幕 落", "from": 1, "to": 10}],
      "lanes": [{"id": "main", "name": "主线", "kind": "main",
                 "segments": [{"from": 1, "to": 10, "label": "落空",
                               "tone": "solid"}]}]
    }

`tone`：`solid`（实心，线正亮着）· `soft`（描边，线在暗里走）· `faint`（虚线，线断着/只剩余温）。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

SWIMLANES_FILENAME = "swimlanes.json"

TONES = ("solid", "soft", "faint")


@dataclass(frozen=True)
class Segment:
    """一条线上的一个段。"""

    start: int
    end: int
    label: str = ""
    tone: str = "solid"


@dataclass(frozen=True)
class Lane:
    """一条线（泳道）。"""

    id: str
    name: str
    kind: str = "line"          # main / line（只影响画法：主线那行画粗一点）
    segments: tuple[Segment, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class Act_banner:
    """幕带（铺在图的最上头那一条）。"""

    name: str
    start: int
    end: int


@dataclass(frozen=True)
class Swimlanes:
    title: str
    start: int
    end: int
    acts: tuple[Act_banner, ...]
    lanes: tuple[Lane, ...]

    @property
    def ok(self) -> bool:
        return bool(self.lanes) and self.end >= self.start


def swimlanes_path(outline_dir: Path | str) -> Path:
    return Path(outline_dir) / SWIMLANES_FILENAME


def _as_int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _span(entry: dict, default_start: int, default_end: int | None):
    start = _as_int(entry.get("from"))
    end = _as_int(entry.get("to"))
    if start is None and end is None:
        return None
    start = default_start if start is None else start
    end = default_end if end is None else end
    if end is None:
        end = start
    if end < start:
        start, end = end, start
    return start, end


def load_swimlanes(path: Path | str) -> Swimlanes:
    """读出框架图数据。**读不出来就返回一个空的**（页面据此显示提示）。"""
    empty = Swimlanes(title="", start=1, end=0, acts=(), lanes=())
    path = Path(path)
    try:
        if not path.is_file():
            return empty
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return empty
    if not isinstance(data, dict):
        return empty

    span = _span(data, 1, None)
    start, end = span if span else (1, 0)

    acts = []
    for index, raw in enumerate(data.get("acts") or [], start=1):
        if not isinstance(raw, dict):
            continue
        got = _span(raw, start, end)
        if not got:
            continue
        a_start, a_end = got
        acts.append(Act_banner(
            name=str(raw.get("name") or raw.get("title") or f"第{index}幕"),
            start=a_start, end=a_end,
        ))

    lanes = []
    for index, raw in enumerate(data.get("lanes") or [], start=1):
        if not isinstance(raw, dict):
            continue
        segments = []
        for seg_raw in raw.get("segments") or []:
            if not isinstance(seg_raw, dict):
                continue
            got = _span(seg_raw, start, end)
            if not got:
                continue
            s_start, s_end = got
            tone = str(seg_raw.get("tone") or "solid").strip().lower()
            segments.append(Segment(
                start=s_start, end=s_end,
                label=str(seg_raw.get("label") or "").strip(),
                tone=tone if tone in TONES else "solid",
            ))
        segments.sort(key=lambda s: (s.start, s.end))
        lanes.append(Lane(
            id=str(raw.get("id") or f"lane{index}"),
            name=str(raw.get("name") or raw.get("title") or f"线{index}"),
            kind=str(raw.get("kind") or "line").strip().lower(),
            segments=tuple(segments),
        ))

    # 数据没给范围时，用段和幕推一个出来——免得整张图压缩成一格
    if end < start:
        ends = [s.end for lane in lanes for s in lane.segments] + [a.end for a in acts]
        end = max(ends) if ends else start

    return Swimlanes(
        title=str(data.get("title") or "").strip(),
        start=start, end=end, acts=tuple(acts), lanes=tuple(lanes),
    )
