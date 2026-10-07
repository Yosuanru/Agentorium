"""框架图数据（`core/swimlanes.py`）——重点是**没有数据时不许崩**。"""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from core.swimlanes import load_swimlanes, swimlanes_path

SAMPLE = {
    "title": "卷一《守拙》",
    "from": 1,
    "to": 100,
    "acts": [
        {"name": "第一幕 落", "from": 1, "to": 10},
        {"name": "第二幕 认门", "from": 11, "to": 34},
    ],
    "lanes": [
        {"id": "main", "name": "主线", "kind": "main",
         "segments": [{"from": 1, "to": 10, "label": "落空", "tone": "solid"}]},
        {"id": "shifu", "name": "师父",
         "segments": [{"from": 1, "to": 9, "label": "落空"},
                      {"from": 10, "to": 34, "label": "淡", "tone": "faint"}]},
    ],
}


def _write(tmp: str, payload) -> Path:
    path = swimlanes_path(tmp)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


class LoadSwimlanesTests(TestCase):
    def test_missing_file_is_not_ok_but_does_not_raise(self) -> None:
        with TemporaryDirectory() as tmp:
            data = load_swimlanes(swimlanes_path(tmp))

            self.assertFalse(data.ok)
            self.assertEqual(data.lanes, ())

    def test_broken_json_is_not_ok(self) -> None:
        with TemporaryDirectory() as tmp:
            swimlanes_path(tmp).write_text("{ 不是 json", encoding="utf-8")

            self.assertFalse(load_swimlanes(swimlanes_path(tmp)).ok)

    def test_reads_acts_lanes_and_segments(self) -> None:
        with TemporaryDirectory() as tmp:
            data = load_swimlanes(_write(tmp, SAMPLE))

            self.assertTrue(data.ok)
            self.assertEqual(data.title, "卷一《守拙》")
            self.assertEqual((data.start, data.end), (1, 100))
            self.assertEqual([a.name for a in data.acts], ["第一幕 落", "第二幕 认门"])
            self.assertEqual([l.name for l in data.lanes], ["主线", "师父"])
            self.assertEqual(data.lanes[0].kind, "main")
            self.assertEqual(data.lanes[1].segments[1].tone, "faint")

    def test_unknown_tone_falls_back_to_solid(self) -> None:
        with TemporaryDirectory() as tmp:
            payload = json.loads(json.dumps(SAMPLE))
            payload["lanes"][0]["segments"][0]["tone"] = "花里胡哨"
            data = load_swimlanes(_write(tmp, payload))

            self.assertEqual(data.lanes[0].segments[0].tone, "solid")

    def test_range_is_inferred_when_not_given(self) -> None:
        with TemporaryDirectory() as tmp:
            data = load_swimlanes(_write(tmp, {
                "lanes": [{"name": "主线",
                           "segments": [{"from": 3, "to": 27}]}],
            }))

            self.assertEqual((data.start, data.end), (1, 27))

    def test_reversed_span_is_normalized(self) -> None:
        with TemporaryDirectory() as tmp:
            data = load_swimlanes(_write(tmp, {
                "from": 1, "to": 50,
                "lanes": [{"name": "主线",
                           "segments": [{"from": 30, "to": 12, "label": "倒着写的"}]}],
            }))

            segment = data.lanes[0].segments[0]
            self.assertEqual((segment.start, segment.end), (12, 30))

    def test_segments_are_sorted_by_start(self) -> None:
        with TemporaryDirectory() as tmp:
            data = load_swimlanes(_write(tmp, {
                "from": 1, "to": 50,
                "lanes": [{"name": "主线", "segments": [
                    {"from": 30, "to": 40}, {"from": 5, "to": 10},
                ]}],
            }))

            self.assertEqual([s.start for s in data.lanes[0].segments], [5, 30])
