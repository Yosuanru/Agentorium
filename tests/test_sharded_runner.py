"""分片切段：几段同时跑的前提是每段不重叠、不遗漏。"""

import unittest

from ui.sharded_runner import shard_ranges


class ShardRangesTests(unittest.TestCase):
    def test_covers_everything_without_gap_or_overlap(self):
        rngs = shard_ranges(1, 10, 4)
        self.assertEqual(rngs, [(1, 4), (5, 8), (9, 10)])
        flat = [n for lo, hi in rngs for n in range(lo, hi + 1)]
        self.assertEqual(flat, list(range(1, 11)))

    def test_single_shard_when_range_smaller_than_size(self):
        self.assertEqual(shard_ranges(88, 100, 60), [(88, 100)])

    def test_exact_multiple_has_no_empty_tail(self):
        self.assertEqual(shard_ranges(1, 8, 4), [(1, 4), (5, 8)])

    def test_reversed_range_is_clamped_not_empty(self):
        # 「到」填小了不该切出空段，退化成单段
        self.assertEqual(shard_ranges(50, 10, 20), [(50, 50)])

    def test_start_below_one_is_clamped(self):
        self.assertEqual(shard_ranges(0, 3, 2), [(1, 2), (3, 3)])


if __name__ == "__main__":
    unittest.main()
