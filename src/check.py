"""sake-watcher 메인 진입점.

흐름:
  1. (선택) random jitter sleep
  2. watchlist.json + state.json 로드
  3. 각 active 쿼리에 대해:
       - canonical URL 빌드
       - HTML fetch (timeout, custom UA)
       - parse_search_results
       - state와 비교하여 알림 후보 산출
  4. 알림 발송 (단계 4에서 실제 SMTP 구현; 지금은 stdout 출력)
  5. state.json 갱신 후 저장

설계 원칙:
- 의사결정 로직(`decide_notifications`)은 순수 함수. HTTP/디스크 I/O 격리.
- 한 쿼리 실패가 전체 실행을 막지 않음. 모든 쿼리가 실패한 경우에만 exit 1.
- 시간 기반 dedup 없음. sold_out → available 전환이 유일한 알림 트리거.
  (희귀 사케 재입고 윈도우가 짧을 수 있어 cooldown이 알림을 놓치게 만든다.)

CLI:
  python -m src.check                  # 실제 실행
  python -m src.check --dry-run        # 알림은 출력만, 상태 저장 안 함
  python -m src.check --no-jitter      # jitter 생략 (테스트/디버깅용)
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import requests

from src.parser import ParseError, ParsedProduct, build_search_url, parse_search_results
from src.state import ProductState, State, load_state, now_utc_iso, save_state

# notify는 main()에서 lazy import — 테스트에서 notify를 import하지 않는 경로 보존
# (test_check.py가 check.py만 import해도 notify의 dependency를 끌고 오지 않음)

# ---- 설정 상수 -------------------------------------------------------------

USER_AGENT = (
    "sake-watcher/0.1 "
    "(personal low-frequency restock notifier; "
    "https://github.com/yourname/sake-watcher)"
)
ACCEPT_LANGUAGE = "ko-KR,ko;q=0.9,ja;q=0.8,en;q=0.7"
FETCH_TIMEOUT_SECONDS = 15
JITTER_MAX_SECONDS = 300  # 0~5분, 1시간 cron 기준

ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_WATCHLIST = ROOT_DIR / "watchlist.json"
DEFAULT_STATE = ROOT_DIR / "state.json"


# ---- 데이터 타입 -----------------------------------------------------------

@dataclass(frozen=True)
class WatchQuery:
    query: str
    label: str
    active: bool = True
    note: str = ""


@dataclass(frozen=True)
class NotificationEvent:
    """sold_out/신규 → available 전환을 표현하는 알림 후보."""

    query: WatchQuery
    product: ParsedProduct
    previous_status: Optional[str]  # None = 신규 발견


@dataclass
class CheckResult:
    """단일 쿼리 처리 결과 요약."""

    query_label: str
    success: bool
    error_message: Optional[str] = None
    product_count: int = 0
    sold_out_count: int = 0
    available_count: int = 0
    notifications: list[NotificationEvent] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.notifications is None:
            self.notifications = []


# ---- watchlist 로드 --------------------------------------------------------

def load_watchlist(path: Path) -> list[WatchQuery]:
    """watchlist.json 파싱. 'active': false인 항목은 제외하지 않고 그대로 반환.

    필터링은 호출자가 수행 (모든 쿼리 목록을 보고 싶을 수 있어서).
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    queries = []
    for item in data.get("queries", []):
        queries.append(
            WatchQuery(
                query=item["query"],
                label=item.get("label", item["query"]),
                active=bool(item.get("active", True)),
                note=item.get("note", ""),
            )
        )
    return queries


# ---- HTTP fetch ------------------------------------------------------------

def fetch_html(url: str, session: Optional[requests.Session] = None) -> str:
    """sake09 검색 결과 페이지 fetch. UTF-8 강제."""
    s = session or requests.Session()
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": ACCEPT_LANGUAGE,
    }
    resp = s.get(url, headers=headers, timeout=FETCH_TIMEOUT_SECONDS)
    resp.raise_for_status()
    # sake09는 Content-Type에 charset=UTF-8을 보내지만 명시적으로 강제
    resp.encoding = "utf-8"
    return resp.text


