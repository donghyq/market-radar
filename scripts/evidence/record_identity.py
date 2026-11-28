"""Match public records by source identity and consolidate repeated replies."""

import re
import unicodedata
from collections import defaultdict
from difflib import SequenceMatcher
from urllib.parse import parse_qs, urlsplit

from evidence_rules import GITHUB_ISSUE_URL, platform_name, thread_key


def normalized_text(value):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", value or "")).casefold()


def signal_origin(channel, source_url):
    """Return an identity only for a URL that names one record on its platform."""
    try:
        url = urlsplit(source_url or "")
        host = url.hostname or ""
    except ValueError:
        return ""
    if url.scheme not in ("http", "https"):
        return ""
    path = url.path.rstrip("/")
    if channel.startswith("B站") and not channel.startswith("B站评论区痛点"):
        if host in ("bilibili.com", "www.bilibili.com", "m.bilibili.com"):
            if match := re.fullmatch(r"/video/(BV[A-Za-z0-9]+|av[0-9]+)", path):
                return "bilibili:" + match[1]
    if channel.startswith("V2EX") and (host == "v2ex.com" or host.endswith(".v2ex.com")):
        if match := re.fullmatch(r"/t/([0-9]+)", path):
            return "v2ex:" + match[1]
    if channel.startswith("GitHub") and host in ("github.com", "www.github.com"):
        if match := GITHUB_ISSUE_URL.fullmatch(source_url):
            return f"github-issue:{match['repo'].lower()}/{match['number']}"
        if re.fullmatch(r"/[\w-]+/[\w.-]+", path, re.ASCII):
            return "github-repo:" + path[1:].lower()
    if channel.startswith("闲鱼") and host in ("goofish.com", "www.goofish.com") and path == "/item":
        item = parse_qs(url.query).get("id", [""])[0]
        if re.fullmatch(r"[0-9]+", item):
            return "goofish:" + item
    if channel.startswith("小红书") and host in ("xiaohongshu.com", "www.xiaohongshu.com"):
        if match := re.fullmatch(r"/(?:explore|discovery/item)/([0-9a-f]{24})", path, re.I):
            return "xiaohongshu:" + match[1].lower()
    if channel.startswith(("AppStore应用", "App Store 应用")):
        if app := appstore_id(source_url):
            return "appstore:" + app
    if channel.startswith(("HackerNews", "Hacker News")) and host == "news.ycombinator.com" and path == "/item":
        item = parse_qs(url.query).get("id", [""])[0]
        if re.fullmatch(r"[0-9]+", item):
            return "hn:" + item
    if channel in ("小众软件论坛", "Appinn Forum") and host == "meta.appinn.net":
        if match := re.fullmatch(r"/t/(?:[^/]+/)?([0-9]+)", path):
            return "appinn:" + match[1]
    return ""


def appstore_id(source_url):
    try:
        url = urlsplit(source_url or "")
        host = url.hostname
    except ValueError:
        return ""
    match = re.search(r"/id([0-9]+)/?$", url.path)
    return match[1] if host == "apps.apple.com" and match else ""


def init_record_identity(conn):
    cols = {row[1] for row in conn.execute("PRAGMA table_info(raw_signals)")}
    if "origin_key" not in cols:
        conn.execute("ALTER TABLE raw_signals ADD COLUMN origin_key TEXT NOT NULL DEFAULT ''")
        rows = conn.execute("SELECT id, channel, source_url FROM raw_signals").fetchall()
        conn.executemany("UPDATE raw_signals SET origin_key=? WHERE id=?",
                         ((signal_origin(channel, url), row_id) for row_id, channel, url in rows))
    conn.execute("CREATE INDEX IF NOT EXISTS raw_signal_origin ON raw_signals(origin_key) WHERE origin_key<>''")
    conn.execute("CREATE TABLE IF NOT EXISTS retired_signal_ids (id INTEGER PRIMARY KEY)")


