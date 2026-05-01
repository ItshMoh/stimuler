import unittest

from scoring import score_accuracy, tokenize


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


if __name__ == "__main__":
    unittest.main()
