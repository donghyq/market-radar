"""Collect public software-help discussions from the Appinn forum."""

import json
import urllib.request
from html.parser import HTMLParser

import radar_cli
from signal_time import newest_results, source_time
from evidence.user_comments import save_comment


BASE_URL = "https://meta.appinn.net"
CHANNEL = "小众软件论坛"
ASK_PATH = "/c/wen-ti-qiu-zhu/7/l/latest.json"


class PostText(HTMLParser):
    """Convert Discourse HTML to plain text while marking quoted material."""

    blocks = {"aside", "blockquote", "br", "div", "h1", "h2", "h3", "li", "p", "pre"}

    def __init__(self):
        super().__init__()
        self.quote_depth = 0
        self.asides = []
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in self.blocks:
            self.parts.append("\n")
        if tag == "blockquote":
            self.quote_depth += 1
        if tag == "aside":
            quoted = "quote" in (dict(attrs).get("class") or "").split()
            self.asides.append(quoted)
            self.quote_depth += quoted

    def handle_endtag(self, tag):
        if tag == "blockquote":
            self.quote_depth = max(0, self.quote_depth - 1)
        if tag == "aside" and self.asides:
            self.quote_depth -= self.asides.pop()
        if tag in self.blocks:
            self.parts.append("\n")

    def handle_data(self, data):
        if self.quote_depth:
            self.parts.extend(f"\n> {line.strip()}\n" for line in data.splitlines() if line.strip())
        else:
            self.parts.append(data)

    def text(self):
        return "\n".join(line.strip() for line in "".join(self.parts).splitlines() if line.strip())


def post_text(html):
    parser = PostText()
    parser.feed(html or "")
    parser.close()
    return parser.text()


def normalize_topic(payload, *, reply_limit=12):
    topic_id = str(payload.get("id") or "")
    posts = (payload.get("post_stream") or {}).get("posts") or []
    root = next((post for post in posts if post.get("post_number") == 1), None)
    title = (payload.get("title") or "").strip()
    if not topic_id.isdigit() or not root or not title or root.get("hidden") or root.get("deleted_at"):
        raise ValueError("missing public topic or opening post")

    parent_url = f"{BASE_URL}/t/topic/{topic_id}"
    topic = {
        "id": f"appinn:{topic_id}", "channel": CHANNEL, "title": title, "content": post_text(root.get("cooked")),
        "thread_id": topic_id, "source_url": parent_url, "author_or_app": root.get("username") or "",
        "author_id": str(root.get("user_id") or ""), "source_published_at": root.get("created_at") or "",
    }
    reply_ids = {post.get("post_number"): str(post.get("id") or "") for post in posts}
    replies = []
    for post in posts:
        if len(replies) >= reply_limit:
            break
        number = post.get("post_number")
        comment_id = reply_ids.get(number)
        if type(number) is not int or number <= 1 or not comment_id or post.get("hidden") or post.get("deleted_at"):
            continue
        if post.get("post_type", 1) != 1:
            continue
        content = post_text(post.get("cooked"))
        if content:
            parent_number = post.get("reply_to_post_number")
            replies.append({
                "channel": CHANNEL, "comment_id": comment_id, "thread_id": topic_id,
                "parent_url": parent_url, "source_url": f"{parent_url}/{number}", "content": content,
                "author_or_app": post.get("username") or "", "author_id": str(post.get("user_id") or ""),
                "reply_to_id": reply_ids.get(parent_number, "") if parent_number != 1 else "",
                "commented_at": post.get("created_at") or "", "comment_time_source": "appinn_post_created",
                "source_updated_at": post.get("updated_at") or "",
            })
    return topic, replies


def fetch_json(path):
    headers = {"User-Agent": radar_cli.USER_AGENT, "Accept": "application/json"}
    request = urllib.request.Request(BASE_URL + path, headers=headers)
    with urllib.request.urlopen(request, timeout=6) as response:
        return json.load(response)


def collect_appinn(conn, *, limit=4):
    try:
        payload = fetch_json(ASK_PATH)
        topics = payload["topic_list"]["topics"]
        if not isinstance(topics, list):
            raise ValueError("expected a public topic list")
    except (OSError, KeyError, TypeError, ValueError) as exc:
        print(f"[WARN] 小众软件论坛列表采集跳过: {exc}")
        return 0, 0

    candidates = ((topic, source_time(topic.get("created_at") or "")[0]) for topic in topics
                  if isinstance(topic, dict) and not topic.get("pinned"))
    added_topics = added_replies = 0
    for item, _ in newest_results(candidates, limit):
        topic_id = str(item.get("id") or "")
        if not topic_id.isdigit():
            continue
        try:
            topic, replies = normalize_topic(fetch_json(f"/t/topic/{topic_id}.json"))
            with conn:
                added = radar_cli.insert_signal(
                    conn, CHANNEL, "公开论坛", "公开求助", "问题求助", topic["title"], topic["content"],
                    topic["author_or_app"], f"{max(0, (item.get('posts_count') or 1) - 1)} 条回复", "", "",
                    topic["source_url"], source_published_at=topic["source_published_at"],
                    published_time_source="appinn_topic_created",
                )
                saved = sum(save_comment(conn, reply, refresh=True) for reply in replies)
            added_topics += int(added)
            added_replies += saved
        except (OSError, TypeError, ValueError, AttributeError) as exc:
            print(f"[WARN] 小众软件论坛主题采集跳过 ({topic_id}): {exc}")
    return added_topics, added_replies