def reserve_signal_ids(conn, ids):
    ids = tuple(ids)
    if not ids:
        return
    if any(type(row_id) is not int or row_id <= 0 for row_id in ids):
        raise ValueError("retired signal IDs must be positive integers")
    conn.executemany(
        """INSERT OR IGNORE INTO retired_signal_ids(id) SELECT ?
           WHERE NOT EXISTS (SELECT 1 FROM raw_signals WHERE id=?)""",
        ((row_id, row_id) for row_id in ids),
    )
    high = max(ids)
    conn.execute("UPDATE sqlite_sequence SET seq=MAX(seq, ?) WHERE name='raw_signals'", (high,))
    conn.execute("""INSERT INTO sqlite_sequence(name, seq)
                    SELECT 'raw_signals', ? WHERE NOT EXISTS
                        (SELECT 1 FROM sqlite_sequence WHERE name='raw_signals')""", (high,))


def same_comment(a, b):
    platform = platform_name(a)
    if platform != platform_name(b):
        return False
    if a["comment_id"] == b["comment_id"]:
        return True
    if platform not in ("V2EX", "GitHub Issues", "小众软件论坛", "B站"):
        return False
    if platform == "B站":
        parent_a = signal_origin("B站", a["parent_url"])
        parent_b = signal_origin("B站", b["parent_url"])
        if not parent_a or not parent_b:
            return False
        same_thread = parent_a == parent_b
    else:
        if not a["thread_id"] or not b["thread_id"]:
            return False
        same_thread = thread_key(a) == thread_key(b)
    author_a = a["author_id"] or normalized_text(a["author_or_app"])
    author_b = b["author_id"] or normalized_text(b["author_or_app"])
    same_author = bool(author_a and author_a == author_b)
    text_a, text_b = normalized_text(a["content"]), normalized_text(b["content"])
    if text_a == text_b:
        return same_thread or (same_author and len(text_a) >= 32)
    if not (same_thread and same_author and min(len(text_a), len(text_b)) >= 40):
        return False
    if re.findall(r"\d+", text_a) != re.findall(r"\d+", text_b):
        return False
    return SequenceMatcher(None, text_a, text_b, autojunk=False).ratio() >= 0.94


def matching_comments(conn, record):
    candidates = [dict(row) for row in conn.execute(
        """SELECT * FROM raw_comments
           WHERE comment_id=? OR (channel=? AND
             (parent_url=? OR (thread_id<>'' AND thread_id=?) OR
              (author_or_app<>'' AND author_or_app=?)))""",
        (record["comment_id"], record["channel"], record["parent_url"], record["thread_id"], record["author_or_app"]),
    )]
    if any(row["channel"] == record["channel"] and row["comment_id"] == record["comment_id"] for row in candidates):
        return []
    return [row for row in candidates if same_comment(row, record)]


def duplicate_legacy_review(conn, channel, source_url, content):
    if not channel.startswith("AppStore中国区差评") or not (app := appstore_id(source_url)):
        return False
    text = normalized_text(content)
    return bool(text) and any(
        appstore_id(parent) == app and normalized_text(review) == text
        for parent, review in conn.execute(
            """SELECT parent_url, content FROM raw_comments
               WHERE channel LIKE 'App Store%' OR channel LIKE 'AppStore%'"""
        )
    )


def comment_number(row):
    number = row["comment_id"]
    return (int(number) if number.isascii() and number.isdecimal() else float("inf"), number)


def comment_duplicate_rows(conn):
    comments = sorted(map(dict, conn.execute("SELECT * FROM raw_comments ORDER BY rowid")), key=comment_number)
    threads, authors, identities = defaultdict(list), defaultdict(list), {}
    comment_duplicates = []
    for row in comments:
        platform = platform_name(row)
        thread = thread_key(row)
        author = (platform, row["author_id"] or normalized_text(row["author_or_app"]))
        identity = (platform, row["comment_id"])
        candidates = (*threads[thread], *authors.get(author, ()))
        prior = identities.get(identity) or min(
            (item for item in candidates if same_comment(item, row)), key=comment_number, default=None,
        )
        if prior is None:
            threads[thread].append(row)
            if author[1]:
                authors[author].append(row)
            identities[identity] = row
        else:
            comment_duplicates.append((row, prior))
    return list(identities.values()), comment_duplicates


