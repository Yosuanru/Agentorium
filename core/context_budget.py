"""Priority-based context budget for AI prompts.

**来历（2026-10-03 改）**：这套预算原本是给 `dsh` 兜底的 —— 那个 CLI 只收
命令行参数，整个提示词必须塞进 Windows ~30K 的 CreateProcess 上限里，所以
所有上下文都被狠狠压缩，越不重要的越先砍。

**可引擎早就换成 `claude` 了，提示词改走 stdin**（见 `core/claude_client.py`
那句「★ 走 stdin，绕开命令行长度限制」）——**天花板已经拆了，帽子还挂在这**。
后果很实：写到几百章时，老那条路（扩写 / 检查 / 更新记忆）只看得到最近
5 章摘要、每章砍到 400 字、伏笔最多喂 8 条，前面几十万字对它等于不存在，
而且它不会说"我没看到第 100 章"，会照着看到的直接往下写。

所以下面几个数放宽了。但**没有放成无限**——上下文越大越稀释是实测过的
（`工作逻辑.md`：「塞得越多效果越差」）。仍然按优先级砍，砍了仍然就地标出来。
"""

from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass

from .foreshadowing import foreshadowing_urgency, urgency_label
from .models import Chapter, RelatedCanon
from .project import NovelProject, chapter_number_from_id
from .project_data import ProjectDataStore

# Sections share this pool; instruction text and section labels live outside it.
# 24000 是 dsh 时代为 30K 命令行上限留的余量。走 stdin 之后没必要卡这么死，
# 放到 96000（约合四万多 token）——再大就只剩稀释，没有增益。
DEFAULT_PROMPT_BUDGET = 96000

# Task-specific history windows.  The current chapter's own planning text is
# more useful for expansion than increasingly old raw prose.
# 原来只看 5 章——写到几百章时等于失忆。放宽到 15 章，每章多留一点。
EXPANSION_SUMMARY_COUNT = 15
CONTINUATION_SUMMARY_COUNT = 6
SUMMARY_PER_CHAPTER_CAP = 600

# A section trimmed below this many chars carries no useful signal; drop it.
MIN_SECTION_CHARS = 160

DROPPED_PLACEHOLDER = "（因上下文长度限制，本节内容已省略）"
HEAD_MARK = "\n…（内容过长，已截断）"
TAIL_MARK = "（前文过长，已截断）\n"

# key: (cap, keep, priority).  Lower priority number is allocated first.
SECTION_RULES: dict[str, tuple[int, str, int]] = {
    "outline": (3000, "head", 0),
    "plot_brief": (2500, "head", 0),
    "style": (1800, "head", 0),
    "content": (12000, "tail", 1),
    "selected_foreshadowing": (3500, "head", 1),
    "core_power": (1800, "head", 1),
    "core_systems": (3500, "head", 1),
    "selected_power": (3500, "head", 1),
    "state": (4000, "head", 2),
    "summaries": (2000, "head", 3),
    "characters": (3000, "head", 4),
    "future_plan": (1500, "head", 5),
    "main_arc": (1500, "head", 5),
    "timeline": (1500, "head", 6),
    "world": (2000, "head", 7),
    "power": (1500, "head", 7),
}


@dataclass(frozen=True)
class Section:
    key: str
    text: str
    cap: int
    keep: str  # "head" | "tail"
    priority: int


