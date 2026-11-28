import io
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import discovery_scanner
import radar_cli
from collectors.appinn_collector import ASK_PATH, CHANNEL as APPINN_CHANNEL, collect_appinn
from collectors.github_issue_comments import collect_issue_comments
from collectors.v2ex_comments import CHANNEL
from evidence.user_comments import load_comments, save_comment
from evidence_rules import default_rules, thread_key
from export_dashboard import comment_signals


class EvidenceRulesTest(unittest.TestCase):
    def setUp(self):
        self.rules = default_rules()
        self.conn = radar_cli.get_conn(pathlib.Path(":memory:"))
        self.addCleanup(self.conn.close)
        radar_cli.init_db(self.conn)
        self.post = {"channel": CHANNEL, "title": "有没有好用的记账软件？",
                     "source_url": "https://www.v2ex.com/t/111", "record_type": "signal"}
        self.reply = {"channel": CHANNEL, "comment_id": "123", "thread_id": "111",
                      "parent_url": self.post["source_url"], "source_url": self.post["source_url"] + "#r_123",
                      "author_id": "52", "content": "我做了个工具，私信我免费领安装包。"}

    def test_explicit_promotion_uses_thread_without_penalizing_other_replies(self):
        complaint = {**self.reply, "comment_id": "124", "content": "上传照片丢失，客服非要我加微解决。"}
        normal = {**self.reply, "comment_id": "125", "content": "推荐钱迹，支持网盘同步。"}
        result = list(self.rules.evaluate_batch([self.post, self.reply, complaint, normal]))
        self.assertEqual([row["evidence_status"] for row in result],
                         ["eligible", "promotional", "eligible", "context"])
        cited = [match for match in result[1]["matches"] if match["field"] == "thread"]
        self.assertEqual(cited[0]["source_url"], self.post["source_url"])
        self.assertFalse(result[1]["counts_as_demand"])
        self.assertIn("具体故障", result[2]["intents"])

    def test_github_comment_collection_paginates_and_preserves_source_identity(self):
        issue = "https://github.com/Example/Editor/issues/42?ref=archive"
        comment = {"id": 9007199254740993, "body": "Export fails when saving a transparent image.",
                   "user": {"id": 27, "login": "reader", "html_url": "https://github.com/reader"},
                   "created_at": "2026-10-10T12:34:56Z", "updated_at": "2026-10-11T12:34:56Z"}
        host = "https://api.github.com/repos/example/editor/issues/42/comments"

        def response(rows, link=""):
            stream = io.BytesIO(json.dumps(rows).encode())
            stream.headers = {"Link": link}
            return stream

        bot = {"id": 12, "body": "Duplicate report.", "user": {"type": "Bot"}}
        other = {"id": 84, "body": "I see the same error too.",
                 "html_url": "https://github.com/Example/Editor/issues/42#issuecomment-84"}
        pages = [response([comment, bot], f'<{host}?per_page=100&page=2>; rel="next"'), response([other])]
        with patch("collectors.github_issue_comments.urllib.request.urlopen", side_effect=pages) as send:
            self.assertEqual(collect_issue_comments(self.conn, issue, user_agent="test"), 2)
        self.assertEqual([call.args[0].full_url for call in send.call_args_list],
                         [f"{host}?per_page=100&page=1", f"{host}?per_page=100&page=2"])
        by_id = {r["comment_id"]: r for r in load_comments(self.conn)}
        saved = by_id["9007199254740993"]
        self.assertEqual(saved["source_url"], "https://github.com/example/editor/issues/42#issuecomment-9007199254740993")
        self.assertEqual(by_id["84"]["source_url"], other["html_url"])
        self.assertEqual(saved["author_id"], "27")
        self.assertEqual(saved["commented_at"], "2026-10-10T12:34:56+00:00")
        self.assertEqual(saved["source_updated_at"], "2026-10-11T12:34:56+00:00")
        self.assertEqual(thread_key(saved), thread_key({"channel": "GitHub Issue报错", "source_url": issue}))
        with patch("collectors.github_issue_comments.urllib.request.urlopen", return_value=response([comment])):
            self.assertEqual(collect_issue_comments(self.conn, issue, user_agent="test"), 0)
        self.assertEqual(len(load_comments(self.conn)), 2)

    def test_context_change_invalidates_a_cached_recommendation(self):
        repeated = "推荐这个记账工具，跨平台查看的这个版本可以在此下载 https://example.test/app"
        first = {**self.reply, "content": repeated}
        self.assertTrue(save_comment(self.conn, first))
        self.assertEqual(comment_signals(self.conn)[0]["evidence_status"], "context")
        with patch.object(self.rules, "evaluate", wraps=self.rules.evaluate) as evaluate:
            comment_signals(self.conn)
            self.assertEqual(evaluate.call_count, 0)
            second = {**first, "comment_id": "124", "thread_id": "112",
                      "parent_url": "https://www.v2ex.com/t/112", "source_url": "https://www.v2ex.com/t/112#r_124"}
            self.assertTrue(save_comment(self.conn, second))
            result = comment_signals(self.conn)
            self.assertEqual(evaluate.call_count, 2)
        self.assertEqual([row["evidence_status"] for row in result], ["unverified", "unverified"])
        repeated = next(match for match in result[0]["matches"] if match["rule_id"] == "repeated-recommendation")
        self.assertEqual(repeated["related_sources"], [second["source_url"]])

    def test_quoted_promotion_and_an_unpaid_price_do_not_change_evidence(self):
        candidate = {**self.reply, "content": "> 自荐，私信我领安装包\n客服让我加微，我的文件导出报错。"}
        result = self.rules.evaluate(candidate)
        self.assertEqual(result["evidence_status"], "eligible")
        self.assertEqual(result["intents"], ["具体故障"])
        inquiry = self.rules.evaluate({"content": "我 99 元会考虑，工具怎么收费？"})
        self.assertEqual(inquiry["intents"], ["询价"])
        hearsay = self.rules.evaluate({**self.reply, "content": "我在用户群里听说开发者离职了。"})
        self.assertEqual(hearsay["evidence_status"], "context")

    def test_followup_from_the_promoting_author_requires_a_call_to_action(self):
        post = {**self.post, "title": "[自荐] 一个记账工具", "author_or_app": "V2EX @example"}
        reply = {**self.reply, "author_or_app": "example", "content": "您可以试用比较一下。"}
        thanks = {**reply, "comment_id": "124", "content": "谢谢回复。"}
        shopper = {**reply, "comment_id": "125", "author_or_app": "reader", "author_id": "53"}
        rows = list(self.rules.evaluate_batch([post, reply, thanks, shopper]))
        self.assertEqual([row["evidence_status"] for row in rows],
                         ["promotional", "promotional", "context", "context"])

    def test_public_forum_keeps_reply_links_and_the_quoted_author_separate(self):
        root = {"id": 30, "post_number": 1, "username": "reader", "user_id": 4,
                "cooked": "<p>要能编辑本地文件。</p>"}
        offer = {"id": 31, "post_number": 2, "username": "creator", "user_id": 5,
                 "cooked": "<p>我做了一个 NAS 播放器，欢迎体验。</p>"}
        quoted = {"id": 32, "post_number": 3, "username": "reviewer", "user_id": 6,
                  "created_at": "2026-11-18T10:11:12Z", "reply_to_post_number": 2,
                  "cooked": '<aside class="quote"><div>开发者自荐</div><blockquote>欢迎下载体验。</blockquote></aside><p>重新安装还是不行。</p>'}
        topic = {"id": 88, "title": "寻找一个轻量编辑器", "post_stream": {"posts": [root, offer, quoted]}}
        listing = {"topic_list": {"topics": [{"id": 88, "posts_count": 3}]}}
        with patch("collectors.appinn_collector.fetch_json", side_effect=lambda path: listing if path == ASK_PATH else topic):
            self.assertEqual(collect_appinn(self.conn), (1, 2))
            self.assertEqual(collect_appinn(self.conn), (0, 0))
        first, second = load_comments(self.conn)
        self.assertEqual(first["channel"], APPINN_CHANNEL)
        self.assertEqual(second["reply_to_id"], first["comment_id"])
        self.assertEqual(second["source_url"], "https://meta.appinn.net/t/topic/88/3")
        self.assertIn("> 开发者自荐", second["content"])
        self.assertEqual([result["evidence_status"] for result in comment_signals(self.conn)],
                         ["promotional", "eligible"])
        disclosed = {"channel": APPINN_CHANNEL, "title": "一个开源程序",
                     "content": "分享一下自己做的开源截图软件。"}
        self.assertEqual(self.rules.evaluate(disclosed)["evidence_status"], "promotional")

    def test_github_issue_matches_report_content_and_skips_template_instructions(self):
        source = {"channel": "GitHub Issue报错(实时API)", "source_url": "https://github.com/example/editor/issues/23"}
        report = {**source, "title": "Exported file opens in the viewer instead of the editor"}
        result = self.rules.evaluate(report)
        self.assertEqual(result["intents"], ["具体故障"])
        note = {**source, "title": "Maintenance note from the editor team",
                "content": "仓库 example/editor 用户高频需求/报错：维护说明。详情摘要：<!-- Please add a title. -->\nNo longer freezes when opening files.\n```\nThe app crashes on start.\n```"}
        self.assertEqual(self.rules.evaluate(note)["evidence_status"], "context")
        self.assertFalse(self.rules.evaluate({**report, "channel": "GitHub 开源项目", "source_url": "https://github.com/example/editor"})["counts_as_demand"])
        empty_form = {**source, "title": "Issue template example", "content": "### Actual Behavior\n\n_No response_\n\n### Steps to reproduce\n\nPlease provide example steps."}
        self.assertFalse(self.rules.evaluate(empty_form)["counts_as_demand"])
        filled_form = {**source, "title": "Unexpected toolbar selection", "content": "### Actual Behavior\n\nThe selected item moves to a different row after editing the label."}
        self.assertIn("具体故障", self.rules.evaluate(filled_form)["intents"])

    def test_short_forum_retest_cites_the_visible_thread(self):
        parent = {"channel": APPINN_CHANNEL, "source_url": "https://meta.appinn.net/t/topic/31",
                  "title": "更新后同步不了"}
        reply = {"channel": APPINN_CHANNEL, "comment_id": "494", "thread_id": "31",
                 "parent_url": parent["source_url"], "source_url": parent["source_url"] + "/3",
                 "content": "试了还是不行。"}
        self.assertFalse(self.rules.evaluate(reply)["counts_as_demand"])
        _, result = self.rules.evaluate_batch([parent, reply])
        self.assertTrue(result["counts_as_demand"])
        self.assertTrue(any(hit["source_url"] == parent["source_url"] for hit in result["matches"]))
        guess = {**reply, "content": "升级可能导致配置失效，无法正常启动对应组件。"}
        self.assertFalse(self.rules.evaluate(guess)["counts_as_demand"])

    def test_comment_labels_carry_source_quotes_for_both_axes(self):
        comment = {**self.reply, "content": "换机后怎么迁移本地文件？同步失败，找客服退款一直不处理。"}
        result = self.rules.evaluate(comment)
        self.assertTrue({"迁移需求", "同步异常", "退款求助", "售后反馈"} <= set(result["intents"]))
        self.assertTrue({"同步与备份", "导入导出与迁移", "离线与本地存储", "客服与售后"} <= set(result["topic_tags"]))
        for label, kind in (("退款求助", "intent"), ("离线与本地存储", "topic")):
            hit = next(match for match in result["matches"] if match.get("label") == label)
            self.assertEqual(hit["label_kind"], kind)
            self.assertEqual(hit["source_url"], comment["source_url"])
            self.assertIn(hit["quote"], comment["content"])

    def test_comment_context_labels_do_not_create_independent_demand(self):
        post = {**self.post, "title": "同步失败，更新后无法启动"}
        examples = [
            ("试了现在可以了。", "修复确认"),
            ("我们已经修复了启动时闪退。", "更新说明"),
            ("建议先备份再重启。", "操作建议"),
            ("我推荐试试 FileKeep。", "产品推荐"),
        ]
        records = [post, *({**self.reply, "comment_id": str(index), "content": content}
                           for index, (content, _) in enumerate(examples))]
        for (_, expected), row in zip(examples, list(self.rules.evaluate_batch(records))[1:]):
            self.assertIn(expected, row["intents"])
            self.assertEqual(row["evidence_status"], "context")
        quoted = {**self.reply, "content": "> 请问这个是订阅还是买断？怎么退款？\n感谢回复。"}
        self.assertEqual(self.rules.evaluate(quoted)["topic_tags"], [])
        self.assertEqual(self.rules.evaluate(quoted)["intents"], [])
        partial = {**self.reply, "content": "我们已经修复了启动时闪退，不过现在同步失败。"}
        result = self.rules.evaluate(partial)
        self.assertIn("更新说明", result["intents"])
        self.assertIn("同步异常", result["intents"])
        self.assertTrue(result["counts_as_demand"])

    def test_signal_cleaning_reuses_results_until_input_changes(self):
        radar_cli.insert_signal(self.conn, "V2EX", "test", "test", "test", "求一款记账软件",
                                "最好能脱机使用", "", "", "", "", self.post["source_url"])
        self.conn.commit()
        radar_cli.clean_and_tag_signals(self.conn)
        with patch.object(self.rules, "evaluate", wraps=self.rules.evaluate) as evaluate:
            radar_cli.clean_and_tag_signals(self.conn)
            self.assertEqual(evaluate.call_count, 0)
            self.conn.execute("UPDATE raw_signals SET content='私信我领取软件' WHERE id=1")
            stats = radar_cli.clean_and_tag_signals(self.conn)
            self.assertEqual(evaluate.call_count, 1)
        self.assertEqual(stats["noise"], 1)

    def test_v2ex_discovery_imports_public_replies_and_keeps_the_existing_id(self):
        topic = {"id": 111, "url": self.post["source_url"], "title": self.post["title"],
                 "content": "需要一款记账软件", "replies": 2}
        replies = [
            {"id": 123, "created": 1700000000, "content": "有推荐的软件吗？",
             "member": {"id": 52, "username": "example"}},
            {"id": 124, "created": 1700000100, "member_id": 54, "content": self.reply["content"],
             "content_rendered": '@<a href="/member/example">example</a> #1'},
        ]

        def public_api(request, **kwargs):
            rows = replies if "replies/show" in request.full_url else [topic]
            return io.BytesIO(json.dumps(rows).encode("utf-8"))

        with patch("urllib.request.urlopen", side_effect=public_api):
            self.assertEqual(discovery_scanner.scan_v2ex_pain_points(self.conn), 1)
            self.assertEqual(discovery_scanner.scan_v2ex_pain_points(self.conn), 0)
        raw = load_comments(self.conn)
        self.assertEqual([(row["comment_id"], row["author_id"], row["reply_to_id"]) for row in raw],
                         [("123", "52", ""), ("124", "54", "123")])
        self.assertEqual(raw[1]["source_url"], self.post["source_url"] + "#r_124")
        self.assertEqual(raw[1]["comment_time_source"], "v2ex_reply_created")
        self.assertEqual(comment_signals(self.conn)[1]["evidence_status"], "promotional")

    def test_app_store_fields_and_newer_review_revision(self):
        entry = {"id": {"label": "45"}, "content": {"label": "导出报错"}, "im:version": {"label": "2.0"},
                 "updated": {"label": "2026-11-18T10:00:00+08:00"}, "im:rating": {"label": "2"},
                 "author": {"name": {"label": "reader"},
                            "uri": {"label": "https://itunes.apple.com/cn/reviews/id12345"}}}
        first = radar_cli.appstore_review_comment(entry, "88")
        self.assertTrue(save_comment(self.conn, first, refresh=True))
        updated = {**first, "content": "新版本已修好", "app_version": "2.1", "source_metric": "5 星",
                   "source_updated_at": "2026-11-19T10:00:00+08:00", "commented_at": "2026-11-19T10:00:00+08:00"}
        self.assertFalse(save_comment(self.conn, updated, refresh=True))
        self.assertFalse(save_comment(self.conn, first, refresh=True))
        record, = load_comments(self.conn)
        self.assertEqual((record["comment_id"], record["thread_id"], record["author_id"]), ("45", "88", "12345"))
        self.assertEqual(record["commented_at"], updated["commented_at"])
        self.assertEqual((record["content"], record["app_version"], record["source_metric"]),
                         (updated["content"], "2.1", "5 星"))

    def test_portable_cli_matches_library_in_independent_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory)
            package = path / "rules"
            shutil.copytree(SCRIPTS.parent / package.name, package, ignore=shutil.ignore_patterns("__pycache__"))
            records = [self.post, self.reply]
            input_path = path / "input.jsonl"
            input_path.write_text("\n".join(json.dumps(record) for record in records), encoding="utf-8")
            result = subprocess.run([sys.executable, str(package / "engine.py"), str(input_path)],
                                    cwd=path, check=True, capture_output=True)
            self.assertEqual([json.loads(line) for line in result.stdout.splitlines()],
                             list(self.rules.evaluate_batch(records)))


if __name__ == "__main__":
    unittest.main()
