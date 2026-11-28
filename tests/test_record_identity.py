import json
import pathlib
import sys
import tempfile
import unittest


sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))

import radar_cli
from collab_utils import RETIRED_IDS_PATH, sync_db_from_jsonl, write_signal_archive
from evidence.record_identity import apply_duplicate_cleanup, duplicate_rows
from evidence.user_comments import COMMENT_ARCHIVE, load_comments, restore_comments, save_comment


class RecordIdentityTest(unittest.TestCase):
    def setUp(self):
        self.conn = radar_cli.get_conn(pathlib.Path(":memory:"))
        self.addCleanup(self.conn.close)
        radar_cli.init_db(self.conn)

    def add_signal(self, row_id, url, title, channel="GitHub近期高星", body="一种常用工具"):
        return radar_cli.insert_signal(self.conn, channel, "test", "test", "test", title, body,
                                       "test-author", "", "", "", url, signal_id=row_id)

    def test_repeated_source_keeps_its_id_and_id_collision_gets_a_new_id(self):
        self.assertTrue(self.add_signal(100, "https://github.com/Example/Tool", "首次采集"))
        self.assertFalse(self.add_signal(101, "https://github.com/example/tool/?source=rss", "重复采集"))
        self.assertEqual(self.conn.execute("SELECT seq FROM sqlite_sequence WHERE name='raw_signals'").fetchone()[0], 100)
        self.assertTrue(self.add_signal(100, "https://github.com/example/other", "两个不同来源使用同一导入编号"))
        self.assertEqual([row[0] for row in self.conn.execute("SELECT id FROM raw_signals ORDER BY id")], [100, 101])

    def test_retired_high_id_is_not_reused_after_restoring_clean_archive(self):
        self.assertTrue(self.add_signal(1, "https://github.com/example/tool", "编号更小的首条记录"))
        self.assertTrue(self.add_signal(1000, "https://github.com/example/old", "旧版二次采集"))
        self.conn.execute("UPDATE raw_signals SET source_url=? WHERE id=1000", ("https://github.com/example/tool",))
        signals, comments = duplicate_rows(self.conn, protected_ids={1000})
        self.assertEqual([(old["id"], keep["id"]) for old, keep in signals], [(1000, 1)])
        apply_duplicate_cleanup(self.conn, signals, comments)

        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            write_signal_archive(self.conn, root)
            self.assertTrue((root / RETIRED_IDS_PATH).is_file())
            restored = radar_cli.get_conn(pathlib.Path(":memory:"))
            self.addCleanup(restored.close)
            radar_cli.init_db(restored)
            self.assertEqual(sync_db_from_jsonl(restored, root, radar_cli.insert_signal), 1)
            (root / RETIRED_IDS_PATH).write_text("[1, 1000]", encoding="utf-8")
            self.assertEqual(sync_db_from_jsonl(restored, root, radar_cli.insert_signal), 0)
            self.assertEqual([r[0] for r in restored.execute("SELECT id FROM retired_signal_ids")], [1000])
            self.assertTrue(radar_cli.insert_signal(restored, "test", "test", "test", "test", "新来源", "新正文",
                                                    "test", "", "", "", "", signal_id=1000))
            self.assertEqual([r[0] for r in restored.execute("SELECT id FROM raw_signals ORDER BY id")], [1, 1001])

    def test_existing_comment_copies_keep_the_smallest_numeric_source_id(self):
        record = {"channel": "V2EX", "parent_url": "https://www.v2ex.com/t/42", "thread_id": "42",
                  "author_or_app": "alice", "comment_id": "100", "content": "第一次归档的文字"}
        self.assertTrue(save_comment(self.conn, record))
        self.assertTrue(save_comment(self.conn, {**record, "comment_id": "9", "content": "另一段文字"}))
        self.conn.execute("UPDATE raw_comments SET content=? WHERE comment_id='9'", (record["content"],))
        signals, comments = duplicate_rows(self.conn)
        self.assertEqual([(old["comment_id"], keep["comment_id"]) for old, keep in comments], [("100", "9")])
        apply_duplicate_cleanup(self.conn, signals, comments)
        self.assertEqual([row["comment_id"] for row in load_comments(self.conn)], ["9"])

    def test_released_archive_upgrades_ids_for_known_origins_only(self):
        retained_url = "https://github.com/example/tool"
        local_url = "https://github.com/example/local"
        self.assertTrue(self.add_signal(1000, retained_url, "旧库留下的编号"))
        self.assertTrue(self.add_signal(1001, local_url, "其他来源碰巧用了同一编号"))
        self.conn.execute("INSERT INTO retired_signal_ids(id) VALUES (1)")
        published = {"id": 1, "channel": "GitHub近期高星", "source_url": retained_url, "title": "发布版本"}
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            archive = root / "data/signals/signals_master.jsonl"
            archive.parent.mkdir(parents=True)
            archive.write_text(json.dumps(published), encoding="utf-8")
            (root / RETIRED_IDS_PATH).write_text("[1000, 1001]", encoding="utf-8")
            for _ in range(2):
                self.assertEqual(sync_db_from_jsonl(self.conn, root, radar_cli.insert_signal), 0)
        self.assertEqual(list(map(tuple, self.conn.execute("SELECT id, source_url FROM raw_signals ORDER BY id"))),
                         [(1, retained_url), (1001, local_url)])
        self.assertEqual([row[0] for row in self.conn.execute("SELECT id FROM retired_signal_ids")], [1000])

    def test_restore_replaces_larger_comment_and_prunes_existing_copies(self):
        record = {"channel": "V2EX", "parent_url": "https://www.v2ex.com/t/42", "thread_id": "42",
                  "author_or_app": "alice", "comment_id": "100", "content": "评论正文"}
        self.assertTrue(save_comment(self.conn, record))
        self.assertTrue(save_comment(self.conn, {**record, "comment_id": "200", "content": "原库的另一条评论"}))
        self.assertTrue(save_comment(self.conn, {**record, "comment_id": "201", "content": "准备模拟的旧版重复项"}))
        self.conn.execute("UPDATE raw_comments SET content='原库的另一条评论' WHERE comment_id='201'")
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            path = root / COMMENT_ARCHIVE
            path.parent.mkdir()
            path.write_text(json.dumps({**record, "comment_id": "9"}), encoding="utf-8")
            restore_comments(self.conn, root)
            restore_comments(self.conn, root)
        self.assertEqual({row["comment_id"] for row in load_comments(self.conn)}, {"9", "200"})

    def test_release_restores_original_issue_body_with_verified_publish_time(self):
        url = "https://github.com/example/tool/issues/7"
        self.assertTrue(self.add_signal(10, url, "导出问题", "GitHub Issues", "旧版截断的模板段落"))
        record = {"id": 10, "channel": "GitHub Issues", "source_url": url, "title": "导出问题",
                  "author_or_app": "test-author", "content": "执行导出时会丢失最后一页",
                  "source_published_at": "2026-11-20T10:00:00Z", "published_time_source": "github_created_at"}
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            path = root / "data/signals/signals_master.jsonl"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(record), encoding="utf-8")
            self.assertEqual(sync_db_from_jsonl(self.conn, root, radar_cli.insert_signal), 0)
        self.assertEqual(self.conn.execute("SELECT content FROM raw_signals WHERE id=10").fetchone()[0],
                         record["content"])

    def test_same_app_listing_url_can_back_distinct_reviews(self):
        parent = "https://apps.apple.com/cn/app/id123456789"
        channel = "AppStore中国区差评(实时API)"
        self.assertTrue(self.add_signal(1, parent, "评论一", channel, "使用时会卡在分享界面"))
        self.assertTrue(self.add_signal(2, parent, "评论二", channel, "打开时字体有问题"))
        review = {"channel": "App Store", "parent_url": parent, "comment_id": "78",
                  "content": "使用时会卡在分享界面"}
        self.assertTrue(save_comment(self.conn, review))
        self.assertTrue(save_comment(self.conn, {**review, "comment_id": "79"}))
        signals, comments = duplicate_rows(self.conn)
        self.assertEqual([(row["id"], target) for row, target in signals], [(1, None)])
        self.assertEqual(comments, [])
        apply_duplicate_cleanup(self.conn, signals, comments)
        self.assertFalse(self.add_signal(1, parent, "评论一", channel, review["content"]))
        self.assertEqual([row[0] for row in self.conn.execute("SELECT id FROM raw_signals")], [2])

    def test_thread_echo_and_nearly_identical_reply_do_not_get_extra_rows(self):
        record = {"channel": "V2EX", "parent_url": "https://www.v2ex.com/t/42", "thread_id": "42",
                  "author_or_app": "alice", "comment_id": "400",
                  "content": "我用这个工具处理长文档之后总是无法正常保存，多次尝试仍然失败，需要每次手工恢复备份才能找回内容。"}
        self.assertTrue(save_comment(self.conn, record))
        self.assertFalse(save_comment(self.conn, {**record, "comment_id": "401", "author_or_app": "bob",
                                                 "content": record["content"].replace("，", "， ")}))
        self.assertFalse(save_comment(self.conn, {**record, "comment_id": "402", "content": record["content"] + "。"}))
        self.assertTrue(save_comment(self.conn, {**record, "comment_id": "403",
                                                "content": record["content"] + "仅版本 2 受影响。"}))
        self.assertEqual([row["comment_id"] for row in load_comments(self.conn)], ["400", "403"])


if __name__ == "__main__":
    unittest.main()
