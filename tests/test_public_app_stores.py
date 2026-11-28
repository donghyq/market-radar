import json
import pathlib
import sqlite3
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))

import radar_cli
from collectors.public_app_stores import GOOGLE_PLAY, TAPTAP, collect_google_play, collect_taptap


def schema(item):
    return '<script type="application/ld+json">' + json.dumps(item) + '</script>'


class PublicAppStoresTest(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.addCleanup(self.conn.close)
        radar_cli.init_db(self.conn)

    def test_google_play_uses_public_review_ids_and_keeps_date_precision(self):
        package = "app.home.plants"
        url = GOOGLE_PLAY + "?id=" + package
        listing = schema({"@type": "SoftwareApplication", "name": "浇水提醒", "url": url})
        chinese = '<header data-review-id="review-1"><span class="bp9Aid">2026年10月3日</span></header><div class="h3YV2d">提醒有用。</div>'
        english = ('<header data-review-id="review-2"><span class="bp9Aid">October 4, 2026</span>'
                   '<div aria-label="Rated 4 stars out of five stars"></div></header><div class="h3YV2d">Easy to use.</div>')
        pages = {url + "&hl=zh_CN&gl=US": listing + chinese, url + "&hl=en_US&gl=US": chinese + english}
        self.assertEqual(list(collect_google_play(self.conn, [("植物养护", package)], fetch=pages.__getitem__)), [(1, 2)])
        self.assertEqual(list(collect_google_play(self.conn, [("植物养护", package)], fetch=pages.__getitem__)), [(0, 0)])
        stored = self.conn.execute("SELECT comment_id, parent_url, commented_at, comment_time_precision, source_metric FROM raw_comments ORDER BY comment_id")
        self.assertEqual([tuple(row) for row in stored], [
            ("review-1", url, "2026-10-03", "date", ""),
            ("review-2", url, "2026-10-04", "date", "4 星"),
        ])

    def test_taptap_preserves_review_link_and_separates_release_from_feedback(self):
        url = TAPTAP + "/app/123"
        page = schema({"@type": "VideoGame", "@id": url, "name": "水彩拼图",
                       "datePublished": "2026-08-09T12:00:00+08:00"})
        page += ('<div class="tap-router review-item review-item--in-app-tab">'
                 '<a href="/review/765"><div>拼图可以自定义难度。</div></a>'
                 '<span class="tap-time review-item__updated-time" title="2026/11/1 08:15:25">昨天</span></div>'
                 '<div class="tap-router review-item review-item--in-app-tab"><a href="/review/766">关卡挺有趣。</a>'
                 '<span class="review-item__modified-tip">修改于 2026/11/3</span></div>')
        self.assertEqual(list(collect_taptap(self.conn, [("轻量游戏", "123")], fetch=lambda _: page)), [(1, 2)])
        self.assertEqual(tuple(self.conn.execute("SELECT origin_key,published_time_source FROM raw_signals").fetchone()),
                         ("taptap:123", "taptap_store_release"))
        saved = self.conn.execute("SELECT parent_url,source_url,commented_at FROM raw_comments ORDER BY comment_id")
        self.assertEqual([tuple(row) for row in saved], [
            (url, TAPTAP + "/review/765", "2026-11-01"), (url, TAPTAP + "/review/766", "2026-11-03"),
        ])
