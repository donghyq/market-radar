"""Normalize replies from the public V2EX endpoint."""

import json
import re
import urllib.request
from urllib.parse import urlsplit

from signal_time import epoch_time
from evidence.user_comments import PUBLIC_REVIEW_LIMIT, save_comment


CHANNEL = "V2EX开发者与需求社区(实时API)"
TOPIC_URL = re.compile(r"https?://(?:[\w-]+\.)*v2ex\.com/t/([0-9]+)/?(?:[?#].*)?$", re.I | re.ASCII)
FLOOR_LINK = re.compile(r'@<a\s+href="/member/([^"/]+)"[^>]*>[^<]+</a>\s*#(\d{1,5})(?!\d)')


def normalize_replies(replies, topic_id, parent_url, *, limit=PUBLIC_REVIEW_LIMIT):
    """Keep source IDs and times. Resolve a quoted floor when the author agrees."""
    parent_url = urlsplit(parent_url)._replace(query="", fragment="").geturl()
    first = max(0, len(replies) - limit)
    for index in range(first, len(replies)):
        reply = replies[index]
        reply_id = str(reply.get("id") or "")
        content = reply.get("content") or ""
        if not reply_id or not content.strip():
            continue
        member = reply.get("member") or {}
        linked_id = ""
        if link := FLOOR_LINK.search(reply.get("content_rendered") or ""):
            user, floor = link[1], int(link[2])
            if 0 < floor <= index:
                linked = replies[floor - 1]
                if (linked.get("member") or {}).get("username") == user:
                    linked_id = str(linked.get("id") or "")
        page = index // 100 + 1
        page_query = f"?p={page}" if page > 1 else ""
        yield {
            "channel": CHANNEL, "comment_id": reply_id, "thread_id": str(topic_id),
            "parent_url": parent_url, "source_url": f"{parent_url}{page_query}#r_{reply_id}",
            "content": content, "author_or_app": member.get("username") or "",
            "author_id": str(reply.get("member_id") or member.get("id") or ""),
            "reply_to_id": linked_id, "commented_at": epoch_time(reply.get("created")),
            "comment_time_source": "v2ex_reply_created", "source_updated_at": epoch_time(reply.get("last_modified")),
        }


def collect_replies(conn, topic_id, parent_url, *, user_agent):
    topic_id = str(topic_id or "")
    if not topic_id.isascii() or not topic_id.isdigit() or not parent_url:
        return 0
    url = f"https://www.v2ex.com/api/replies/show.json?topic_id={topic_id}"
    request = urllib.request.Request(url, headers={"User-Agent": user_agent})
    try:
        with urllib.request.urlopen(request, timeout=6) as response:
            replies = json.load(response)
        if not isinstance(replies, list):
            raise ValueError("expected a list of public replies")
        comments = list(normalize_replies(replies, topic_id, parent_url))
        with conn:
            return sum(save_comment(conn, comment, refresh=True) for comment in comments)
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        print(f"[WARN] V2EX 回帖采集跳过 ({topic_id}): {exc}")
        return 0
