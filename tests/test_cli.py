import io
import json
import os
import tempfile
import unittest
from urllib.error import HTTPError
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch

from contextcrumb.cli import main
from contextcrumb.compressor import CompressionResult, TokenDecision


class FakeCompressor:
    def __init__(self) -> None:
        self.calls = []

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
        self.calls.append((text, threshold, target_keep_ratio, golden, golden_min_keep_ratio, return_tokens))
        return CompressionResult(
            text="compressed text",
            original_text=text,
            stats={
                "input_tokens": 2,
                "kept_tokens": 1,
                "deleted_tokens": 1,
                "token_keep_ratio": 0.5,
            },
        )

    def compress_file(
        self,
        path,
        *,
        encoding="utf-8",
        threshold=0.5,
        target_keep_ratio=None,
        golden=True,
        golden_min_keep_ratio=1 / 3,
        return_tokens=False,
    ):
        text = Path(path).read_text(encoding=encoding)
        self.calls.append((str(path), encoding, threshold, target_keep_ratio, golden, golden_min_keep_ratio, return_tokens))
        tokens = [
            TokenDecision("file", 0, 4, 0.9, True),
            TokenDecision("text", 5, 9, 0.1, False),
        ] if return_tokens and text == "file text" else []
        return CompressionResult(
            text="compressed file context",
            original_text=text,
            stats={
                "input_tokens": 4,
                "kept_tokens": 2,
                "deleted_tokens": 2,
                "token_keep_ratio": 0.5,
                "source_path": str(path),
                "source_encoding": encoding,
            },
            tokens=tokens,
        )


