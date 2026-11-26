#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import datetime
import hashlib
import json
import os
import pathlib
import sqlite3
import tempfile
from contextlib import contextmanager

from signal_time import LEGACY_DATE_SOURCE, market_today, source_time


def now_str() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@contextmanager
def atomic_text(path: pathlib.Path, *, encoding: str = "utf-8"):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding=encoding, newline="\n", dir=path.parent, delete=False
        ) as stream:
            temp = pathlib.Path(stream.name)
            yield stream
        os.replace(temp, path)
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)


def restore_signal(conn, r, insert_fn) -> bool:
    """Restore an archived signal, including IDs referenced by project evidence."""
    fields = (
        "channel", "source_tier", "category", "query_term", "title", "content",
        "author_or_app", "metric_primary", "metric_secondary", "rating_or_price",
        "source_url", "published_at", "collected_at", "source_published_at",
        "published_time_source", "observed_at",
    )
    values = {field: r.get(field, "") for field in fields}
    values["source_tier"] = r.get("source_tier", "历史归档")
    signal_id = r.get("id")
    added = insert_fn(
        conn=conn,
        signal_id=signal_id if type(signal_id) is int and signal_id > 0 else None,
        **values,
    )
    if not values["source_published_at"] and (
        not values["observed_at"] or values["published_time_source"] == LEGACY_DATE_SOURCE
    ):
        legacy_day, precision = source_time(values["published_at"])
        if precision == "date":
            conn.execute(
                """UPDATE raw_signals SET published_time_source=?
                   WHERE channel=? AND title=? AND author_or_app=? AND published_at=?
                     AND COALESCE(source_published_at, '')=''
                     AND COALESCE(published_time_source, '')=''""",
                (LEGACY_DATE_SOURCE, values["channel"], values["title"][:200],
                 values["author_or_app"][:100], legacy_day),
            )
    if added:
        conn.execute(
            """UPDATE raw_signals SET pain_tags=?, is_noise=?, noise_reason=?,
               freshness_tier=?, audience_tag=?, persona_note=?, first_seen=?, last_seen=?
               WHERE id=last_insert_rowid()""",
            (
                r.get("pain_tags", ""), r.get("is_noise", 0), r.get("noise_reason", ""),
                r.get("freshness_tier", "30d_active"), r.get("audience_tag", ""),
                r.get("persona_note", ""),
                r.get("first_seen", ""), r.get("last_seen", ""),
            ),
        )
    elif any(r.get(field) for field in ("first_seen", "last_seen", "observed_at")):
        conn.execute(
            """UPDATE raw_signals
               SET first_seen=COALESCE(NULLIF(first_seen, ''), ?),
                   last_seen=COALESCE(NULLIF(last_seen, ''), ?),
                   observed_at=COALESCE(NULLIF(observed_at, ''), ?)
               WHERE channel=? AND title=? AND author_or_app=?
                 AND (COALESCE(first_seen, '')='' OR COALESCE(last_seen, '')=''
                      OR COALESCE(observed_at, '')='')""",
            (
                r.get("first_seen") or "", r.get("last_seen") or "", r.get("observed_at") or "",
                values["channel"], values["title"][:200], values["author_or_app"][:100],
            ),
        )
    return added


def sync_db_from_jsonl(conn: sqlite3.Connection, base_dir: pathlib.Path, insert_fn) -> int:
    jsonl_path = base_dir / "data" / "signals" / "signals_master.jsonl"
    if not jsonl_path.exists():
        return 0
    loaded = 0
    for line in jsonl_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        if restore_signal(conn, json.loads(line), insert_fn):
            loaded += 1
    conn.commit()
    return loaded


