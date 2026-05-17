"""notify.py 회귀 테스트.

SMTP는 모킹. 실제 Gmail 연결 안 함.
"""
from __future__ import annotations

import os
import smtplib
import unittest
from unittest.mock import MagicMock, patch

from src.check import NotificationEvent, WatchQuery
from src.notify import (
    GmailConfig,
    NotifyConfigError,
    NotifyResult,
    build_email,
    build_html_body,
    build_plain_body,
    build_subject,
    send_notifications,
)
from src.parser import ParsedProduct


def _sample_event(price: int = 16980, prev_status: str = "sold_out") -> NotificationEvent:
    query = WatchQuery(query="거북이 720", label="거북이 720 시리즈", active=True)
    product = ParsedProduct(
        product_id="9262",
        product_key="sake09:9262",
        name="금거북이 신슈키레이 키 준마이다이긴죠 킨몬니시키(720ml) 信州亀齢 き 39 金紋錦",
        detail_url="https://sake09.com/shop/products/detail.php?product_id=9262",
        image_url="https://sake09.com/shop/upload/save_image/04110946_6434addaa9d37.jpg",
        price_jpy=price,
        stock_status="available",
    )
    return NotificationEvent(query=query, product=product, previous_status=prev_status)


# ---- GmailConfig ---------------------------------------------------------

