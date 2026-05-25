import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from contextcrumb.compressor import CompressionResult
from contextcrumb.mcp_shrink import (
    CatalogShrinkStats,
    ContextCrumbShrinkRuntime,
    decode_message,
    encode_content_length_message,
    main,
    transform_message,
)


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
        target_keep_ratio=0.5,
        golden=True,
        golden_min_keep_ratio=1 / 3,
        return_tokens=False,
    ):
        self.calls.append((text, threshold, target_keep_ratio, golden, golden_min_keep_ratio, return_tokens))
        shortened = text.replace("verbose ", "").replace("carefully ", "").strip()
        return CompressionResult(
            text=shortened,
            original_text=text,
            stats={
                "input_tokens": len(text.split()),
                "kept_tokens": len(shortened.split()),
                "deleted_tokens": max(len(text.split()) - len(shortened.split()), 0),
                "token_keep_ratio": len(shortened.split()) / len(text.split()) if text.split() else 0.0,
                "mode": "target_keep_ratio",
                "model_id": "fake-model",
                "backend": "fake",
            },
        )


class McpShrinkRuntimeTests(unittest.TestCase):
    def setUp(self):
        FakeCompressor.instances = 0

    def test_compresses_catalog_description_with_model(self):
        runtime = ContextCrumbShrinkRuntime(compressor_factory=FakeCompressor)
        stats = CatalogShrinkStats()
        message = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "tools": [
                    {
                        "name": "read_file",
                        "description": "verbose Read a file carefully from disk.",
                    }
                ]
            },
        }

        transformed = transform_message(message, runtime, fields=("description",), stats=stats)

        description = transformed["result"]["tools"][0]["description"]
        self.assertEqual(description, "Read a file from disk.")
        self.assertEqual(transformed["result"]["tools"][0]["name"], "read_file")
        self.assertEqual(stats.fields_compressed, 1)
        self.assertEqual(FakeCompressor.instances, 1)

    def test_preserves_protected_spans_outside_model_input(self):
        runtime = ContextCrumbShrinkRuntime(compressor_factory=FakeCompressor)
        message = {
            "result": {
                "tools": [
                    {
                        "name": "fetch",
                        "description": "verbose Open https://example.com and call fetchData(user_id).",
                    }
                ]
            }
        }

        transformed = transform_message(message, runtime, fields=("description",))

        description = transformed["result"]["tools"][0]["description"]
        self.assertIn("https://example.com", description)
        self.assertIn("fetchData(user_id)", description)

    def test_transforms_all_catalog_shapes(self):
        runtime = ContextCrumbShrinkRuntime(compressor_factory=FakeCompressor)
        message = {
            "result": {
                "tools": [{"description": "verbose tool"}],
                "prompts": [{"description": "verbose prompt"}],
                "resources": [{"description": "verbose resource"}],
                "resourceTemplates": [{"description": "verbose template"}],
            }
        }

        transformed = transform_message(message, runtime, fields=("description",))

        self.assertEqual(transformed["result"]["tools"][0]["description"], "tool")
        self.assertEqual(transformed["result"]["prompts"][0]["description"], "prompt")
        self.assertEqual(transformed["result"]["resources"][0]["description"], "resource")
        self.assertEqual(transformed["result"]["resourceTemplates"][0]["description"], "template")

    def test_leaves_requests_and_tool_results_unchanged(self):
        runtime = ContextCrumbShrinkRuntime(compressor_factory=FakeCompressor)
        request = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"arguments": {"description": "verbose arg"}}}
        tool_result = {"jsonrpc": "2.0", "id": 1, "result": {"content": [{"type": "text", "text": "verbose result"}]}}

        self.assertEqual(transform_message(request, runtime, fields=("description",)), request)
        self.assertEqual(transform_message(tool_result, runtime, fields=("description",)), tool_result)
        self.assertEqual(FakeCompressor.instances, 0)

    def test_service_mode_uses_service_request(self):
        service_request = Mock(
            return_value={
                "text": "service text",
                "original_text": "verbose service text",
                "stats": {"input_tokens": 3, "kept_tokens": 2, "deleted_tokens": 1},
            }
        )
        runtime = ContextCrumbShrinkRuntime(use_service=True, service_request_func=service_request)

        self.assertEqual(runtime.shrink_text("verbose service text"), "service text")
        service_request.assert_called_once()
        self.assertEqual(service_request.call_args.args[1], "/compress")