@dataclass(frozen=True)
class AIContext:
    """One immutable-in-use snapshot of all source data for an AI task."""

    project_root: str
    chapter_id: str
    chapter: Chapter
    related: RelatedCanon
    story_state: dict
    chapter_summaries: dict
    main_arc: str
    future_plan: str
    style_guide: str

    def fingerprint(self, editor_text: str | None = None) -> str:
        payload = {
            "project_root": self.project_root,
            "chapter_id": self.chapter_id,
            "chapter": {
                "title": self.chapter.title,
                "outline": self.chapter.outline,
                "plot_brief": self.chapter.plot_brief,
                "content": self.chapter.content,
                "raw": self.chapter.raw,
            },
            "related": {
                "characters": self.related.characters,
                "world": self.related.world,
                "power": self.related.power,
                "core_power": self.related.core_power,
                "core_systems": self.related.core_systems,
                "selected_power": self.related.selected_power,
                "timeline": self.related.timeline,
            },
            "story_state": self.story_state,
            "chapter_summaries": self.chapter_summaries,
            "main_arc": self.main_arc,
            "future_plan": self.future_plan,
            "style_guide": self.style_guide,
            "editor_text": editor_text,
        }
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_ai_context(
    project: NovelProject,
    chapter_id: str,
    *,
    character_scope: str = "chapter",
    include_world: bool = True,
    include_power: bool = True,
    include_timeline: bool = True,
    selected_power: list[str] | tuple[str, ...] | None = None,
) -> AIContext:
    """Load prompt sources through one project data facade.

    The default keeps the complete canon for compatibility.  Prompt builders
    can narrow canon loading for a task so long projects do not pay the cost of
    reading every world/power file before budgeting even begins.
    """
    return build_task_context(
        project,
        chapter_id,
        character_scope=character_scope,
        include_world=include_world,
        include_power=include_power,
        include_timeline=include_timeline,
        selected_power=selected_power,
    )


def build_task_context(
    project: NovelProject,
    chapter_id: str,
    *,
    character_scope: str = "chapter",
    include_world: bool = True,
    include_power: bool = True,
    include_timeline: bool = True,
    selected_power: list[str] | tuple[str, ...] | None = None,
) -> AIContext:
    """Build an AI context with an explicit canon loading profile."""
    store = ProjectDataStore(project)
    chapter = store.load_chapter(chapter_id)
    character_query = None
    if character_scope == "planning":
        character_query = "\n".join(
            part for part in (chapter.title, chapter.outline, chapter.plot_brief) if part
        )
    core_systems = store.list_core_systems()
    selected_systems = tuple(core_systems) + tuple(selected_power or ())
    return AIContext(
        project_root=str(store.root.resolve()).casefold(),
        chapter_id=str(chapter_id),
        chapter=chapter,
        related=store.find_related_canon(
            chapter_id,
            character_query=character_query,
            include_world=include_world,
            include_power=include_power,
            include_timeline=include_timeline,
            selected_power=selected_systems,
            core_power_paths=core_systems,
        ),
        story_state=store.load_story_state(),
        chapter_summaries=store.load_chapter_summaries(),
        main_arc=store.load_main_arc(),
        future_plan=store.load_future_plan(),
        style_guide=store.load_style_guide(),
    )


def allocate(sections: list[Section], budget: int) -> dict[str, str]:
    """Fit sections into the budget, trimming from the lowest priority up.

    Returns each section's final text.  A section that could not be kept maps
    to ``DROPPED_PLACEHOLDER`` so the model sees "omitted for length" instead
    of concluding the data does not exist.
    """
    result: dict[str, str] = {}
    remaining = max(0, int(budget))
    for section in sorted(sections, key=lambda item: item.priority):
        text = str(section.text).strip()
        if not text:
            continue
        capped_len = min(len(text), section.cap)
        if capped_len <= remaining:
            result[section.key] = (
                text if len(text) <= section.cap else _trim(text, section.cap, section.keep)
            )
            remaining -= capped_len
        elif remaining >= MIN_SECTION_CHARS:
            result[section.key] = _trim(text, remaining, section.keep)
            remaining = 0
        else:
            result[section.key] = DROPPED_PLACEHOLDER
    return result


