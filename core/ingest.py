"""把一本书弄进拆文库：本地能做的全在本地做完，不花一分钱。

三档拆法，只有第一档在这里：

  ① 扫描（本文件，零成本）—— 规范化原文、建章节表、算结构图与节奏曲线。
     几分钟内出结果，而且**不调用任何模型**。
  ② 轻量拆 / ③ 全本逐章拆 —— 要调模型，交给面板的 AI 通道跑，
     用 `style/技法样本/_拆书流程.md` 那套流程。

第 ① 档的价值不只是省钱：**它是后面所有分析的底座。** 章节边界一旦定错，
后面每一张表都跟着错——所以这一步宁可慢一点、显式一点。
"""
from __future__ import annotations

import csv
import io
import re
from pathlib import Path

from core.paths import workspace_root
from core.storage import atomic_write_text


def _corpus_root() -> Path:
    """拆文库在哪。**必须走 workspace_root()**——打包后 `__file__` 指向 bundle 内部，
    写死 `parents[2]` 会把拆出来的东西放进 dist/，面板里永远看不到它。"""
    return workspace_root() / "拆文库"

CH_HEAD = re.compile(r"^第([0-9]+)章\s*(.*)$")
VOL_HEAD = re.compile(r"^\s*第[〇零一二三四五六七八九十百千万两0-9]+卷")
COMB_HEAD = re.compile(r"^\s*第[〇零一二三四五六七八九十百千万两0-9]+卷\s*第")


def _read_source_text(src: Path) -> str:
    """读一本 txt。**必须回落 GB18030**。

    网文 txt 大半是 GBK 编码，而按 utf-8 严格解码遇到非法字节**不抛错**
    （尤其带 errors='replace' 时）——它是把每个汉字换成 U+FFFD。
    整本原文会静默变成问号，chapter_index 的字数行号跟着全错，而且不报错。
    另一条导入路（ui/document_controller.py）早就这么回落了，这里漏了。
    """
    try:
        return src.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        return src.read_text(encoding="gb18030")


def normalize(text: str) -> tuple[list[dict], list[str]]:
    """切章并规范化。

    处理两种常见脏格式：
      · 标题行 + 紧接着又把标题和正文黏在一行（《天不应》就是这种）
      · 标题行后面才是正文
    章号一律**按出现顺序重编**——原书章号可能重号、跳号，不能信。
    """
    lines = [ln.rstrip("\r") for ln in text.replace("\r\n", "\n").split("\n")]

    # 作者感言里以「第X卷」开头的句子会被误当卷标题 —— 并进上一行
    kept: list[str] = []
    merged = 0
    for ln in lines:
        if (VOL_HEAD.match(ln) and not COMB_HEAD.match(ln)
                and not CH_HEAD.match(ln.strip())
                and kept and kept[-1].strip() and not CH_HEAD.match(kept[-1].strip())):
            kept[-1] += ln.strip()
            merged += 1
            continue
        kept.append(ln)
    lines = kept

    blocks: list[dict] = []
    i = 0
    while i < len(lines):
        s = lines[i].strip()
        m = CH_HEAD.match(s)
        if m:
            title = m.group(2).strip() or ("第%s章" % m.group(1))
            nxt = lines[i + 1] if i + 1 < len(lines) else ""
            if nxt.startswith(s) and len(nxt) > len(s):
                # 黏连行：标题又贴了一遍 + 正文
                blocks.append({"title": title, "src": int(m.group(1)), "head": i,
                               "first": nxt[len(s):], "body": i + 2})
                i += 2
                continue
            if nxt == s:
                blocks.append({"title": title, "src": int(m.group(1)), "head": i,
                               "first": None, "body": i + 2})
                i += 2
                continue
            blocks.append({"title": title, "src": int(m.group(1)), "head": i,
                           "first": None, "body": i + 1})
            i += 1
            continue
        i += 1

    mapping: list[dict] = []
    out: list[str] = []
    for idx, b in enumerate(blocks):
        stop = blocks[idx + 1]["head"] if idx + 1 < len(blocks) else len(lines)
        out.append("第%d章 %s" % (idx + 1, b["title"]))
        if b["first"] and b["first"].strip():
            out.append(b["first"])
        body = lines[b["body"]:stop]
        while body and not body[-1].strip():
            body.pop()
        out.extend(body)
        mapping.append({"seq": idx + 1, "src_label": b["src"], "title": b["title"]})
    return mapping, out


