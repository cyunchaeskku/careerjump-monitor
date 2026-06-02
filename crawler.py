"""
CareerJump 취업공고 모니터링 크롤러
- MBB / 빅4 (PwC, EY, Deloitte, KPMG) 공고 필터링
- 새 글 감지 → Slack 알림 + Google Calendar 등록
"""

import os, json, re, pickle
from dotenv import load_dotenv
load_dotenv()
from openai import OpenAI
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

# ─── 설정 ───────────────────────────────────────────
BOARD_URL = "https://careerjump.co.kr/board/%EC%B7%A8%EC%97%85%EA%B3%B5%EA%B3%A0/articles"
BASE_URL  = "https://careerjump.co.kr"

# 이 스크립트 위치 기준으로 데이터 파일 저장
BASE_DIR      = Path(__file__).parent
SEEN_IDS_FILE = BASE_DIR / "seen_ids.json"
TOKEN_FILE    = BASE_DIR / "token.pickle"
CREDS_FILE    = BASE_DIR / "credentials.json"

TARGET_KEYWORDS = [
    "mckinsey", "맥킨지",
    "bain", "베인",
    "bcg",
    "pwc", "pw c",
    "ey한영", "ernst", "이와이",
    "deloitte", "딜로이트",
    "kpmg",
]

SCOPES = ["https://www.googleapis.com/auth/calendar"]

# ─── 유틸 ────────────────────────────────────────────
def load_seen_posts() -> dict:
    if SEEN_IDS_FILE.exists():
        data = json.loads(SEEN_IDS_FILE.read_text())
        # 구버전 list 형식 마이그레이션
        if isinstance(data, list):
            return {id_: {} for id_ in data}
        return data
    return {}

def save_seen_posts(posts: dict):
    SEEN_IDS_FILE.write_text(json.dumps(posts, ensure_ascii=False, indent=2))

def is_target(title: str) -> bool:
    t = title.lower().replace(" ", "")
    return any(kw.replace(" ", "") in t for kw in TARGET_KEYWORDS)

def extract_deadline(text: str) -> str | None:
    patterns = [
        r"모집\s*기간[^\n]*?[~～]\s*(\d{4}[./]\d{1,2}[./]\d{1,2})",
        r"지원\s*기간[^\n]*?[~～]\s*(\d{4}[./]\d{1,2}[./]\d{1,2})",
        r"마감[^\n]*?(\d{4}[./]\d{1,2}[./]\d{1,2})",
        r"(\d{4}[./]\d{1,2}[./]\d{1,2})\s*(?:까지|마감|채용\s*시\s*조기마감)",
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            raw = m.group(1).replace("/", "-").replace(".", "-")
            # YYYY-M-D → YYYY-MM-DD 정규화
            parts = raw.split("-")
            if len(parts) == 3:
                return f"{parts[0]}-{parts[1].zfill(2)}-{parts[2].zfill(2)}"
    return None

def summarize(text: str) -> str:
    """핵심 섹션만 추출"""
    key_headers = ["회사", "근무 기간", "근무기간", "내용", "주요 업무",
                   "자격 요건", "우대 사항", "근무 환경", "지원 방법", "모집 기간"]
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    result, capturing = [], False
    for line in lines:
        if any(kw in line for kw in key_headers):
            capturing = True
        if capturing:
            result.append(line)
        if len(result) > 50:
            break
    return "\n".join(result) if result else "\n".join(lines[:40])

def llm_analyze(text: str) -> dict:
    """LLM으로 공고 요약 + 마감일 추출. {"summary": str, "deadline": "YYYY-MM-DD" | None}"""
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        return {"summary": "", "deadline": None}
    try:
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        "당신은 컨설팅 채용 공고를 분석하는 어시스턴트입니다.\n"
                        "채용 공고 본문을 읽고 아래 JSON을 반환하세요:\n"
                        "{\n"
                        '  "summary": "• 회사/직무\\n• 주요 업무 (2~3줄)\\n• 자격 요건 (핵심만)\\n• 우대 사항 (핵심만) — 없는 항목 생략, 200자 이내",\n'
                        '  "deadline": "YYYY-MM-DD 형식 마감일, 없으면 null"\n'
                        "}\n"
                        "deadline은 지원 마감일만 추출하세요. 모집 기간 종료일, 서류 마감일 등 모두 포함."
                    ),
                },
                {"role": "user", "content": text[:4000]},
            ],
            max_tokens=500,
            temperature=0.1,
        )
        result = json.loads(response.choices[0].message.content)
        deadline = result.get("deadline")
        if deadline and not re.match(r"^\d{4}-\d{2}-\d{2}$", str(deadline)):
            deadline = None
        return {"summary": result.get("summary", ""), "deadline": deadline}
    except Exception as e:
        print(f"  [LLM] 분석 실패: {e}")
        return {"summary": "", "deadline": None}

