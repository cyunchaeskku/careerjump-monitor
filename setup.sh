#!/bin/zsh
# CareerJump 모니터링 셋업 스크립트
# 사용법: zsh setup.sh

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLIST_NAME="com.yunchae.careerjump"
PLIST_DST="$HOME/Library/LaunchAgents/$PLIST_NAME.plist"
LOG_DIR="$HOME/Library/Logs/careerjump"

echo "======================================"
echo "  CareerJump 모니터링 셋업 시작"
echo "======================================"

# 1. Python 확인
PYTHON=$(which python3)
echo "[1/6] Python: $PYTHON"

# 2. 의존성 설치
echo "[2/6] 의존성 설치 중..."
pip3 install -r "./requirements.txt" --quiet
# python3 -m playwright install chromium
echo "      완료"

# 3. Slack Webhook URL 입력
echo ""
echo "[3/6] Slack Incoming Webhook URL을 입력하세요."
echo "      (Slack 앱 → 해당 채널 → Integrations → Add Webhook)"
read "SLACK_URL?      URL: "
if [[ -z "$SLACK_URL" ]]; then
    echo "      [ERROR] URL이 비어 있습니다. 종료."
    exit 1
fi

# 4. Google Calendar 인증 (선택)
echo ""
echo "[4/6] Google Calendar 연동 (선택사항)"
echo "      credentials.json 파일이 $SCRIPT_DIR 에 있으면 자동 연동됩니다."
if [[ -f "$SCRIPT_DIR/credentials.json" ]]; then
    echo "      credentials.json 발견 → 첫 실행 시 브라우저 인증창이 뜹니다."
    python3 "$SCRIPT_DIR/crawler.py" --auth-only 2>/dev/null || true
else
    echo "      credentials.json 없음 → Calendar 연동 건너뜀"
fi

# 5. plist 설정 및 등록
echo "[5/6] launchd 스케줄 등록 중..."
mkdir -p "$LOG_DIR"
mkdir -p "$HOME/Library/LaunchAgents"

# 플레이스홀더 치환
sed \
    -e "s|PYTHON_PATH_PLACEHOLDER|$PYTHON|g" \
    -e "s|SCRIPT_PATH_PLACEHOLDER|$SCRIPT_DIR/crawler.py|g" \
    -e "s|SLACK_WEBHOOK_PLACEHOLDER|$SLACK_URL|g" \
    -e "s|LOG_PATH_PLACEHOLDER|$LOG_DIR|g" \
    "$SCRIPT_DIR/com.yunchae.careerjump.plist" > "$PLIST_DST"

# 기존 job 언로드 후 재등록
launchctl unload "$PLIST_DST" 2>/dev/null || true
launchctl load "$PLIST_DST"
echo "      등록 완료: $PLIST_DST"

# 6. pmset: 매일 08:55 자동 wake (절전 모드 해제)
echo "[6/6] 절전 자동 해제 설정 (매일 08:55)..."
sudo pmset repeat wakeorpoweron MTWRFSU 08:55:00
echo "      완료 (sudo 필요)"

echo ""
echo "======================================"
echo "  셋업 완료!"
echo ""
echo "  실행 시간  : 매일 오전 09:00"
echo "  Wake 시간  : 매일 오전 08:55"
echo "  로그 위치  : $LOG_DIR/"
echo "  대상 공고  : MBB (McKinsey/Bain/BCG) + 빅4 (PwC/EY/Deloitte/KPMG)"
echo ""
echo "  지금 바로 테스트 실행:"
echo "  SLACK_WEBHOOK_URL='$SLACK_URL' python3 $SCRIPT_DIR/crawler.py"
echo "======================================"