class TestGmailConfig(unittest.TestCase):
    def test_loads_from_env(self) -> None:
        env = {
            "GMAIL_USER": "test@gmail.com",
            "GMAIL_APP_PASSWORD": "abcd efgh ijkl mnop",  # 공백 포함된 Google 표시 형식
            "NOTIFY_TO": "recipient@example.com",
        }
        with patch.dict(os.environ, env, clear=True):
            cfg = GmailConfig.from_env()
        self.assertEqual(cfg.user, "test@gmail.com")
        self.assertEqual(cfg.app_password, "abcdefghijklmnop")  # 공백 제거 확인
        self.assertEqual(cfg.to, "recipient@example.com")
        self.assertEqual(cfg.from_name, "sake-watcher")

    def test_custom_from_name(self) -> None:
        env = {
            "GMAIL_USER": "test@gmail.com",
            "GMAIL_APP_PASSWORD": "x",
            "NOTIFY_TO": "to@example.com",
            "GMAIL_FROM_NAME": "사케 감시봇",
        }
        with patch.dict(os.environ, env, clear=True):
            cfg = GmailConfig.from_env()
        self.assertEqual(cfg.from_name, "사케 감시봇")

    def test_missing_all_raises_with_all_names(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(NotifyConfigError) as ctx:
                GmailConfig.from_env()
        msg = str(ctx.exception)
        self.assertIn("GMAIL_USER", msg)
        self.assertIn("GMAIL_APP_PASSWORD", msg)
        self.assertIn("NOTIFY_TO", msg)

    def test_missing_one_raises_with_that_name(self) -> None:
        env = {
            "GMAIL_USER": "test@gmail.com",
            "GMAIL_APP_PASSWORD": "x",
            # NOTIFY_TO missing
        }
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaises(NotifyConfigError) as ctx:
                GmailConfig.from_env()
        self.assertIn("NOTIFY_TO", str(ctx.exception))
        self.assertNotIn("GMAIL_USER", str(ctx.exception))

    def test_whitespace_only_treated_as_missing(self) -> None:
        env = {"GMAIL_USER": "   ", "GMAIL_APP_PASSWORD": "x", "NOTIFY_TO": "to@x"}
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaises(NotifyConfigError) as ctx:
                GmailConfig.from_env()
        self.assertIn("GMAIL_USER", str(ctx.exception))


# ---- Subject / Body 렌더링 -----------------------------------------------

class TestBuildSubject(unittest.TestCase):
    def test_contains_label_and_price(self) -> None:
        s = build_subject(_sample_event(price=16980))
        self.assertIn("거북이 720 시리즈", s)
        self.assertIn("16,980엔", s)
        self.assertTrue(s.startswith("[사케 재입고]"))

    def test_truncates_long_product_name(self) -> None:
        ev = _sample_event()
        s = build_subject(ev)
        # 상품명이 30자 초과 → 잘림 표시 포함
        self.assertIn("…", s)

    def test_format_complete(self) -> None:
        """현실적인 전체 제목 형식 회귀."""
        s = build_subject(_sample_event(price=14980))
        self.assertEqual(
            s,
            "[사케 재입고] 거북이 720 시리즈 / 금거북이 신슈키레이 키 준마이다이긴죠 킨몬니시키(72… (14,980엔)",
        )


class TestBuildPlainBody(unittest.TestCase):
    def test_contains_essential_fields(self) -> None:
        body = build_plain_body(_sample_event())
        # 사용자가 즉시 행동에 필요한 모든 정보
        self.assertIn("금거북이 신슈키레이", body)  # 상품명
        self.assertIn("16,980엔", body)  # 가격
        self.assertIn("https://sake09.com/shop/products/detail.php?product_id=9262", body)
        self.assertIn("sake09:9262", body)  # product_key
        self.assertIn("sold_out", body)  # 이전 상태
        self.assertIn("구매 가능", body)

    def test_new_discovery_shows_appropriate_label(self) -> None:
        ev = _sample_event(prev_status=None)  # type: ignore[arg-type]
        body = build_plain_body(ev)
        self.assertIn("신규 발견", body)


class TestBuildHtmlBody(unittest.TestCase):
    def test_contains_image_link_price(self) -> None:
        html = build_html_body(_sample_event())
        self.assertIn(
            "https://sake09.com/shop/upload/save_image/04110946_6434addaa9d37.jpg", html
        )
        self.assertIn("/shop/products/detail.php?product_id=9262", html)
        self.assertIn("16,980엔", html)
        # 상품명 표시
        self.assertIn("금거북이", html)

    def test_escapes_html_in_user_data(self) -> None:
        """상품명에 HTML 특수문자가 있어도 안전."""
        query = WatchQuery(query="test", label="<script>alert(1)</script>", active=True)
        product = ParsedProduct(
            product_id="1",
            product_key="sake09:1",
            name='<img onerror="x">',
            detail_url="https://sake09.com/",
            image_url="https://sake09.com/x.jpg",
            price_jpy=100,
            stock_status="available",
        )
        ev = NotificationEvent(query=query, product=product, previous_status="sold_out")
        html = build_html_body(ev)
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertNotIn('<img onerror="x">', html)
        # 이스케이프된 형태로는 존재해야 함
        self.assertIn("&lt;script&gt;", html)


class TestBuildEmail(unittest.TestCase):
    def test_multipart_with_plain_and_html(self) -> None:
        cfg = GmailConfig(
            user="me@gmail.com", app_password="x", to="me@gmail.com", from_name="sake-watcher"
        )
        msg = build_email(_sample_event(), cfg)
        self.assertEqual(msg["To"], "me@gmail.com")
        # From은 friendly name 포함
        self.assertIn("sake-watcher", msg["From"])
        self.assertIn("me@gmail.com", msg["From"])
        # subject 존재
        self.assertIn("[사케 재입고]", msg["Subject"])
        # multipart 구조 — plain + html 모두 존재
        bodies = list(msg.iter_parts())
        self.assertEqual(len(bodies), 2)
        types = sorted(p.get_content_type() for p in bodies)
        self.assertEqual(types, ["text/html", "text/plain"])


# ---- SMTP 발송 (mocked) ---------------------------------------------------

class TestSendNotifications(unittest.TestCase):
    def setUp(self) -> None:
        self.cfg = GmailConfig(
            user="me@gmail.com", app_password="x", to="me@gmail.com"
        )

    def test_empty_events_makes_no_smtp_connection(self) -> None:
        with patch("smtplib.SMTP") as mock_smtp:
            result = send_notifications([], self.cfg)
        mock_smtp.assert_not_called()
        self.assertEqual(result.sent, 0)
        self.assertEqual(result.failed, 0)

    def test_successful_batch_send(self) -> None:
        events = [_sample_event(price=14980), _sample_event(price=16980)]
        with patch("smtplib.SMTP") as mock_smtp:
            mock_inst = mock_smtp.return_value.__enter__.return_value
            result = send_notifications(events, self.cfg)
        # 단일 연결만 (효율 검증)
        mock_smtp.assert_called_once_with("smtp.gmail.com", 587, timeout=30)
        mock_inst.starttls.assert_called_once()
        mock_inst.login.assert_called_once_with("me@gmail.com", "x")
        self.assertEqual(mock_inst.send_message.call_count, 2)
        self.assertEqual(result.sent, 2)
        self.assertEqual(result.failed, 0)

    def test_per_send_failure_isolated(self) -> None:
        """1통 실패해도 나머지는 발송됨."""
        events = [_sample_event(price=1), _sample_event(price=2), _sample_event(price=3)]
        with patch("smtplib.SMTP") as mock_smtp:
            mock_inst = mock_smtp.return_value.__enter__.return_value
            # 두 번째 호출만 실패
            mock_inst.send_message.side_effect = [
                None,
                smtplib.SMTPRecipientsRefused({"x": (550, b"rejected")}),
                None,
            ]
            result = send_notifications(events, self.cfg)
        self.assertEqual(result.sent, 2)
        self.assertEqual(result.failed, 1)
        self.assertEqual(len(result.errors), 1)
        self.assertIn("SMTPRecipientsRefused", result.errors[0])

    def test_connection_failure_marks_all_failed(self) -> None:
        """connect/login 자체 실패 → 모든 알림 실패 처리."""
        events = [_sample_event() for _ in range(3)]
        with patch("smtplib.SMTP") as mock_smtp:
            mock_smtp.side_effect = smtplib.SMTPConnectError(421, "service unavailable")
            result = send_notifications(events, self.cfg)
        self.assertEqual(result.sent, 0)
        self.assertEqual(result.failed, 3)
        self.assertTrue(any("connection" in e.lower() or "smtp" in e.lower() for e in result.errors))

    def test_auth_failure_marks_all_failed(self) -> None:
        events = [_sample_event() for _ in range(2)]
        with patch("smtplib.SMTP") as mock_smtp:
            mock_inst = mock_smtp.return_value.__enter__.return_value
            mock_inst.login.side_effect = smtplib.SMTPAuthenticationError(
                535, b"username and password not accepted"
            )
            result = send_notifications(events, self.cfg)
        self.assertEqual(result.sent, 0)
        self.assertEqual(result.failed, 2)


if __name__ == "__main__":
    unittest.main()
