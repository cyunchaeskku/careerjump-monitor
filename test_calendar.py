import pickle
from pathlib import Path
from googleapiclient.discovery import build

TOKEN_FILE = Path(__file__).parent / "token.pickle"

with open(TOKEN_FILE, "rb") as f:
    creds = pickle.load(f)

service = build("calendar", "v3", credentials=creds)

event = {
    "summary": "[테스트] 캘린더 연동 확인",
    "description": "crawler.py 캘린더 연동 테스트",
    "start": {"dateTime": "2026-06-21T23:59:00+09:00"},
    "end":   {"dateTime": "2026-06-21T23:59:00+09:00"},
}

result = service.events().insert(calendarId="primary", body=event).execute()
print("등록 완료:", result.get("htmlLink"))
