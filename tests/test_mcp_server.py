import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from contextcrumb.compressor import CompressionResult, TokenDecision
from contextcrumb.mcp_server import (
    ContextCrumbMcpRuntime,
    _load_fastmcp,
    benchmark_runtime,
    build_mcp_server,
)
from contextcrumb.mcp_types import McpServerConfig


class FakeCompressor:
    instances = 0

    def __init__(self, **kwargs):
        FakeCompressor.instances += 1
        self.kwargs = kwargs
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
        self.calls.append(("text", text, threshold, target_keep_ratio, golden, golden_min_keep_ratio, return_tokens))
        tokens = [
            TokenDecision("hello", 0, 5, 0.9, True),
            TokenDecision("world", 6, 11, 0.1, False),
        ] if return_tokens else []
        return CompressionResult(
            text=f"compressed: {text}",
            original_text=text,
            stats={
                "mode": "target_keep_ratio" if target_keep_ratio is not None else "threshold",
                "threshold": threshold,
                "target_keep_ratio": target_keep_ratio,
                "requested_golden": golden,
                "requested_golden_min_keep_ratio": golden_min_keep_ratio,
            },
            tokens=tokens,
        )

    def compress_file(self, path, **kwargs):
        text = Path(path).read_text(encoding=kwargs.get("encoding", "utf-8"))
        if not text.strip():
            raise ValueError("Input file is empty.")
        result = self.compress(
            text,
            **{
                key: value
                for key, value in kwargs.items()
                if key not in {"encoding", "content_mode", "config"}
            },
        )
        result.stats["source_path"] = str(path)
        return result


class SlowInitFakeCompressor(FakeCompressor):
    def __init__(self, **kwargs):
        time.sleep(0.01)
        super().__init__(**kwargs)


class FakeFastMCP:
    def __init__(self, name, **kwargs):
        self.name = name
        self.kwargs = kwargs
        self.tools = {}
        self.run_called = False

    def tool(self):
        def decorator(func):
            self.tools[func.__name__] = func
            return func

        return decorator

    def run(self):
        self.run_called = True


