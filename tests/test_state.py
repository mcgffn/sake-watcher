"""state.py 회귀 테스트."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.state import ProductState, State, load_state, now_utc_iso, save_state


def _sample_product(key: str = "sake09:9262", status: str = "sold_out") -> ProductState:
    return ProductState(
        product_key=key,
        name="테스트 상품",
        detail_url=f"https://sake09.com/shop/products/detail.php?product_id={key.split(':')[1]}",
        image_url="https://sake09.com/x.jpg",
        price_jpy=16980,
        stock_status=status,
        first_seen_utc="2026-05-16T00:00:00+00:00",
        last_seen_utc="2026-05-16T00:00:00+00:00",
        last_status_change_utc="2026-05-16T00:00:00+00:00",
        discovered_via_query="거북이 720",
    )


class TestLoadState(unittest.TestCase):
    def test_loads_missing_file_as_empty_state(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "nonexistent.json"
            state = load_state(path)
            self.assertEqual(state.products, {})
            self.assertIsNone(state.last_check_utc)

    def test_loads_empty_file_as_empty_state(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "empty.json"
            path.write_text("", encoding="utf-8")
            state = load_state(path)
            self.assertEqual(state.products, {})

    def test_loads_initial_state_json_schema(self) -> None:
        """단계 1에서 생성된 state.json 초기 형태 호환."""
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "state.json"
            path.write_text(
                json.dumps({"schema_version": 1, "last_check_utc": None, "products": {}}),
                encoding="utf-8",
            )
            state = load_state(path)
            self.assertEqual(state.schema_version, 1)
            self.assertEqual(state.products, {})

    def test_rejects_unsupported_schema_version(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "state.json"
            path.write_text(
                json.dumps({"schema_version": 99, "products": {}}),
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                load_state(path)


class TestSaveLoadRoundtrip(unittest.TestCase):
    def test_roundtrip_preserves_all_fields(self) -> None:
        original = State(
            last_check_utc="2026-05-16T12:00:00+00:00",
            products={
                "sake09:9262": _sample_product("sake09:9262", "sold_out"),
                "sake09:14655": _sample_product("sake09:14655", "available"),
            },
        )
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "state.json"
            save_state(path, original)
            reloaded = load_state(path)
            self.assertEqual(reloaded.last_check_utc, original.last_check_utc)
            self.assertEqual(len(reloaded.products), 2)
            self.assertEqual(reloaded.products["sake09:9262"].price_jpy, 16980)
            self.assertEqual(reloaded.products["sake09:14655"].stock_status, "available")

    def test_save_produces_utf8_korean_readable(self) -> None:
        """ensure_ascii=False로 한글이 그대로 저장되어야 함 (git diff 가독성)."""
        product = _sample_product()
        state = State(products={product.product_key: product})
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "state.json"
            save_state(path, state)
            raw = path.read_text(encoding="utf-8")
            self.assertIn("테스트 상품", raw)
            self.assertIn("거북이 720", raw)


class TestNowUtcIso(unittest.TestCase):
    def test_includes_offset(self) -> None:
        s = now_utc_iso()
        # +00:00 timezone offset이 포함되어야 함
        self.assertTrue(s.endswith("+00:00") or s.endswith("Z"))


if __name__ == "__main__":
    unittest.main()
