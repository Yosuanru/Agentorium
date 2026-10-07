import unittest

from ui.editor import (
    LARGE_DOCUMENT_CHARS,
    MAX_FIND_HIGHLIGHTS,
    calculate_editor_stats,
    find_highlight_config,
)


class EditorPerformanceTests(unittest.TestCase):
    def test_stats_count_body_characters_including_punctuation(self) -> None:
        """只算正文、含标点、不含空格换行（口径对齐番茄，见 core.text_stats）。"""
        self.assertEqual(
            calculate_editor_stats("# 第一章 缺哪一笔\n\n## 正文\n\n你好，世界。\n\n第二段。\n"),
            "10 字 · 2 段 · 约 1 分钟阅读",
        )
        self.assertEqual(calculate_editor_stats(""), "0 字 · 0 段")

    def test_stats_fall_back_to_whole_text_without_body_heading(self) -> None:
        self.assertEqual(
            calculate_editor_stats("你好\n\n第二段。"),
            "6 字 · 2 段 · 约 1 分钟阅读",
        )

    def test_stats_skip_halfwidth_characters(self) -> None:
        """半角字符不计入（番茄口径）——正文里唯一出现的是间隔号 `·`。"""
        self.assertEqual(
            calculate_editor_stats("他看见“无主·三号”。"),
            "10 字 · 1 段 · 约 1 分钟阅读",
        )

    def test_find_highlights_are_limited_for_many_matches(self) -> None:
        limit, suffix = find_highlight_config(1000, MAX_FIND_HIGHLIGHTS + 1)
        self.assertEqual(limit, MAX_FIND_HIGHLIGHTS)
        self.assertIn("仅显示前", suffix)

        limit, suffix = find_highlight_config(1000, 1001)
        self.assertEqual(limit, 0)
        self.assertIn("仅显示数量", suffix)

    def test_large_documents_skip_find_highlights(self) -> None:
        limit, suffix = find_highlight_config(LARGE_DOCUMENT_CHARS, 1)
        self.assertEqual(limit, 0)
        self.assertIn("大文档", suffix)


if __name__ == "__main__":
    unittest.main()
