"""对话栏「应用到正文」的解析：AI 给的 ```正文 块怎么抽出来。

要求：只有明确标了「正文」的围栏才算改稿；解释用的普通代码块不能误伤。
"""

import unittest

from ui.chat_panel import split_candidate


class SplitCandidateTests(unittest.TestCase):
    def test_extracts_body_and_hides_it_from_transcript(self):
        text = "我把开头收紧了。\n\n```正文\n他站在崖边。\n风灌进衣袖。\n```\n\n后面就顺了。"
        shown, body = split_candidate(text)
        self.assertEqual(body, "他站在崖边。\n风灌进衣袖。")
        self.assertIn("改后正文", shown)
        self.assertNotIn("```", shown)
        self.assertIn("后面就顺了", shown)

    def test_plain_reply_has_no_candidate(self):
        shown, body = split_candidate("这段没问题，不用改。")
        self.assertIsNone(body)
        self.assertEqual(shown, "这段没问题，不用改。")

    def test_other_code_fences_are_not_treated_as_prose(self):
        _, body = split_candidate("这样写：\n\n```python\nprint('hi')\n```")
        self.assertIsNone(body)

    def test_empty_fence_yields_no_candidate(self):
        shown, body = split_candidate("```正文\n\n```")
        self.assertIsNone(body)
        self.assertEqual(shown, "```正文\n\n```")

    def test_fence_marker_allows_surrounding_spaces(self):
        _, body = split_candidate("``` 正文\n正文内容。\n```")
        self.assertEqual(body, "正文内容。")


if __name__ == "__main__":
    unittest.main()
