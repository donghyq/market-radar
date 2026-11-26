import json
import pathlib
import sys
import tempfile
import unittest
from datetime import date


sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))

import radar_cli
from collab_utils import dump_db_to_jsonl, sync_db_from_jsonl
from persona_and_freshness import compute_freshness, enrich_all_signals
from signal_time import LEGACY_DATE_SOURCE, source_day, source_time


class SignalTimeTest(unittest.TestCase):
    def test_time_requires_date_or_explicit_offset(self):
        self.assertEqual(source_time("2026-11-24"), ("2026-11-24", "date"))
        self.assertEqual(source_time("2026-11-24T08:00:00Z"), ("2026-11-24T08:00:00+00:00", "timestamp"))
        for value in ("", "2026-02-30", "2026-11-24T08:00:00"):
            with self.subTest(value=value):
                self.assertEqual(source_time(value), ("", "unknown"))

    def test_source_day_is_consistent_across_offsets(self):
        ref = date(2026, 11, 24)
        self.assertEqual(source_day("2026-11-23T17:00:00Z"), "2026-11-24")
        self.assertEqual(source_day("2026-11-24T01:00:00+08:00"), "2026-11-24")
        self.assertEqual(compute_freshness("2026-11-17", ref)[0], "7d_hot")
        self.assertEqual(compute_freshness("2026-11-16", ref)[0], "30d_active")
        self.assertEqual(compute_freshness("2026-11-25", ref)[0], "recent_unverified")

    def test_collecting_old_content_today_does_not_make_it_recent(self):
        conn = radar_cli.get_conn(pathlib.Path(":memory:"))
        radar_cli.init_db(conn)
        defaults = dict.fromkeys(("source_tier", "category", "query_term", "content", "author_or_app",
                                 "metric_primary", "metric_secondary", "rating_or_price", "source_url"), "")
        for title, source in (("已核实旧帖", "2024-01-01"), ("旧版未核实", ""), ("今天有日期", "2026-11-24")):
            radar_cli.insert_signal(conn, "测试", title=title, published_at="2026-11-24",
                                    source_published_at=source, **defaults)
        enrich_all_signals(conn, "2026-11-24")
        self.assertEqual(
            {r["title"]: (r["freshness_tier"], r["published_at"]) for r in conn.execute("SELECT * FROM raw_signals")},
            {"已核实旧帖": ("stale_archive", "2026-11-24"),
             "旧版未核实": ("recent_unverified", "2026-11-24"),
             "今天有日期": ("7d_hot", "2026-11-24")},
        )
        conn.close()

    def test_legacy_migration_and_archive_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            archive = root / "data/signals/signals_master.jsonl"
            archive.parent.mkdir(parents=True)
            old = {
                "id": 42, "channel": "App Store", "title": "旧线索", "content": "原文",
                "published_at": "2024-01-01", "collected_at": "2024-01-15 12:00:00",
                "first_seen": "2024-01-15", "last_seen": "2024-01-16",
                "source_url": "https://example.test/old",
            }
            archive.write_text(json.dumps(old) + "\n", encoding="utf-8")
            conn = radar_cli.get_conn(root / "radar.db")
            radar_cli.init_db(conn)
            conn.execute("ALTER TABLE raw_signals DROP COLUMN source_published_at")
            radar_cli.init_db(conn)
            radar_cli.init_db(conn)
            self.assertEqual(sync_db_from_jsonl(conn, root, radar_cli.insert_signal), 1)
            self.assertEqual(sync_db_from_jsonl(conn, root, radar_cli.insert_signal), 0)
            new = {
                **old, "id": 71, "title": "新资料", "source_published_at": "2026-11-24T16:00:00+08:00",
                "published_time_source": "测试来源", "observed_at": "2026-11-24T08:30:00+00:00",
            }
            with archive.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(new) + "\n")
            self.assertEqual(sync_db_from_jsonl(conn, root, radar_cli.insert_signal), 1)
            dump_db_to_jsonl(conn, root)
            conn.close()
            restored = radar_cli.get_conn(root / "restored.db")
            radar_cli.init_db(restored)
            self.assertEqual(sync_db_from_jsonl(restored, root, radar_cli.insert_signal), 2)
            rows = {r["id"]: dict(r) for r in restored.execute("SELECT * FROM raw_signals")}
            restored.close()
            for field in ("content", "published_at", "collected_at", "first_seen", "last_seen", "source_url"):
                self.assertEqual(rows[42][field], old[field])
            self.assertEqual(rows[42]["observed_at"], "")
            self.assertEqual(rows[42]["source_published_at"], "")
            self.assertEqual(rows[42]["published_time_source"], LEGACY_DATE_SOURCE)
            self.assertEqual(rows[71]["source_published_at"], new["source_published_at"])
            self.assertEqual(rows[71]["published_time_precision"], "timestamp")
            self.assertEqual(rows[71]["observed_at"], new["observed_at"])

    def test_reapplying_archive_does_not_allocate_signal_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            archive = root / "data/signals/signals_master.jsonl"
            archive.parent.mkdir(parents=True)
            existing = {"id": 42, "channel": "测试", "title": "已有信号"}
            archive.write_text(json.dumps(existing) + "\n", encoding="utf-8")
            conn = radar_cli.get_conn(root / "radar.db")
            try:
                radar_cli.init_db(conn)
                self.assertEqual(sync_db_from_jsonl(conn, root, radar_cli.insert_signal), 1)
                for _ in range(3):
                    self.assertEqual(sync_db_from_jsonl(conn, root, radar_cli.insert_signal), 0)
                self.assertEqual(conn.execute("SELECT seq FROM sqlite_sequence WHERE name='raw_signals'").fetchone()[0], 42)

                with archive.open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps({**existing, "title": "真正的新信号"}) + "\n")
                self.assertEqual(sync_db_from_jsonl(conn, root, radar_cli.insert_signal), 1)
                self.assertEqual(sync_db_from_jsonl(conn, root, radar_cli.insert_signal), 0)
                rows = conn.execute("SELECT id, title FROM raw_signals ORDER BY id").fetchall()
                self.assertEqual([tuple(row) for row in rows], [(42, "已有信号"), (43, "真正的新信号")])
                self.assertEqual(conn.execute("SELECT seq FROM sqlite_sequence WHERE name='raw_signals'").fetchone()[0], 43)
            finally:
                conn.close()

    def test_archive_date_for_previously_restored_signal_yields_to_source_time(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            archive = root / "data/signals/signals_master.jsonl"
            archive.parent.mkdir(parents=True)
            legacy = {
                "id": 42, "channel": "测试", "title": "归档信号", "published_at": "2026-11-20",
                "collected_at": "2026-11-20 07:30:00",
            }
            unverified = {
                **legacy, "id": 43, "title": "新采时间未知", "observed_at": "2026-11-24T08:00:00Z",
            }
            conn = radar_cli.get_conn(root / "radar.db")
            try:
                radar_cli.init_db(conn)
                conn.execute(
                    """INSERT INTO raw_signals (id, channel, source_tier, category,
                       query_term, title, content, collected_at, published_at)
                       VALUES (42, '测试', '', '', '', '归档信号', '', ?, ?)""",
                    (legacy["collected_at"], legacy["published_at"]),
                )
                archive.write_text("\n".join(map(json.dumps, (legacy, unverified))) + "\n", encoding="utf-8")
                self.assertEqual(sync_db_from_jsonl(conn, root, radar_cli.insert_signal), 1)
                enrich_all_signals(conn, "2026-11-25")
                self.assertEqual(
                    [tuple(row) for row in conn.execute(
                        "SELECT id, published_time_source, freshness_tier FROM raw_signals ORDER BY id"
                    )],
                    [(42, LEGACY_DATE_SOURCE, "7d_hot"), (43, "", "recent_unverified")],
                )
                verified = {
                    **legacy,
                    "source_published_at": "2026-10-29T12:00:00+00:00",
                    "published_time_source": "源站实测",
                }
                archive.write_text("\n".join(map(json.dumps, (verified, legacy))) + "\n", encoding="utf-8")
                self.assertEqual(sync_db_from_jsonl(conn, root, radar_cli.insert_signal), 0)
                enrich_all_signals(conn, "2026-11-25")
                row = conn.execute("SELECT * FROM raw_signals WHERE id=42").fetchone()
                self.assertEqual(row["published_at"], legacy["published_at"])
                self.assertEqual(row["published_time_source"], "源站实测")
                self.assertEqual(row["freshness_tier"], "30d_active")
            finally:
                conn.close()

    def test_existing_rows_restore_missing_dates_before_rearchiving(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        root = pathlib.Path(folder.name)
        archive = root / "data/signals/signals_master.jsonl"
        archive.parent.mkdir(parents=True)
        archived = {
            "id": 42, "channel": "B站", "title": "旧线索",
            "first_seen": "2026-11-18", "last_seen": "2026-11-24",
            "observed_at": "2026-11-24T08:30:00+00:00",
        }
        archive.write_text(json.dumps(archived) + "\n", encoding="utf-8")
        conn = radar_cli.get_conn(root / "radar.db")
        self.addCleanup(conn.close)
        radar_cli.init_db(conn)
        conn.execute(
            """INSERT INTO raw_signals (id, channel, source_tier, category,
                  query_term, title, content, collected_at) VALUES (?, ?, '', '', '', ?, '', ?)""",
            (42, archived["channel"], archived["title"], "2026-11-18 12:00:00"),
        )
        self.assertEqual(sync_db_from_jsonl(conn, root, radar_cli.insert_signal), 0)
        archive.write_text(json.dumps({**archived, "last_seen": "2026-11-25"}) + "\n", encoding="utf-8")
        self.assertEqual(sync_db_from_jsonl(conn, root, radar_cli.insert_signal), 0)
        dump_db_to_jsonl(conn, root)
        snapshot = json.loads(archive.read_text(encoding="utf-8"))
        restored = conn.execute("SELECT * FROM raw_signals").fetchone()
        for field in ("id", "first_seen", "last_seen", "observed_at"):
            self.assertEqual(snapshot[field], archived[field])
            self.assertEqual(restored[field], archived[field])


if __name__ == "__main__":
    unittest.main()
