"""state.json read/write — 실행 간 유일한 상태 저장소.

설계 원칙:
- 모든 시각은 UTC ISO 8601 문자열로 저장. timezone-aware.
- product_key 기준으로 dict 보관. 순회 순서에 의존하지 않음.
- 스키마 변경 가능성에 대비해 schema_version 필드 유지.
- load_state는 파일이 없거나 비어 있을 때 빈 State를 반환 (첫 실행 안전).
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

SCHEMA_VERSION = 1


def now_utc_iso() -> str:
    """현재 UTC 시각을 ISO 8601 (offset 포함)로 반환."""
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ProductState:
    """state.json에 저장되는 단일 상품 레코드."""

    product_key: str
    name: str
    detail_url: str
    image_url: str
    price_jpy: int
    stock_status: str               # 마지막으로 본 상태
    first_seen_utc: str
    last_seen_utc: str
    last_status_change_utc: Optional[str] = None
    last_notified_utc: Optional[str] = None
    # 어느 쿼리에서 처음 발견되었는지 (디버깅용, 알림 로직에는 사용 안 함)
    discovered_via_query: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> "ProductState":
        return cls(
            product_key=d["product_key"],
            name=d["name"],
            detail_url=d["detail_url"],
            image_url=d["image_url"],
            price_jpy=int(d["price_jpy"]),
            stock_status=d["stock_status"],
            first_seen_utc=d["first_seen_utc"],
            last_seen_utc=d["last_seen_utc"],
            last_status_change_utc=d.get("last_status_change_utc"),
            last_notified_utc=d.get("last_notified_utc"),
            discovered_via_query=d.get("discovered_via_query", ""),
        )


@dataclass
class State:
    """state.json 전체 구조."""

    schema_version: int = SCHEMA_VERSION
    last_check_utc: Optional[str] = None
    products: dict[str, ProductState] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "last_check_utc": self.last_check_utc,
            "products": {k: asdict(v) for k, v in sorted(self.products.items())},
        }

    @classmethod
    def from_dict(cls, d: dict) -> "State":
        return cls(
            schema_version=int(d.get("schema_version", SCHEMA_VERSION)),
            last_check_utc=d.get("last_check_utc"),
            products={
                k: ProductState.from_dict(v) for k, v in d.get("products", {}).items()
            },
        )


def load_state(path: Path) -> State:
    """state.json을 읽어 State 반환. 파일 없거나 비어 있으면 빈 State."""
    if not path.exists() or path.stat().st_size == 0:
        return State()
    raw = path.read_text(encoding="utf-8")
    if not raw.strip():
        return State()
    data = json.loads(raw)
    state = State.from_dict(data)
    if state.schema_version != SCHEMA_VERSION:
        raise ValueError(
            f"unsupported state schema version: {state.schema_version} "
            f"(expected {SCHEMA_VERSION})"
        )
    return state


def save_state(path: Path, state: State) -> None:
    """State를 state.json으로 직렬화. UTF-8, 들여쓰기 2, 키 정렬."""
    text = json.dumps(state.to_dict(), ensure_ascii=False, indent=2, sort_keys=False)
    # 파일 끝에 항상 newline (git diff 깔끔)
    path.write_text(text + "\n", encoding="utf-8")