def build_index(rows_src: list[dict], texts: list[str]) -> list[dict]:
    """行号 + 字数 + 定位符。行号是给 grep 和编辑器用的。"""
    idx = []
    line = 1
    for m, body in zip(rows_src, texts):
        n = body.count("\n") + 1
        idx.append({
            "chapter": m["seq"], "source_chapter": m["src_label"],
            "volume": "", "title": m["title"],
            "start_line": line, "end_line": line + n - 1,
            "char_count": len(re.sub(r"\s", "", body)),
            "source_locator": "原文/原文.txt:L%d-L%d" % (line, line + n - 1),
            "status": "ok" if body.strip() else "empty",
        })
        # 章与章之间**没有**空行：normalize() 逐章剥掉了尾部空行，写文件时
        # 也只是 "\n".join(out_lines)。以前这里写 `line += n + 1`（注释说 +1 是
        # 章节间的空行），那个空行根本不存在，于是每过一章行号就多飘一行——
        # 第 1 章对，第 352 章整整偏 351 行，读原文时越往后越取不到东西。
        line += n
    return idx


def structure_windows(idx: list[dict], texts: list[str], size: int = 40) -> list[list[str]]:
    """结构图：每 size 章一段，看名字类密度和对话占比。"""
    import re as _re
    DIAL = _re.compile(r"[“「][^”」\n]*[”」]")
    out = []
    for i in range(0, len(texts), size):
        chunk = texts[i:i + size]
        flat = _re.sub(r"\s", "", "\n".join(chunk))
        if not flat:
            continue
        d = sum(len(_re.sub(r"\s", "", x)) for x in DIAL.findall("\n".join(chunk)))
        out.append([
            "%s-%s" % (idx[i]["source_chapter"], idx[min(i + size - 1, len(idx) - 1)]["source_chapter"]),
            "%d" % (len(flat) / len(chunk)),
            "%.1f%%" % (d / len(flat) * 100),
        ])
    return out


def build_ingest_prompt(book_name: str, mode: str, start: int, end: int,
                        shards: int = 4) -> str:
    """拼「拆这本书」的提示词。

    **抽成纯函数**是为了能被测试：以前它长在 MainWindow 的方法里，
    测试得先起一个窗口才能验——而起窗口的测试在整套里会互相打架、把跑测卡死。
    这里不碰 Qt，测起来干净。

    ⚠️ 占位符**顺序**要和参数严格对应。静态检查只能数个数，
    个数对、顺序错（有次把书名顶到了 %d 上）只有真跑才炸。
    """
    tier = {"light": "轻量拆（粗拆：按主题跳着读，只出技法条目，不产逐章摘要）",
            "full": "全本逐章拆（精拆：一章一章读完，逐章摘要必须有）"}.get(mode, mode)
    count = max(1, min(12, int(shards or 4)))
    return (
        "按 `style/技法样本/_拆书流程.md`，把《%s》第 %d–%d 章拆掉。\n"
        "拆法：**%s**\n\n"
        "原文：`拆文库/%s/原文/原文.txt`\n"
        "章节表：`拆文库/%s/chapter_index.csv`——用里面的起止行号取，**别在全书里自己找章节**\n\n"
        "要求：\n"
        "1. 本地扫描**已经做过了**，直接从精读开始。\n"
        "2. **派几个代理、怎么分段**：作者希望分 **%d 段**"
        "（如果他没改界面上的数就是这个）；\n"
        "   用 Task 并行派出去，每个代理给具体章号。\n"
        "3. 输出格式严格照流程第 4 步——**「要写「X」」那一行必须在最前面**。\n"
        "4. 逐章摘要写 `拆文库/%s/章节/第N章_摘要.md`；\n"
        "   技法条目写 `拆文库/%s/_analysis_cache/片段-%d-%d.md`。\n"
        "   ⚠️ 并行阶段**不要动 `style/技法样本/` 里的册子**——并册留到最后单独一步，\n"
        "   几片同时写同一册会抢文件。\n"
        "5. **不许新造设定**；按题材归册，**不预设哪一类不学**（打斗进 06，写坏的进 09）。\n\n"
        "跑完照流程第 7 步收尾：并册 ＋ 把**面板上看得见的每一项**同步进项目——\n"
        "摘要/状态/伏笔/人物/设定/线索词表/关系图/总大纲/后续规划/文风指南/世界观/体系设定/时间线/角色索引。\n"
        "全程把进展说给我听；做完回一段白话：拆了哪几章、派了几个代理、产物在哪、哪条没做到。"
        % (book_name, start, end, tier,
           book_name,                       # 原文路径
           book_name,                       # 章节表路径
           count,                           # 分几段
           book_name,                       # 逐章摘要路径
           book_name, start, end)           # 片段文件名
    )


