# CareerJump 컨설팅 공고 모니터링

MBB + 빅4 신규 공고를 매일 자동으로 감지해 Slack 알림 + Google Calendar 일정 등록하는 스크립트.

## 기술 스택

| 역할 | 기술 |
|---|---|
| 크롤링 | Playwright (Chromium headless) |
| LLM 요약 + 마감일 추출 | OpenAI GPT-4o-mini |
| 알림 | Slack Incoming Webhook |
| 일정 등록 | Google Calendar API (OAuth 2.0) |
| 스케줄러 | macOS launchd (매일 09:00) |
| 환경변수 | python-dotenv (.env) |

## 동작 흐름

1. launchd가 매일 09:00 `crawler.py` 실행
2. CareerJump 게시판 크롤링 → MBB/빅4 키워드 필터링
3. `seen_ids.json`에 없는 신규 공고만 처리
4. 공고 본문 크롤링 → GPT-4o-mini로 요약 + 마감일 추출
5. Slack 알림 전송 (AI 요약 + 공고 전문 포함)
6. 마감일 있으면 Google Calendar에 일정 자동 등록

## 파일 구성

```
careerjump-monitor/
├── crawler.py                   # 메인 크롤러
├── setup.sh                     # 최초 1회 실행 (설치 + 스케줄 등록)
├── requirements.txt
├── .env                         # SLACK_WEBHOOK_URL, OPENAI_API_KEY
├── seen_ids.json                # 이미 알림 보낸 글 ID 기록 (자동 관리)
├── com.yunchae.careerjump.plist # launchd 템플릿 (setup.sh가 자동 설정)
├── credentials.json             # Google Calendar OAuth 클라이언트 파일
└── token.pickle                 # Google Calendar 인증 토큰 (자동 생성)
```

## 설치 방법

### Step 1. 저장소 클론 또는 폴더 이동
```bash
cd ~/careerjump-monitor
```

### Step 2. .env 파일 작성
```
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/XXX
OPENAI_API_KEY=sk-...
```

### Step 3 (선택). Google Calendar 연동
1. [Google Cloud Console](https://console.cloud.google.com/) → 새 프로젝트
2. **Google Calendar API** 활성화
3. **OAuth 2.0 클라이언트 ID** 생성 (데스크탑 앱) → JSON 다운로드
4. 파일명을 `credentials.json`으로 바꿔서 이 폴더에 저장
5. OAuth 동의 화면 → 대상 → **앱 게시** (Publishing status: Production으로 변경)

### Step 4. 셋업 실행
```bash
bash setup.sh
```
- Playwright Chromium 설치
- Slack Webhook URL 입력
- Google Calendar 브라우저 인증 (credentials.json 있을 때)
- launchd 스케줄 등록 (매일 09:00)
- pmset 절전 해제 예약 (매일 08:55)

## Slack 알림 구조

```
📢 새 컨설팅 공고 알림
제목: [MBB-Full time] ...
등록일: 2026-06-01
📅 마감일: 2026-06-30
링크: https://...

🤖 AI 요약
• 회사/직무: ...
• 주요 업무: ...
• 자격 요건: ...

📄 공고 전문
(본문 원문)
```

## 테스트 실행
```bash
python3 crawler.py
```

## 로그 확인
```bash
tail -f ~/Library/Logs/careerjump/careerjump.log
```

## 모니터링 대상

McKinsey, Bain, BCG, PwC, EY/EY한영, Deloitte/딜로이트, KPMG

## 스케줄 관리
```bash
# 일시 중지
launchctl unload ~/Library/LaunchAgents/com.yunchae.careerjump.plist

# 재개
launchctl load ~/Library/LaunchAgents/com.yunchae.careerjump.plist

# 절전 해제 예약 확인
pmset -g sched
```