# ─── Playwright 크롤링 ───────────────────────────────
def fetch_board(page) -> list[dict]:
    page.goto(BOARD_URL, wait_until="networkidle", timeout=30000)
    links = page.eval_on_selector_all(
        "a[href*='/articles/']",
        """els => els.map(el => {
            const row = el.closest('tr');
            const cells = row ? Array.from(row.querySelectorAll('td')) : [];
            const dateCell = cells.length >= 2 ? cells[cells.length - 2].textContent.trim() : '';
            return { href: el.href, text: el.textContent.trim(), date: dateCell };
        })"""
    )
    posts = []
    for l in links:
        m = re.search(r"/articles/(\d+)", l["href"])
        if m and l["text"]:
            posts.append({
                "id":    m.group(1),
                "title": l["text"],
                "url":   l["href"],
                "date":  l["date"],
            })
    return posts

FOOTER_CUTOFF_MARKERS = [
    "회사명 : 커리어점프",
    "Career Jump Corp.",
    "All rights reserved",
    "사업자 번호",
    "통신판매 등록번호",
]

def fetch_article(page, url: str) -> dict:
    page.goto(url, wait_until="networkidle", timeout=30000)
    # 본문 컨테이너 우선 시도
    for selector in [".board-view-content", ".article-content", ".view-content", ".post-content", "article", ".content"]:
        el = page.query_selector(selector)
        if el:
            body = el.inner_text()
            break
    else:
        body = page.inner_text("body")

    # footer 텍스트 잘라내기
    for marker in FOOTER_CUTOFF_MARKERS:
        idx = body.find(marker)
        if idx != -1:
            body = body[:idx].strip()
            break

    return {"body": body, "deadline": extract_deadline(body)}

# ─── Slack ───────────────────────────────────────────
def send_slack(webhook_url: str, post: dict, summary: str, deadline: str | None, llm_summary: str = ""):
    import urllib.request
    deadline_str = f"*📅 마감일:* `{deadline}`" if deadline else "*📅 마감일:* 글에서 직접 확인 필요"
    llm_section = f"\n*🤖 AI 요약*\n{llm_summary}\n" if llm_summary else ""
    text = (
        f":loudspeaker: *새 컨설팅 공고 알림*\n"
        f"*제목:* {post['title']}\n"
        f"*등록일:* {post['date']}\n"
        f"{deadline_str}\n"
        f"*링크:* {post['url']}\n"
        f"{llm_section}\n"
        f"*📄 공고 전문*\n```{summary[:1500]}```"
    )
    data = json.dumps({"text": text, "username": "CareerJump봇", "icon_emoji": ":briefcase:"}).encode()
    req = urllib.request.Request(webhook_url, data=data,
                                  headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=10)

def send_slack_reminder(webhook_url: str, active_posts: list[dict]):
    import urllib.request
    today = datetime.now().date()
    if active_posts:
        lines = []
        for p in active_posts:
            deadline = p.get("deadline")
            dl_str = f"`{deadline}`" if deadline else "마감일 미확인"
            lines.append(f"• <{p['url']}|{p['title']}> — {dl_str}")
        body = "\n".join(lines)
        text = (
            f":zzz: *오늘 신규 컨설팅 공고 없음*\n\n"
            f"*📋 마감 전 기존 공고 ({len(active_posts)}건)*\n{body}"
        )
    else:
        text = ":zzz: *오늘 신규 컨설팅 공고 없음*\n마감 전 기존 공고도 없습니다."
    data = json.dumps({"text": text, "username": "CareerJump봇", "icon_emoji": ":briefcase:"}).encode()
    req = urllib.request.Request(webhook_url, data=data,
                                  headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=10)

