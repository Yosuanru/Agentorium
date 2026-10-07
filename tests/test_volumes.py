"""卷 / 幕 分组（`core/volumes.py`）——重点是**没有表的时候必须跟以前一模一样**。"""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from core.project import loose_chapter_number
from core.volumes import group_chapters, load_volumes, volumes_path

SAMPLE = {
    "volumes": [
        {
            "id": "v1",
            "name": "卷一",
            "title": "守拙",
            "from": 1,
            "to": 100,
            "acts": [
                {"id": "v1a1", "name": "第一幕", "title": "落", "from": 1, "to": 10},
                {"id": "v1a2", "name": "第二幕", "title": "认门", "from": 11, "to": 34},
                {"id": "v1a3", "name": "第三幕", "title": "夺", "from": 35, "to": 50},
            ],
        },
        {
            "id": "v2",
            "name": "卷二",
            "title": "过手",
            "from": 101,
            "to": 200,
            "acts": [{"id": "v2a1", "name": "第一幕", "from": 101, "to": 120}],
        },
    ]
}


def _number_of(path):
    return loose_chapter_number(Path(path).stem)


class LoadVolumesTests(TestCase):
    def test_missing_file_is_empty_not_an_error(self) -> None:
        with TemporaryDirectory() as tmp:
            self.assertEqual(load_volumes(volumes_path(tmp)), [])

    def test_broken_json_is_empty_not_an_error(self) -> None:
        with TemporaryDirectory() as tmp:
            path = volumes_path(tmp)
            path.write_text("{ 这不是 json", encoding="utf-8")
            self.assertEqual(load_volumes(path), [])

    def test_reads_labels_and_ranges(self) -> None:
        with TemporaryDirectory() as tmp:
            path = volumes_path(tmp)
            path.write_text(json.dumps(SAMPLE, ensure_ascii=False), encoding="utf-8")

            volumes = load_volumes(path)

            self.assertEqual([v.label for v in volumes], ["卷一 守拙", "卷二 过手"])
            self.assertEqual((volumes[0].start, volumes[0].end), (1, 100))
            self.assertEqual(
                [a.label for a in volumes[0].acts],
                ["第一幕 落", "第二幕 认门", "第三幕 夺"],
            )

    def test_entry_without_range_is_skipped(self) -> None:
        with TemporaryDirectory() as tmp:
            path = volumes_path(tmp)
            path.write_text(
                json.dumps({"volumes": [{"name": "没有起止"}, SAMPLE["volumes"][0]]},
                           ensure_ascii=False),
                encoding="utf-8",
            )

            volumes = load_volumes(path)

            self.assertEqual([v.id for v in volumes], ["v1"])


class GroupChaptersTests(TestCase):
    def setUp(self) -> None:
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = volumes_path(tmp.name)
        path.write_text(json.dumps(SAMPLE, ensure_ascii=False), encoding="utf-8")
        self.volumes = load_volumes(path)
        # 故意乱序传进去 —— 分组要按表里的顺序排，不按传入顺序
        self.chapters = [f"chapter_{n:02d}" for n in (3, 1, 40, 12, 105, 2)]

    def test_without_volumes_it_is_one_flat_block(self) -> None:
        blocks = group_chapters([], self.chapters, _number_of)

        self.assertEqual(len(blocks), 1)
        volume, acts = blocks[0]
        self.assertIsNone(volume)
        self.assertEqual(acts, [(None, self.chapters)])

    def test_volumes_come_out_in_declared_order(self) -> None:
        blocks = group_chapters(self.volumes, self.chapters, _number_of)

        self.assertEqual([b[0].id for b in blocks], ["v1", "v2"])

    def test_acts_keep_declared_order_and_drop_empty_ones(self) -> None:
        blocks = group_chapters(self.volumes, self.chapters, _number_of)

        v1 = blocks[0][1]
        # 第三幕（35–50）里只有 40 一章 → 留；没有内容的幕不出现
        self.assertEqual([act.id for act, _ in v1], ["v1a1", "v1a2", "v1a3"])
        self.assertEqual(v1[0][1], ["chapter_01", "chapter_02", "chapter_03"])
        self.assertEqual(v1[1][1], ["chapter_12"])
        self.assertEqual(v1[2][1], ["chapter_40"])

    def test_chapter_outside_the_table_gets_its_own_block(self) -> None:
        blocks = group_chapters(self.volumes, self.chapters + ["chapter_500"], _number_of)

        self.assertIsNone(blocks[-1][0])
        self.assertEqual(blocks[-1][1][0][1], ["chapter_500"])

    def test_front_matter_before_the_first_volume_goes_on_top(self) -> None:
        blocks = group_chapters(self.volumes, ["chapter_00", "chapter_05"], _number_of)

        self.assertIsNone(blocks[0][0])
        self.assertEqual(blocks[0][1][0][1], ["chapter_00"])
        # 第二块才是卷，且 05 落进第一幕
        self.assertEqual(blocks[1][0].id, "v1")
        self.assertEqual(blocks[1][1][0][1], ["chapter_05"])

    def test_untitled_ids_do_not_crash_and_land_in_the_loose_block(self) -> None:
        blocks = group_chapters(self.volumes, ["序章"], _number_of)

        self.assertIsNone(blocks[0][0])
        self.assertEqual(blocks[0][1][0][1], ["序章"])
