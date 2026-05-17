"""Gmail SMTP 알림 발송 (App Password 인증).

외부 의존성 없음 — stdlib smtplib + email만.

환경변수:
  GMAIL_USER          - "you@gmail.com" (인증 + From 주소)
  GMAIL_APP_PASSWORD  - 16자 Gmail App Password (공백 있어도 자동 제거됨)
  NOTIFY_TO           - 수신자 이메일 (보통 GMAIL_USER와 동일)
  GMAIL_FROM_NAME     - (선택) From의 friendly name. 기본 "sake-watcher"

발송 정책:
  - 알림 1건 = 이메일 1통. 모바일 푸시에서 어떤 상품인지 즉시 식별 가능.
  - 단일 SMTP 연결로 batch 발송. connect/login 1회만.
  - 개별 발송 실패는 격리. 1통 실패가 나머지 발송을 막지 않음.
  - 연결/인증 자체가 실패하면 전체를 실패로 표시.
"""
from __future__ import annotations

import os
import smtplib
from dataclasses import dataclass, field
from email.message import EmailMessage
from email.utils import formataddr
from typing import Optional

from src.check import NotificationEvent

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587  # submission, STARTTLS
SMTP_TIMEOUT_SECONDS = 30


class NotifyConfigError(Exception):
    """필수 환경변수 누락 등 설정 단계 오류."""


@dataclass(frozen=True)
class GmailConfig:
    user: str
    app_password: str
    to: str
    from_name: str = "sake-watcher"

    @classmethod
    def from_env(cls) -> "GmailConfig":
        user = os.environ.get("GMAIL_USER", "").strip()
        # App Password는 Google이 "abcd efgh ijkl mnop" 형식으로 표시 → 공백 제거
        password = os.environ.get("GMAIL_APP_PASSWORD", "").strip().replace(" ", "")
        to = os.environ.get("NOTIFY_TO", "").strip()
        from_name = os.environ.get("GMAIL_FROM_NAME", "sake-watcher").strip()

        missing = []
        if not user:
            missing.append("GMAIL_USER")
        if not password:
            missing.append("GMAIL_APP_PASSWORD")
        if not to:
            missing.append("NOTIFY_TO")
        if missing:
            raise NotifyConfigError(
                f"missing required env vars: {', '.join(missing)}"
            )

        return cls(user=user, app_password=password, to=to, from_name=from_name)


@dataclass
class NotifyResult:
    sent: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)


# ---- 이메일 콘텐츠 빌드 ---------------------------------------------------

def build_subject(event: NotificationEvent) -> str:
    """모바일 푸시에서 한눈에 식별 가능하도록 짧고 구체적인 제목.

    형식: [사케 재입고] <label> / <상품명, 최대 30자> (<가격>엔)
    """
    name = event.product.name
    name_short = name if len(name) <= 30 else name[:29] + "…"
    return f"[사케 재입고] {event.query.label} / {name_short} ({event.product.price_jpy:,}엔)"


def build_plain_body(event: NotificationEvent) -> str:
    prev = event.previous_status or "신규 발견"
    return (
        f"[{event.query.label}] 재입고 감지\n"
        f"\n"
        f"{event.product.name}\n"
        f"{event.product.price_jpy:,}엔\n"
        f"상태: {prev} → 구매 가능\n"
        f"\n"
        f"→ {event.product.detail_url}\n"
        f"\n"
        f"이미지: {event.product.image_url}\n"
        f"product_key: {event.product.product_key}\n"
        f"\n"
        f"이 알림은 sake09 검색 결과 페이지의 상태 변화 감지에 기반합니다.\n"
        f"실제 구매 가능 여부는 접속 시점에 달라질 수 있습니다.\n"
    )