class McpRuntimeTests(unittest.TestCase):
    def setUp(self):
        FakeCompressor.instances = 0
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

    def test_compress_text_returns_structured_result(self):
        runtime = ContextCrumbMcpRuntime(McpServerConfig(model_id="fake-model"), compressor_factory=FakeCompressor)

        result = runtime.compress_text("hello world")

        self.assertEqual(result["text"], "compressed: hello world")
        self.assertEqual(result["original_text"], "hello world")
        self.assertEqual(result["stats"]["mode"], "threshold")
        event = json.loads(Path(os.environ["CONTEXTCRUMB_STATS_FILE"]).read_text(encoding="utf-8"))
        self.assertEqual(event["source"], "mcp")
        self.assertEqual(event["command"], "mcp.compress_text")

    def test_compress_file_includes_source_path(self):
        runtime = ContextCrumbMcpRuntime(McpServerConfig(model_id="fake-model"), compressor_factory=FakeCompressor)

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "context.txt"
            path.write_text("file context", encoding="utf-8")

            result = runtime.compress_file(str(path))

        self.assertEqual(result["text"], "compressed: file context")
        self.assertEqual(result["stats"]["source_path"], str(path))
        event = json.loads(Path(os.environ["CONTEXTCRUMB_STATS_FILE"]).read_text(encoding="utf-8"))
        self.assertEqual(event["source_path"], "context.txt")

    def test_empty_inputs_return_clear_errors(self):
        runtime = ContextCrumbMcpRuntime(McpServerConfig(model_id="fake-model"), compressor_factory=FakeCompressor)

        with self.assertRaisesRegex(ValueError, "No input text provided"):
            runtime.compress_text("   ")

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "empty.txt"
            path.write_text("", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "Input file is empty"):
                runtime.compress_file(str(path))

    def test_tool_arguments_pass_through(self):
        runtime = ContextCrumbMcpRuntime(McpServerConfig(model_id="fake-model"), compressor_factory=FakeCompressor)

        result = runtime.compress_text(
            "hello world",
            threshold=0.7,
            target_keep_ratio=0.4,
            golden=False,
            golden_min_keep_ratio=0.2,
            return_tokens=True,
        )

        self.assertEqual(result["stats"]["mode"], "target_keep_ratio")
        self.assertEqual(result["stats"]["threshold"], 0.7)
        self.assertEqual(result["stats"]["target_keep_ratio"], 0.4)
        self.assertEqual(result["stats"]["requested_golden_min_keep_ratio"], 0.2)
        self.assertIn("tokens", result)

    def test_in_process_runtime_reuses_one_compressor(self):
        runtime = ContextCrumbMcpRuntime(McpServerConfig(model_id="fake-model"), compressor_factory=FakeCompressor)

        runtime.compress_text("first")
        runtime.compress_text("second")

        self.assertEqual(FakeCompressor.instances, 1)
        self.assertTrue(runtime.model_loaded)

    def test_service_mode_uses_service_without_loading_compressor(self):
        service_request = Mock(
            return_value={
                "text": "service text",
                "original_text": "hello world",
                "stats": {"mode": "threshold"},
            }
        )
        compressor_factory = Mock(side_effect=AssertionError("compressor should not load"))
        runtime = ContextCrumbMcpRuntime(
            McpServerConfig(use_service=True, service_url="http://127.0.0.1:8765"),
            compressor_factory=compressor_factory,
            service_request_func=service_request,
        )

        result = runtime.compress_text("hello world", target_keep_ratio=0.5)

        self.assertEqual(result["text"], "service text")
        compressor_factory.assert_not_called()
        service_request.assert_called_once()
        self.assertEqual(service_request.call_args.args[1], "/compress")
        self.assertEqual(service_request.call_args.args[2]["target_keep_ratio"], 0.5)
        self.assertFalse(Path(os.environ["CONTEXTCRUMB_STATS_FILE"]).exists())

    def test_service_file_mode_sends_path_payload(self):
        service_request = Mock(
            return_value={
                "text": "service file",
                "original_text": "file text",
                "stats": {"source_path": "context.txt"},
            }
        )
        runtime = ContextCrumbMcpRuntime(
            McpServerConfig(use_service=True),
            compressor_factory=Mock(side_effect=AssertionError("compressor should not load")),
            service_request_func=service_request,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "context.txt"
            path.write_text("file text", encoding="utf-8")

            result = runtime.compress_file(str(path), encoding="utf-8")

        self.assertEqual(result["text"], "service file")
        self.assertEqual(service_request.call_args.args[1], "/compress_file")
        self.assertEqual(service_request.call_args.args[2]["path"], str(path))

    def test_service_errors_become_tool_errors(self):
        runtime = ContextCrumbMcpRuntime(
            McpServerConfig(use_service=True),
            compressor_factory=Mock(side_effect=AssertionError("compressor should not load")),
            service_request_func=Mock(side_effect=SystemExit("service unavailable")),
        )

        with self.assertRaisesRegex(RuntimeError, "service unavailable"):
            runtime.compress_text("hello world")

    def test_adapter_latency_path_is_warm_after_first_call(self):
        runtime = ContextCrumbMcpRuntime(McpServerConfig(model_id="fake-model"), compressor_factory=SlowInitFakeCompressor)

        timings = benchmark_runtime(runtime, "hello world")
        start = time.perf_counter()
        for _ in range(25):
            runtime.compress_text("hello world")
        repeated_seconds = time.perf_counter() - start

        self.assertEqual(SlowInitFakeCompressor.instances, 1)
        self.assertLess(timings["warm_seconds"], timings["cold_seconds"])
        self.assertLess(repeated_seconds, 0.5)


class McpServerBuildTests(unittest.TestCase):
    def test_build_mcp_server_registers_expected_tools_without_loading_model(self):
        runtime = ContextCrumbMcpRuntime(
            McpServerConfig(model_id="fake-model"),
            compressor_factory=Mock(side_effect=AssertionError("should be lazy")),
        )

        with patch("contextcrumb.mcp_server._load_fastmcp", return_value=FakeFastMCP):
            mcp = build_mcp_server(McpServerConfig(model_id="fake-model"), runtime=runtime)

        self.assertEqual(mcp.name, "ContextCrumb")
        self.assertIn("compress_text", mcp.tools)
        self.assertIn("compress_file", mcp.tools)
        self.assertFalse(runtime.model_loaded)

    def test_missing_mcp_dependency_has_install_hint(self):
        real_import = __import__

        def fake_import(name, *args, **kwargs):
            if name.startswith("mcp"):
                raise ImportError("missing mcp")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fake_import):
            with self.assertRaisesRegex(RuntimeError, "contextcrumb\\[mcp\\]"):
                _load_fastmcp()


if __name__ == "__main__":
    unittest.main()
