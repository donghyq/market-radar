"""Local comment records associated with their original posts."""

import json
from pathlib import Path
from urllib.parse import urlsplit

from collab_utils import atomic_text
from comment_profiles import profile_evidence
from signal_time import observed_now, source_time


COMMENT_ARCHIVE = Path(".market-radar/comments.jsonl")


def init_comments(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS raw_comments (
            channel TEXT NOT NULL,
            comment_id TEXT NOT NULL,
            parent_url TEXT NOT NULL,
            source_url TEXT NOT NULL,
            content TEXT NOT NULL,
            author_or_app TEXT NOT NULL DEFAULT '',
            author_profile_url TEXT NOT NULL DEFAULT '',
            commented_at TEXT NOT NULL DEFAULT '',
            comment_time_precision TEXT NOT NULL DEFAULT 'unknown',
            comment_time_source TEXT NOT NULL DEFAULT '',
            observed_at TEXT NOT NULL DEFAULT '',
            source_metric TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (channel, comment_id)
        )
    """)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(raw_comments)")}
    if "profile_evidence" not in columns:
        conn.execute("ALTER TABLE raw_comments ADD COLUMN profile_evidence TEXT NOT NULL DEFAULT '{}'")
    if "source_metric" not in columns:
        conn.execute("ALTER TABLE raw_comments ADD COLUMN source_metric TEXT NOT NULL DEFAULT ''")


def http_url(value):
    value = (value or "").strip()
    try:
        url = urlsplit(value)
        if url.scheme in ("http", "https") and url.hostname and not url.username:
            return value
    except ValueError:
        pass
    return ""


def save_comment(conn, record):
    channel = (record.get("channel") or "").strip()
    comment_id = (record.get("comment_id") or "").strip()
    content = record.get("content") or ""
    parent_url = http_url(record.get("parent_url"))
    if not channel or not comment_id or not content.strip() or not parent_url:
        raise ValueError("评论需要 channel、comment_id、content 和有效的 parent_url")

    value, precision = source_time(record.get("commented_at", ""))
    time_source = record.get("comment_time_source") or ""
    profile_url = http_url(record.get("author_profile_url"))
    evidence = profile_evidence(record)
    cursor = conn.execute(
        """INSERT OR IGNORE INTO raw_comments (
               channel, comment_id, parent_url, source_url, content, author_or_app,
               author_profile_url, commented_at, comment_time_precision, comment_time_source, observed_at,
               profile_evidence, source_metric
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            channel, comment_id, parent_url, http_url(record.get("source_url")) or parent_url,
            content, record.get("author_or_app") or "", profile_url,
            value, precision, time_source if value else "",
            record.get("observed_at") or observed_now(),
            json.dumps(evidence, ensure_ascii=False),
            record.get("source_metric") or "",
        ),
    )
    if cursor.rowcount:
        return True

    conn.execute(
        """UPDATE raw_comments SET author_profile_url=?
           WHERE channel=? AND comment_id=? AND parent_url=? AND author_profile_url='' AND ? <> ''""",
        (profile_url, channel, comment_id, parent_url, profile_url),
    )
    if evidence:
        row = conn.execute(
            "SELECT profile_evidence FROM raw_comments WHERE channel=? AND comment_id=? AND parent_url=?",
            (channel, comment_id, parent_url),
        ).fetchone()
        if row is not None:
            existing = json.loads(row[0])
            merged = {**evidence, **existing}
            if merged != existing:
                conn.execute(
                    "UPDATE raw_comments SET profile_evidence=? WHERE channel=? AND comment_id=?",
                    (json.dumps(merged, ensure_ascii=False), channel, comment_id),
                )
    return False


def load_comments(conn):
    comments = [dict(row) for row in conn.execute("SELECT * FROM raw_comments ORDER BY channel, comment_id")]
    for comment in comments:
        comment["profile_evidence"] = json.loads(comment["profile_evidence"])
    return comments


def restore_comments(conn, base_dir):
    archive = base_dir / COMMENT_ARCHIVE
    if archive.exists():
        with conn, archive.open(encoding="utf-8") as stream:
            for line in stream:
                if line.strip():
                    save_comment(conn, json.loads(line))


def archive_comments(conn, base_dir):
    comments = load_comments(conn)
    if comments:
        with atomic_text(base_dir / COMMENT_ARCHIVE) as stream:
            for comment in comments:
                stream.write(json.dumps(comment, ensure_ascii=False) + "\n")
