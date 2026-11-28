"""Persist derived evidence assessments in Market Radar's local database."""

import hashlib
import json

from evidence_rules import default_rules


SIGNAL_RULE_FIELDS = ("id", "channel", "title", "content", "metric_primary", "source_url",
                      "published_at", "source_published_at", "published_time_source")


def signal_record(row):
    return {field: row[field] for field in SIGNAL_RULE_FIELDS}


def init_evidence_cache(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS evidence_cache (
        record_type TEXT NOT NULL,
        record_key TEXT NOT NULL,
        fingerprint TEXT NOT NULL,
        assessment TEXT NOT NULL,
        PRIMARY KEY (record_type, record_key)
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS signal_rule_state (
        signal_id INTEGER PRIMARY KEY, fingerprint TEXT NOT NULL
    )""")
    conn.execute("""CREATE TRIGGER IF NOT EXISTS signal_rule_input_changed
        AFTER UPDATE OF channel, title, content, metric_primary, is_noise, noise_reason, pain_tags ON raw_signals
        WHEN OLD.channel IS NOT NEW.channel OR OLD.title IS NOT NEW.title OR OLD.content IS NOT NEW.content
          OR OLD.metric_primary IS NOT NEW.metric_primary OR OLD.is_noise IS NOT NEW.is_noise
          OR OLD.noise_reason IS NOT NEW.noise_reason OR OLD.pain_tags IS NOT NEW.pain_tags
        BEGIN DELETE FROM signal_rule_state WHERE signal_id=OLD.id; END""")
    conn.execute("""CREATE TRIGGER IF NOT EXISTS signal_rule_input_removed AFTER DELETE ON raw_signals
        BEGIN DELETE FROM signal_rule_state WHERE signal_id=OLD.id; END""")


def update_signal_assessments(conn):
    rules = default_rules()
    columns = ", ".join(f"s.{field}" for field in SIGNAL_RULE_FIELDS)
    records = conn.execute(f"""SELECT {columns} FROM raw_signals s
        LEFT JOIN signal_rule_state state ON state.signal_id=s.id
        WHERE state.fingerprint IS NULL OR state.fingerprint<>?""", (rules.fingerprint,)).fetchall()
    updates = []
    for row in records:
        result = rules.evaluate(signal_record(row))
        updates.append((result["is_noise"], result["noise_reason"], ",".join(result["pain_tags"]), row["id"]))
    conn.executemany("UPDATE raw_signals SET is_noise=?, noise_reason=?, pain_tags=? WHERE id=?", updates)
    conn.executemany("REPLACE INTO signal_rule_state VALUES (?, ?)",
                     ((row["id"], rules.fingerprint) for row in records))


def assess_records(conn, records, *, posts=()):
    rules = default_rules()
    existing = {
        key: (fingerprint, assessment)
        for key, fingerprint, assessment in conn.execute(
            "SELECT record_key, fingerprint, assessment FROM evidence_cache WHERE record_type='comment'"
        )
    }
    contexts = rules.contexts([*records, *posts])
    updated = []
    assessments = []
    for record, context in zip(records, contexts):
        key = json.dumps([record["channel"], record["comment_id"]], ensure_ascii=False)
        serialized = json.dumps([rules.fingerprint, record, context], sort_keys=True, ensure_ascii=False)
        fingerprint = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
        saved = existing.get(key)
        if saved and saved[0] == fingerprint:
            result = json.loads(saved[1])
        else:
            result = rules.evaluate(record, context)
            updated.append(("comment", key, fingerprint, json.dumps(result, ensure_ascii=False)))
        assessments.append(result)
    if updated:
        conn.executemany("""INSERT INTO evidence_cache VALUES (?, ?, ?, ?)
            ON CONFLICT(record_type, record_key) DO UPDATE SET
                fingerprint=excluded.fingerprint, assessment=excluded.assessment""", updated)
    return assessments
