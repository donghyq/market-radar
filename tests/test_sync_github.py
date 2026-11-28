import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch


sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))

from sync_github import PAGE_FILES, git_blob_sha, prepare_files, render_page


class SyncFilesTest(unittest.TestCase):
    def test_include_code_collects_nested_scripts_and_root_rules(self):
        code_paths = {
            "scripts/collectors/v2ex_comments.py",
            "scripts/evidence/evidence_cache.py",
            "scripts/dashboard/dashboard_config.json",
            "scripts/dashboard/workstation.css",
            "scripts/dashboard/market_heat.js",
            "scripts/market_heat.py",
            "rules/classification/classifier.py",
            "rules/classification/classification_rules.json",
            "config/consumer_queries.json",
            "docs/DEV_PLAN_0.2.3.md",
            ".github/workflows/daily_radar.yml",
            "rules/__init__.py",
            "rules/engine.py",
            "rules/evidence_rules.json",
            "rules/README.md",
        }
        page = render_page({"signals": []})
        remote = {path: git_blob_sha(page.encode("utf-8")) for path in PAGE_FILES}

        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            for name in code_paths | {"rules/__pycache__/engine.pyc"}:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("fixture", encoding="utf-8")
            for name in PAGE_FILES:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(page.encode("utf-8"))

            files = prepare_files(root, remote, include_code=True)

        self.assertEqual({file["path"] for file in files}, code_paths)

    def test_check_only_accepts_windows_line_endings_and_never_posts_large_blobs(self):
        from sync_github import RENDERER_FILES

        page = render_page({"signals": []})
        remote = {path: git_blob_sha(page.encode("utf-8")) for path in PAGE_FILES}
        remote.update({path: git_blob_sha(b"fixture\n") for path in RENDERER_FILES})
        content = b"x" * 400_001
        with tempfile.TemporaryDirectory() as folder, patch("sync_github.api") as api:
            root = pathlib.Path(folder)
            for name in (*RENDERER_FILES, *PAGE_FILES, "exports/signals_full.csv"):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                if name in PAGE_FILES:
                    path.write_bytes(page.encode("utf-8"))
                elif name in RENDERER_FILES:
                    path.write_bytes(b"fixture\r\n")
                else:
                    path.write_bytes(content)
            files = prepare_files(root, remote, check_only=True)
            api.assert_not_called()
        self.assertEqual([(item["path"], item["sha"]) for item in files], [("exports/signals_full.csv", git_blob_sha(content))])


if __name__ == "__main__":
    unittest.main()
