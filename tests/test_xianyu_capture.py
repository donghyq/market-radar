import pathlib
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))

import auto_browser_collector as collector


class XianyuCaptureTest(unittest.TestCase):
    def test_reports_http_status_at_the_failing_stage(self):
        self.assertEqual(collector.xianyu_http_failure("搜索接口", 401), "搜索接口返回 HTTP 401（需要登录）")
        self.assertEqual(collector.xianyu_http_failure("搜索接口", 403), "搜索接口返回 HTTP 403（站点拒绝访问）")
        self.assertEqual(collector.xianyu_http_failure("搜索接口", 429), "搜索接口返回 HTTP 429（请求受限）")
        self.assertEqual(collector.xianyu_page_failure(SimpleNamespace(status=200), "https://passport.goofish.com/login"),
                         "搜索页转到了登录或验证页面")

    def test_service_error_keeps_only_the_safe_code(self):
        session = {"ret": ["FAIL_SYS_TOKEN_EXPIRED::private payload"]}
        verification = {"ret": "FAIL_SYS_USER_VALIDATE::private payload"}
        self.assertEqual(collector.xianyu_payload_failure(session), "登录状态或会话凭证异常（FAIL_SYS_TOKEN_EXPIRED）")
        self.assertEqual(collector.xianyu_payload_failure(verification), "平台要求验证（FAIL_SYS_USER_VALIDATE）")
        self.assertEqual(collector.xianyu_payload_failure({"ret": ["sensitive message"]}), "平台返回业务失败")
        self.assertEqual(collector.xianyu_payload_failure({"ret": ["SUCCESS::ok"], "data": {"resultList": []}}), "")

    def test_combined_flags_use_the_interactive_single_pass(self):
        args = ["collector", "--login", "--collect", "--consumer-once", "--keywords", "电子请柬定制"]
        with patch.object(sys, "argv", args), patch.object(collector, "run_browser_collector") as run:
            collector.main()
        run.assert_called_once_with(mode="login_collect", targets=["xianyu"], keywords=["电子请柬定制"], consumer_once=True)

    def test_manual_confirmation_requires_an_open_marketplace_window(self):
        page = SimpleNamespace(url="https://www.goofish.com/", is_closed=lambda: False)
        with patch("builtins.input", return_value="y"):
            self.assertTrue(collector.confirm_xianyu_login(page))
            page.url = "https://passport.goofish.com/login"
            self.assertFalse(collector.confirm_xianyu_login(page))
