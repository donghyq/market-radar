import io
import json
import pathlib
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch


sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))

import radar_cli
import scale_collector
from export_dashboard import export_all
from user_comments import archive_comments, load_comments, restore_comments


class CollectedCommentsTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = pathlib.Path(directory.name)
        self.conn = radar_cli.get_conn(self.root / "radar.db")
        self.addCleanup(self.conn.close)
        radar_cli.init_db(self.conn)
        self.published = (datetime.now(timezone.utc) - timedelta(hours=2)).replace(microsecond=0)

    def appstore_responses(self):
        app = {
            "trackId": 123, "trackName": "样本应用", "userRatingCount": 200,
            "averageUserRating": 3.5, "description": "用于验证评论与应用的样本。",
            "releaseDate": "2024-01-01T00:00:00Z",
        }
        review = {
            "id": {"label": "apple-review-1"}, "title": {"label": "扣费问题"},
            "content": {"label": "样本评价原文，购买会员后依然无法使用导出功能。"},
            "im:rating": {"label": "2"}, "updated": {"label": self.published.isoformat()},
            "author": {"name": {"label": "公开昵称"}},
        }

        def responses(request, **_kwargs):
            if "customerreviews" in request.full_url:
                data = {"feed": {"entry": [review, {**review, "id": {"label": "apple-review-2"}}]}}
            else:
                data = {"results": [app]}
            return io.BytesIO(json.dumps(data).encode())

        return app, responses

    def test_daily_appstore_separates_app_reviews_and_public_output(self):
        app, responses = self.appstore_responses()
        with patch("radar_cli.urllib.request.urlopen", side_effect=responses):
            self.assertEqual(radar_cli.collect_appstore(self.conn, [("测试", "测试")]), 1)
            app["trackName"] = "样本应用改名"
            self.assertEqual(radar_cli.collect_appstore(self.conn, [("测试", "测试")]), 0)
        signals = self.conn.execute("SELECT * FROM raw_signals").fetchall()
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0]["title"], "样本应用")
        self.assertEqual(signals[0]["source_published_at"], "2024-01-01T00:00:00+00:00")
        comments = load_comments(self.conn)
        self.assertEqual([row["comment_id"] for row in comments], ["apple-review-1", "apple-review-2"])
        for comment in comments:
            self.assertEqual(comment["parent_url"], signals[0]["source_url"])
            self.assertEqual(comment["commented_at"], self.published.isoformat())
            self.assertEqual(comment["source_metric"], "2 星")

        archive_comments(self.conn, self.root)
        restored = radar_cli.get_conn(self.root / "restored.db")
        self.addCleanup(restored.close)
        radar_cli.init_db(restored)
        restore_comments(restored, self.root)
        self.assertEqual(load_comments(restored), comments)
        public = export_all(self.conn, self.root)
        local = export_all(self.conn, self.root, with_comments=True)
        self.assertNotIn("样本评价原文", public.read_text(encoding="utf-8"))
        self.assertIn("样本评价原文", local.read_text(encoding="utf-8"))

    def test_scale_appstore_uses_same_review_ids_as_daily_collection(self):
        _, responses = self.appstore_responses()
        with patch("scale_collector.urllib.request.urlopen", side_effect=responses):
            apps = scale_collector.fetch_appstore_category(("测试", "测试"))
        for app, category, term, reviews in apps:
            radar_cli.save_appstore_feedback(self.conn, app, category, term, reviews)
        self.assertEqual(len(apps), 1)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM raw_signals").fetchone()[0], 1)
        self.assertEqual([row["comment_id"] for row in load_comments(self.conn)], ["apple-review-1", "apple-review-2"])

    def test_bilibili_separates_video_and_reply_with_independent_time(self):
        gone = self.published - timedelta(days=2)
        video = {"title": "测试视频", "description": "样本视频简介", "bvid": "BV1Demo",
                 "aid": 44, "pubdate": int(gone.timestamp())}
        reply = {"rpid_str": "123456", "rpid": 123456, "content": {"message": "评论原文\n仍有段落"},
                 "member": {"uname": "公开昵称"}, "ctime": int(self.published.timestamp()), "like": 9}

        def responses(url, **_kwargs):
            if "/reply?" in url:
                data = {"data": {"replies": [reply]}}
            else:
                data = {"data": {"result": [video]}}
            return io.BytesIO(json.dumps(data).encode())

        with patch("radar_cli.urllib.request.build_opener") as builder:
            builder.return_value.open.side_effect = responses
            self.assertEqual(radar_cli.collect_bilibili(self.conn, [("测试", "测试")]), 1)
            self.assertEqual(radar_cli.collect_bilibili(self.conn, [("测试", "测试")]), 0)
        signal = self.conn.execute("SELECT * FROM raw_signals").fetchone()
        self.assertNotIn("评论原文", signal["content"])
        self.assertEqual(signal["source_published_at"], gone.isoformat())
        comment, = load_comments(self.conn)
        self.assertEqual(comment["comment_id"], "123456")
        self.assertEqual(comment["content"], reply["content"]["message"])
        self.assertEqual(comment["commented_at"], self.published.isoformat())
        self.assertEqual(comment["parent_url"], signal["source_url"])
        self.assertEqual(comment["source_metric"], "9 赞")


if __name__ == "__main__":
    unittest.main()
