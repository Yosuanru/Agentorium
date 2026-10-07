"""正文字数统计（口径由作者 2026-10-06 定，对齐番茄）。

**只算「正文」那一段**，数里面每个**非空白、非半角**的字符——汉字、全角标点都算。

不算的三样：
  · 章节标题行（`# 第一章 …`）和 `## 正文` 这一行本身；
  · 空格、空行、换行；
  · **半角字符**（码位不超过 U+00FF，即 ASCII ＋ Latin-1）——番茄不数它们。

**怎么定的（四点实测，全部吻合）**：

| 章 | 正文里的半角字符 | 这里算 | 番茄显示 |
|---|---|---|---|
| 1 | 0 个 | 4047 | 4047 |
| 2 | 0 个 | 2677 | 2677 |
| 7 | 1 个（间隔号 `·`） | 2273 | 2272 |
| 9 | 2 个（间隔号 `·`） | 2799 | 2797 |

⚠️ **`—`（U+2014 破折号）和 `…`（U+2026 省略号）不是半角，番茄照常算**——
第 1 章有 `——`、第 2 章有 `……`，两章的数都对得上。**别把它们跟着一起减掉。**

没有 `## 正文` 标记的文件（设定、大纲、角色卡）退回"整篇去掉所有标题行"，
这样在编辑器里打开什么文件都能有个数。
"""

from __future__ import annotations

import re

_HEADING_RE = re.compile(r"^#{1,6}\s")
_BODY_HEADING_RE = re.compile(r"^#{1,6}\s*正文\s*$")
_PARAGRAPH_SPLIT_RE = re.compile(r"\n\s*\n")
# 拆文库的原文.txt 里，每章块的第一行是裸标题（「第1章 缺哪一笔」，没有 #）。
_CHAPTER_HEADING_RE = re.compile(r"^第\s*[0-9０-９一二三四五六七八九十百千零两]+\s*[章回节](?:\s|　|$)")


def strip_chapter_heading(text: str) -> str:
    """去掉块首那一行章节标题。

    只认「第N章」这一种写法——认不出就原样返回，不猜、不砍正文
    （拆文库三个书源都是这个格式，但万一某本没有标题行，砍掉就是真丢字）。
    """
    text = str(text or "")
    first, sep, rest = text.partition("\n")
    if sep and _CHAPTER_HEADING_RE.match(first.strip()):
        return rest
    return text


def chapter_body(text: str) -> str:
    """取出「正文」那一段。

    有 `## 正文` 标记的：从它下一行起，到下一个标题行为止。
    没有这个标记的：整篇去掉所有标题行（设定、大纲这些文件走这条）。
    """
    text = str(text or "")
    lines = text.splitlines()
    start = None
    for index, line in enumerate(lines):
        if _BODY_HEADING_RE.match(line.strip()):
            start = index + 1
            break

    if start is None:
        return "\n".join(line for line in lines if not _HEADING_RE.match(line.strip()))

    end = len(lines)
    for index in range(start, len(lines)):
        if _HEADING_RE.match(lines[index].strip()):
            end = index
            break
    return "\n".join(lines[start:end])


def is_counted(ch: str) -> bool:
    """这个字符算不算一个字：**非空白、且不是半角**。

    半角 ＝ 码位不超过 U+00FF（ASCII ＋ Latin-1）。本书正文里真正会碰到的只有
    间隔号 `·`（U+00B7）——番茄不数它。
    """
    return not ch.isspace() and ord(ch) > 0xFF


def body_char_count(text: str) -> int:
    """正文字数：每个非空白、非半角的字符算一个（含标点）。口径＝番茄。"""
    return sum(1 for ch in chapter_body(text) if is_counted(ch))


def body_paragraph_count(text: str) -> int:
    """正文段数：按空行分段，空段不算。"""
    return len([part for part in _PARAGRAPH_SPLIT_RE.split(chapter_body(text)) if part.strip()])
