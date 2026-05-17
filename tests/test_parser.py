"""parser.py 회귀 테스트.

HAR 두 케이스를 fixture로 박아 놓고, parser가 정확히 같은 결과를 돌려주는지 검증한다.
sake09 HTML 구조가 바뀌면 이 테스트가 깨진다 → 운영 중 parser 깨짐의 1차 방어선.

stdlib unittest만 사용 (pytest 의존 없음). 실행:
    python -m unittest discover tests
"""
from __future__ import annotations

import unittest
from pathlib import Path

from src.parser import (
    ParsedProduct,
    ParseError,
    build_search_url,
    parse_search_results,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SOLD_OUT_HTML = (FIXTURES_DIR / "sold_out_geobukgi_720.html").read_text(encoding="utf-8")
AVAILABLE_HTML = (FIXTURES_DIR / "available_nabeshima_kitashizuku_18.html").read_text(encoding="utf-8")


class TestBuildSearchUrl(unittest.TestCase):
    """검색어 → canonical URL 변환."""

    def test_single_keyword(self) -> None:
        url = build_search_url("거북이")
        self.assertEqual(
            url,
            "https://sake09.com/shop/products/list.php?name=%EA%B1%B0%EB%B6%81%EC%9D%B4",
        )

    def test_multi_keyword_with_space(self) -> None:
        """공백이 +로 인코딩되어야 함 (HAR과 동일 형식)."""
        url = build_search_url("거북이 720")
        self.assertEqual(
            url,
            "https://sake09.com/shop/products/list.php?name=%EA%B1%B0%EB%B6%81%EC%9D%B4+720",
        )

    def test_three_keywords(self) -> None:
        url = build_search_url("우부스나 카바 4농")
        self.assertEqual(
            url,
            "https://sake09.com/shop/products/list.php?name=%EC%9A%B0%EB%B6%80%EC%8A%A4%EB%82%98+%EC%B9%B4%EB%B0%94+4%EB%86%8D",
        )

    def test_keyword_with_decimal(self) -> None:
        url = build_search_url("나베시마 키타시즈쿠 1.8")
        self.assertIn("name=%EB%82%98%EB%B2%A0%EC%8B%9C%EB%A7%88+", url)
        self.assertTrue(url.endswith("1.8"))

    def test_collapses_consecutive_spaces(self) -> None:
        url = build_search_url("거북이   720")  # 3 spaces
        self.assertEqual(
            url,
            "https://sake09.com/shop/products/list.php?name=%EA%B1%B0%EB%B6%81%EC%9D%B4+720",
        )

    def test_strips_leading_trailing_whitespace(self) -> None:
        url = build_search_url("  거북이 720  ")
        self.assertEqual(
            url,
            "https://sake09.com/shop/products/list.php?name=%EA%B1%B0%EB%B6%81%EC%9D%B4+720",
        )

    def test_empty_raises(self) -> None:
        with self.assertRaises(ValueError):
            build_search_url("")

    def test_whitespace_only_raises(self) -> None:
        with self.assertRaises(ValueError):
            build_search_url("   ")


class TestParseSoldOutFixture(unittest.TestCase):
    """HAR 1: "거북이 720" 검색 결과. 4개 상품 전부 품절."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.products = parse_search_results(SOLD_OUT_HTML)
        cls.by_pid = {p.product_id: p for p in cls.products}

    def test_finds_exactly_four_products(self) -> None:
        self.assertEqual(len(self.products), 4)

    def test_expected_product_ids(self) -> None:
        self.assertEqual(
            sorted(p.product_id for p in self.products),
            ["2484", "4829", "9262", "9264"],
        )

    def test_all_sold_out(self) -> None:
        for p in self.products:
            with self.subTest(product_id=p.product_id):
                self.assertEqual(p.stock_status, "sold_out")

    def test_product_9262_full_fields(self) -> None:
        p = self.by_pid["9262"]
        self.assertEqual(p.product_key, "sake09:9262")
        self.assertEqual(p.name, "금거북이 신슈키레이 키 준마이다이긴죠 킨몬니시키(720ml) 信州亀齢 き 39 金紋錦")
        self.assertEqual(p.detail_url, "https://sake09.com/shop/products/detail.php?product_id=9262")
        self.assertEqual(p.image_url, "https://sake09.com/shop/upload/save_image/04110946_6434addaa9d37.jpg")
        self.assertEqual(p.price_jpy, 16980)
        self.assertEqual(p.stock_status, "sold_out")

    def test_product_2484_full_fields(self) -> None:
        p = self.by_pid["2484"]
        self.assertEqual(p.name, "은거북이 신슈키레이 키 준마이다이긴죠 미야마(720ml) 信州亀齢 き 純米大吟醸 美山")
        self.assertEqual(p.price_jpy, 16980)
        self.assertEqual(p.stock_status, "sold_out")

    def test_product_9264_lower_price_variant(self) -> None:
        """같은 상품명이지만 product_id와 가격이 다른 케이스: product_id 기준 분리 확인."""
        p = self.by_pid["9264"]
        self.assertEqual(p.price_jpy, 14980)
        self.assertEqual(p.product_key, "sake09:9264")

    def test_product_4829_full_fields(self) -> None:
        p = self.by_pid["4829"]
        self.assertEqual(p.price_jpy, 14980)
        self.assertEqual(p.stock_status, "sold_out")


class TestParseAvailableFixture(unittest.TestCase):
    """HAR 2: "나베시마 키타시즈쿠 1.8" 검색 결과. 5개 상품 전부 구매 가능."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.products = parse_search_results(AVAILABLE_HTML)
        cls.by_pid = {p.product_id: p for p in cls.products}

    def test_finds_exactly_five_products(self) -> None:
        self.assertEqual(len(self.products), 5)

    def test_expected_product_ids(self) -> None:
        self.assertEqual(
            sorted(p.product_id for p in self.products),
            ["1045", "14655", "5866", "5867", "970"],
        )

    def test_all_available(self) -> None:
        for p in self.products:
            with self.subTest(product_id=p.product_id):
                self.assertEqual(p.stock_status, "available")

    def test_product_14655_full_fields(self) -> None:
        p = self.by_pid["14655"]
        self.assertEqual(p.product_key, "sake09:14655")
        self.assertEqual(p.name, "나베시마 준마이다이긴죠 키타시즈쿠 생주 (1.8리터) 鍋島 純米大吟醸 きたしずく 生酒")
        self.assertEqual(p.detail_url, "https://sake09.com/shop/products/detail.php?product_id=14655")
        self.assertEqual(p.image_url, "https://sake09.com/shop/upload/save_image/12251211_5e02d36f74479.jpg")
        self.assertEqual(p.price_jpy, 18980)
        self.assertEqual(p.stock_status, "available")

    def test_price_range_spans_one_to_five_digit(self) -> None:
        """5,480 ~ 18,980 모두 정확히 파싱되는지 (쉼표 처리 회귀 방지)."""
        self.assertEqual(self.by_pid["5867"].price_jpy, 5480)
        self.assertEqual(self.by_pid["5866"].price_jpy, 8980)
        self.assertEqual(self.by_pid["1045"].price_jpy, 8680)
        self.assertEqual(self.by_pid["970"].price_jpy, 12980)
        self.assertEqual(self.by_pid["14655"].price_jpy, 18980)

    def test_no_form_contains_sold_out_keyword(self) -> None:
        """페이지 전체에 '장바구니'(2회) / 'cart'(6회)가 존재해도 영향 없어야 함."""
        for p in self.products:
            with self.subTest(product_id=p.product_id):
                self.assertEqual(p.stock_status, "available")


class TestParserRobustness(unittest.TestCase):
    """경계 조건 및 실패 케이스."""

    def test_empty_html_returns_empty_list(self) -> None:
        self.assertEqual(parse_search_results(""), [])

    def test_whitespace_only_html_returns_empty_list(self) -> None:
        self.assertEqual(parse_search_results("   \n\t  "), [])

    def test_html_with_no_product_forms_returns_empty(self) -> None:
        """form은 있지만 product_form*이 아닌 경우 — 검색 결과 0건."""
        html = "<html><body><form name='login'>...</form></body></html>"
        self.assertEqual(parse_search_results(html), [])

    def test_form_missing_h3_raises(self) -> None:
        html = """
        <form name="product_form9999" action="?">
          <div class="list_area clearfix"></div>
        </form>
        """
        with self.assertRaises(ParseError) as ctx:
            parse_search_results(html)
        self.assertIn("h3", str(ctx.exception).lower())

    def test_form_missing_price_span_raises(self) -> None:
        html = """
        <form name="product_form9999" action="?">
          <div class="list_area clearfix">
            <a href="/shop/products/detail.php?product_id=9999">
              <img src="/x.jpg" class="picture" />
            </a>
            <h3><a href="/shop/products/detail.php?product_id=9999">Test Product</a></h3>
          </div>
        </form>
        """
        with self.assertRaises(ParseError) as ctx:
            parse_search_results(html)
        self.assertIn("price02_default_9999", str(ctx.exception))

    def test_returns_frozen_dataclass(self) -> None:
        """ParsedProduct는 immutable이어야 함 (상태 추적 안정성)."""
        products = parse_search_results(SOLD_OUT_HTML)
        with self.assertRaises(Exception):
            products[0].stock_status = "available"  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
