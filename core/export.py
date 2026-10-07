"""Shared manuscript rendering for export previews and final files."""

from __future__ import annotations

from .project import NovelProject


def strip_markdown(text: str) -> str:
    """读校样：只留正文，顺手脱掉 markdown 记号。

    ⚠️ 原来是「见到 `## 大纲` 就跳过」的**黑名单**——结果 `## 章尾钩子`、
    `## 因果`、`## 证据` 这些照样漏进导出件里（作者要拿去投稿的，这是事故）。
    改成**白名单：只取 `## 正文` 段**。
    """
    lines: list[str] = []
    for line in body_only(text).splitlines():
        if line.startswith("# "):
            line = line[2:].strip()
        lines.append(line)
    return "\n".join(lines)


def body_only(text: str) -> str:
    """只取 `## 正文` 那一段，其余（大纲 / 关键事件 / 因果 / 章尾钩子 / 证据）都不导。

    投稿是给编辑看的——**不能把大纲一起交上去**。
    以前 md 导出是整份文件倒出去，规划全带出来了（作者要拿去投稿，这就是事故）。
    没有 `## 正文` 段的老格式章，退回整份内容，不至于导出个空的。
    """
    lines = str(text or "").splitlines()
    out: list[str] = []
    inside = False
    for line in lines:
        if line.startswith("# ") and not out:
            out.append(line)            # 章节标题要留着（读者得知道这是第几章）
            out.append("")              # 标题和正文之间留一行
            continue
        if line.strip() == "## 正文":
            inside = True
            continue
        if inside and line.startswith("## "):
            break                       # 到下一节，正文结束
        if inside:
            out.append(line)
    if not inside:
        # 没有 `## 正文` 段。以前这里"退回整份"，但那等于**给大纲开了一条漏出去的路**
        # （投稿件里混进规划，作者会很难看）。
        # 宁缺毋滥：只留标题，正文为空。真是老格式没有正文段的稿，导出前先补上 `## 正文`。
        title = next((ln for ln in out if ln.startswith("# ")), "")
        return title.strip()
    import re
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out).strip())


def render_manuscript(project: NovelProject, options: dict) -> str:
    """Render the selected chapters using the same rules for preview/export."""
    selected_ids = {str(item) for item in options.get("chapter_ids", [])}
    chapters = [
        path for path in project.list_chapters() if path.stem in selected_ids
    ]
    if not chapters:
        return ""

    plain_text = options.get("format") == "txt"
    remove_markdown = plain_text or bool(options.get("strip"))
    blocks: list[str] = []
    if options.get("include_title"):
        blocks.append(project.name if plain_text else f"# {project.name}")
    if options.get("include_toc"):
        toc_title = "目录" if plain_text else "## 目录"
        toc_lines = [
            f"{index}. {project.load_chapter(path.stem).title}"
            for index, path in enumerate(chapters, 1)
        ]
        blocks.append(toc_title + "\n\n" + "\n".join(toc_lines))

    for path in chapters:
        try:
            raw = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        blocks.append(strip_markdown(raw).strip() if remove_markdown
                      else body_only(raw).strip())

    separator = "\n\n***\n\n" if options.get("separators") else "\n\n\n"
    return separator.join(blocks).strip()
