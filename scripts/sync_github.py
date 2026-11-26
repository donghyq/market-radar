#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
多人协作安全同步器 (Pull-Merge-Compile-Publish)
支持任意团队成员（Collaborator）运行：
1. 自动从远端 main 分支拉取最新 signals_master.jsonl 与 ideas/*.json，与本地新增信号按 uid 做并集无损合并（绝不冲掉队友刚抓的数据）；
2. 自动重算人群画像与时效统计，重新导出 CSV 与单文件看板；
3. 原子提交同步至 GitHub 仓库与线上 Pages。
"""
import argparse
import base64
import csv
import hashlib
import json
import os
import pathlib
import sqlite3
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import radar_cli
from collab_utils import dump_db_to_jsonl, restore_signal, sync_db_from_jsonl
from export_dashboard import export_all, render_page
from persona_and_freshness import ensure_columns, enrich_all_signals

BASE = pathlib.Path(__file__).resolve().parent.parent
REPO_SLUG = os.environ.get("MR_GITHUB_REPO", "donghyq/market-radar")
REPO = f"repos/{REPO_SLUG}"

PAGE_FILES = ("index.html", "docs/index.html")
RENDERER_FILES = (
    "scripts/export_dashboard.py", "scripts/template.html", "scripts/dashboard_app.js",
    "scripts/research_workstation.js", "scripts/workstation.css",
)
DATA_FILES = (
    "config/watch_keywords.json",
    "inbox/chanmama_xianyu_xhs_signals.csv", "exports/signals_full.csv",
    "data/signals/signals_master.jsonl", "data/tech_radar.json", "data/persona_stats.json",
)


def ensure_gh_account():
    """若本机同时登录了多个 GitHub 账号且包含仓库主账号，则自动切过去；单账号团队成员直接使用自身 Collaborator 权限"""
    st = subprocess.run(["gh", "auth", "status"], capture_output=True, text=True)
    owner = REPO_SLUG.split("/")[0]
    if owner in st.stdout and f"account {owner}" in st.stdout:
        subprocess.run(["gh", "auth", "switch", "-u", owner], capture_output=True)


def api(path, method="GET", payload=None):
    args = ["gh", "api", "-X", method, f"{REPO}/{path}"]
    if payload is not None:
        args += ["--input", "-"]
    return json.loads(subprocess.run(
        args, input=json.dumps(payload) if payload is not None else None,
        text=True, stdout=subprocess.PIPE, check=True,
    ).stdout)


def git_blob_sha(content):
    return hashlib.sha1(f"blob {len(content)}\0".encode() + content).hexdigest()


def pull_and_merge_remote_data(remote_map: dict):
    """拉取远端最新信号流与立项文件，与本地数据做无损并集合并，防止多人覆盖"""
    remote_jsonl_sha = remote_map.get("data/signals/signals_master.jsonl")
    local_jsonl = BASE / "data/signals/signals_master.jsonl"
    if remote_jsonl_sha and (not local_jsonl.exists() or git_blob_sha(local_jsonl.read_bytes()) != remote_jsonl_sha):
        blob = api(f"git/blobs/{remote_jsonl_sha}")
        remote_bytes = base64.b64decode(blob.get("content", ""))
        remote_lines = remote_bytes.decode("utf-8", errors="ignore").splitlines()

        conn = radar_cli.get_conn()
        radar_cli.init_db(conn)
        ensure_columns(conn)
        sync_db_from_jsonl(conn, BASE, radar_cli.insert_signal)

        merged_new = 0
        for ln in remote_lines:
            if not ln.strip():
                continue
            r = json.loads(ln)
            r.setdefault("source_tier", "远端合并")
            if restore_signal(conn, r, radar_cli.insert_signal):
                merged_new += 1
        conn.commit()

        # 同步远端新增的队友立项 JSON
        for r_path, r_sha in remote_map.items():
            if r_path.startswith("data/ideas/") and r_path.endswith(".json"):
                lp = BASE / r_path
                if not lp.exists():
                    lp.parent.mkdir(parents=True, exist_ok=True)
                    b_data = base64.b64decode(api(f"git/blobs/{r_sha}").get("content", ""))
                    lp.write_bytes(b_data)

        radar_cli.clean_and_tag_signals(conn)
        dump_db_to_jsonl(conn, BASE)
        rows = conn.execute("SELECT id, published_at, freshness_tier, audience_tag, channel, source_tier, category, query_term, author_or_app, title, content, metric_primary, metric_secondary, rating_or_price, pain_tags, is_noise, collected_at, source_url FROM raw_signals").fetchall()
        with (BASE / "exports" / "signals_full.csv").open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(["id","published_at","freshness_tier","audience_tag","channel","source_tier","category","query_term","author_or_app","title","content","metric_primary","metric_secondary","rating_or_price","pain_tags","is_noise","collected_at","source_url"])
            w.writerows([tuple(row) for row in rows])
        export_all(conn, BASE)
        conn.close()
        if merged_new:
            print(f"[MERGE] 已无损合入队友在远端新增的 {merged_new} 条信号并重编译看板。")


def prepare_files(root, remote, include_code=False):
    if not include_code:
        drift = [path for path in RENDERER_FILES
                 if not (root / path).is_file() or git_blob_sha((root / path).read_bytes()) != remote.get(path)]
        if drift:
            raise ValueError("本地渲染代码与 main 不一致，如需连同代码改动一起发布请加 --include-code：" + "、".join(drift))

    html = (root / PAGE_FILES[0]).read_text(encoding="utf-8")
    bundle = json.loads(html.split("const DATA = ", 1)[1].split(";\n</script>", 1)[0])
    if html != render_page(bundle) or html.encode() != (root / PAGE_FILES[1]).read_bytes():
        export_all(None, root)

    files = list(DATA_FILES) + list(PAGE_FILES)
    if include_code:
        files.extend(RENDERER_FILES)
        files.extend([
            "README.md", "run_radar.py", "Mac一键采集向导.command", "Windows一键采集向导.bat",
            *[str(p.relative_to(root)) for p in sorted((root / "scripts").glob("*.py"))],
            *[str(p.relative_to(root)) for p in sorted((root / "scripts").glob("*.json"))],
            *[str(p.relative_to(root)) for p in sorted((root / "team-toolkit").glob("*")) if p.is_file()],
        ])
    for folder in ("data/ideas", "data/archives"):
        files.extend(str(p.relative_to(root)) for p in sorted((root / folder).glob("*.json")))

    changed = []
    for rel in dict.fromkeys(files):
        path = root / rel
        if path.is_file():
            content = path.read_bytes()
            if git_blob_sha(content) != remote.get(rel):
                mode = "100755" if rel.endswith((".command", ".sh")) else "100644"
                changed.append({"path": rel, "mode": mode, "type": "blob", "content": content.decode("utf-8")})
    return changed


def sync(check_only=False, include_code=False):
    ensure_gh_account()
    head = api("git/ref/heads/main")["object"]["sha"]
    tree = api(f"git/commits/{head}")["tree"]["sha"]
    result = api(f"git/trees/{tree}?recursive=1")
    if result["truncated"]:
        raise ValueError("未能获取完整的远端文件列表，已停止同步。")
    remote = {entry["path"]: entry["sha"] for entry in result["tree"] if entry["type"] == "blob"}

    if not check_only:
        pull_and_merge_remote_data(remote)

    changed = prepare_files(BASE, remote, include_code=include_code)
    if not changed:
        print("数据和页面均无变更。")
        return
    if check_only:
        print("将同步：" + "、".join(entry["path"] for entry in changed))
        return
    new_tree = api("git/trees", "POST", {"base_tree": tree, "tree": changed})["sha"]
    commit = api("git/commits", "POST", {
        "message": "chore: sync team market radar signals and pages", "tree": new_tree, "parents": [head],
    })["sha"]
    api("git/refs/heads/main", "PATCH", {"sha": commit, "force": False})
    print(f"已安全合并并同步 {len(changed)} 个文件至 GitHub：{commit[:7]}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="检查待同步文件，不写远端")
    parser.add_argument("--include-code", action="store_true", help="连同脚本、配置和文档变更一并同步")
    args = parser.parse_args()
    try:
        sync(check_only=args.check, include_code=args.include_code)
    except (ValueError, IndexError, OSError, subprocess.CalledProcessError) as exc:
        raise SystemExit(f"同步未完成：{exc}") from exc
