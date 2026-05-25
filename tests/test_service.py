import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from contextcrumb.compressor import CompressionResult
from contextcrumb.service import ContextCrumbService, create_app


class FakeCompressor:
    instances = 0

    def __init__(self, **kwargs):
        FakeCompressor.instances += 1
        self.kwargs = kwargs

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
        return CompressionResult(
            text=f"compressed: {text}",
            original_text=text,
            stats={
                "mode": "target_keep_ratio" if target_keep_ratio is not None else "golden" if golden else "threshold",
                "threshold": threshold,
                "target_keep_ratio": target_keep_ratio,
                "golden_min_keep_ratio": golden_min_keep_ratio,
            },
        )

    def compress_file(self, path, **kwargs):
        text = Path(path).read_text(encoding=kwargs.get("encoding", "utf-8"))
        if not text.strip():
            raise ValueError("Input file is empty.")
        result = self.compress(text, **{key: value for key, value in kwargs.items() if key != "encoding"})
        result.stats["source_path"] = str(path)
        return result


class ServiceTests(unittest.TestCase):
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

    def make_client(self, **service_kwargs):
        service = ContextCrumbService(
            model_id="fake-model",
            idle_timeout=None,
            compressor_factory=FakeCompressor,
            **service_kwargs,
        )
        return TestClient(create_app(service)), service

    def test_health_reports_unloaded_model_before_first_request(self):
        client, _ = self.make_client()

        response = client.get("/health")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["model_loaded"])
        self.assertTrue(payload["file_reads_enabled"])
        self.assertGreaterEqual(len(payload["allowed_file_roots"]), 1)

    def test_compress_reuses_warm_compressor(self):
        client, service = self.make_client()

        first = client.post("/compress", json={"text": "first text"}).json()
        second = client.post("/compress", json={"text": "second text", "target_keep_ratio": 0.4}).json()

        self.assertEqual(first["text"], "compressed: first text")
        self.assertEqual(first["stats"]["mode"], "golden")
        self.assertEqual(second["stats"]["mode"], "target_keep_ratio")
        self.assertEqual(FakeCompressor.instances, 1)
        self.assertTrue(service.status()["model_loaded"])
        events = [
            json.loads(line)
            for line in Path(os.environ["CONTEXTCRUMB_STATS_FILE"]).read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual([event["source"] for event in events], ["service", "service"])

    def test_compress_rejects_empty_text(self):
        client, _ = self.make_client()

        response = client.post("/compress", json={"text": "   "})

        self.assertEqual(response.status_code, 400)

    def test_compress_can_disable_stats_logging(self):
        client, _ = self.make_client()

        response = client.post("/compress", json={"text": "first text", "no_stats": True})

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Path(os.environ["CONTEXTCRUMB_STATS_FILE"]).exists())

    def test_compress_file_includes_source_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, _ = self.make_client(allowed_file_roots=[temp_dir])
            path = Path(temp_dir) / "input.txt"
            path.write_text("file text", encoding="utf-8")

            response = client.post("/compress_file", json={"path": str(path)})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["text"], "compressed: file text")
        self.assertEqual(payload["stats"]["source_path"], str(path))
        event = json.loads(Path(os.environ["CONTEXTCRUMB_STATS_FILE"]).read_text(encoding="utf-8"))
        self.assertEqual(event["command"], "compress_file")
        self.assertEqual(event["source_path"], "input.txt")

    def test_compress_file_rejects_empty_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, _ = self.make_client(allowed_file_roots=[temp_dir])
            path = Path(temp_dir) / "empty.txt"
            path.write_text("   ", encoding="utf-8")

            response = client.post("/compress_file", json={"path": str(path)})

        self.assertEqual(response.status_code, 400)
        self.assertIn("Input file is empty.", response.json()["detail"])

    def test_compress_file_rejects_path_outside_allowed_roots_without_loading_model(self):
        with tempfile.TemporaryDirectory() as allowed_dir:
            with tempfile.TemporaryDirectory() as blocked_dir:
                client, service = self.make_client(allowed_file_roots=[allowed_dir])
                path = Path(blocked_dir) / "blocked.txt"
                path.write_text("blocked text", encoding="utf-8")

                response = client.post("/compress_file", json={"path": str(path)})

        self.assertEqual(response.status_code, 403)
        self.assertIn("outside allowed roots", response.json()["detail"])
        self.assertFalse(service.status()["model_loaded"])
        self.assertEqual(FakeCompressor.instances, 0)

    def test_compress_file_can_be_disabled_without_loading_model(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client, service = self.make_client(file_reads_enabled=False, allowed_file_roots=[temp_dir])
            path = Path(temp_dir) / "input.txt"
            path.write_text("file text", encoding="utf-8")

            response = client.post("/compress_file", json={"path": str(path)})

        self.assertEqual(response.status_code, 403)
        self.assertIn("disabled", response.json()["detail"])
        self.assertFalse(service.status()["model_loaded"])
        self.assertEqual(FakeCompressor.instances, 0)

    def test_idle_shutdown_marks_attached_server_for_exit(self):
        class FakeServer:
            should_exit = False

        service = ContextCrumbService(idle_timeout=0.01, compressor_factory=FakeCompressor)
        server = FakeServer()
        service.attach_server(server)

        time.sleep(0.05)

        self.assertTrue(server.should_exit)


if __name__ == "__main__":
    unittest.main()
