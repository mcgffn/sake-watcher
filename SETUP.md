# 설정 가이드 (1회)

이 문서는 sake-watcher를 처음 배포하는 절차다. **약 30분 소요**.

## 진행 체크리스트

- [ ] **1.** GitHub repo 생성 (private)
- [ ] **2.** 파일 업로드 (sake-watcher 디렉토리 전체)
- [ ] **3.** Gmail 2단계 인증 활성화
- [ ] **4.** Gmail App Password 발급
- [ ] **5.** Repository Secrets 등록 (3~4개)
- [ ] **6.** ⚠️ Workflow 권한을 "Read and write"로 설정 (**가장 흔한 실수 지점**)
- [ ] **7.** 첫 dry-run 실행 → 파싱 확인
- [ ] **8.** 첫 실제 실행 → 이메일 도착 확인
- [ ] **9.** cron 자동 실행 확인 (1시간 대기)

---

## 1. GitHub repo 생성

1. https://github.com/new 접속
2. Repository name: `sake-watcher` (원하는 이름 가능)
3. **Visibility: Private** 강력 권장
   - 이유: state.json에 본인 관심 상품 목록과 가격 기록이 남는다. NOTIFY_TO 이메일 주소도 commit 메시지 author에 노출될 수 있다.
4. **README, .gitignore, license는 추가하지 않음** (이미 sake-watcher에 포함되어 있음)
5. **Create repository**

## 2. 파일 업로드

두 방법 중 편한 쪽 선택.

### 방법 A: git CLI (권장)

```bash
cd /path/to/sake-watcher
git init
git add .
git commit -m "initial commit"
git branch -M main
git remote add origin https://github.com/<USERNAME>/sake-watcher.git
git push -u origin main
```

### 방법 B: GitHub 웹 업로드

1. 빈 repo 페이지에서 "uploading an existing file" 클릭
2. sake-watcher 디렉토리의 **모든 파일과 폴더**를 드래그
3. **중요**: `.github/workflows/` 같은 숨김 디렉토리도 포함되어야 한다. macOS Finder는 기본적으로 숨김 디렉토리를 숨기므로, Cmd+Shift+. 로 표시한 후 드래그.
4. Commit changes

업로드 후 repo 메인 페이지에서 다음 파일들이 모두 보이는지 확인:
- `src/check.py`, `src/notify.py`, `src/parser.py`, `src/state.py`
- `.github/workflows/check.yml`, `.github/workflows/manage.yml`
- `scripts/manage_watchlist.py`
- `watchlist.json`, `state.json`, `requirements.txt`, `README.md`

## 3. Gmail 2단계 인증 활성화

이미 활성화되어 있으면 건너뛴다. App Password는 2단계 인증 없이는 생성 불가능하다.

1. https://myaccount.google.com/security 접속
2. "Google에 로그인하는 방법" 섹션 → **2단계 인증** 클릭
3. 안내에 따라 활성화 (휴대전화 인증)

## 4. Gmail App Password 발급

1. https://myaccount.google.com/apppasswords 접속  
   ⚠️ Google이 Security 페이지에서 이 메뉴 공개 링크를 제거했다. **위 URL로 직접 접근해야 한다**. Security 페이지에서 못 찾는다고 당황하지 말 것.
2. "앱 이름" 입력: `sake-watcher` (식별용, 아무거나 가능)
3. **만들기** 클릭
4. 16자 비밀번호가 표시된다. 예: `abcd efgh ijkl mnop`
5. **그대로 복사** (공백 있어도 무방 — notify.py가 자동 제거). 이 화면을 닫으면 다시 못 본다.

이 페이지가 안 보이면:
- 2단계 인증이 꺼져 있음 (단계 3 다시)
- 회사/학교 계정에서 관리자가 비활성화함 → 개인 Gmail 사용
- Advanced Protection Program 가입자 → App Password 사용 불가 (다른 SMTP 서비스 필요)

## 5. Repository Secrets 등록

GitHub repo 페이지에서:

1. **Settings** 탭 → 좌측 **Secrets and variables** → **Actions**
2. **New repository secret** 버튼으로 다음을 하나씩 등록:

| Name | Value | 필수 |
|---|---|---|
| `GMAIL_USER` | `you@gmail.com` (앱 패스워드를 발급받은 Gmail 주소) | ✓ |
| `GMAIL_APP_PASSWORD` | 단계 4에서 받은 16자 (공백 있어도 OK) | ✓ |
| `NOTIFY_TO` | 알림 받을 주소 (보통 GMAIL_USER와 동일) | ✓ |
| `GMAIL_FROM_NAME` | 발신자 표시명 (예: `사케 워처`) | 선택 |

각각 **Add secret** 클릭.

