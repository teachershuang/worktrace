from __future__ import annotations

import unittest

from worktrace.timeline.merge import text_similarity, tokenize


class TimelineMergeTests(unittest.TestCase):
    def test_chinese_text_uses_bigrams_instead_of_whole_sentences(self) -> None:
        tokens = tokenize("配置大模型和 OCR 服务调用流程")

        self.assertIn("配置", tokens)
        self.assertIn("模型", tokens)
        self.assertIn("OCR".lower()[:2], tokens)
        self.assertGreater(len(tokens), 5)

    def test_related_chinese_activity_has_nonzero_similarity(self) -> None:
        similarity = text_similarity(
            "配置大模型和 OCR 服务调用流程",
            "调试大模型与 OCR 服务接口",
        )

        self.assertGreaterEqual(similarity, 0.22)


if __name__ == "__main__":
    unittest.main()