# ---- 알림 의사결정 (순수 함수, 테스트 용이) -------------------------------

def decide_notifications(
    query: WatchQuery,
    parsed_products: list[ParsedProduct],
    state: State,
    now_iso: str,
) -> list[NotificationEvent]:
    """현재 파싱 결과와 직전 state를 비교해 알림 대상 산출.

    부수효과 있음: state.products를 in-place로 업데이트.
    (트랜잭션을 분리하면 코드가 복잡해지고 이득이 적음. main에서 state를
    save하기 전 dry-run 체크가 있어 안전.)

    알림 조건:
      - product_key가 state에 없고 현재 status == "available"  → 신규+이용가능
      - product_key가 state에 있고 이전 sold_out → 현재 available → 재입고

    알림 미발생:
      - 현재 status == "sold_out" (어떤 케이스든)
      - available → available 유지
      - 신규 발견인데 sold_out (관찰만)
    """
    notifications: list[NotificationEvent] = []

    for product in parsed_products:
        prev = state.products.get(product.product_key)

        if prev is None:
            # 신규 발견
            new_record = ProductState(
                product_key=product.product_key,
                name=product.name,
                detail_url=product.detail_url,
                image_url=product.image_url,
                price_jpy=product.price_jpy,
                stock_status=product.stock_status,
                first_seen_utc=now_iso,
                last_seen_utc=now_iso,
                last_status_change_utc=now_iso,
                last_notified_utc=None,
                discovered_via_query=query.query,
            )
            if product.stock_status == "available":
                notifications.append(
                    NotificationEvent(query=query, product=product, previous_status=None)
                )
                new_record.last_notified_utc = now_iso
            state.products[product.product_key] = new_record
        else:
            # 기존 상품: 메타데이터 갱신 + 상태 전환 검사
            prev.name = product.name  # 상품명/가격이 미세하게 바뀔 수 있음
            prev.detail_url = product.detail_url
            prev.image_url = product.image_url
            prev.price_jpy = product.price_jpy
            prev.last_seen_utc = now_iso

            previous_status = prev.stock_status
            if previous_status != product.stock_status:
                prev.last_status_change_utc = now_iso
                prev.stock_status = product.stock_status

            if previous_status == "sold_out" and product.stock_status == "available":
                notifications.append(
                    NotificationEvent(
                        query=query, product=product, previous_status="sold_out"
                    )
                )
                prev.last_notified_utc = now_iso

    return notifications


# ---- 단일 쿼리 처리 --------------------------------------------------------

def process_query(
    query: WatchQuery,
    state: State,
    now_iso: str,
    session: Optional[requests.Session] = None,
) -> CheckResult:
    """한 쿼리에 대해 fetch + parse + decide 전체 수행. 예외는 잡아서 결과에 담음."""
    try:
        url = build_search_url(query.query)
        html = fetch_html(url, session=session)
        products = parse_search_results(html)
        notifications = decide_notifications(query, products, state, now_iso)
        return CheckResult(
            query_label=query.label,
            success=True,
            product_count=len(products),
            sold_out_count=sum(1 for p in products if p.stock_status == "sold_out"),
            available_count=sum(1 for p in products if p.stock_status == "available"),
            notifications=notifications,
        )
    except (requests.RequestException, ParseError, ValueError) as e:
        return CheckResult(
            query_label=query.label,
            success=False,
            error_message=f"{type(e).__name__}: {e}",
        )


# ---- 알림 출력 (단계 4 이전 placeholder) ----------------------------------

def render_notification_text(event: NotificationEvent) -> str:
    """단계 4에서 SMTP 본문으로 재사용될 형식."""
    prev = event.previous_status or "신규 발견"
    return (
        f"[{event.query.label}]\n"
        f"  상품명: {event.product.name}\n"
        f"  가격: {event.product.price_jpy:,} JPY\n"
        f"  상태: {prev} → {event.product.stock_status}\n"
        f"  상세: {event.product.detail_url}\n"
        f"  이미지: {event.product.image_url}\n"
        f"  product_key: {event.product.product_key}"
    )


