"""拆书提示词的生成：占位符不能有残留、段数要带进去。

⚠️ 为什么要有这个测试：静态检查只能数占位符**个数**，
个数对但**顺序/类型**错（有次把书名顶到了 %d 上）它查不出来，只有真跑才炸。

⚠️ 这里**故意不碰 Qt**——提示词拼装已经抽成 `core.ingest.build_ingest_prompt`。
早先这测试要起一个 MainWindow 才验得了，结果在整套里和别的 Qt 测试打架、把跑测卡死。
纯函数测起来干净也快。
"""

import unittest

from core.ingest import build_ingest_prompt


class IngestPromptTests(unittest.TestCase):
    def test_prompt_has_no_leftover_placeholders(self):
        text = build_ingest_prompt("天不应", "full", 151, 160, 4)
        self.assertNotIn("%s", text)
        self.assertNotIn("%d", text)
        self.assertIn("第 151–160 章", text)
        self.assertIn("《天不应》", text)

    def test_shard_count_reaches_prompt(self):
        self.assertIn("希望分 **6 段**", build_ingest_prompt("天不应", "full", 1, 60, 6))

    def test_light_mode_says_rough(self):
        text = build_ingest_prompt("天不应", "light", 1, 5, 2)
        self.assertIn("粗拆", text)
        self.assertIn("全本逐章拆", build_ingest_prompt("天不应", "full", 1, 5, 2))

    def test_shard_count_is_clamped(self):
        self.assertIn("希望分 **12 段**", build_ingest_prompt("书", "full", 1, 999, 99))
        # 0 / 空 = "没填"，退回默认 4（不是 1）——界面上的框最少就是 1
        self.assertIn("希望分 **4 段**", build_ingest_prompt("书", "full", 1, 999, 0))
        self.assertIn("希望分 **1 段**", build_ingest_prompt("书", "full", 1, 999, 1))

    def test_range_and_paths_land_where_expected(self):
        text = build_ingest_prompt("天不应", "full", 88, 107, 3)
        self.assertIn("拆文库/天不应/原文/原文.txt", text)
        self.assertIn("拆文库/天不应/chapter_index.csv", text)
        self.assertIn("片段-88-107.md", text)


if __name__ == "__main__":
    unittest.main()
