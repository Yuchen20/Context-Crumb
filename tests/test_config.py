import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from contextcrumb.cli import main
from contextcrumb.config import resolve_config


class ConfigTests(unittest.TestCase):
    def test_config_set_show_unset_uses_env_config_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            with patch.dict(os.environ, {"CONTEXTCRUMB_CONFIG": str(config_path)}):
                with redirect_stdout(io.StringIO()):
                    self.assertEqual(main(["config", "set", "compression.content_mode", "code-comments"]), 0)

                output = io.StringIO()
                with redirect_stdout(output):
                    self.assertEqual(main(["config", "show", "--user"]), 0)
                self.assertIn('content_mode = "code-comments"', output.getvalue())

                with redirect_stdout(io.StringIO()):
                    self.assertEqual(main(["config", "unset", "compression.content_mode"]), 0)

                output = io.StringIO()
                with redirect_stdout(output):
                    self.assertEqual(main(["config", "show", "--user"]), 0)
                self.assertIn('content_mode = "auto"', output.getvalue())

    def test_project_config_overrides_user_config(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            user_config = root / "user.toml"
            project = root / "project"
            project.mkdir()
            user_config.write_text('[compression]\ncontent_mode = "raw"\n', encoding="utf-8")
            (project / "contextcrumb.toml").write_text(
                '[compression]\ncontent_mode = "code-comments"\n',
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"CONTEXTCRUMB_CONFIG": str(user_config)}):
                config = resolve_config(start=project)
            self.assertEqual(config.compression.content_mode, "code-comments")


if __name__ == "__main__":
    unittest.main()
