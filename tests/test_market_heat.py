from datetime import date
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from market_heat import build_market_heat


class MarketHeatTest(unittest.TestCase):
    today = date(2026, 11, 28)

    def signal(self, number, **fields):
        return {"id": number, "display_id": f"S{number}", "channel": "V2EX", "title": "想找照片修复工具",
                "source_url": f"https://www.v2ex.com/t/{number}", "source_published_at": "2026-11-27", **fields}

    def comment(self, number, **fields):
        return {"id": str(number), "display_id": f"C{number}", "record_type": "comment",
                "channel": "V2EX开发者与需求社区(实时API)", "parent_url": "https://v2ex.com/t/1",
                "source_published_at": "2026-11-27T20:00:00+00:00",
                "counts_as_demand": True, **fields}

    def build(self, records, archives=()):
        return build_market_heat(records, archives, as_of=self.today)

    def test_comment_inherits_the_product_and_uses_its_own_source_day(self):
        app = self.signal(1, channel="AppStore应用(实时API)", title="旧照宝-照片修复",
                          source_url="https://apps.apple.com/cn/app/id100",
                          published_time_source="appstore_release_date")
        post = self.signal(2, title="有没有旧照宝的替代品")
        reply = self.comment(1, parent_url="https://v2ex.com/t/2#reply1")
        events = self.build([app, post, reply])["events"]
        self.assertEqual([row["product"] for row in events], ["appstore:100"] * 3)
        self.assertEqual(events[0]["metrics"], ["production"])
        self.assertNotIn("timestamp", events[0])
        self.assertEqual(events[2]["metrics"], ["discussion", "demand"])
        self.assertEqual(events[2]["day"], "2026-11-28")
        self.assertEqual(events[2]["timestamp"], "2026-11-27T20:00:00+00:00")

    def test_deduplicates_public_posts_and_comments_and_excludes_promotion(self):
        signals = [self.signal(1), self.signal(2, source_url="https://v2ex.com/t/1#reply1"),
                   self.signal(3, evidence_status="promotional")]
        comment = self.comment(1)
        events = self.build([*signals, comment, dict(comment)])["events"]
        self.assertEqual([row["id"] for row in events], ["S1", "C1"])

    def test_catalog_and_legacy_dates_do_not_create_dated_discussion_or_production(self):
        catalog = self.signal(1, channel="京东服务", source_tier="公开目录",
                              source_url="https://item.jd.com/123.html", counts_as_demand=True)
        post = self.signal(2, published_time_source="legacy_archive_date", published_at="2026-11-28")
        future = self.signal(3, source_published_at="2026-11-29")
        events = self.build([catalog, post, future])["events"]
        self.assertEqual([(row["id"], row["day"], row["metrics"]) for row in events],
                         [("S2", "", ["discussion"]), ("S3", "", ["discussion"])])
        self.assertTrue(all("timestamp" not in row for row in events))

    def test_unrelated_products_with_the_same_name_keep_separate_ids(self):
        apps = [self.signal(i, channel="AppStore应用(实时API)", title="旧照宝",
                            source_url=f"https://apps.apple.com/cn/app/id{i}",
                            published_time_source="appstore_release_date") for i in (1, 2)]
        events = self.build([*apps, self.signal(3, title="旧照宝怎么用", content="使用咨询")])["events"]
        self.assertEqual([event["product"] for event in events], ["appstore:1", "appstore:2", ""])

    def test_archived_app_review_uses_the_app_name_and_keeps_evidence_decision(self):
        review = self.signal(1, channel="AppStore中国区差评(实时API)", title="[1星差评] 根本不能用",
                             author_or_app="口袋扫描王", category="招投标与合同办公工具",
                             source_url="https://apps.apple.com/cn/app/id100?uo=4",
                             counts_as_demand=True, evidence_status="eligible")
        original = dict(review)
        heat = self.build([review])
        self.assertEqual(heat["record_groups"]["S1"]["category_id"], "digital_office")
        self.assertEqual(heat["record_groups"]["S1"]["topic_id"], "documents")
        self.assertEqual(heat["record_groups"]["S1"]["product_name"], "口袋扫描王")
        self.assertEqual(heat["events"][0]["metrics"], ["discussion", "demand"])
        self.assertEqual(review, original)

    def test_ambiguous_product_alias_needs_its_configured_context(self):
        posts = [self.signal(1, title="论文讨论反重力场"), self.signal(2, title="反重力的账号 Pro 额度怎么查")]
        groups = self.build(posts)["record_groups"]
        self.assertEqual(groups["S1"]["product_id"], "")
        self.assertEqual(groups["S2"]["product_id"], "name:antigravity")
        self.assertEqual(groups["S2"]["basis"], "alias_title")

    def test_only_explicit_complete_coverage_can_establish_a_zero(self):
        archives = [{"date": "2026-11-28", "valid_signals": 55, "market_heat_coverage": [
            {"date": "2026-11-27", "category": "digital_content", "metric": "demand", "complete": True},
            {"date": "2026-11-27", "category": "照片处理与修图", "metric": "production", "complete": True},
            {"date": "2026-11-28", "metric": "discussion", "complete": False},
            {"date": "2026-11-29", "metric": "discussion", "complete": True},
        ]}]
        heat = self.build([], archives)
        self.assertEqual(heat["coverage"], [("2026-11-27", "数字内容制作与运营", "", "demand")])
        self.assertEqual(heat["categories"], ["数字内容制作与运营"])

    def test_related_topics_share_a_chart_group_and_keep_separate_topic_labels(self):
        heat = self.build([self.signal(1, title="求照片修复工具"), self.signal(2, title="需要科普动画代做")])
        groups = list(heat["record_groups"].values())
        self.assertEqual([g["topic_id"] for g in groups], ["photos", "animation"])
        self.assertEqual({g["category_id"] for g in groups}, {"digital_content"})
        self.assertEqual({e["category"] for e in heat["events"]}, {"数字内容制作与运营"})

    def test_consumer_products_and_services_use_existing_chart_groups(self):
        heat = self.build([
            self.signal(1, title="宠物喂养记录"),
            self.signal(2, title="老照片基础修复"),
            self.signal(3, title="睡前故事和儿童绘本"),
            self.signal(4, title="名画拼图"),
        ])
        groups = list(heat["record_groups"].values())
        self.assertEqual([g["category_id"] for g in groups], [
            "everyday_consumption", "everyday_consumption", "learning_reading", "desktop_entertainment",
        ])

    def test_version_and_service_releases_need_explicit_published_metadata(self):
        releases = [
            self.signal(1, title="Antigravity 2.0", source_url="https://example.test/releases/v2",
                        published_time_source="product_version_release"),
            self.signal(2, title="Antigravity 2.1", source_url="https://example.test/releases/v2.1",
                        published_time_source="product_version_release"),
            self.signal(3, title="照片修复服务上线", source_url="https://example.test/service/01",
                        published_time_source="service_listing_published"),
            self.signal(4, title="我更新了 Anthropic 工具", published_time_source="v2ex_topic_created"),
        ]
        events = self.build(releases)["events"]
        self.assertEqual([event.get("release") for event in events], ["版本发布", "版本发布", "服务发布", None])
