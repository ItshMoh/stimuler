import unittest

from scoring import (
    build_reliability_warnings,
    detect_fillers,
    detect_pauses,
    levenshtein_distance,
    score_accuracy,
    score_delivery,
    score_pronunciation,
    text_to_phonetic,
    tokenize,
)


class ScoringTest(unittest.TestCase):
    def test_tokenize_normalizes_case_and_punctuation(self):
        self.assertEqual(tokenize("Hello, I'm Michael."), ["hello", "im", "michael"])

    def test_exact_match_scores_100(self):
        result = score_accuracy(
            "Hello, I am Michael from Philadelphia.",
            "hello i am michael from philadelphia",
        )

        self.assertEqual(result["accuracy"], 100)
        self.assertEqual(result["metrics"]["match_count"], 6)
        self.assertEqual(result["metrics"]["substitution_count"], 0)

    def test_one_word_answer_scores_low(self):
        result = score_accuracy(
            "Hello, I am Michael from Philadelphia.",
            "hello",
        )

        self.assertEqual(result["accuracy"], 17)
        self.assertEqual(result["metrics"]["omission_count"], 5)

    def test_wrong_fluent_sentence_scores_zero(self):
        result = score_accuracy(
            "Hello, I am Michael from Philadelphia.",
            "today i want to discuss my favorite food",
        )

        self.assertEqual(result["accuracy"], 0)
        self.assertGreaterEqual(result["metrics"]["substitution_count"], 5)

    def test_omitted_word_is_counted(self):
        result = score_accuracy(
            "The project is on track.",
            "the project on track",
        )

        self.assertEqual(result["accuracy"], 80)
        self.assertEqual(result["metrics"]["omission_count"], 1)

    def test_inserted_words_are_penalized_less_than_missing_target_words(self):
        result = score_accuracy(
            "The project is on track.",
            "the project is currently on track",
        )

        self.assertEqual(result["accuracy"], 90)
        self.assertEqual(result["metrics"]["insertion_count"], 1)

    def test_delivery_scores_wpm_fillers_and_pauses(self):
        words = [
            {"word": "hello", "start": 0.0, "end": 0.3},
            {"word": "um", "start": 0.4, "end": 0.6},
            {"word": "i", "start": 1.9, "end": 2.0},
            {"word": "am", "start": 2.2, "end": 2.4},
            {"word": "michael", "start": 2.5, "end": 2.9},
        ]

        result = score_delivery(words)

        self.assertEqual(result["metrics"]["words_per_minute"], 103)
        self.assertEqual(result["metrics"]["filler_count"], 1)
        self.assertEqual(result["metrics"]["awkward_pause_count"], 1)
        self.assertEqual(result["scores"]["filler"], 88)
        self.assertLess(result["scores"]["pause"], 100)
        self.assertLess(result["scores"]["fluency"], 100)

    def test_detect_fillers_includes_multi_word_phrase(self):
        fillers = detect_fillers(
            [
                {"word": "you", "start": 0.0, "end": 0.1},
                {"word": "know", "start": 0.1, "end": 0.3},
                {"word": "actually", "start": 0.4, "end": 0.7},
            ]
        )

        self.assertEqual([filler["word"] for filler in fillers], ["you know", "actually"])

    def test_detect_pauses_ignores_short_gaps(self):
        pauses = detect_pauses(
            [
                {"word": "the", "start": 0.0, "end": 0.2},
                {"word": "project", "start": 0.8, "end": 1.0},
                {"word": "is", "start": 2.4, "end": 2.5},
            ]
        )

        self.assertEqual(len(pauses), 1)
        self.assertEqual(pauses[0]["type"], "awkward_pause")

    def test_text_to_phonetic_normalizes_similar_sounds(self):
        self.assertEqual(text_to_phonetic("Phone quick"), "fn kwk")

    def test_levenshtein_distance_counts_edits(self):
        self.assertEqual(levenshtein_distance("kitten", "sitting"), 3)

    def test_pronunciation_scores_exact_transcript_high(self):
        result = score_pronunciation(
            "Hello, I am Michael from Philadelphia.",
            "hello i am michael from philadelphia",
            [
                {"word": "hello", "confidence": 0.96},
                {"word": "i", "confidence": 0.98},
                {"word": "am", "confidence": 0.97},
                {"word": "michael", "confidence": 0.94},
                {"word": "from", "confidence": 0.95},
                {"word": "philadelphia", "confidence": 0.92},
            ],
        )

        self.assertGreaterEqual(result["score"], 95)
        self.assertEqual(result["metrics"]["phonetic_similarity"], 100)

    def test_pronunciation_scores_wrong_transcript_lower(self):
        result = score_pronunciation(
            "Hello, I am Michael from Philadelphia.",
            "today we discuss food",
            [{"word": "today", "confidence": 0.98}],
        )

        self.assertLess(result["score"], 60)

    def test_reliability_warning_uses_low_transcript_confidence(self):
        warnings = build_reliability_warnings(0.7, [{"word": "hello", "confidence": 0.9}])

        self.assertEqual(len(warnings), 1)

    def test_reliability_warning_uses_word_confidence_when_transcript_missing(self):
        warnings = build_reliability_warnings(
            None,
            [{"word": "hello", "confidence": 0.7}, {"word": "there", "confidence": 0.75}],
        )

        self.assertEqual(len(warnings), 1)


if __name__ == "__main__":
    unittest.main()