def scan(src: Path, name: str | None = None) -> dict:
    """第 ① 档：本地扫描。不调模型。

    产出到 拆文库/{书名}/：原文/原文.txt、chapter_index.csv、线索词表.txt（空模板）。
    """
    name = name or src.stem
    text = _read_source_text(src)
    mapping, out_lines = normalize(text)
    if not mapping:
        # 纯散文 / 空文件 / 只有卷标题：一行「第N章」都没有。
        # 直接拒掉，别先建出个空目录再在 build_index 那儿抛 IndexError。
        raise ValueError("这个文件里一行「第N章」都没找到——不像小说正文。没有动任何文件。")

    out_dir = _corpus_root() / name
    (out_dir / "原文").mkdir(parents=True, exist_ok=True)

    atomic_write_text(out_dir / "原文" / "原文.txt", "\n".join(out_lines) + "\n")

    # 按章切回正文
    texts, cur = [], []
    for ln in out_lines:
        if CH_HEAD.match(ln.strip()) and cur:
            texts.append("\n".join(cur))
            cur = [ln]
        else:
            cur.append(ln)
    if cur:
        texts.append("\n".join(cur))

    idx = build_index(mapping, texts)
    # 原子写：chapter_index.csv 是全书**唯一真源**，写到一半崩了会留下半截索引，
    # 面板的表格页和 books.chapter_text 都会照着坏索引取错章。
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(idx[0].keys()), lineterminator="\n")
    writer.writeheader()
    writer.writerows(idx)
    atomic_write_text(out_dir / "chapter_index.csv", buffer.getvalue(),
                      encoding="utf-8-sig")

    # 线索词表：导入时只留说明，**由拆书的 AI 收尾时按读到的线索手填**。
    # 不让机器自动生成——试过，按「名词最大断档」扫出来全是普通词（石像、马肉、烧刀子）。
    # 线索是有语义的，得先知道哪条线重要才追得动。空着「线索轨迹」表就是空的。
    tl = out_dir / "线索词表.txt"
    if not tl.exists():
        tl.write_text(
            "# 线索词表（导入时先空着，等拆书收尾时由 AI 按读到的线索填）\n"
            "# 一行一个词；面板的「分析 · 线索轨迹」表按这份表扫全书。\n"
            "# 留空 = 线索轨迹表没有数据。收尾时必须填。\n"
            "# （机器不自动生成：按「名词最大断档」扫出来全是普通词，噪声太大。）\n\n",
            encoding="utf-8")

    return {"name": name, "dir": str(out_dir), "chapters": len(idx),
            "chars": sum(r["char_count"] for r in idx),
            "empty": sum(1 for r in idx if r["status"] != "ok")}