⚠️ Secrets는 한 번 등록하면 값을 다시 볼 수 없다 (마스킹). 이름만 보이고 값은 Update로 덮어쓸 수만 있다. App Password를 분실했으면 Google에서 새로 발급받아 갱신.

## 6. ⚠️ Workflow 권한 설정 (가장 흔한 실수 지점)

이걸 빠뜨리면 workflow는 실행되지만 state.json commit이 **403 Permission Denied** 로 실패한다.

1. Settings 탭 → 좌측 **Actions** → **General**
2. 아래쪽 **Workflow permissions** 섹션
3. **"Read and write permissions"** 라디오 선택
4. **"Allow GitHub Actions to create and approve pull requests"** 는 켜지 않아도 됨
5. **Save**

## 7. 첫 dry-run 실행 (이메일 미발송, 안전한 검증)

1. repo의 **Actions** 탭
2. 좌측에서 **Check sake09 stock** workflow 선택
3. 우측 **Run workflow** 드롭다운
4. **dry_run** 토글을 **true**로 설정
5. **Run workflow** 클릭

약 30초~1분 후 실행이 완료된다 (jitter 때문에 짧으면 5초, 길면 6분). 실행 클릭 → **Run stock check** 단계 로그 확인.

**정상 출력 예시:**
```
[jitter] sleeping 142.3s
[load] 2 active / 2 total queries
[load] state has 0 known products
[ok] 거북이 720: 4 products (4 sold_out, 0 available, 0 new alerts)
[ok] 우부스나 카바 4농: 0 products (0 sold_out, 0 available, 0 new alerts)
[notify-dryrun] 0 notification(s) would be sent:
[notify] no notifications to send
[dry-run] state.json NOT saved
```

상품 수가 0인 쿼리는 검색 결과가 없거나 검색어 자체가 sake09에 매칭이 안 되는 경우. 검색어를 sake09 사이트에서 직접 입력해보고 결과 비교.

**문제 시:**
- `[FATAL] missing required env vars`: 단계 5 secrets 누락 → 환경변수 이름 정확히 일치 확인
- `[ERR] ...: ConnectionError`: GitHub Actions에서 sake09 도달 실패 (드물지만 가능) → 재실행
- `[ERR] ...: ParseError`: sake09 HTML 변경 가능성 → 단계 8 트러블슈팅

## 8. 첫 실제 실행 (이메일 발송)

dry-run이 정상 작동했으면 실제 실행.

1. Actions → Check sake09 stock → Run workflow
2. **dry_run을 false (기본값)로 둠**
3. Run workflow

⚠️ **첫 실행 시 알림 폭주 가능성**

현재 watchlist에 있는 검색어들이 sake09에서 **이미 구매 가능한 상품**을 가지고 있다면, 그 상품들 전부에 대해 알림이 발송된다. 예시 watchlist 기준 "나베시마 키타시즈쿠 1.8"은 5개 available → **5통 도착**.

이게 거슬리면:
- 옵션 A: 이대로 두기. 현재 살 수 있는 상품을 한 번에 파악 가능. 두 번째 실행부터는 정상.
- 옵션 B: watchlist.json에서 모든 entry의 `active`를 `false`로 둔 채 첫 실행 → state는 비어 있는 상태로 유지 → 그 다음 watchlist를 다시 활성화. 이러면 이후 sold_out → available 전환만 알림.
- 옵션 C: `--seed` 모드 추가 (현재 미구현). 첫 실행만 state 채우고 알림은 스킵하는 모드. 원하면 알려달라.

**정상 작동 확인:**
- Run stock check 로그에 `[notify] sent=N failed=0`
- Gmail inbox에 메일 도착 (1~5분 내)
- repo 메인에 새 commit: `chore(state): scheduled check ...`
- state.json 클릭해보면 products가 기록되어 있음

## 9. cron 자동 실행 확인

1시간 대기 후 Actions 탭에서 자동 실행 확인.

- 첫 자동 실행은 push 후 다음 정각 17분에 잡힘
- GitHub Actions 큐 부하 시 최대 30분 지연 가능 (정상)
- workflow 한 번이라도 자동 실행되면 cron 활성화 완료

자동 실행이 24시간 지나도 안 보이면:
- repo Settings → Actions → General → "Actions permissions"이 "Allow all actions" 인지 확인
- workflow 파일이 default branch (main)에 있는지 확인

---

# 일상 운영

## 검색어 추가

### 방법 A: 파일 직접 편집 (모바일 가능)

1. repo 메인에서 `watchlist.json` 클릭
2. 우측 상단 연필 아이콘 (Edit this file)
3. JSON에 새 entry 추가:
   ```json
   {
     "query": "다사이 39",
     "label": "다사이 39 시리즈",
     "active": true,
     "note": ""
   }
   ```
4. 하단 **Commit changes**

다음 cron 실행부터 반영. JSON 문법 (특히 콤마) 주의.

