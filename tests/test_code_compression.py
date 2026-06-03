import tempfile
import unittest
from pathlib import Path

from contextcrumb.code_compression import compress_code_comments
from contextcrumb.config import CodeConfig
from contextcrumb.compressor import CompressionResult


class FakeSpanCompressor:
    def __init__(self):
        self.inputs = []

    def compress(
        self,
        text,
        *,
        threshold=0.5,
        target_keep_ratio=None,
        golden=True,
        golden_min_keep_ratio=1 / 3,
        return_tokens=False,
    ):
        self.inputs.append((text, target_keep_ratio))
        return CompressionResult(text="short", original_text=text, stats={"mode": "threshold"})


class CodeCompressionTests(unittest.TestCase):
    def test_python_comments_and_docstrings_compress_without_changing_code(self):
        source = (
            "# This is a long module comment\n"
            "def add(a, b):\n"
            "    \"\"\"This explains the addition behavior in many words\"\"\"\n"
            "    return a + b  # This inline comment is verbose\n"
        )
        compressor = FakeSpanCompressor()

        result = compress_code_comments(
            compressor,
            source,
            path="example.py",
            config=CodeConfig(),
        )

        self.assertIn("# short\n", result.text)
        self.assertIn('"""short"""', result.text)
        self.assertIn("def add(a, b):\n", result.text)
        self.assertIn("    return a + b  # short\n", result.text)
        self.assertEqual(result.stats["content_mode"], "code-comments")
        self.assertTrue(result.stats["preserved_code_exact"])
        self.assertEqual(result.stats["compressed_span_count"], 3)
        self.assertEqual([ratio for _, ratio in compressor.inputs], [0.55, 0.65, 0.55])

    def test_typescript_comments_compress_without_changing_code(self):
        source = (
            "const value = 1; // This explains the value in too many words\n"
            "/* This block comment explains a public API in too many words */\n"
            "export function getValue() { return value; }\n"
        )
        compressor = FakeSpanCompressor()

        result = compress_code_comments(
            compressor,
            source,
            path="example.ts",
            config=CodeConfig(),
        )

        self.assertIn("const value = 1; // short\n", result.text)
        self.assertIn("/* short */", result.text)
        self.assertIn("export function getValue() { return value; }\n", result.text)
        self.assertEqual(result.stats["code_language"], "typescript")


if __name__ == "__main__":
    unittest.main()