def gather_sections(
    project: NovelProject,
    chapter_id: str,
    keys,
    *,
    content_keep: str = "tail",
    content_cap: int | None = None,
    summary_count: int = EXPANSION_SUMMARY_COUNT,
    selected_foreshadowing: list[dict] | tuple[dict, ...] | None = None,
    selected_power: list[str] | tuple[str, ...] | None = None,
    context: AIContext | None = None,
) -> list[Section]:
    """Load the named standard sections in deterministic rule order."""
    context = context or build_ai_context(
        project,
        chapter_id,
        selected_power=selected_power,
    )
    chapter = context.chapter
    related = context.related
    summary_count = max(0, int(summary_count))
    raw = {
        "outline": chapter.outline,
        "plot_brief": chapter.plot_brief,
        "content": chapter.content,
        "style": context.style_guide,
        "selected_foreshadowing": render_selected_foreshadowing(
            selected_foreshadowing, current_chapter_id=chapter_id
        ),
        "core_power": related.core_power,
        "core_systems": related.core_systems,
        "selected_power": related.selected_power,
        "state": json.dumps(
            compact_story_state(context.story_state),
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        "summaries": prior_chapter_summaries(
            project,
            chapter_id,
            count=summary_count,
            per_summary_cap=SUMMARY_PER_CHAPTER_CAP,
            summaries=context.chapter_summaries,
        ),
        "characters": related.characters,
        "future_plan": context.future_plan,
        "main_arc": context.main_arc,
        "timeline": related.timeline,
        "world": related.world,
        "power": related.power,
    }
    sections: list[Section] = []
    wanted = set(keys)
    for key in SECTION_RULES:
        if key not in wanted:
            continue
        text = str(raw.get(key) or "").strip()
        if not text:
            continue
        cap, keep, priority = SECTION_RULES[key]
        if key == "summaries":
            # The setting controls the number of summaries, so let this
            # section grow with that choice. The global prompt budget still
            # trims it after higher-priority sections are allocated.
            cap = max(cap, summary_count * SUMMARY_PER_CHAPTER_CAP)
        if key == "content":
            keep = content_keep
            if content_cap is not None:
                cap = max(1, int(content_cap))
        sections.append(Section(key, text, cap, keep, priority))
    return sections


def render_selected_foreshadowing(notes: object, *, current_chapter_id: str = "") -> str:
    """Render only author-selected notes with a bounded per-note payload.

    ⚠️ 原来是 `notes[:8]`——**按文件顺序取前 8 条**。写到几百章时，
    open 的伏笔堆到几十上百条，AI 每次收到的八条可能是早该忘的，
    **真正到点该回收的那条反而送不进上下文**。
    改成：有计划回收章的排前面（按该收的章号），再按优先级，最后才轮到其它；
    条数也从 8 放宽到 20。

    2026-10-03 补：光按「计划章」排还有个洞——**压根没填计划回收章的伏笔会永远垫底**，
    埋到几百章也没人提醒。现在先用 `foreshadowing_urgency` 把「计划章已过」
    「埋很久又没计划章」两种顶到最前，并在正文里打 ⚠️ 标；两处排序共用同一判断。
    """
    if not isinstance(notes, (list, tuple)):
        return ""

    def _chapter_of(note: dict) -> int:
        raw = str(note.get("planned_resolution_chapter") or "").strip()
        digits = "".join(ch for ch in raw if ch.isdigit())
        return int(digits) if digits else 99999

    current = chapter_number_from_id(current_chapter_id)
    priority_rank = {"high": 0, "medium": 1, "low": 2}
    ordered = sorted(
        (note for note in notes if isinstance(note, dict)),
        key=lambda note: (
            foreshadowing_urgency(note, current),
            0 if _chapter_of(note) < 99999 else 1,
            _chapter_of(note),
            priority_rank.get(str(note.get("priority") or "").strip(), 3),
        ),
    )
    rendered: list[str] = []
    for note in ordered[:20]:
        if not isinstance(note, dict):
            continue
        note_id = str(note.get("id") or "").strip()
        title = str(note.get("title") or "未命名伏笔").strip()
        description = str(note.get("note") or "暂无说明").strip()
        characters = ", ".join(str(item) for item in note.get("related_characters") or [])
        lines = [f"- 伏笔 ID：{note_id}"]
        # 红标紧跟 ID，免得被后面的长说明挤出 700 字封顶之外。
        flag = urgency_label(foreshadowing_urgency(note, current))
        if flag:
            lines.append(f"  {flag}")
        lines += [f"  标题：{title}", f"  说明：{description}"]
        metadata = [
            ("首次出现", note.get("first_seen_chapter")),
            ("最近出现", note.get("recent_seen_chapter")),
            ("计划回收", note.get("planned_resolution_chapter")),
            ("优先级", note.get("priority")),
            ("关联人物", characters),
        ]
        for label, value in metadata:
            if str(value or "").strip():
                lines.append(f"  {label}：{value}")
        rendered.append("\n".join(lines)[:700])
    return "\n\n".join(rendered)[:3500]


def compact_story_state(
    state: dict,
    *,
    value_cap: int = 200,
    hook_cap: int = 120,
    max_list_items: int = 24,
    max_hooks: int = 24,
) -> dict:
    """Bound a story state for prompting without breaking its structure.

    Capped strings end with "…" so prompts can tell the model not to copy a
    truncated value back verbatim.
    """
    if not isinstance(state, dict):
        return {}
    compacted: dict[str, object] = {}
    for key, value in state.items():
        if key == "foreshadowing" and isinstance(value, list):
            compacted[key] = [_cap_text(item, hook_cap) for item in value[:max_hooks]]
        elif key == "characters" and isinstance(value, dict):
            # 已退场（死了 / 走了）的别再占注入预算。
            # 这份 state 是"当前在场"的快照，不是人物总账——写到几百章时，
            # 一串死角色会排在前面，把还活着的重要角色挤出去。
            # （他们的完整档案在 canon/characters/ 里，没丢。）
            #
            # ⚠️ 子串匹配只看**这个角色自己的 state**，而且要求"已死"这类词出现在
            # 开头 12 字内——不然"他父母已死"会把活着的角色也误删。
            live = {
                name: detail for name, detail in value.items()
                if not any(tag in str(detail)[:12] for tag in ("已死", "已退场", "已离场", "身亡"))
            }
            # dict 也得切片：`_cap_value` 只对 list 截断，对 dict 是全量——
            # 那样 max_list_items 就是个死参数（注释说的封顶根本不生效）。
            if max_list_items and len(live) > max_list_items:
                live = dict(list(live.items())[:max_list_items])
            compacted[key] = _cap_value(live, value_cap, max_list_items)
        else:
            compacted[key] = _cap_value(value, value_cap, max_list_items)
    return compacted


def prior_chapter_summaries(
    project: NovelProject,
    chapter_id: str,
    *,
    count: int = 5,
    per_summary_cap: int = 400,
    summaries: dict | None = None,
) -> str:
    """Recent summaries that cannot spoil chapters after the current one.

    Chapters sort numerically (chapter_2 before chapter_10); summaries of
    later chapters are excluded so regenerating an early chapter does not
    feed the model future plot.
    """
    current = chapter_number_from_id(chapter_id)
    entries: list[tuple[int, int, str, str]] = []
    source = summaries if summaries is not None else project.load_chapter_summaries()
    for key, value in (source or {}).items():
        text = str(value).strip()
        if not text or key == chapter_id:
            continue
        number = chapter_number_from_id(key)
        if current is not None and number is not None and number > current:
            continue
        entries.append((0 if number is None else 1, number or 0, key, text))
    entries.sort(key=lambda entry: (entry[0], entry[1]))
    recent = entries[-count:]
    return "\n\n".join(
        f"### {key}\n{_cap_text(text, per_summary_cap)}" for _rank, _number, key, text in recent
    )


def _trim(text: str, allowance: int, keep: str) -> str:
    if keep == "tail":
        return TAIL_MARK + text[-(allowance - len(TAIL_MARK)) :]
    return text[: allowance - len(HEAD_MARK)] + HEAD_MARK


def _cap_value(value: object, cap: int, max_items: int) -> object:
    if isinstance(value, str):
        return _cap_text(value, cap)
    if isinstance(value, list):
        return [_cap_value(item, cap, max_items) for item in value[:max_items]]
    if isinstance(value, dict):
        return {str(key): _cap_value(item, cap, max_items) for key, item in value.items()}
    return value


def _cap_text(value: object, cap: int) -> str:
    text = str(value).strip()
    if len(text) <= cap:
        return text
    return text[:cap].rstrip() + "…"
