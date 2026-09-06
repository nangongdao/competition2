"""Unit tests for the translation memory service (V5.3)."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest


BACKEND_ROOT = Path(__file__).resolve().parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from services.translation_memory import (
    MAX_ENTRIES,
    TranslationMemoryService,
    build_language_pair,
    character_similarity,
    normalize_text,
    token_jaccard_similarity,
)


class NormalizeTests(unittest.TestCase):
    def test_normalize_lowercases_and_strips_punctuation(self) -> None:
        self.assertEqual(
            normalize_text("Hello, World! 你好，世界！"),
            "hello world 你好 世界",
        )

    def test_normalize_empty(self) -> None:
        self.assertEqual(normalize_text("   "), "")
        self.assertEqual(normalize_text(""), "")


class SimilarityTests(unittest.TestCase):
    def test_character_similarity_perfect_match(self) -> None:
        self.assertEqual(character_similarity("hello world", "hello world"), 1.0)

    def test_character_similarity_partial(self) -> None:
        similarity = character_similarity("hello world", "hello there")
        self.assertGreater(similarity, 0.5)
        self.assertLess(similarity, 1.0)

    def test_character_similarity_no_overlap(self) -> None:
        self.assertEqual(character_similarity("abc", "xyz"), 0.0)

    def test_token_jaccard_overlap(self) -> None:
        self.assertGreater(
            token_jaccard_similarity("the quick fox", "a quick fox"),
            0.0,
        )
        self.assertEqual(
            token_jaccard_similarity("the quick fox", "zzz yyy xxx"),
            0.0,
        )


class TranslationMemoryServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tm = TranslationMemoryService(session_id="test-session")

    def test_lookup_exact_hit(self) -> None:
        self.tm.add("Good morning everyone", "大家早上好", language_pair="en->zh-CN")
        match = self.tm.lookup("Good morning everyone", language_pair="en->zh-CN")

        self.assertIsNotNone(match)
        if match is not None:
            self.assertEqual(match.translated, "大家早上好")
            self.assertEqual(match.similarity, 1.0)

    def test_lookup_exact_hit_is_case_and_punctuation_insensitive(self) -> None:
        self.tm.add("Hello, World!", "你好，世界", language_pair="en->zh-CN")
        match = self.tm.lookup("hello world", language_pair="en->zh-CN")

        self.assertIsNotNone(match)
        if match is not None:
            self.assertEqual(match.translated, "你好，世界")

    def test_lookup_fuzzy_hit_for_similar_sentence(self) -> None:
        self.tm.add(
            "The Kubernetes cluster is running in production",
            "Kubernetes 集群已在生产环境运行",
            language_pair="en->zh-CN",
        )
        match = self.tm.lookup(
            "The Kubernetes cluster is running in production now",
            language_pair="en->zh-CN",
        )

        self.assertIsNotNone(match)
        if match is not None:
            self.assertGreaterEqual(match.similarity, 0.82)

    def test_lookup_miss_for_unrelated_sentence(self) -> None:
        self.tm.add("Good morning everyone", "大家早上好", language_pair="en->zh-CN")
        match = self.tm.lookup(
            "Quantum physics explains subatomic particles",
            language_pair="en->zh-CN",
        )

        self.assertIsNone(match)

    def test_lookup_short_sentence_does_not_fuzzy_match(self) -> None:
        self.tm.add("Hi there", "你好", language_pair="en->zh-CN")
        # 过短句子不模糊匹配
        match = self.tm.lookup("Hi", language_pair="en->zh-CN")
        self.assertIsNone(match)

    def test_lookup_respects_language_pair(self) -> None:
        self.tm.add("Hello", "你好", language_pair="en->zh-CN")
        # 语言对不一致时不命中
        match = self.tm.lookup("Hello", language_pair="ja->zh-CN")
        self.assertIsNone(match)

    def test_add_deduplicates_and_updates(self) -> None:
        self.tm.add("Hello world", "你好世界", language_pair="en->zh-CN")
        self.tm.add("Hello world", "你好世界（修正）", language_pair="en->zh-CN")

        self.assertEqual(self.tm.size, 1)
        match = self.tm.lookup("Hello world", language_pair="en->zh-CN")
        if match is not None:
            self.assertEqual(match.translated, "你好世界（修正）")

    def test_stats_counts(self) -> None:
        self.tm.add("Alpha beta gamma", "阿尔法贝塔伽马", language_pair="en->zh-CN")
        self.tm.lookup("Alpha beta gamma", language_pair="en->zh-CN")  # hit
        self.tm.lookup("Totally different thing", language_pair="en->zh-CN")  # miss

        stats = self.tm.stats
        self.assertEqual(stats["hits"], 1)
        self.assertEqual(stats["misses"], 1)
        self.assertEqual(stats["written"], 1)
        self.assertEqual(stats["size"], 1)

    def test_export_and_load_roundtrip(self) -> None:
        self.tm.add("Hello world", "你好世界", language_pair="en->zh-CN")
        entries = self.tm.export_entries()

        new_tm = TranslationMemoryService(session_id="other")
        imported = new_tm.load_entries(entries)
        self.assertEqual(imported, 1)
        match = new_tm.lookup("Hello world", language_pair="en->zh-CN")
        self.assertIsNotNone(match)

    def test_load_entries_ignores_invalid(self) -> None:
        imported = self.tm.load_entries([
            {"source": "A", "translated": "甲"},
            {"source": "", "translated": "乙"},
            {"source": "C", "translated": ""},
            "not-a-dict",
            {"source": 123, "translated": "x"},
        ])
        self.assertEqual(imported, 1)

    def test_capacity_bounded(self) -> None:
        for index in range(MAX_ENTRIES + 10):
            self.tm.add(f"Sentence number {index}", f"句子 {index}", language_pair="en->zh-CN")

        self.assertLessEqual(self.tm.size, MAX_ENTRIES)

    def test_clear(self) -> None:
        self.tm.add("Hello", "你好", language_pair="en->zh-CN")
        self.tm.clear()
        self.assertEqual(self.tm.size, 0)
        self.assertIsNone(self.tm.lookup("Hello", language_pair="en->zh-CN"))

    def test_to_json_roundtrip(self) -> None:
        self.tm.add("Hello world", "你好世界", language_pair="en->zh-CN")
        payload = self.tm.to_json()
        self.assertIn("你好世界", payload)
        self.assertIn("version", payload)


class LanguagePairTests(unittest.TestCase):
    def test_build_language_pair(self) -> None:
        self.assertEqual(build_language_pair("en", "zh-CN"), "en->zh-CN")
        self.assertEqual(build_language_pair("zh-CN", "en"), "zh-CN->en")


if __name__ == "__main__":
    unittest.main()
