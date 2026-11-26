import csv
import json
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch


sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))

import radar_cli
from comment_profiles import label_comment
from export_dashboard import export_all
from user_comments import COMMENT_ARCHIVE, archive_comments, load_comments, restore_comments, save_comment


class UserCommentTest(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = pathlib.Path(folder.name)
        self.conn = radar_cli.get_conn(self.root / "radar.db")
        self.addCleanup(self.conn.close)
        radar_cli.init_db(self.conn)
        self.sample = {
            "channel": "B站", "comment_id": "13", "parent_url": "https://example.test/old",
            "source_url": "https://example.test/old#comment", "content": "刚试用，声音有点大",
            "commented_at": "2026-11-24T13:00:00+08:00", "comment_time_source": "导表",
            "author_or_app": "作者", "author_profile_url": "https://example.test/profile",
            "observed_at": "2026-11-24T05:30:00Z",
        }

    def test_comment_round_trip_and_duplicate(self):
        self.assertTrue(save_comment(self.conn, self.sample))
        self.assertFalse(save_comment(self.conn, {**self.sample, "content": "重复版本"}))
        self.assertTrue(save_comment(self.conn, {**self.sample, "channel": "小红书"}))
        archive_comments(self.conn, self.root)
        recovered = radar_cli.get_conn(self.root / "restored.db")
        self.addCleanup(recovered.close)
        radar_cli.init_db(recovered)
        restore_comments(recovered, self.root)
        restore_comments(recovered, self.root)
        self.assertEqual(load_comments(recovered), load_comments(self.conn))
        row = load_comments(recovered)[0]
        self.assertEqual(row["commented_at"], self.sample["commented_at"])
        self.assertEqual(row["parent_url"], self.sample["parent_url"])
        self.assertEqual(row["content"], self.sample["content"])

    def test_archive_failure_keeps_previous_complete_file(self):
        save_comment(self.conn, self.sample)
        archive_comments(self.conn, self.root)
        path = self.root / COMMENT_ARCHIVE
        saved = path.read_bytes()
        save_comment(self.conn, {**self.sample, "comment_id": "14"})
        with patch("collab_utils.os.replace", side_effect=OSError("simulated interruption")):
            with self.assertRaises(OSError):
                archive_comments(self.conn, self.root)
        self.assertEqual(path.read_bytes(), saved)
        archive_comments(self.conn, self.root)
        self.assertEqual(len(path.read_text(encoding="utf-8").splitlines()), 2)

    def test_csv_import_keeps_old_format_and_comment_sources(self):
        inbox = self.root / "inbox"
        inbox.mkdir()
        (inbox / "old.csv").write_text("channel,title,content\nold,existing,original\n", encoding="utf-8")
        fields = ["record_type", *self.sample]
        with (inbox / "comments.csv").open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerow({**self.sample, "record_type": "comment"})
            writer.writerow({**self.sample, "record_type": "comment", "channel": "小红书"})
        self.assertEqual(radar_cli.ingest_inbox_csv(self.conn, inbox), 3)
        self.assertEqual(radar_cli.ingest_inbox_csv(self.conn, inbox), 0)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM raw_signals").fetchone()[0], 1)
        rows = load_comments(self.conn)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["author_profile_url"], self.sample["author_profile_url"])
        self.assertEqual(rows[1]["parent_url"], self.sample["parent_url"])

    def test_profile_source_is_optional_and_attached_to_the_correct_comment(self):
        record = {**self.sample, "author_profile_url": "", "age": "27", "ip_location": "IP属地：广东"}
        self.assertTrue(save_comment(self.conn, record))
        self.assertEqual(load_comments(self.conn)[0]["profile_evidence"], {})
        with patch("urllib.request.urlopen", side_effect=AssertionError("unexpected network call")):
            self.assertFalse(save_comment(self.conn, {**record, "profile_source": "测试授权导出"}))
            self.assertTrue(save_comment(self.conn, {**record, "comment_id": "14", "profile_source": "测试导出",
                                                     "ip_location": "192.0.2.4", "age": ""}))
        self.assertFalse(save_comment(self.conn, {**record, "parent_url": "https://example.test/unrelated",
                                                  "occupation": "教师", "profile_source": "另一条资料"}))
        first, second = load_comments(self.conn)
        self.assertEqual(first["profile_evidence"]["age"], {"value": "27", "source": "测试授权导出"})
        self.assertEqual(first["profile_evidence"]["ip_location"]["value"], "广东")
        self.assertNotIn("occupation", first["profile_evidence"])
        self.assertEqual(second["profile_evidence"], {})

    def test_comment_labels_use_independent_evidence(self):
        save_comment(self.conn, {**self.sample, "content": "我今年29岁，我是小学老师。我平时喜欢做手工。功能不错，但续航太短，多少钱？",
                                 "ip_location": "广东", "profile_source": "测试授权导出"})
        labels = label_comment(load_comments(self.conn)[0])
        tags = labels["profile_tags"]
        self.assertEqual(tags["age"]["value"], "25–34岁")
        self.assertEqual(tags["occupation"]["value"], "小学老师")
        self.assertEqual(tags["occupation"]["quote"], "我是小学老师")
        self.assertEqual(tags["ip_location"], {"value": "广东", "source": "测试授权导出"})
        self.assertEqual(tags["interests"]["value"], "做手工")
        self.assertEqual(labels["stance"], "褒贬并存")
        self.assertEqual(labels["intents"], ["询价"])

    def test_comment_labels_leave_unknowns_and_handle_negation(self):
        labels = label_comment({"content": "我不太推荐。朋友是教师，今年他27岁。"})
        self.assertEqual(labels["stance"], "负面")
        self.assertTrue(all(tag["value"] == "未知" for tag in labels["profile_tags"].values()))
        self.assertEqual(label_comment({"content": "功能很稳，好用。"})["stance"], "正面")
        self.assertEqual(label_comment({"content": "哪里买？"})["stance"], "不明确")

    def test_local_export_is_separate_and_keeps_sourced_labels(self):
        save_comment(self.conn, {**self.sample, "content": "我是教师。",
                                 "ip_location": "广东", "profile_source": "测试导出"})
        save_comment(self.conn, {**self.sample, "comment_id": "14", "content": "=1+1",
                                 "author_profile_url": "javascript:alert(1)"})
        public = export_all(self.conn, self.root)
        public_before = public.read_bytes()
        local = export_all(self.conn, self.root, with_comments=True)
        self.assertEqual(public.read_bytes(), public_before)
        self.assertEqual((self.root / "docs/index.html").read_bytes(), public_before)
        public_data = public.read_text(encoding="utf-8").split("const DATA = ", 1)[1].split(";\n</script>", 1)[0]
        self.assertNotIn("comment_coverage", json.loads(public_data))
        self.assertNotIn(self.sample["author_profile_url"], public_data)
        page = local.read_text(encoding="utf-8")
        data = json.loads(page.split("const DATA = ", 1)[1].split(";\n</script>", 1)[0])
        self.assertEqual(data["comment_coverage"], {
            "total": 2, "counts": {"age": 0, "ip_location": 1, "occupation": 1, "interests": 0},
        })
        self.assertEqual(data["signals"][0]["source_published_at"], self.sample["commented_at"])
        self.assertEqual(data["signals"][0]["parent_url"], self.sample["parent_url"])
        self.assertEqual(data["signals"][0]["author_profile_url"], self.sample["author_profile_url"])
        self.assertEqual(data["signals"][1]["author_profile_url"], "")
        with (local.parent / "exports/signals_full.csv").open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual(rows[0]["occupation"], "教师")
        self.assertEqual(rows[0]["occupation_source"], "评论自述")
        self.assertEqual(rows[0]["age_band"], "未知")
        self.assertEqual(rows[1]["content"], "'=1+1")


if __name__ == "__main__":
    unittest.main()
