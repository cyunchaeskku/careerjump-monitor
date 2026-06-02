# CareerJump 컨설팅 공고 모니터링

MBB + 빅4 신규 공고를 매일 자동으로 Slack에 알려주는 스크립트.

## 구성

```
careerjump-monitor/
├── crawler.py                   # 메인 크롤러
├── setup.sh                     # 최초 1회 실행 (설치 + 스케줄 등록)
├── requirements.txt
├── seen_ids.json                 # 이미 알림 보낸 글 ID 기록 (자동 관리)
├── com.yunchae.careerjump.plist  # launchd 템플릿 (setup.sh가 자동 설정)
└── credentials.json             # (선택) Google Calendar OAuth 파일
```

## 설치 방법

### Step 1. 저장소 클론 또는 폴더 이동
```bash
cd ~/careerjump-monitor
```

### Step 2. Slack Webhook 준비
1. Slack 앱 → 알림 받을 채널 → **Integrations** → **Add an App**
2. **Incoming WebHooks** 추가 → Webhook URL 복사

### Step 3 (선택). Google Calendar 연동
1. [Google Cloud Console](https://console.cloud.google.com/) → 새 프로젝트
2. **Google Calendar API** 활성화
3. **OAuth 2.0 클라이언트 ID** 생성 (데스크탑 앱) → JSON 다운로드
4. 파일명을 `credentials.json`으로 바꿔서 이 폴더에 저장

### Step 4. 셋업 실행
```bash
bash setup.sh
```
- Slack Webhook URL 입력 요청
- Playwright Chromium 설치
- launchd 스케줄 등록 (매일 09:00)
- pmset 절전 해제 예약 (매일 08:55)

## 테스트 실행
```bash
SLACK_WEBHOOK_URL='https://hooks.slack.com/services/XXX' python3 crawler.py
```

## 로그 확인
```bash
tail -f ~/Library/Logs/careerjump/careerjump.log
```

## 모니터링 대상 키워드
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
