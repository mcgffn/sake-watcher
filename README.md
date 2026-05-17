# sake-watcher

sake09.com의 특정 검색어 결과를 주기적으로 확인하고, 상품이 **품절 → 구매 가능** 상태로 전환되면 Gmail로 알림을 보내는 개인용 봇.

> 처음 사용하는 경우 **[SETUP.md](./SETUP.md)** 부터 읽을 것. 약 30분 소요.

## 핵심 설계

- **GitHub Actions cron** 기반 (매시 17분 + 5분 jitter, 효과적 간격 약 60분)
- 외부 의존성: GitHub + Gmail SMTP 두 가지
- 검색어는 `watchlist.json` 한 파일에서 관리 (직접 편집 또는 Manage Watchlist workflow)
- 상태는 `state.json`으로 보관 (git history가 자동 audit log)
- HTML parser 깨짐 시 workflow가 실패 → GitHub가 등록 이메일로 자동 알림

## 디렉토리 구조

```
sake-watcher/
├── .github/workflows/
│   ├── check.yml          # 매시 17분 cron + 수동 실행 (dry-run 옵션)
│   └── manage.yml         # workflow_dispatch 폼으로 watchlist 관리
├── src/
│   ├── check.py           # 메인 진입점
│   ├── parser.py          # sake09 HTML parser (HAR 회귀 테스트 보호)
│   ├── notify.py          # Gmail SMTP 발송
│   └── state.py           # state.json 직렬화
├── scripts/
│   └── manage_watchlist.py  # CLI 도구, manage.yml이 호출
├── tests/
│   ├── fixtures/          # HAR에서 추출한 회귀 테스트 HTML
│   └── test_*.py          # 78개 테스트
├── watchlist.json         # 검색어 목록 (사용자 편집)
├── state.json             # 직전 상태 (자동 관리)
├── requirements.txt
├── README.md
└── SETUP.md               # 첫 설치 가이드
```

## 검색어 관리

### 방법 A: 직접 편집

GitHub 웹/모바일에서 `watchlist.json`을 열어 편집.

```json
{
  "query": "거북이 720",
  "label": "신슈키레이 거북이 720ml 시리즈",
  "active": true,
  "note": "선택 메모"
}
```

- `query`: sake09 검색창에 그대로 던지는 문자열. 공백으로 구분된 여러 키워드.
- `label`: 이메일 제목과 본문에 표시되는 이름.
- `active`: `false`로 두면 일시 중지 (삭제 대신 권장).
- `note`: 본인용 메모.

수정 후 commit → 다음 cron부터 반영.

### 방법 B: Manage Watchlist 폼

Actions 탭 → **Manage Watchlist** → Run workflow → action(add/remove/toggle) + query 입력. JSON 문법 몰라도 동작.

## 운영 주기 조정

`.github/workflows/check.yml`의 cron 표현식 변경.

| 표현식 | 효과 |
|---|---|
| `17 * * * *` | 매시 (기본) |
| `17 */2 * * *` | 2시간마다 |
| `17 */4 * * *` | 4시간마다 |

⚠️ **1시간보다 짧게 설정 비권장**. sake09 부담과 bot 의심 위험.

`src/check.py`의 `JITTER_MAX_SECONDS`도 함께 조정 가능 (기본 300초 = 5분).

## 로컬 테스트

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 단위 테스트
python -m unittest discover tests

# dry-run (이메일 미발송, state 미저장)
python -m src.check --dry-run --no-jitter
```

## 문제 해결

전체 트러블슈팅은 [SETUP.md](./SETUP.md) 하단 참조.

빠른 진단:

- **알림이 안 옴**: Actions 탭에서 최근 실행 결과 확인 → 빨간 X면 GitHub가 자동 이메일도 보냈을 것
- **403 push 실패**: Workflow permissions이 "Read and write"인지 확인
- **535 auth failed**: Gmail App Password 재발급 필요 (Google 비밀번호 변경 시 자동 폐기됨)

## 운영 통계

| 항목 | 값 |
|---|---|
| 코드 (src + scripts) | ~970줄 |
| 테스트 | 78개 / ~85ms |
| 외부 의존성 | requests, beautifulsoup4 |
| 월 GitHub Actions 사용 | ~300분 (free 한도 2000분) |
| 월 Gmail 발송 추정 | ~10건 (한도 15,000건/월) |
| 첫 배포 후 첫 알림까지 | ~1시간 |