class CliTests(unittest.TestCase):
    def setUp(self):
        self._stats_temp = tempfile.TemporaryDirectory()
        self._env_patch = patch.dict(
            os.environ,
            {
                "CONTEXTCRUMB_STATS_FILE": str(Path(self._stats_temp.name) / "stats.jsonl"),
                "CONTEXTCRUMB_STATS_PATH_MODE": "basename",
            },
        )
        self._env_patch.start()

    def tearDown(self):
        self._env_patch.stop()
        self._stats_temp.cleanup()

    def test_cli_outputs_plain_text(self):
        fake = FakeCompressor()
        output = io.StringIO()

        with patch("contextcrumb.cli.ContextCompressor", return_value=fake):
            with redirect_stdout(output):
                exit_code = main(["compress", "--text", "some long text"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(output.getvalue().strip(), "compressed text")
        self.assertEqual(fake.calls, [("some long text", 0.5, None, True, 1 / 3, False)])
        stats_path = Path(os.environ["CONTEXTCRUMB_STATS_FILE"])
        event = json.loads(stats_path.read_text(encoding="utf-8"))
        self.assertEqual(event["source"], "cli")
        self.assertEqual(event["command"], "compress")

    def test_cli_reads_input_file_and_outputs_json(self):
        fake = FakeCompressor()
        output = io.StringIO()

        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "input.txt"
            input_path.write_text("file text", encoding="utf-8")

            with patch("contextcrumb.cli.ContextCompressor", return_value=fake):
                with redirect_stdout(output):
                    exit_code = main(["compress", "--input", str(input_path), "--json"])

        payload = json.loads(output.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["text"], "compressed text")
        self.assertEqual(payload["original_text"], "file text")
        self.assertEqual(fake.calls, [("file text", 0.5, None, True, 1 / 3, False)])

    def test_cli_accepts_positional_file_for_compress(self):
        fake = FakeCompressor()
        output = io.StringIO()

        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "input.txt"
            input_path.write_text("file text", encoding="utf-8")

            with patch("contextcrumb.cli.ContextCompressor", return_value=fake):
                with redirect_stdout(output):
                    exit_code = main(["compress", str(input_path)])

        self.assertEqual(exit_code, 0)
        self.assertEqual(output.getvalue().strip(), "compressed text")
        self.assertEqual(fake.calls, [("file text", 0.5, None, True, 1 / 3, False)])

    def test_cli_can_disable_golden_mode(self):
        fake = FakeCompressor()
        output = io.StringIO()

        with patch("contextcrumb.cli.ContextCompressor", return_value=fake):
            with redirect_stdout(output):
                exit_code = main(["compress", "--text", "some long text", "--no-golden"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(fake.calls, [("some long text", 0.5, None, False, 1 / 3, False)])

    def test_cli_rejects_empty_text(self):
        with self.assertRaises(SystemExit):
            main(["compress", "--text", "   "])

    def test_cli_load_file_defaults_to_golden_mode(self):
        fake = FakeCompressor()
        output = io.StringIO()

        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "context.txt"
            input_path.write_text("large file context", encoding="utf-8")

            with patch("contextcrumb.cli.ContextCompressor", return_value=fake):
                with redirect_stdout(output):
                    exit_code = main(["load", str(input_path)])

        self.assertEqual(exit_code, 0)
        self.assertEqual(output.getvalue().strip(), "compressed file context")
        self.assertEqual(fake.calls, [(str(input_path), "utf-8", 0.5, None, True, 1 / 3, False)])

    def test_cli_load_file_outputs_json_with_source_stats(self):
        fake = FakeCompressor()
        output = io.StringIO()

        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "context.txt"
            input_path.write_text("large file context", encoding="utf-8")

            with patch("contextcrumb.cli.ContextCompressor", return_value=fake):
                with redirect_stdout(output):
                    exit_code = main(["load", str(input_path), "--json"])

        payload = json.loads(output.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["text"], "compressed file context")
        self.assertEqual(payload["stats"]["source_path"], str(input_path))
        event = json.loads(Path(os.environ["CONTEXTCRUMB_STATS_FILE"]).read_text(encoding="utf-8"))
        self.assertEqual(event["source_path"], "context.txt")

    def test_cli_no_stats_disables_logging(self):
        fake = FakeCompressor()
        output = io.StringIO()

        with patch("contextcrumb.cli.ContextCompressor", return_value=fake):
            with redirect_stdout(output):
                exit_code = main(["compress", "--text", "some long text", "--no-stats"])

        self.assertEqual(exit_code, 0)
        self.assertFalse(Path(os.environ["CONTEXTCRUMB_STATS_FILE"]).exists())

    def test_cli_stats_no_history(self):
        output = io.StringIO()

        with redirect_stdout(output):
            exit_code = main(["stats"])

        self.assertEqual(exit_code, 0)
        self.assertIn("Runs:", output.getvalue())
        self.assertIn("0", output.getvalue())

    def test_cli_stats_json(self):
        fake = FakeCompressor()
        output = io.StringIO()

        with patch("contextcrumb.cli.ContextCompressor", return_value=fake):
            with redirect_stdout(io.StringIO()):
                main(["compress", "--text", "some long text"])
            with redirect_stdout(output):
                exit_code = main(["stats", "--json"])

        payload = json.loads(output.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["runs"], 1)
        self.assertEqual(payload["tokens_saved"], 1)

    def test_cli_load_target_keep_ratio_overrides_golden_mode(self):
        fake = FakeCompressor()
        output = io.StringIO()

        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "context.txt"
            input_path.write_text("large file context", encoding="utf-8")

            with patch("contextcrumb.cli.ContextCompressor", return_value=fake):
                with redirect_stdout(output):
                    exit_code = main(["load", str(input_path), "--target-keep-ratio", "0.3"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(fake.calls, [(str(input_path), "utf-8", 0.5, 0.3, True, 1 / 3, False)])

    def test_cli_inspect_outputs_stats_report(self):
        fake = FakeCompressor()
        output = io.StringIO()

        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "input.txt"
            input_path.write_text("file text", encoding="utf-8")

            with patch("contextcrumb.cli.ContextCompressor", return_value=fake):
                with redirect_stdout(output):
                    exit_code = main(["inspect", str(input_path)])

        self.assertEqual(exit_code, 0)
        self.assertIn("Source:", output.getvalue())
        self.assertIn("Tokens:", output.getvalue())

    def test_cli_diff_marks_deleted_tokens(self):
        fake = FakeCompressor()
        output = io.StringIO()

        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "input.txt"
            input_path.write_text("file text", encoding="utf-8")

            with patch("contextcrumb.cli.ContextCompressor", return_value=fake):
                with redirect_stdout(output):
                    exit_code = main(["diff", str(input_path)])

        self.assertEqual(exit_code, 0)
        self.assertEqual(output.getvalue().strip(), "file [-text-]")
        self.assertEqual(fake.calls, [(str(input_path), "utf-8", 0.5, None, True, 1 / 3, True)])

    def test_cli_batch_writes_compressed_files(self):
        fake = FakeCompressor()
        output = io.StringIO()

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_dir = root / "docs"
            output_dir = root / "compressed"
            nested = input_dir / "nested"
            nested.mkdir(parents=True)
            first = input_dir / "a.md"
            second = nested / "b.md"
            first.write_text("file text", encoding="utf-8")
            second.write_text("file text", encoding="utf-8")

            with patch("contextcrumb.cli.ContextCompressor", return_value=fake):
                with redirect_stdout(output):
                    exit_code = main(["batch", str(input_dir), "--glob", "*.md", "--out", str(output_dir)])

            self.assertEqual((output_dir / "a.md").read_text(encoding="utf-8"), "compressed file context")
            self.assertEqual((output_dir / "nested" / "b.md").read_text(encoding="utf-8"), "compressed file context")

        self.assertEqual(exit_code, 0)
        self.assertIn("Compressed 2 file(s).", output.getvalue())

    def test_cli_compress_can_use_service_for_text(self):
        output = io.StringIO()
        result = CompressionResult(text="service text", original_text="some long text", stats={"mode": "golden"})

        with patch("contextcrumb.cli.ContextCompressor") as compressor_class:
            with patch("contextcrumb.cli.service_compress_text", return_value=result) as service_compress:
                with redirect_stdout(output):
                    exit_code = main(["compress", "--text", "some long text", "--use-service"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(output.getvalue().strip(), "service text")
        compressor_class.assert_not_called()
        service_compress.assert_called_once()

    def test_cli_service_payload_forwards_no_stats(self):
        output = io.StringIO()
        result = CompressionResult(text="service text", original_text="some long text", stats={"mode": "golden"})

        with patch("contextcrumb.cli.service_request") as service_request:
            with patch("contextcrumb.cli.service_compress_text", return_value=result) as service_compress:
                with redirect_stdout(output):
                    exit_code = main(["compress", "--text", "some long text", "--use-service", "--no-stats"])

        self.assertEqual(exit_code, 0)
        service_compress.assert_called_once()
        args = service_compress.call_args.args[1]
        self.assertTrue(args.no_stats)
        service_request.assert_not_called()

    def test_cli_load_can_use_service_for_file(self):
        output = io.StringIO()
        result = CompressionResult(text="service file", original_text="file text", stats={"mode": "golden"})

        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "input.txt"
            input_path.write_text("file text", encoding="utf-8")

            with patch("contextcrumb.cli.ContextCompressor") as compressor_class:
                with patch("contextcrumb.cli.service_compress_file", return_value=result) as service_compress:
                    with redirect_stdout(output):
                        exit_code = main(["load", str(input_path), "--use-service"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(output.getvalue().strip(), "service file")
        compressor_class.assert_not_called()
        service_compress.assert_called_once()

    def test_cli_service_status_outputs_health(self):
        output = io.StringIO()
        health = {"model_loaded": True, "backend": "onnx", "idle_seconds": 1.25, "idle_timeout": 3600}

        with patch("contextcrumb.cli.service_request", return_value=health):
            with redirect_stdout(output):
                exit_code = main(["service", "status"])

        self.assertEqual(exit_code, 0)
        self.assertIn("Model loaded: True", output.getvalue())

    def test_cli_service_stop_calls_shutdown(self):
        output = io.StringIO()

        with patch("contextcrumb.cli.service_request", return_value={"ok": True}) as service_request:
            with redirect_stdout(output):
                exit_code = main(["service", "stop"])

        self.assertEqual(exit_code, 0)
        service_request.assert_called_once()
        self.assertIn("/shutdown", service_request.call_args.args)

    def test_cli_service_start_spawns_background_process(self):
        output = io.StringIO()
        process = Mock()
        process.pid = 1234

        def fake_service_request(*args, **kwargs):
            raise SystemExit("not running")

        with patch("contextcrumb.cli.service_request", side_effect=fake_service_request):
            with patch("contextcrumb.cli.subprocess.Popen", return_value=process) as popen:
                with patch("contextcrumb.cli.wait_for_service", return_value={"ok": True, "model_loaded": True}):
                    with redirect_stdout(output):
                        exit_code = main(["service", "start", "--lazy-load", "--log-file", str(Path(tempfile.gettempdir()) / "contextcrumb-test-service.log")])

        self.assertEqual(exit_code, 0)
        popen.assert_called_once()
        self.assertIn("Started ContextCrumb service", output.getvalue())

    def test_cli_service_start_forwards_file_read_options(self):
        output = io.StringIO()
        process = Mock()
        process.pid = 1234

        def fake_service_request(*args, **kwargs):
            raise SystemExit("not running")

        with tempfile.TemporaryDirectory() as temp_dir:
            allowed_root = Path(temp_dir) / "docs"
            log_file = Path(temp_dir) / "contextcrumb-test-service.log"

            with patch("contextcrumb.cli.service_request", side_effect=fake_service_request):
                with patch("contextcrumb.cli.subprocess.Popen", return_value=process) as popen:
                    with patch("contextcrumb.cli.wait_for_service", return_value={"ok": True, "model_loaded": True}):
                        with redirect_stdout(output):
                            exit_code = main(
                                [
                                    "service",
                                    "start",
                                    "--allow-root",
                                    str(allowed_root),
                                    "--disable-file-reads",
                                    "--lazy-load",
                                    "--log-file",
                                    str(log_file),
                                ]
                            )

        self.assertEqual(exit_code, 0)
        command = popen.call_args.args[0]
        self.assertIn("--allow-root", command)
        self.assertIn(str(allowed_root), command)
        self.assertIn("--disable-file-reads", command)

    def test_cli_serve_passes_file_read_options(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            allowed_root = Path(temp_dir) / "docs"

            with patch("contextcrumb.service.run_service", return_value=0) as run_service:
                exit_code = main(["serve", "--allow-root", str(allowed_root), "--disable-file-reads"])

        self.assertEqual(exit_code, 0)
        self.assertFalse(run_service.call_args.kwargs["file_reads_enabled"])
        self.assertEqual(run_service.call_args.kwargs["allowed_file_roots"], [allowed_root])

    def test_cli_empty_file_handling(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            empty_file = Path(temp_dir) / "empty.txt"
            empty_file.write_text("", encoding="utf-8")

            # Local load
            with self.assertRaises(SystemExit) as cm:
                main(["load", str(empty_file)])
            self.assertEqual(str(cm.exception), "Input file is empty.")

            # Local inspect
            with self.assertRaises(SystemExit) as cm:
                main(["inspect", str(empty_file)])
            self.assertEqual(str(cm.exception), "Input file is empty.")

            # Local diff
            with self.assertRaises(SystemExit) as cm:
                main(["diff", str(empty_file)])
            self.assertEqual(str(cm.exception), "Input file is empty.")

    def test_cli_service_empty_file_handling(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            empty_file = Path(temp_dir) / "empty.txt"
            empty_file.write_text("", encoding="utf-8")

            # Mock urlopen to raise HTTPError with "Input file is empty."
            fp = io.BytesIO(b'{"detail":"Input file is empty."}')
            err = HTTPError("http://127.0.0.1:8765/compress_file", 400, "Bad Request", {}, fp)

            with patch("contextcrumb.cli.urlopen", side_effect=err):
                with self.assertRaises(SystemExit) as cm:
                    main(["load", str(empty_file), "--use-service"])
                self.assertEqual(str(cm.exception), "Input file is empty.")


if __name__ == "__main__":
    unittest.main()