def emit_notifications(
    events: list[NotificationEvent],
    dry_run: bool,
) -> tuple[int, int]:
    """알림 발송. dry_run=True면 stdout 출력만, False면 실제 Gmail SMTP 전송.

    반환: (sent_count, failed_count). dry_run에서는 (0, 0).
    """
    if not events:
        print("[notify] no notifications to send")
        return (0, 0)

    if dry_run:
        print(f"[notify-dryrun] {len(events)} notification(s) would be sent:")
        for e in events:
            print("---")
            print(render_notification_text(e))
        return (0, 0)

    # lazy import — Gmail 설정이 필요 없는 dry-run에서는 notify 모듈을 건드리지 않음
    from src.notify import GmailConfig, send_notifications

    config = GmailConfig.from_env()  # 누락 시 NotifyConfigError → main에서 처리
    result = send_notifications(events, config)
    print(f"[notify] sent={result.sent} failed={result.failed}")
    for err in result.errors:
        print(f"  notify-error: {err}", file=sys.stderr)
    return (result.sent, result.failed)


# ---- main ------------------------------------------------------------------

def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="sake09 restock checker")
    p.add_argument("--dry-run", action="store_true", help="상태 저장과 알림 발송 생략")
    p.add_argument("--no-jitter", action="store_true", help="random sleep 생략")
    p.add_argument("--watchlist", type=Path, default=DEFAULT_WATCHLIST)
    p.add_argument("--state", type=Path, default=DEFAULT_STATE)
    return p.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)

    # Fail fast: 실제 실행에서 Gmail 자격증명 누락이면 fetch도 하지 않고 즉시 종료.
    # workflow exit 1 → GitHub 자동 이메일 (실패 사실 통보).
    if not args.dry_run:
        from src.notify import GmailConfig, NotifyConfigError
        try:
            GmailConfig.from_env()
        except NotifyConfigError as e:
            print(f"[FATAL] {e}", file=sys.stderr)
            print(
                "[hint] Set GMAIL_USER, GMAIL_APP_PASSWORD, NOTIFY_TO secrets in repo, "
                "or use --dry-run for offline testing.",
                file=sys.stderr,
            )
            return 1

    if not args.no_jitter:
        delay = random.uniform(0, JITTER_MAX_SECONDS)
        print(f"[jitter] sleeping {delay:.1f}s")
        time.sleep(delay)

    queries = load_watchlist(args.watchlist)
    active_queries = [q for q in queries if q.active]
    print(
        f"[load] {len(active_queries)} active / {len(queries)} total queries"
    )

    state = load_state(args.state)
    print(f"[load] state has {len(state.products)} known products")

    now_iso = now_utc_iso()
    session = requests.Session()

    results: list[CheckResult] = []
    all_notifications: list[NotificationEvent] = []
    for q in active_queries:
        result = process_query(q, state, now_iso, session=session)
        results.append(result)
        if result.success:
            print(
                f"[ok] {q.label}: {result.product_count} products "
                f"({result.sold_out_count} sold_out, {result.available_count} available, "
                f"{len(result.notifications)} new alerts)"
            )
            all_notifications.extend(result.notifications)
        else:
            print(f"[ERR] {q.label}: {result.error_message}", file=sys.stderr)

    state.last_check_utc = now_iso

    sent, failed = emit_notifications(all_notifications, dry_run=args.dry_run)

    if args.dry_run:
        print("[dry-run] state.json NOT saved")
    else:
        save_state(args.state, state)
        print(f"[save] state.json updated ({len(state.products)} products tracked)")

    # 종료 코드 정책:
    #   - 모든 active 쿼리가 실패 → 1 (workflow 빨갛게 → GitHub 자동 알림)
    #   - 알림 전부 발송 실패 (1건 이상 있었는데 0건 성공) → 1
    #   - 그 외 → 0
    if active_queries and all(not r.success for r in results):
        print("[FATAL] all queries failed", file=sys.stderr)
        return 1
    if all_notifications and not args.dry_run and sent == 0 and failed > 0:
        print("[FATAL] all notification sends failed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
