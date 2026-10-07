from unittest import TestCase

from core.foreshadowing import (
    URGENCY_NORMAL,
    URGENCY_OVERDUE,
    URGENCY_STALE,
    foreshadowing_urgency,
)
from ui.foreshadowing_selection_dialog import sort_foreshadowing_notes


class ForeshadowingUrgencyTests(TestCase):
    def test_overdue_when_planned_chapter_already_passed(self) -> None:
        note = {"planned_resolution_chapter": "chapter_40"}
        self.assertEqual(foreshadowing_urgency(note, 50), URGENCY_OVERDUE)

    def test_normal_when_planned_chapter_upcoming(self) -> None:
        note = {"planned_resolution_chapter": "chapter_60"}
        self.assertEqual(foreshadowing_urgency(note, 50), URGENCY_NORMAL)

    def test_stale_when_unplanned_and_long_dormant(self) -> None:
        note = {"planned_resolution_chapter": "", "recent_seen_chapter": "chapter_10"}
        self.assertEqual(foreshadowing_urgency(note, 200), URGENCY_STALE)

    def test_falls_back_to_first_seen_when_never_reappeared(self) -> None:
        note = {"first_seen_chapter": "chapter_05"}
        self.assertEqual(foreshadowing_urgency(note, 160), URGENCY_STALE)

    def test_recent_unplanned_note_is_normal(self) -> None:
        note = {"recent_seen_chapter": "chapter_190"}
        self.assertEqual(foreshadowing_urgency(note, 200), URGENCY_NORMAL)

    def test_unknown_current_chapter_is_normal(self) -> None:
        self.assertEqual(foreshadowing_urgency({"first_seen_chapter": "1"}, None), URGENCY_NORMAL)


class ForeshadowingSelectionTests(TestCase):
    def test_stale_note_rises_above_higher_priority(self) -> None:
        notes = [
            {"id": "fresh-high", "title": "新埋的高优先级", "priority": "high",
             "planned_resolution_chapter": "chapter_210", "recent_seen_chapter": "chapter_99",
             "status": "open"},
            {"id": "stale-low", "title": "埋了很久的低优先级", "priority": "low",
             "planned_resolution_chapter": "", "first_seen_chapter": "chapter_01",
             "status": "open"},
        ]
        result = sort_foreshadowing_notes(notes, "chapter_200")
        self.assertEqual([note["id"] for note in result], ["stale-low", "fresh-high"])

    def test_sort_prioritizes_high_and_near_term_notes(self) -> None:
        notes = [
            {
                "id": "low",
                "title": "低优先级",
                "priority": "low",
                "planned_resolution_chapter": "chapter_03",
                "status": "open",
            },
            {
                "id": "high",
                "title": "高优先级",
                "priority": "high",
                "planned_resolution_chapter": "chapter_08",
                "status": "open",
            },
            {
                "id": "resolved",
                "title": "已回收",
                "priority": "high",
                "planned_resolution_chapter": "chapter_02",
                "status": "resolved",
            },
        ]

        result = sort_foreshadowing_notes(notes, "chapter_02")

        self.assertEqual([note["id"] for note in result], ["high", "low"])

    def test_sort_does_not_mutate_input_notes(self) -> None:
        notes = [{"id": "f1", "title": "伏笔", "status": "open", "priority": "medium"}]
        result = sort_foreshadowing_notes(notes, "chapter_01")
        result[0]["title"] = "已修改副本"
        self.assertEqual(notes[0]["title"], "伏笔")
