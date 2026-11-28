"""Local comment records associated with their original posts."""

import json
from pathlib import Path
from urllib.parse import urlsplit

from collab_utils import atomic_text
from evidence_rules import platform_name
from signal_time import observed_now, source_time

from .comment_profiles import profile_evidence
from .evidence_cache import assess_records
from .record_identity import comment_duplicate_rows, comment_number, discard_comments, matching_comments


COMMENT_ARCHIVE = Path(".market-radar/comments.jsonl")
CONTEXT_FIELDS = ("thread_id", "reply_to_id", "author_id", "app_version", "source_updated_at")


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
    for field in CONTEXT_FIELDS:
        if field not in columns:
            conn.execute(f"ALTER TABLE raw_comments ADD COLUMN {field} TEXT NOT NULL DEFAULT ''")
    conn.execute("CREATE INDEX IF NOT EXISTS raw_comment_thread ON raw_comments(channel, parent_url)")


def http_url(value):
    value = (value or "").strip()
    try:
        url = urlsplit(value)
        if url.scheme in ("http", "https") and url.hostname and not url.username:
            return value
    except ValueError:
        pass
    return ""


def save_comment(conn, record, *, refresh=False):
    channel = (record.get("channel") or "").strip()
    comment_id = (record.get("comment_id") or "").strip()
    content = record.get("content") or ""
    parent_url = http_url(record.get("parent_url"))
    if not channel or not comment_id or not content.strip() or not parent_url:
        raise ValueError("评论需要 channel、comment_id、content 和有效的 parent_url")

    value, precision = source_time(record.get("commented_at", ""))
    time_source = record.get("comment_time_source") or ""
    profile_url = http_url(record.get("author_profile_url"))
    source_url = http_url(record.get("source_url")) or parent_url
    updated_at, _ = source_time(record.get("source_updated_at", ""))
    thread_id, reply_to_id, author_id, app_version = (str(record.get(field) or "").strip()
                                                     for field in CONTEXT_FIELDS[:-1])
    context = (thread_id, reply_to_id, author_id, app_version)
    evidence = profile_evidence(record)
    if not conn.in_transaction:
        conn.execute("BEGIN IMMEDIATE")
    candidate = {
        "channel": channel, "comment_id": comment_id, "parent_url": parent_url, "source_url": source_url,
        "content": content, "thread_id": thread_id, "author_id": author_id,
        "author_or_app": record.get("author_or_app") or "",
    }
    duplicates = matching_comments(conn, candidate)
    if any(comment_number(row) <= comment_number(candidate) for row in duplicates):
        return False
    cursor = conn.execute(
        """INSERT OR IGNORE INTO raw_comments (
               channel, comment_id, parent_url, source_url, content, author_or_app,
               author_profile_url, commented_at, comment_time_precision, comment_time_source, observed_at,
               profile_evidence, source_metric, thread_id, reply_to_id, author_id, app_version, source_updated_at
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            channel, comment_id, parent_url, source_url,
            content, record.get("author_or_app") or "", profile_url,
            value, precision, time_source if value else "",
            record.get("observed_at") or observed_now(),
            json.dumps(evidence, ensure_ascii=False),
            record.get("source_metric") or "",
            *context, updated_at,
        ),
    )
    if cursor.rowcount:
        discard_comments(conn, duplicates)
        return True

    if refresh and updated_at:
        conn.execute("""UPDATE raw_comments SET content=?, reply_to_id=?, source_updated_at=?,
              app_version=COALESCE(NULLIF(?,''),app_version),
              source_metric=COALESCE(NULLIF(?,''),source_metric),
              commented_at=COALESCE(NULLIF(?,''),commented_at),
              comment_time_precision=CASE WHEN ?<>'' THEN ? ELSE comment_time_precision END,
              comment_time_source=COALESCE(NULLIF(?,''),comment_time_source)
            WHERE channel=? AND comment_id=? AND parent_url=? AND
              (source_updated_at='' OR julianday(source_updated_at)<julianday(?))""",
            (content, reply_to_id, updated_at, app_version, record.get("source_metric") or "",
             value, value, precision, time_source if value else "", channel, comment_id, parent_url, updated_at),
        )
    conn.execute(
        """UPDATE raw_comments SET
            author_profile_url=COALESCE(NULLIF(author_profile_url,''),?),
            source_url=CASE WHEN source_url=parent_url THEN ? ELSE source_url END,
            thread_id=COALESCE(NULLIF(thread_id,''),?),
            reply_to_id=COALESCE(NULLIF(reply_to_id,''),?),
            author_id=COALESCE(NULLIF(author_id,''),?),
            app_version=COALESCE(NULLIF(app_version,''),?)
           WHERE channel=? AND comment_id=? AND parent_url=? AND (
              (author_profile_url='' AND ?<>'') OR (source_url=parent_url AND ?<>parent_url)
              OR (thread_id='' AND ?<>'') OR (reply_to_id='' AND ?<>'') OR (author_id='' AND ?<>'')
              OR (app_version='' AND ?<>'')
           )""",
        (profile_url, source_url, *context, channel, comment_id, parent_url, profile_url, source_url, *context),
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


def assess_comments(conn, comments):
    if not comments:
        return []
    platforms = {platform_name(comment) for comment in comments}
    rows = conn.execute("""SELECT id, channel, title, content, source_url, author_or_app
        FROM raw_signals WHERE source_url <> '' ORDER BY id""")
    posts = [post for row in rows if platform_name(post := dict(row)) in platforms]
    return assess_records(conn, comments, posts=posts)


def restore_comments(conn, base_dir):
    archive = base_dir / COMMENT_ARCHIVE
    with conn:
        if not conn.in_transaction:
            conn.execute("BEGIN IMMEDIATE")
        if archive.exists():
            with archive.open(encoding="utf-8") as stream:
                for line in stream:
                    if line.strip():
                        save_comment(conn, json.loads(line))
        _, duplicates = comment_duplicate_rows(conn)
        discard_comments(conn, (row for row, _ in duplicates))


def archive_comments(conn, base_dir):
    comments = load_comments(conn)
    if comments:
        with atomic_text(base_dir / COMMENT_ARCHIVE) as stream:
            for comment in comments:
                stream.write(json.dumps(comment, ensure_ascii=False) + "\n")
