#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import csv
import datetime
import json
import pathlib
import shutil

from collab_utils import atomic_text, sync_db_from_jsonl
from comment_profiles import PROFILE_FIELDS, label_comment
from user_comments import COMMENT_ARCHIVE, load_comments, restore_comments

BASE_DIR = pathlib.Path(__file__).resolve().parent.parent
CFG_PATH = pathlib.Path(__file__).resolve().parent / "dashboard_config.json"
WP_PATH = pathlib.Path(__file__).resolve().parent / "whitepaper_config.json"
TPL_PATH = pathlib.Path(__file__).resolve().parent / "template.html"


def render_page(bundle):
    page = TPL_PATH.read_text(encoding="utf-8")
    for name in ("dashboard_app.js", "research_workstation.js"):
        code = TPL_PATH.with_name(name).read_text(encoding="utf-8")
        page = page.replace(f'<script src="scripts/{name}"></script>', f"<script>\n{code}\n</script>")
    css = TPL_PATH.with_name("workstation.css").read_text(encoding="utf-8")
    page = page.replace('<link rel="stylesheet" href="scripts/workstation.css">', f"<style>\n{css}\n</style>")
    data = json.dumps(bundle, ensure_ascii=False).replace("<", r"\u003c")
    return page.replace("__RADAR_DATA_JSON__", data)


def comment_signals(conn):
    """Project comments onto the existing signal view without changing any stored signal ID."""
    rows = []
    for index, comment in enumerate(load_comments(conn), 1):
        labels = label_comment(comment)
        rows.append({
            "id": -index,
            "record_type": "comment",
            "title": "用户评论",
            "category": "用户评论",
            "channel": comment["channel"],
            "comment_id": comment["comment_id"],
            "parent_url": comment["parent_url"],
            "source_url": comment["source_url"],
            "content": comment["content"],
            "author_or_app": comment["author_or_app"],
            "author_profile_url": comment["author_profile_url"],
            "metric_primary": comment["source_metric"],
            "source_published_at": comment["commented_at"],
            "published_time_precision": comment["comment_time_precision"],
            "published_time_source": comment["comment_time_source"],
            "observed_at": comment["observed_at"],
            "is_noise": 0,
            **labels,
        })
    return rows


def write_local_csv(path, signals):
    base_fields = (
        "id", "published_at", "freshness_tier", "audience_tag", "channel", "source_tier",
        "category", "query_term", "author_or_app", "title", "content", "metric_primary",
        "metric_secondary", "rating_or_price", "pain_tags", "is_noise", "collected_at", "source_url",
        "record_type", "comment_id", "parent_url", "source_published_at", "published_time_precision",
        "published_time_source", "observed_at", "stance", "intents",
    )
    tag_columns = {field: "age_band" if field == "age" else field for field in PROFILE_FIELDS}
    fields = [*base_fields, *(column for name in tag_columns.values() for column in (name, name + "_source"))]
    with atomic_text(path, encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for signal in signals:
            row = {field: signal.get(field, "") for field in base_fields}
            row["record_type"] = row["record_type"] or "signal"
            row["intents"] = "、".join(signal.get("intents", ()))
            for field, field_name in tag_columns.items():
                tag = signal.get("profile_tags", {}).get(field, {})
                row[field_name] = tag.get("value", "")
                row[field_name + "_source"] = tag.get("source", "")
            writer.writerow({
                key: "'" + val if isinstance(val, str) and val.lstrip().startswith(("=", "+", "-", "@")) else val
                for key, val in row.items()
            })


def export_all(conn=None, base_dir=BASE_DIR, *, with_comments=False):
    if conn is None:
        import radar_cli

        conn = radar_cli.get_conn(base_dir / "radar.db")
        try:
            radar_cli.init_db(conn)
            sync_db_from_jsonl(conn, base_dir, radar_cli.insert_signal)
            if with_comments:
                restore_comments(conn, base_dir)
            return export_all(conn, base_dir, with_comments=with_comments)
        finally:
            conn.close()

    signals = [dict(r) for r in conn.execute("SELECT * FROM raw_signals ORDER BY is_noise ASC, id ASC").fetchall()]
    cfg = json.loads(CFG_PATH.read_text(encoding="utf-8"))
    wp = json.loads(WP_PATH.read_text(encoding="utf-8")) if WP_PATH.exists() else {}

    # 读取团队人脉提报的独立 JSON 文件 (data/ideas/*.json) 并与基准项目合并按分数排序
    projects = list(cfg.get("projects", []))
    ideas_dir = base_dir / "data" / "ideas"
    if ideas_dir.exists():
        for jf in sorted(ideas_dir.glob("*.json")):
            try:
                obj = json.loads(jf.read_text(encoding="utf-8"))
                if obj.get("code") and obj.get("title"):
                    projects.append(obj)
            except Exception:
                pass
    projects.sort(key=lambda x: x.get("score", 0), reverse=True)

    # 读取历史归档列表 (data/archives/*.json)
    archives = []
    arch_dir = base_dir / "data" / "archives"
    if arch_dir.exists():
        for af in sorted(arch_dir.glob("*.json"), reverse=True):
            try:
                archives.append(json.loads(af.read_text(encoding="utf-8")))
            except Exception:
                pass

    ps_path = base_dir / "data" / "persona_stats.json"
    persona_stats = json.loads(ps_path.read_text(encoding="utf-8")) if ps_path.exists() else {}
    tr_path = base_dir / "data" / "tech_radar.json"
    tech_radar = json.loads(tr_path.read_text(encoding="utf-8")) if tr_path.exists() else {"items": []}
    bundle = {
        "persona_stats": persona_stats,
        "tech_radar": tech_radar.get("items", []),
        "updated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "projects": projects,
        "existing_ideas": cfg.get("existing_ideas", []),
        "signals": signals,
        "whitepaper": wp,
        "archives": archives,
    }

    if with_comments:
        comments = comment_signals(conn)
        bundle["comment_coverage"] = {
            "total": len(comments),
            "counts": {
                name: sum(bool(row["profile_tags"][name]["source"]) for row in comments)
                for name in PROFILE_FIELDS
            },
        }
        signals.extend(comments)
        local_dir = base_dir / COMMENT_ARCHIVE.parent
        write_local_csv(local_dir / "exports/signals_full.csv", signals)
        out = local_dir / "index.html"
        with atomic_text(out) as stream:
            stream.write(render_page(bundle))
        return out

    out = base_dir / "index.html"
    docs = base_dir / "docs/index.html"
    out.write_text(render_page(bundle), encoding="utf-8")
    docs.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(out, docs)
    return out


if __name__ == "__main__":
    p = export_all()
    print("Dashboard v2 exported:", p, p.stat().st_size)
