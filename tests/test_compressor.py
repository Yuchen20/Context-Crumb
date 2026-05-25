import importlib.util
import unittest

from contextcrumb.compressor import (
    ContextCompressor,
    TokenDecision,
    aggregate_word_keep_probabilities,
    build_compressed_text,
    build_token_decisions,
    compute_golden_cutoff,
)
from contextcrumb.spans import tokenize_with_spans


class CompressorTests(unittest.TestCase):
    def test_threshold_decisions_keep_scores_at_or_above_threshold(self):
        tokens = tokenize_with_spans("A small test.")
        decisions = build_token_decisions(tokens, [0.9, 0.2, 0.7, 0.1], 0.5, None)

        self.assertEqual([decision.keep for decision in decisions], [True, False, True, False])

    def test_target_keep_ratio_keeps_highest_probabilities(self):
        tokens = tokenize_with_spans("A small test.")
        decisions = build_token_decisions(tokens, [0.9, 0.2, 0.7, 0.1], 0.5, 0.5)

        self.assertEqual([decision.keep for decision in decisions], [True, False, True, False])

    def test_compressed_text_preserves_original_token_spans(self):
        original = "Hello,   careful world!"
        decisions = [
            TokenDecision("Hello", 0, 5, 0.9, True),
            TokenDecision(",", 5, 6, 0.9, True),
            TokenDecision("careful", 9, 16, 0.1, False),
            TokenDecision("world", 17, 22, 0.9, True),
            TokenDecision("!", 22, 23, 0.9, True),
        ]

        self.assertEqual(build_compressed_text(original, decisions), "Hello, world!")

    def test_sliding_window_probabilities_are_averaged_by_word_id(self):
        probabilities = aggregate_word_keep_probabilities(
            word_ids_by_window=[
                [None, 0, 1, 1, None],
                [None, 1, 2, None],
            ],
            keep_probs_by_window=[
                [0.0, 0.2, 0.8, 0.6, 0.0],
                [0.0, 0.4, 0.9, 0.0],
            ],
            word_count=3,
        )

        self.assertEqual(probabilities, [0.2, 0.6, 0.9])

    def test_invalid_target_keep_ratio_raises(self):
        tokens = tokenize_with_spans("A test.")

        with self.assertRaises(ValueError):
            build_token_decisions(tokens, [0.9, 0.8, 0.7], 0.5, 1.1)

    def test_golden_cutoff_uses_largest_word_token_probability_gap(self):
        tokens = tokenize_with_spans("Keep this, delete that.")
        cutoff = compute_golden_cutoff(tokens, [0.95, 0.9, 0.99, 0.2, 0.1, 0.99])

        self.assertAlmostEqual(cutoff.cutoff, 0.55)
        self.assertAlmostEqual(cutoff.gap, 0.7)
        self.assertAlmostEqual(cutoff.keep_ratio, 0.5)
        self.assertEqual(cutoff.keep_count, 2)
        self.assertEqual(cutoff.basis_count, 4)
        self.assertFalse(cutoff.capped)

    def test_golden_cutoff_keeps_at_least_one_third_word_tokens(self):
        tokens = tokenize_with_spans("one two three four five six")
        cutoff = compute_golden_cutoff(tokens, [0.99, 0.1, 0.09, 0.08, 0.07, 0.06])

        self.assertAlmostEqual(cutoff.cutoff, 0.1)
        self.assertAlmostEqual(cutoff.keep_ratio, 1 / 3)
        self.assertEqual(cutoff.keep_count, 2)
        self.assertEqual(cutoff.basis_count, 6)
        self.assertTrue(cutoff.capped)

    def test_target_keep_ratio_overrides_default_golden_mode(self):
        class FakeCompressor(ContextCompressor):
            def __init__(self):
                self.max_length = 1024
                self.stride = 64
                self.backend = "fake"
                self.window_batch_size = None

            def score_keep_probabilities(self, text):
                return tokenize_with_spans(text), [0.9, 0.1, 0.8, 0.2], 1

        result = FakeCompressor().compress("A small test.", target_keep_ratio=0.5)

        self.assertEqual(result.stats["mode"], "target_keep_ratio")
        self.assertEqual(result.stats["target_keep_ratio"], 0.5)
        self.assertNotIn("golden_cutoff", result.stats)

    @unittest.skipIf(importlib.util.find_spec("torch") is None, "torch optional dependency is not installed")
    def test_from_components_uses_provided_model(self):
        class FakeModel:
            label2id = {"KEEP": 1}

            def __init__(self):
                self.device = None
                self.eval_called = False

            def to(self, device):
                self.device = device
                return self

            def eval(self):
                self.eval_called = True

        tokenizer = object()
        model = FakeModel()

        compressor = ContextCompressor.from_components(tokenizer, model, device="cpu")

        self.assertEqual(compressor.backend, "torch")
        self.assertIs(compressor.tokenizer, tokenizer)
        self.assertIs(compressor.model, model)
        self.assertTrue(model.eval_called)
        self.assertIsNotNone(model.device)


if __name__ == "__main__":
    unittest.main()