### 방법 B: Manage Watchlist 폼

1. Actions 탭 → **Manage Watchlist** → Run workflow
2. action: `add`, query: `다사이 39`, label: (선택) 입력
3. Run workflow

30초 후 watchlist.json이 자동 갱신.

## 검색어 임시 중지

- 폼: Manage Watchlist → `toggle` → query 입력
- 파일: `"active": false` 로 변경

## 검색어 삭제

- 폼: Manage Watchlist → `remove` → query 입력
- 파일: 해당 entry 통째로 삭제

⚠️ 삭제하면 state에 있던 그 검색어 관련 product 추적도 같이 잃는다. 임시 보류만 원하면 toggle 사용.

## workflow 전체 중지

Actions 탭 → 좌측 Check sake09 stock → 우측 "..." 메뉴 → **Disable workflow**

다시 켤 때는 같은 메뉴 → Enable.

## 알림 도착 확인이 안 됨

순서대로 점검:

1. Actions 최근 실행 결과 (빨간 X 있나?) 확인
2. Run stock check 로그에 `sent=N` 표시되는지 확인
3. Gmail 스팸함 확인 (한국어 발신자명은 가끔 분류됨)
4. Gmail에서 발신자 주소 검색해서 도착했지만 다른 라벨로 들어갔는지 확인
5. 그래도 없으면 Gmail App Password 만료 가능성 (Google 비밀번호 변경 시 자동 폐기). 단계 4 다시.

---

# 트러블슈팅

## SMTP 535 Authentication Failed

가장 흔한 원인 순서:
1. App Password가 아닌 일반 Gmail 비밀번호를 등록함 → 단계 4 다시
2. App Password가 만료됨 (Google 비밀번호 변경 후 자동 폐기) → 새로 발급
3. `GMAIL_USER` 와 App Password 발급받은 계정이 다름 → 두 값 일치 확인

## 403 Resource not accessible by integration

state.json commit 단계에서 실패. 원인은 **Workflow permissions** (단계 6).

Settings → Actions → General → Workflow permissions → "Read and write" 선택했는지 재확인.

## SMTP Connection timeout

GitHub Actions 환경에서 smtp.gmail.com:587 도달 실패. 드물지만 발생 가능.

대체 옵션:
- port 465로 변경 (notify.py의 `SMTP_PORT = 587` 을 `465`로, `starttls()` 호출 제거, `SMTP_SSL` 사용)
- SendGrid Free (월 100통, API 기반이라 SMTP 차단과 무관) 등으로 전환

## ParseError로 workflow 실패

sake09 HTML 구조 변경 가능성. GitHub이 자동으로 등록 이메일에 워크플로 실패 알림을 보낸다.

대응:
1. tests/fixtures의 HTML과 sake09 현재 응답 비교
2. 새 HAR 캡처 후 fixture 갱신 + parser.py 조정
3. tests/test_parser.py 실행해 회귀 없는지 확인

## 검색 결과 0개로 계속 잡힘

가능성:
- sake09 검색에 그 검색어 자체가 매칭 안 됨 → sake09 사이트에서 직접 입력해보고 확인
- 검색어 정규화 (앞뒤 공백 제거, 연속 공백 1개로) 차이 → manage_watchlist.py로 다시 추가
- IP 차단 일시 발생 → 다음 cron까지 대기

## state.json이 거대해짐

검색어를 자주 바꿔서 누적된 product가 많아진 경우. 우려 수준이 아니라면 무시 가능.

정리하려면:
- 로컬에서 state.json을 `{"schema_version": 1, "last_check_utc": null, "products": {}}` 로 초기화 후 commit
- 다음 실행에서 현재 결과로 다시 채워짐
- ⚠️ 부작용: 이미 구매 가능한 상품이 "신규"로 다시 잡혀 알림 발송

---

# 알아두면 좋은 운영 사실

- **GitHub Actions cron 정확도**: 정각 17분에 시작하지만 부하 시 최대 ~30분 지연. 5분 jitter 내부 적용까지 합쳐 효과적 간격은 55~95분.
- **60일 무활동 자동 비활성화**: scheduled workflow는 repo 활동 없으면 자동 disable. 우리는 매 실행마다 state.json commit하므로 무관.
- **Gmail 일 500통 한도**: 이 봇이 도달할 가능성 거의 없음. 도달했다면 parser가 깨져서 모든 상품이 "신규"로 잡히는 버그일 가능성 높음.
- **GitHub Free Actions 분 한도**: private repo는 월 2000분, 우리는 월 ~300분 사용. Public repo는 무제한.
- **state.json git history**: 매 실행마다 commit이라 1년이면 ~8800 commit. 무겁다고 느껴지면 주기적으로 `git filter-branch` 로 정리 가능 (운영 후 1년 시점에 결정).