class McpShrinkFramingTests(unittest.TestCase):
    def test_decodes_and_encodes_content_length_message(self):
        message = {"jsonrpc": "2.0", "id": 1, "result": {"tools": []}}
        payload = encode_content_length_message(message)

        decoded = decode_message(payload)

        self.assertEqual(decoded, message)
        self.assertIn(b"Content-Length:", payload)

    def test_invalid_json_is_passed_through_by_decode_error(self):
        with self.assertRaises(json.JSONDecodeError):
            decode_message(b"{not json}\n")


class McpShrinkCliTests(unittest.TestCase):
    def test_help_does_not_start_proxy(self):
        stdout = io.StringIO()

        with patch("contextcrumb.mcp_shrink.run_proxy") as run_proxy:
            with self.assertRaises(SystemExit) as cm:
                with patch("sys.stdout", stdout):
                    main(["--help"])

        self.assertEqual(cm.exception.code, 0)
        self.assertIn("contextcrumb-shrink", stdout.getvalue())
        run_proxy.assert_not_called()

    def test_main_requires_upstream_command(self):
        stderr = io.StringIO()

        with patch("sys.stderr", stderr):
            exit_code = main([])

        self.assertEqual(exit_code, 2)
        self.assertIn("upstream-command", stderr.getvalue())

    def test_main_passes_configuration_to_proxy(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_dir = Path(temp_dir) / "cache"
            with patch("contextcrumb.mcp_shrink.run_proxy", return_value=0) as run_proxy:
                exit_code = main(
                    [
                        "--fields",
                        "description,title",
                        "--mode",
                        "service",
                        "--service-url",
                        "http://127.0.0.1:9999",
                        "--target-keep-ratio",
                        "0.4",
                        "--cache-dir",
                        str(cache_dir),
                        "fake-server",
                        "--flag",
                    ]
                )

        self.assertEqual(exit_code, 0)
        config = run_proxy.call_args.args[0]
        self.assertEqual(config.fields, ("description", "title"))
        self.assertTrue(config.use_service)
        self.assertEqual(config.service_url, "http://127.0.0.1:9999")
        self.assertEqual(config.target_keep_ratio, 0.4)
        self.assertEqual(config.upstream_command, ("fake-server", "--flag"))


class McpShrinkIntegrationTests(unittest.TestCase):
    def test_proxy_transforms_fake_server_catalog_response(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            server = Path(temp_dir) / "fake_server.py"
            server.write_text(
                "\n".join(
                    [
                        "import json, sys",
                        "for line in sys.stdin:",
                        "    request = json.loads(line)",
                        "    print(json.dumps(request), flush=True)",
                        "    print(json.dumps({'jsonrpc':'2.0','id':2,'result':{'tools':[{'name':'x','description':'verbose catalog'}]}}), flush=True)",
                    ]
                ),
                encoding="utf-8",
            )

            config_env = {
                "CONTEXTCRUMB_STATS": "0",
            }
            with patch.dict(os.environ, config_env):
                from contextcrumb.mcp_shrink import ShrinkProxyConfig, run_proxy

                stdin = io.BytesIO(b'{"jsonrpc":"2.0","id":1,"method":"tools/list"}\n')
                stdout = io.BytesIO()
                exit_code = run_proxy(
                    ShrinkProxyConfig(
                        upstream_command=(os.sys.executable, str(server)),
                        fields=("description",),
                    ),
                    stdin=stdin,
                    stdout=stdout,
                    compressor_factory=FakeCompressor,
                )

        self.assertEqual(exit_code, 0)
        lines = stdout.getvalue().decode("utf-8").splitlines()
        self.assertEqual(json.loads(lines[0])["method"], "tools/list")
        self.assertEqual(json.loads(lines[1])["result"]["tools"][0]["description"], "catalog")


if __name__ == "__main__":
    unittest.main()
