#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一键通过 gh api 将无冲突 JSONL 数据层、人脉立项卡、定时任务与新版看板同步到 GitHub 独立仓库"""
import base64
import json
import pathlib
import subprocess

BASE = pathlib.Path(__file__).resolve().parent.parent
REPO = "donghyq/market-radar"

STATIC_FILES = [
    ".gitignore",
    ".github/workflows/daily_radar.yml",
    "README.md",
    "SKILL.md",
    "index.html",
    "docs/index.html",
    "inbox/chanmama_xianyu_xhs_signals.csv",
    "exports/signals_full.csv",
    "data/signals/signals_master.jsonl",
    "scripts/radar_cli.py",
    "scripts/discovery_scanner.py",
    "scripts/auto_browser_collector.py",
    "scripts/collab_utils.py",
    "scripts/research_workstation.js",
    "scripts/workstation.css",
    "scripts/export_dashboard.py",
    "scripts/template.html",
    "scripts/dashboard_app.js",
    "scripts/dashboard_config.json",
    "scripts/whitepaper_config.json",
    "scripts/opportunities_seed.json",
    "scripts/sync_github.py",
]


def put_file(rel: str):
    p = BASE / rel
    if not p.exists():
        return
    sha = None
    chk = subprocess.run(["gh", "api", f"repos/{REPO}/contents/{rel}"], capture_output=True, text=True)
    if chk.returncode == 0:
        try:
            sha = json.loads(chk.stdout).get("sha")
        except Exception:
            pass
    b64 = base64.b64encode(p.read_bytes()).decode("ascii")
    body = {"message": f"chore: sync {rel}", "content": b64, "branch": "main"}
    if sha:
        body["sha"] = sha
    res = subprocess.run(
        ["gh", "api", "-X", "PUT", f"repos/{REPO}/contents/{rel}", "--input", "-"],
        input=json.dumps(body),
        capture_output=True,
        text=True,
    )
    print(f"[SYNC] {rel} -> {'OK' if res.returncode == 0 else res.stderr[:100]}")


def delete_remote_db():
    chk = subprocess.run(["gh", "api", f"repos/{REPO}/contents/radar.db"], capture_output=True, text=True)
    if chk.returncode == 0:
        sha = json.loads(chk.stdout).get("sha")
        if sha:
            body = json.dumps({"message": "chore: remove binary radar.db in favor of conflict-free JSONL", "sha": sha, "branch": "main"})
            subprocess.run(["gh", "api", "-X", "DELETE", f"repos/{REPO}/contents/radar.db", "--input", "-"], input=body, capture_output=True, text=True)
            print("[CLEAN] Removed binary radar.db from remote Git repository")


def sync():
    delete_remote_db()
    for rel in STATIC_FILES:
        put_file(rel)
    for folder in ["data/ideas", "data/archives"]:
        d = BASE / folder
        if d.exists():
            for jf in sorted(d.glob("*.json")):
                put_file(f"{folder}/{jf.name}")


if __name__ == "__main__":
    sync()
