import pathlib
import sys
import tempfile
import unittest


sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))

from sync_github import PAGE_FILES, git_blob_sha, prepare_files, render_page


class SyncFilesTest(unittest.TestCase):
    def test_include_code_collects_nested_scripts_and_root_rules(self):
        code_paths = {
            "scripts/collectors/v2ex_comments.py",
            "scripts/evidence/evidence_cache.py",
            "scripts/dashboard/dashboard_config.json",
            "scripts/dashboard/workstation.css",
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


if __name__ == "__main__":
    unittest.main()