def duplicate_rows(conn, protected_ids=()):
    """Consolidate duplicate records under the lowest original ID of their type."""
    protected_ids = set(protected_ids)
    comments, comment_duplicates = comment_duplicate_rows(conn)
    review_contents = {(appstore_id(row["parent_url"]), normalized_text(row["content"]))
                       for row in comments if platform_name(row) == "App Store"}
    by_origin = defaultdict(list)
    signal_duplicates = []
    for row in map(dict, conn.execute("SELECT * FROM raw_signals ORDER BY id")):
        if origin := signal_origin(row["channel"], row["source_url"]):
            by_origin[origin].append(row)
        if row["channel"].startswith("AppStore中国区差评") and row["id"] not in protected_ids:
            app = appstore_id(row["source_url"])
            if app and (app, normalized_text(row["content"])) in review_contents:
                signal_duplicates.append((row, None))
    for group in by_origin.values():
        if len(group) < 2:
            continue
        keep = group[0]
        signal_duplicates.extend((row, keep) for row in group if row is not keep)
    return signal_duplicates, comment_duplicates


def reconcile_archived_retirements(conn, records, retired_ids):
    """Apply released numbering to matching legacy rows without claiming unrelated IDs."""
    canonical = {}
    for row in records:
        row_id = row.get("id")
        origin = signal_origin(row.get("channel", ""), row.get("source_url", ""))
        if origin and type(row_id) is int and row_id > 0 and row_id not in retired_ids:
            canonical[origin] = min(canonical.get(origin, row_id), row_id)
    duplicates = []
    for old_id in sorted(set(retired_ids)):
        row = conn.execute("SELECT * FROM raw_signals WHERE id=?", (old_id,)).fetchone()
        if row is None:
            continue
        origin = row["origin_key"]
        if new_id := canonical.get(origin):
            keep = conn.execute("SELECT * FROM raw_signals WHERE id=?", (new_id,)).fetchone()
            if keep is None:
                conn.execute("DELETE FROM retired_signal_ids WHERE id=?", (new_id,))
                conn.execute("UPDATE raw_signals SET id=? WHERE id=?", (new_id, old_id))
                conn.execute("DELETE FROM signal_rule_state WHERE signal_id IN (?,?)", (old_id, new_id))
            elif keep["origin_key"] == origin:
                duplicates.append((row, keep))
        elif duplicate_legacy_review(conn, row["channel"], row["source_url"], row["content"]):
            duplicates.append((row, None))
    apply_duplicate_cleanup(conn, duplicates, ())


def discard_comments(conn, rows):
    conn.executemany("DELETE FROM raw_comments WHERE channel=? AND comment_id=?",
                     ((row["channel"], row["comment_id"]) for row in rows))


def apply_duplicate_cleanup(conn, signal_duplicates, comment_duplicates):
    """Apply a cleanup in the caller's transaction and carry forward recent metrics."""
    newest = {}
    for removed, keep in signal_duplicates:
        if keep is not None:
            key = keep["id"]
            previous = newest.get(key, keep)
            if (removed["last_seen"] or "", removed["observed_at"] or "", removed["id"]) > (
                previous["last_seen"] or "", previous["observed_at"] or "", previous["id"]
            ):
                newest[key] = removed
    conn.executemany("DELETE FROM raw_signals WHERE id=?", ((row["id"],) for row, _ in signal_duplicates))
    reserve_signal_ids(conn, (row["id"] for row, _ in signal_duplicates))
    conn.executemany(
        """UPDATE raw_signals SET metric_primary=?, metric_secondary=?, rating_or_price=?,
             last_seen=MAX(COALESCE(last_seen, ''), ?) WHERE id=?""",
        ((row["metric_primary"], row["metric_secondary"], row["rating_or_price"], row["last_seen"] or "", keep_id)
         for keep_id, row in newest.items()),
    )
    discard_comments(conn, (row for row, _ in comment_duplicates))