# ─── Google Calendar ─────────────────────────────────
def get_calendar_service():
    creds = None
    if TOKEN_FILE.exists():
        with open(TOKEN_FILE, "rb") as f:
            creds = pickle.load(f)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDS_FILE), SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "wb") as f:
            pickle.dump(creds, f)
    return build("calendar", "v3", credentials=creds)

def add_calendar_event(service, post: dict, deadline_str: str):
    try:
        dl = datetime.strptime(deadline_str, "%Y-%m-%d")
    except ValueError:
        print(f"  [Calendar] 날짜 파싱 실패: {deadline_str}")
        return
    if dl.date() < datetime.now().date():
        print(f"  [Calendar] 이미 지난 날짜 스킵: {deadline_str}")
        return
    event = {
        "summary":     f"[지원마감] {post['title']}",
        "description": f"공고 링크: {post['url']}",
        "start":       {"date": dl.strftime("%Y-%m-%d")},
        "end":         {"date": dl.strftime("%Y-%m-%d")},
        "reminders": {
            "useDefault": False,
            "overrides": [
                {"method": "email",  "minutes": 24 * 60},  # 1일 전
                {"method": "popup",  "minutes": 24 * 60},  # 1일 전
                {"method": "popup",  "minutes": 3  * 60},  # 당일 3시간 전
            ],
        },
    }
    result = service.events().insert(calendarId="primary", body=event).execute()
    print(f"  [Calendar] 일정 추가됨: {result.get('htmlLink')}")

# ─── 메인 ────────────────────────────────────────────
def main():
    slack_webhook = os.environ.get("SLACK_WEBHOOK_URL", "")
    if not slack_webhook:
        print("[ERROR] SLACK_WEBHOOK_URL 환경변수가 없습니다. ~/.zshrc 또는 ~/.bash_profile 확인.")
        return

    # Google Calendar: credentials.json 있으면 연동
    cal_service = None
    if CREDS_FILE.exists() or TOKEN_FILE.exists():
        try:
            cal_service = get_calendar_service()
        except Exception as e:
            print(f"[Calendar] 인증 실패 (계속 진행): {e}")

    seen_posts = load_seen_posts()
    today = datetime.now().date()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            locale="ko-KR",
            viewport={"width": 1280, "height": 800},
        )
        page = ctx.new_page()

        print(f"[{datetime.now():%Y-%m-%d %H:%M}] 게시판 크롤링 시작...")
        posts = fetch_board(page)
        print(f"  전체 게시글: {len(posts)}개")

        new_posts = [p for p in posts if p["id"] not in seen_posts and is_target(p["title"])]
        print(f"  신규 대상 공고: {len(new_posts)}개")

        if not new_posts:
            active = []
            for id_, meta in seen_posts.items():
                dl = meta.get("deadline")
                if not dl:
                    active.append(meta)
                else:
                    try:
                        if datetime.strptime(dl, "%Y-%m-%d").date() >= today:
                            active.append(meta)
                    except ValueError:
                        pass
            send_slack_reminder(slack_webhook, active)
            print(f"  → 새 공고 없음. 리마인더 전송 (마감 전 공고 {len(active)}건).")
            browser.close()
            return

        for post in new_posts:
            print(f"\n  [신규] {post['title']}")
            try:
                article  = fetch_article(page, post["url"])
                summary  = summarize(article["body"])
                llm      = llm_analyze(article["body"])
                deadline = article["deadline"] or llm["deadline"]

                send_slack(slack_webhook, post, summary, deadline, llm["summary"])
                print(f"  → Slack 전송 완료 | 마감: {deadline or '미확인'}")

                if cal_service and deadline:
                    add_calendar_event(cal_service, post, deadline)

                seen_posts[post["id"]] = {
                    "title":    post["title"],
                    "url":      post["url"],
                    "deadline": deadline,
                }
            except Exception as e:
                print(f"  → 오류: {e}")

        browser.close()

    save_seen_posts(seen_posts)
    print(f"\n완료: {len(new_posts)}개 처리됨.")

if __name__ == "__main__":
    main()
