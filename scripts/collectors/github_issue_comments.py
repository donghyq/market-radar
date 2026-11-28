"""Collect public GitHub Issue discussions with their original comment IDs."""

import json
import re
import urllib.request

from evidence_rules import GITHUB_ISSUE_URL
from evidence.user_comments import save_comment


CHANNEL = "GitHub Issues"
NEXT_PAGE = re.compile(r';\s*rel="next"')


def collect_issue_comments(conn, issue_url, *, user_agent):
    issue = GITHUB_ISSUE_URL.fullmatch(issue_url or "")
    if not issue:
        return 0

    repo, number = issue["repo"].lower(), issue["number"]
    parent = f"https://github.com/{repo}/issues/{number}"
    endpoint = f"https://api.github.com/repos/{repo}/issues/{number}/comments"
    headers = {"User-Agent": user_agent, "Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28"}
    comments = []
    page = 1
    try:
        while True:
            request = urllib.request.Request(f"{endpoint}?per_page=100&page={page}", headers=headers)
            with urllib.request.urlopen(request, timeout=10) as response:
                batch = json.load(response)
                more = NEXT_PAGE.search(response.headers.get("Link", ""))
            if not isinstance(batch, list) or any(not isinstance(comment, dict) for comment in batch):
                raise ValueError("expected a list of public issue comments")
            comments.extend(batch)
            if not more:
                break
            page += 1
    except (OSError, ValueError) as exc:
        print(f"[WARN] GitHub Issue 评论采集跳过 ({repo} #{number}): {exc}")
        return 0

    inserted = 0
    with conn:
        for comment in comments:
            user = comment.get("user") or {}
            comment_id = str(comment.get("id") or "")
            body = comment.get("body") or ""
            if user.get("type") == "Bot" or not comment_id.isdigit() or not body.strip():
                continue
            inserted += save_comment(conn, {
                "channel": CHANNEL,
                "comment_id": comment_id,
                "thread_id": parent,
                "parent_url": parent,
                "source_url": comment.get("html_url") or f"{parent}#issuecomment-{comment_id}",
                "content": body,
                "author_or_app": user.get("login") or "",
                "author_id": str(user.get("id") or ""),
                "author_profile_url": user.get("html_url") or "",
                "commented_at": comment.get("created_at") or "",
                "comment_time_source": "github_issue_comment_created",
                "source_updated_at": comment.get("updated_at") or "",
            }, refresh=True)
    return inserted
