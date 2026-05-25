import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import Mock, patch

from contextcrumb.mcp_server import config_from_args, main


class McpCliTests(unittest.TestCase):
    def test_help_does_not_build_server(self):
        output = io.StringIO()

        with patch("contextcrumb.mcp_server.build_mcp_server") as build_mcp_server:
            with self.assertRaises(SystemExit) as cm:
                with redirect_stdout(output):
                    main(["--help"])

        self.assertEqual(cm.exception.code, 0)
        self.assertIn("contextcrumb-mcp", output.getvalue())
        build_mcp_server.assert_not_called()

    def test_main_builds_server_from_cli_args(self):
        server = Mock()

        with patch("contextcrumb.mcp_server.build_mcp_server", return_value=server) as build_mcp_server:
            exit_code = main(
                [
                    "--model",
                    "fake-model",
                    "--backend",
                    "onnx",
                    "--device",
                    "cpu",
                    "--max-length",
                    "512",
                    "--stride",
                    "32",
                    "--window-batch-size",
                    "8",
                    "--revision",
                    "main",
                    "--use-service",
                    "--service-url",
                    "http://127.0.0.1:8765",
                ]
            )

        self.assertEqual(exit_code, 0)
        server.run.assert_called_once()
        config = build_mcp_server.call_args.args[0]
        self.assertEqual(config.model_id, "fake-model")
        self.assertEqual(config.device, "cpu")
        self.assertEqual(config.max_length, 512)
        self.assertEqual(config.stride, 32)
        self.assertEqual(config.window_batch_size, 8)
        self.assertEqual(config.revision, "main")
        self.assertTrue(config.use_service)
        self.assertEqual(config.service_url, "http://127.0.0.1:8765")

    def test_main_reports_missing_optional_dependency(self):
        error = RuntimeError("install with contextcrumb[mcp]")
        output = io.StringIO()

        with patch("contextcrumb.mcp_server.build_mcp_server", side_effect=error):
            with redirect_stderr(output):
                exit_code = main([])

        self.assertEqual(exit_code, 1)
        self.assertIn("contextcrumb[mcp]", output.getvalue())

    def test_config_from_args_preserves_cache_dir(self):
        parser_args = Mock(
            model="fake-model",
            backend="onnx",
            device="cpu",
            revision=None,
            cache_dir="cache",
            max_length=1024,
            stride=64,
            window_batch_size=None,
            use_service=False,
            service_url="http://127.0.0.1:8765",
        )

        config = config_from_args(parser_args)

        self.assertEqual(config.cache_dir, "cache")
        self.assertFalse(config.use_service)


if __name__ == "__main__":
    unittest.main()
