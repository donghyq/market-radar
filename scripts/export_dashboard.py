#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import datetime
import json
import pathlib
import shutil
import sqlite3

BASE_DIR = pathlib.Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "radar.db"
OUT_HTML = BASE_DIR / "index.html"
DOCS_HTML = BASE_DIR / "docs" / "index.html"
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


def export_all(conn=None, base_dir=BASE_DIR):
    close_conn = False
    if conn is None:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        close_conn = True

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

    bundle = {
        "updated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "projects": projects,
        "existing_ideas": cfg.get("existing_ideas", []),
        "signals": signals,
        "whitepaper": wp,
        "archives": archives,
    }

    page = render_page(bundle)
    OUT_HTML.write_text(page, encoding="utf-8")
    DOCS_HTML.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(OUT_HTML, DOCS_HTML)

    if close_conn:
        conn.close()
    return OUT_HTML


if __name__ == "__main__":
    p = export_all()
    print("Dashboard v2 exported:", p, p.stat().st_size)