def dump_db_to_jsonl(conn: sqlite3.Connection, base_dir: pathlib.Path) -> int:
    from persona_and_freshness import enrich_all_signals
    today = market_today().isoformat()
    rep = enrich_all_signals(conn, today)
    conn.execute(
        """UPDATE raw_signals
           SET first_seen=COALESCE(NULLIF(first_seen, ''), substr(collected_at, 1, 10)),
               last_seen=COALESCE(NULLIF(last_seen, ''), NULLIF(substr(observed_at, 1, 10), ''),
                                  NULLIF(first_seen, ''), substr(collected_at, 1, 10))
           WHERE COALESCE(first_seen, '')='' OR COALESCE(last_seen, '')=''"""
    )
    conn.commit()
    rows = [dict(r) for r in conn.execute("SELECT * FROM raw_signals ORDER BY id ASC").fetchall()]
    jsonl_path = base_dir / "data" / "signals" / "signals_master.jsonl"
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    with atomic_text(jsonl_path) as f:
        for r in rows:
            key = f"{r['channel']}|{r['title']}|{r['author_or_app']}"
            r["uid"] = hashlib.md5(key.encode("utf-8")).hexdigest()[:10]
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    arch_dir = base_dir / "data" / "archives"
    arch_dir.mkdir(parents=True, exist_ok=True)
    snap = {
        "date": today,
        "updated_at": now_str(),
        "total_signals": len(rows),
        "valid_signals": sum(1 for r in rows if not r["is_noise"]),
        "noise_signals": sum(1 for r in rows if r["is_noise"]),
    }
    (arch_dir / f"{today}.json").write_text(json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8")
    (base_dir / "data" / "persona_stats.json").write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(rows)


def submit_custom_idea(
    base_dir: pathlib.Path,
    title: str,
    proposer: str,
    what_to_do: str,
    buyer_and_price: str,
    evidence_desc: str,
    acquisition_channel: str,
    mvp_days: int = 7,
    has_paid_proof: bool = True,
) -> pathlib.Path:
    s_pay = 36 if has_paid_proof else 24
    s_acq = 22 if any(k in acquisition_channel for k in ["群", "人脉", "老客", "小红书", "闲鱼", "评论"]) else 16
    s_del = 14 if mvp_days <= 7 else (11 if mvp_days <= 14 else 7)
    s_comp = 8
    s_val = 9 if has_paid_proof else 6
    total = s_pay + s_acq + s_del + s_comp + s_val

    risk_notes = []
    if not has_paid_proof:
        risk_notes.append("当前仅有人脉口头意向，尚未收到定金，需警惕『叫好不叫座』伪需求。")
    if mvp_days > 10:
        risk_notes.append(f"预估研发周期({mvp_days}天)偏长，切忌闭门造车，必须先用人工/脚本跑通前3单。")
    if any(k in buyer_and_price for k in ["B端", "机构", "企业"]):
        risk_notes.append("面向B端客户极易陷入定制化与长账期泥潭，务必坚持『先收首款/卖标准化年卡』原则。")
    if not risk_notes:
        risk_notes.append("人脉需求明确且交付周期短，核心风险在于能否从单一熟人客户复制到公域陌生买家。")

    idea_code = "TEAM-" + hashlib.md5(title.encode("utf-8")).hexdigest()[:6].upper()
    idea_obj = {
        "code": idea_code,
        "category_tag": f"🤝 团队人脉提报 · 提报人：{proposer}",
        "title": f"【人脉挖掘】{title}",
        "score": total,
        "score_detail": f"付费意愿 {s_pay}/40 · 获客截流 {s_acq}/25 · 研发交付 {s_del}/15 · 竞争缝隙 {s_comp}/10 · 48h测款 {s_val}/10",
        "plain_what_to_do": what_to_do,
        "workflow_steps": [
            f"【人脉一手输入】{evidence_desc}",
            f"【最小产品处理】控制在 {mvp_days} 天内用现有脚本/模板搭出半自动流水线，优先保核心交付结果",
            f"【商业变现输出】通过 {acquisition_channel} 触达首批客户，按『{buyer_and_price}』收款交付",
        ],
        "who_pays_and_price": buyer_and_price,
        "ai_sharp_review": "【AI 锐评自动诊断】" + " ".join(risk_notes),
        "plan_48h": f"由提报人({proposer})在 48 小时内联系该人脉客户，发去一份手工/半自动制作的样品 Demo，要求对方先预付 99~299 元测试定金；收到真金白银后再启动正式开发。",
        "evidence_ids": [],
        "created_at": now_str(),
    }
    ideas_dir = base_dir / "data" / "ideas"
    ideas_dir.mkdir(parents=True, exist_ok=True)
    out_path = ideas_dir / f"{idea_code}.json"
    out_path.write_text(json.dumps(idea_obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path
