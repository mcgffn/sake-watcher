"""check.py 알림 의사결정 로직 회귀 테스트.

decide_notifications는 순수 함수이므로 HTTP 모킹 없이 직접 검증한다.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.check import (
    NotificationEvent,
    WatchQuery,
    decide_notifications,
    load_watchlist,
)
from src.parser import ParsedProduct
from src.state import ProductState, State

NOW = "2026-05-16T12:00:00+00:00"
QUERY = WatchQuery(query="거북이 720", label="거북이 720 시리즈", active=True)


def _make_product(pid: str, status: str, price: int = 16980) -> ParsedProduct:
    return ParsedProduct(
        product_id=pid,
        product_key=f"sake09:{pid}",
        name=f"테스트 상품 {pid}",
        detail_url=f"https://sake09.com/shop/products/detail.php?product_id={pid}",
        image_url=f"https://sake09.com/img_{pid}.jpg",
        price_jpy=price,
        stock_status=status,
    )


def _existing_record(key: str, status: str) -> ProductState:
    return ProductState(
        product_key=key,
        name="prev name",
        detail_url="https://sake09.com/old",
        image_url="https://sake09.com/old.jpg",
        price_jpy=10000,
        stock_status=status,
        first_seen_utc="2026-05-15T00:00:00+00:00",
        last_seen_utc="2026-05-15T00:00:00+00:00",
        last_status_change_utc="2026-05-15T00:00:00+00:00",
        discovered_via_query="거북이 720",
    )


class TestNewProductTransitions(unittest.TestCase):
    """state에 없던 product_key를 처음 발견한 케이스."""

    def test_new_available_triggers_notification(self) -> None:
        state = State()
        product = _make_product("9999", "available")
        events = decide_notifications(QUERY, [product], state, NOW)
        self.assertEqual(len(events), 1)
        self.assertIsNone(events[0].previous_status)
        self.assertEqual(events[0].product.product_key, "sake09:9999")
        # state에도 기록되어야 함
        self.assertIn("sake09:9999", state.products)
        self.assertEqual(state.products["sake09:9999"].last_notified_utc, NOW)

    def test_new_sold_out_records_but_no_notification(self) -> None:
        state = State()
        product = _make_product("9999", "sold_out")
        events = decide_notifications(QUERY, [product], state, NOW)
        self.assertEqual(events, [])
        self.assertIn("sake09:9999", state.products)
        self.assertIsNone(state.products["sake09:9999"].last_notified_utc)


class TestExistingProductTransitions(unittest.TestCase):
    """state에 이미 있는 product_key의 상태 변화."""

    def test_sold_out_to_available_triggers_notification(self) -> None:
        state = State(
            products={"sake09:9262": _existing_record("sake09:9262", "sold_out")}
        )
        product = _make_product("9262", "available")
        events = decide_notifications(QUERY, [product], state, NOW)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].previous_status, "sold_out")
        self.assertEqual(state.products["sake09:9262"].stock_status, "available")
        self.assertEqual(state.products["sake09:9262"].last_status_change_utc, NOW)

    def test_available_to_available_no_notification(self) -> None:
        state = State(
            products={"sake09:9262": _existing_record("sake09:9262", "available")}
        )
        product = _make_product("9262", "available")
        events = decide_notifications(QUERY, [product], state, NOW)
        self.assertEqual(events, [])
        # last_status_change_utc는 그대로
        self.assertEqual(
            state.products["sake09:9262"].last_status_change_utc,
            "2026-05-15T00:00:00+00:00",
        )

    def test_sold_out_to_sold_out_no_notification(self) -> None:
        state = State(
            products={"sake09:9262": _existing_record("sake09:9262", "sold_out")}
        )
        product = _make_product("9262", "sold_out")
        events = decide_notifications(QUERY, [product], state, NOW)
        self.assertEqual(events, [])

    def test_available_to_sold_out_no_notification(self) -> None:
        """재고 소진 방향은 알림 대상 아님."""
        state = State(
            products={"sake09:9262": _existing_record("sake09:9262", "available")}
        )
        product = _make_product("9262", "sold_out")
        events = decide_notifications(QUERY, [product], state, NOW)
        self.assertEqual(events, [])
        self.assertEqual(state.products["sake09:9262"].stock_status, "sold_out")
        self.assertEqual(state.products["sake09:9262"].last_status_change_utc, NOW)


class TestMixedScenarios(unittest.TestCase):
    """현실적인 다중 product 시나리오."""

    def test_promotional_variants_tracked_separately(self) -> None:
        """동일 상품명 다른 product_id (프로모션 variant) — 별도로 알림."""
        state = State(
            products={
                "sake09:9262": _existing_record("sake09:9262", "sold_out"),
                "sake09:9264": _existing_record("sake09:9264", "sold_out"),
            }
        )
        products = [
            _make_product("9262", "available", price=16980),
            _make_product("9264", "available", price=14980),
        ]
        events = decide_notifications(QUERY, products, state, NOW)
        self.assertEqual(len(events), 2)
        keys = {e.product.product_key for e in events}
        self.assertEqual(keys, {"sake09:9262", "sake09:9264"})

    def test_only_one_of_many_resolves(self) -> None:
        """4개 중 1개만 재입고 — 1건만 알림."""
        state = State(
            products={
                "sake09:9262": _existing_record("sake09:9262", "sold_out"),
                "sake09:2484": _existing_record("sake09:2484", "sold_out"),
                "sake09:9264": _existing_record("sake09:9264", "sold_out"),
                "sake09:4829": _existing_record("sake09:4829", "sold_out"),
            }
        )
        products = [
            _make_product("9262", "sold_out"),
            _make_product("2484", "available"),  # 이것만 풀림
            _make_product("9264", "sold_out"),
            _make_product("4829", "sold_out"),
        ]
        events = decide_notifications(QUERY, products, state, NOW)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].product.product_key, "sake09:2484")

    def test_no_time_based_dedup_re_notifies_on_re_transition(self) -> None:
        """sold_out → available → sold_out → available 사이클: 두 번째도 알림.

        시간 기반 dedup이 없다는 것을 명시적으로 검증.
        """
        # 1차: sold_out → available, 알림
        state = State(
            products={"sake09:9262": _existing_record("sake09:9262", "sold_out")}
        )
        events1 = decide_notifications(
            QUERY, [_make_product("9262", "available")], state, NOW
        )
        self.assertEqual(len(events1), 1)

        # 2차: 같은 실행 사이클에서 다시 sold_out 관찰
        events2 = decide_notifications(
            QUERY, [_make_product("9262", "sold_out")], state, NOW
        )
        self.assertEqual(events2, [])

        # 3차: 또 available로 전환 → 알림 다시 발생
        later = "2026-05-16T13:00:00+00:00"
        events3 = decide_notifications(
            QUERY, [_make_product("9262", "available")], state, later
        )
        self.assertEqual(len(events3), 1)


class TestLoadWatchlist(unittest.TestCase):
    def test_loads_step1_watchlist(self) -> None:
        """단계 1에서 만든 watchlist.json 호환."""
        sample = {
            "queries": [
                {
                    "query": "거북이 720",
                    "label": "신슈키레이 거북이 720ml 시리즈",
                    "active": True,
                    "note": "test",
                },
                {
                    "query": "우부스나 카바 4농",
                    "label": "우부스나 카바 4농",
                    "active": False,
                },
            ]
        }
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "watchlist.json"
            path.write_text(json.dumps(sample, ensure_ascii=False), encoding="utf-8")
            queries = load_watchlist(path)
            self.assertEqual(len(queries), 2)
            self.assertEqual(queries[0].query, "거북이 720")
            self.assertTrue(queries[0].active)
            self.assertFalse(queries[1].active)

    def test_label_defaults_to_query_if_missing(self) -> None:
        sample = {"queries": [{"query": "거북이 720"}]}
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "watchlist.json"
            path.write_text(json.dumps(sample, ensure_ascii=False), encoding="utf-8")
            queries = load_watchlist(path)
            self.assertEqual(queries[0].label, "거북이 720")


if __name__ == "__main__":
    unittest.main()