def build_html_body(event: NotificationEvent) -> str:
    prev = event.previous_status or "신규 발견"
    # 한국어 + 일본어 혼용 상품명을 그대로 표시. HTML 이스케이프 처리.
    from html import escape
    name_esc = escape(event.product.name)
    label_esc = escape(event.query.label)
    detail_url = escape(event.product.detail_url, quote=True)
    image_url = escape(event.product.image_url, quote=True)
    key_esc = escape(event.product.product_key)
    prev_esc = escape(prev)
    price_str = f"{event.product.price_jpy:,}엔"

    return f"""<!doctype html>
<html lang="ko">
<body style="margin:0;padding:16px;background:#f5f5f7;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;color:#222;">
  <div style="max-width:520px;margin:0 auto;background:#fff;border-radius:8px;padding:20px;box-shadow:0 1px 3px rgba(0,0,0,0.08);">
    <div style="font-size:12px;color:#888;margin-bottom:4px;">{label_esc}</div>
    <div style="font-size:18px;font-weight:600;margin-bottom:12px;">재입고 감지</div>
    <table cellpadding="0" cellspacing="0" border="0" style="width:100%;">
      <tr>
        <td style="width:140px;vertical-align:top;padding-right:14px;">
          <img src="{image_url}" alt="" style="width:130px;height:auto;border-radius:6px;display:block;" />
        </td>
        <td style="vertical-align:top;">
          <div style="font-size:14px;font-weight:600;line-height:1.4;margin-bottom:8px;">{name_esc}</div>
          <div style="font-size:20px;font-weight:700;color:#d63838;margin-bottom:10px;">{price_str}</div>
          <div style="font-size:12px;color:#666;">상태: {prev_esc} → <strong style="color:#0a7b3e;">구매 가능</strong></div>
        </td>
      </tr>
    </table>
    <div style="margin-top:18px;">
      <a href="{detail_url}" style="display:inline-block;padding:11px 20px;background:#0066cc;color:#fff;text-decoration:none;border-radius:6px;font-weight:600;font-size:14px;">sake09에서 보기 →</a>
    </div>
    <hr style="margin:20px 0;border:0;border-top:1px solid #eee;" />
    <div style="font-size:11px;color:#999;line-height:1.5;">
      product_key: <code>{key_esc}</code><br/>
      이 알림은 검색 결과 페이지의 상태 변화 감지에 기반합니다. 실제 구매 가능 여부는 접속 시점에 달라질 수 있습니다.
    </div>
  </div>
</body>
</html>
"""


def build_email(event: NotificationEvent, config: GmailConfig) -> EmailMessage:
    """단일 알림에 대한 multipart/alternative 이메일 메시지 생성."""
    msg = EmailMessage()
    msg["Subject"] = build_subject(event)
    msg["From"] = formataddr((config.from_name, config.user))
    msg["To"] = config.to
    # plain text를 먼저 set_content로, HTML을 add_alternative로 — 표준 multipart 순서
    msg.set_content(build_plain_body(event))
    msg.add_alternative(build_html_body(event), subtype="html")
    return msg


# ---- SMTP 발송 ------------------------------------------------------------

def send_notifications(
    events: list[NotificationEvent],
    config: GmailConfig,
) -> NotifyResult:
    """단일 SMTP 연결로 N통 batch 발송. 개별 실패 격리."""
    result = NotifyResult()
    if not events:
        return result

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=SMTP_TIMEOUT_SECONDS) as smtp:
            smtp.starttls()
            smtp.login(config.user, config.app_password)

            for event in events:
                try:
                    msg = build_email(event, config)
                    smtp.send_message(msg)
                    result.sent += 1
                except smtplib.SMTPException as e:
                    result.failed += 1
                    result.errors.append(
                        f"{event.product.product_key}: {type(e).__name__}: {e}"
                    )
                except Exception as e:
                    # 예: 이메일 빌드 중 인코딩 오류 등
                    result.failed += 1
                    result.errors.append(
                        f"{event.product.product_key}: build/send error: "
                        f"{type(e).__name__}: {e}"
                    )

    except (smtplib.SMTPException, OSError) as e:
        # connect / starttls / login 자체가 실패한 경우 — 나머지 전부 실패 처리
        remaining = len(events) - (result.sent + result.failed)
        result.failed += remaining
        result.errors.append(
            f"SMTP connection or authentication failed: "
            f"{type(e).__name__}: {e} (failed to deliver {remaining} pending)"
        )

    return result
