import json
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))

import radar_cli
from collectors.consumer_sources import collect_notion, jd_items
from evidence_rules import default_rules


class ConsumerMarketTest(unittest.TestCase):
    def setUp(self):
        self.rules = default_rules()

    def assess(self, content, **extra):
        return self.rules.evaluate({"content": content, "source_url": "https://example.test/1", **extra})

    def test_buyer_budget_is_not_a_paid_price(self):
        result = self.assess("有没有人能帮我排版？预算50元，交付一份Word文件，今天能做吗？")
        self.assertTrue(result["counts_as_demand"])
        self.assertEqual(result["market"]["segment"], "virtual_service")
        self.assertEqual(result["market"]["role"], "buyer_request")
        self.assertEqual(result["market"]["facts"]["budget"], "预算50元")
        self.assertFalse(result["market"]["paid_evidence"])

    def test_paid_small_delivery_ranks_above_slow_delivery(self):
        body = "我请人做文档排版。我付了35元，{time}交付一份PDF，改了2次。"
        quick = self.assess(body.format(time="2小时"))
        slow = self.assess(body.format(time="30天"))
        self.assertTrue(quick["market"]["paid_evidence"])
        self.assertEqual(quick["market"]["facts"]["revisions"], "改了2次")
        self.assertGreater(quick["market"]["priority"], slow["market"]["priority"])

    def test_catalog_is_background_even_with_buyer_language(self):
        result = self.assess("照片修复。产品介绍引用了顾客说我花了20元。", source_tier="公开目录",
                             category="消费级虚拟服务", rating_or_price="19元")
        self.assertFalse(result["counts_as_demand"])
        self.assertFalse(result["market"]["paid_evidence"])
        self.assertEqual(result["market"]["facts"], {"asking_price": "19元"})

    def test_comment_can_inherit_the_market_of_an_app(self):
        url = "https://apps.apple.com/cn/app/id123"
        records = [
            {"channel": "AppStore应用(实时API)", "title": "时光", "category": "消费级虚拟产品 / 学习",
             "source_url": url, "content": "欢迎打开体验。"},
            {"channel": "App Store", "comment_id": "12345", "parent_url": url, "content": "充了39的一周会员。"},
        ]
        parent, child = self.rules.evaluate_batch(records)
        self.assertFalse(parent["counts_as_demand"])
        self.assertEqual(child["market"]["segment"], "virtual_product")
        self.assertTrue(child["market"]["paid_evidence"])

    def test_notion_uses_the_listing_and_reuses_published_review_identity(self):
        item = {
            "@type": "Product", "name": "Budget planner", "description": "Template for monthly budgets",
            "offers": {"price": 12, "priceCurrency": "USD"},
            "review": [{"name": "Helpful", "reviewBody": "I used this template for two weeks.",
                        "datePublished": "2026-10-01", "author": {"name": "Guest"}}],
        }
        def fetch(page):
            return '<script type="application/ld+json">' + json.dumps(item) + "</script>"

        with radar_cli.get_conn(pathlib.Path(":memory:")) as conn:
            radar_cli.init_db(conn)
            self.assertEqual(list(collect_notion(conn, ["budget"], fetch=fetch)), [(1, 1)])
            self.assertEqual(list(collect_notion(conn, ["budget"], fetch=fetch)), [(0, 0)])
            self.assertEqual(conn.execute("SELECT rating_or_price FROM raw_signals").fetchone()[0], "USD 12")

    def test_jd_links_are_restricted_to_matching_items(self):
        page = """
          <a class="price-href" href="//item.jd.com/1.html" title="老照片修复无痕改字">商家一</a>
          <a class="price-href" href="//item.jd.com/2.html" title="老照片修复与修补">商家二</a>
          <a class="price-href" href="https://other.test/3.html" title="老照片修复">其他</a>
        """
        self.assertEqual(list(jd_items(page, "老照片修复")), [("https://item.jd.com/2.html", "老照片修复与修补")])
