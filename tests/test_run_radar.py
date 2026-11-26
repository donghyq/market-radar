import io
import pathlib
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import call, patch


sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import run_radar


class RadarMenuTest(unittest.TestCase):
    def test_collect_then_open_local_comments(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            page = root / ".market-radar" / "index.html"

            def script(name, args=None):
                if name == "radar_cli.py" and args == ["export", "--with-comments"]:
                    page.parent.mkdir()
                    page.write_text("local workbench", encoding="utf-8")
                return 0

            with (
                patch("run_radar.ROOT", root),
                patch("run_radar.run_script", side_effect=script) as runner,
                patch("run_radar.webbrowser.open") as browser,
                patch("builtins.input", side_effect=["1", "6", "0"]),
                redirect_stdout(io.StringIO()),
            ):
                run_radar.menu()

            self.assertEqual(runner.call_args_list, [
                call("tech_radar.py"),
                call("auto_discover_ideas.py"),
                call("radar_cli.py", ["run-all"]),
                call("radar_cli.py", ["export", "--with-comments"]),
            ])
            browser.assert_called_once_with(page.as_uri())

    def test_failed_export_does_not_open_previous_page(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            page = root / ".market-radar" / "index.html"
            page.parent.mkdir()
            page.write_text("old workbench", encoding="utf-8")
            with (
                patch("run_radar.ROOT", root),
                patch("run_radar.run_script", return_value=1),
                patch("run_radar.webbrowser.open") as browser,
                patch("builtins.input", side_effect=["6", "0"]),
                redirect_stdout(io.StringIO()) as output,
            ):
                run_radar.menu()

            browser.assert_not_called()
            self.assertIn("本地工作台生成失败", output.getvalue())


if __name__ == "__main__":
    unittest.main()
