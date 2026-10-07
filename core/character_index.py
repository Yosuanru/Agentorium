"""角色出场索引：把「某某人在第几章干了什么」串成一条线。

搭档的原话：「我想确认某个角色之前是怎么写的，我只有 grep，而 grep 给的是噪音不是答案。
grep「阿水」命中 215 次，散在 150 章里，我得一条条读到第 38 章才找到那句交底。」

角色卡是**快照**（她现在是什么人），不是**索引**（她一路怎么走过来的）。
写第 151 章时要的正是后者。这里就把索引建出来，落到项目的 `memory/角色索引.md`。
"""
from __future__ import annotations

import re
from pathlib import Path

from core.project import chapter_sort_key
from core.storage import atomic_write_text

FILENAME = "角色索引.md"


def _one_line(summary: str, name: str) -> str:
    """从一章摘要里挑出含这个名字的那一句，压成一行。"""
    text = " ".join(str(summary or "").split())
    for sentence in re.split(r"(?<=[。！？；])", text):
        if name in sentence:
            return sentence.strip()[:90]
    return text[:90]


def build(project) -> str:
    """按角色生成出场索引。返回 markdown 文本（没有数据就返回空串）。"""
    from core.project_data import ProjectDataStore
    store = ProjectDataStore(project)
    try:
        summaries = store.load_chapter_summaries() or {}
    except (OSError, ValueError):
        return ""
    if not summaries:
        return ""

    # 角色卡在 canon/characters/ **子目录**里（canon/ 直接下只有 timeline.md 之类）。
    try:
        card_names = sorted(p.stem for p in (Path(project.canon_dir) / "characters").glob("*.md"))
    except OSError:
        card_names = []
    if not card_names:
        return ""

    ordered = sorted(summaries, key=chapter_sort_key)
    blocks = ["# 角色出场索引", "",
              "> 每行 = 这个人在那一章做了什么（从逐章摘要里挑出来的那一句）。",
              "> **写新章之前先扫一眼相关角色这一段**，比 grep 一整本强。",
              "> 由面板自动生成，手改会被下次覆盖。", ""]
    for name in card_names:
        hits = [(cid, _one_line(summaries[cid], name))
                for cid in ordered if name in str(summaries[cid])]
        if not hits:
            continue
        blocks.append("## %s（%d 章）" % (name, len(hits)))
        for chapter_id, line in hits:
            number = re.sub(r"^chapter_0*", "", chapter_id) or chapter_id
            blocks.append("- 第%s章：%s" % (number, line))
        # 太久没露面的，标出来——配角几百章不出现，没人提醒就容易写成失踪人口
        last = hits[-1][0]
        gap = len(ordered) - ordered.index(last) - 1
        if gap >= 100:
            blocks.append("- ⚠️ **已经 %d 章没露面了**（上次：第%s章）"
                          % (gap, re.sub(r"^chapter_0*", "", last)))
        blocks.append("")
    return "\n".join(blocks).rstrip() + "\n"


def write(project) -> Path | None:
    """生成并落盘。没有数据时不动文件。"""
    text = build(project)
    if not text:
        return None
    target = Path(project.memory_dir) / FILENAME
    atomic_write_text(target, text)
    return target
