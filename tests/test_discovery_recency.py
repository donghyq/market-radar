import io
import json
import pathlib
import sys
import tempfile
import time
import unittest
from unittest.mock import patch


sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))

import discovery_scanner
import radar_cli


class DiscoveryRecencyTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.conn = radar_cli.get_conn(pathlib.Path(directory.name) / "radar.db")
        self.addCleanup(self.conn.close)
        radar_cli.init_db(self.conn)
        self.now = int(time.time())

    def assert_selected(self, expected):
        titles = self.conn.execute("SELECT title FROM raw_signals ORDER BY id").fetchall()
        self.assertEqual([row["title"] for row in titles], expected)

    def test_bilibili_sorts_before_taking_four(self):
        dates = [self.now - 800, None, self.now - 600, self.now + 600, self.now - 20, self.now - 400]
        items = [{"title": str(i), "bvid": f"BV{i}", "pubdate": date} for i, date in enumerate(dates)]
        response = json.dumps({"data": {"result": items}}).encode()
        with patch("radar_cli.urllib.request.build_opener") as build_opener:
            build_opener.return_value.open.side_effect = [io.BytesIO(), io.BytesIO(response)]
            radar_cli.collect_bilibili(self.conn, custom_queries=[("test", "test")])
        self.assert_selected(["4", "5", "2", "0"])

    def test_wechat_sorts_before_taking_three(self):
        timestamps = [self.now - 800, None, self.now - 600, self.now - 20]
        blocks = []
        for index, timestamp in enumerate(timestamps):
            date = f"timeConvert('{timestamp}')" if timestamp else ""
            blocks.append(f'<div class="txt-box"><h3><a href="/{index}">{index}</a></h3>{date}</div></div>')
        with patch("radar_cli.urllib.request.urlopen", return_value=io.BytesIO("".join(blocks).encode())):
            radar_cli.collect_wechat_sogou(self.conn, custom_queries=[("test", "test")])
        self.assert_selected(["3", "2", "0"])

    def test_v2ex_sorts_before_taking_six_and_keeps_unknown_source_order(self):
        dates = [self.now - 800, None, "invalid", self.now - 600, self.now - 400, None, self.now - 20]
        items = [
            {"title": f"社区反馈样本{i}", "url": f"https://example.test/{i}", "created": date, "replies": 5}
            for i, date in enumerate(dates)
        ]
        response = json.dumps(items).encode()
        with patch("discovery_scanner.urllib.request.urlopen", side_effect=lambda *args, **kw: io.BytesIO(response)):
            discovery_scanner.scan_v2ex_pain_points(self.conn)
        self.assert_selected([f"社区反馈样本{i}" for i in (6, 4, 3, 0, 1, 2)])


if __name__ == "__main__":
    unittest.main()
