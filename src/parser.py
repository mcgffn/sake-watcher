"""sake09.com 검색 결과 페이지 HTML parser.

이 모듈은 단일 책임을 갖는다:
- 검색 쿼리 문자열 → canonical search URL 생성
- 검색 결과 HTML → ParsedProduct 목록

설계 원칙:
- 상태값은 "sold_out" / "available" 두 가지뿐. unknown 없음.
- 필수 필드가 누락되면 ParseError를 던진다. silent fallback 금지.
- 외부에서 호출하는 메인 스크립트는 ParseError를 잡아 workflow를 실패시킴.
  workflow 실패 = GitHub가 자동으로 이메일 알림 = parser 깨짐 감지 무료.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import quote_plus, urljoin

from bs4 import BeautifulSoup, Tag

DEFAULT_BASE_URL = "https://sake09.com"

# product_form 요소의 name 속성 매칭 (e.g. "product_form9262")
_PRODUCT_FORM_NAME_RE = re.compile(r"^product_form(\d+)$")

# 가격 텍스트에서 첫 번째 정수(쉼표 포함) 추출
_PRICE_RE = re.compile(r"(\d{1,3}(?:,\d{3})*)")


class ParseError(Exception):
    """HTML이 예상 구조와 다를 때 발생.

    이 예외가 발생하면 호출자는 workflow를 실패 처리해야 한다.
    절대 silent하게 무시하거나 unknown 상태로 fallback하지 말 것.
    """


@dataclass(frozen=True)
class ParsedProduct:
    """파싱된 단일 상품 정보. 모든 필드 필수."""

    product_id: str         # sake09 내부 ID, e.g. "9262"
    product_key: str        # 시스템 전역 키, e.g. "sake09:9262"
    name: str               # 상품명 (한국어/일본어 혼용)
    detail_url: str         # 절대 URL
    image_url: str          # 절대 URL
    price_jpy: int          # 정수 엔화
    stock_status: str       # "sold_out" | "available"


def build_search_url(query: str, base_url: str = DEFAULT_BASE_URL) -> str:
    """검색 쿼리를 canonical search URL로 변환.

    예:
        "거북이 720" → https://sake09.com/shop/products/list.php?name=%EA%B1%B0%EB%B6%81%EC%9D%B4+720

    공백은 +로 인코딩된다 (sake09가 받는 형식). 연속 공백은 하나로 정리된다.
    """
    if not query or not query.strip():
        raise ValueError("query must not be empty")

    # 앞뒤 trim + 연속 공백을 단일 공백으로 정리
    cleaned = " ".join(query.split())
    encoded = quote_plus(cleaned)
    return f"{base_url}/shop/products/list.php?name={encoded}"


def parse_search_results(html: str, base_url: str = DEFAULT_BASE_URL) -> list[ParsedProduct]:
    """sake09 검색 결과 HTML → ParsedProduct 목록.

    검색 결과가 0건이면 빈 리스트를 반환한다 (정상 케이스).
    상품 form이 있는데 필수 필드가 누락되면 ParseError를 던진다.
    """
    if not html or not html.strip():
        return []

    soup = BeautifulSoup(html, "html.parser")
    forms = soup.find_all("form", attrs={"name": _PRODUCT_FORM_NAME_RE})

    return [_parse_form(form, base_url) for form in forms]


def _parse_form(form: Tag, base_url: str) -> ParsedProduct:
    """단일 <form name="product_formXXX"> 요소 파싱."""
    name_attr = form.get("name", "")
    m = _PRODUCT_FORM_NAME_RE.match(name_attr)
    if not m:
        # find_all 필터로 이미 정규식 매칭된 form만 들어오므로 정상이라면 도달 불가
        raise ParseError(f"form name does not match expected pattern: {name_attr!r}")
    product_id = m.group(1)

    name, detail_url = _extract_name_and_detail_url(form, product_id, base_url)
    image_url = _extract_image_url(form, product_id, base_url)
    price_jpy = _extract_price(form, product_id)
    stock_status = _detect_stock_status(form)

    return ParsedProduct(
        product_id=product_id,
        product_key=f"sake09:{product_id}",
        name=name,
        detail_url=detail_url,
        image_url=image_url,
        price_jpy=price_jpy,
        stock_status=stock_status,
    )


def _extract_name_and_detail_url(form: Tag, pid: str, base_url: str) -> tuple[str, str]:
    h3 = form.find("h3")
    if h3 is None:
        raise ParseError(f"missing <h3> in product_form{pid}")
    anchor = h3.find("a")
    if anchor is None:
        raise ParseError(f"missing <h3><a> in product_form{pid}")
    name = anchor.get_text(strip=True)
    if not name:
        raise ParseError(f"empty product name in product_form{pid}")
    href = anchor.get("href", "").strip()
    if not href:
        raise ParseError(f"missing detail href in product_form{pid}")
    return name, urljoin(base_url, href)


def _extract_image_url(form: Tag, pid: str, base_url: str) -> str:
    img = form.find("img", class_="picture")
    if img is None:
        raise ParseError(f"missing <img class='picture'> in product_form{pid}")
    src = img.get("src", "").strip()
    if not src:
        raise ParseError(f"empty image src in product_form{pid}")
    return urljoin(base_url, src)


def _extract_price(form: Tag, pid: str) -> int:
    span = form.find("span", id=f"price02_default_{pid}")
    if span is None:
        raise ParseError(f"missing price span price02_default_{pid}")
    text = span.get_text()
    m = _PRICE_RE.search(text)
    if not m:
        raise ParseError(f"no price number in {text!r} for product_form{pid}")
    return int(m.group(1).replace(",", ""))


def _detect_stock_status(form: Tag) -> str:
    """form 내부 텍스트에서 '품 절' 존재 여부로 상태 판정.

    공백/줄바꿈 변형에 강건하도록 모든 whitespace 제거 후 '품절'로 매칭한다.
    """
    text = form.get_text()
    normalized = re.sub(r"\s+", "", text)
    return "sold_out" if "품절" in normalized else "available"
