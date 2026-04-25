# -*- coding: utf-8 -*-
"""
Notion DB 재생성 스크립트
- databases.update() 대신 databases.create() 한 번에 모든 속성 포함
- 기존 DB는 Notion에서 수동 삭제 필요 (API로는 삭제 불가)
- 실행 후 출력된 ID를 config/.env 에 붙여넣기

실행: python scripts/recreate_notion_dbs.py
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from notion_client import Client
from config.settings import NOTION_TOKEN

client = Client(auth=NOTION_TOKEN)

# ── 부모 페이지 찾기 ─────────────────────────────────────────────
print("KangSub Bot 페이지 검색...")
# filter 값을 "page" 로 수정 (API v2 호환)
results = client.search(
    query="KangSub Bot",
    filter={"value": "page", "property": "object"}
).get("results", [])

if not results:
    print("ERR: 'KangSub Bot' 페이지를 찾을 수 없습니다.")
    print("     Notion에서 페이지를 만들고 인테그레이션을 연결하세요.")
    sys.exit(1)

pid = results[0]["id"]
print(f"  부모 페이지: {pid}")
print()


def create_db(title: str, properties: dict) -> str:
    """DB 생성 — 속성 포함, 생성 직후 검증"""
    try:
        db = client.databases.create(
            parent={"type": "page_id", "page_id": pid},
            title=[{"type": "text", "text": {"content": title}}],
            properties=properties,
        )
        db_id = db["id"]
        # 생성 직후 속성 검증
        verify = client.databases.retrieve(database_id=db_id)
        props = list(verify.get("properties", {}).keys())
        print(f"  OK [{title}] id={db_id}")
        print(f"     속성 확인: {props}")
        return db_id
    except Exception as e:
        print(f"  ERR [{title}]: {e}")
        return ""


print("=" * 60)
print("DB 생성 시작 (모든 속성 포함)")
print("=" * 60)

# ── Trade Journal ──────────────────────────────────────────────
trades_id = create_db("Trade Journal", {
    "Name":       {"title": {}},
    "Code":       {"rich_text": {}},
    "Side":       {"select": {"options": [
                    {"name": "BUY",  "color": "green"},
                    {"name": "SELL", "color": "red"},
                    {"name": "STOP", "color": "orange"},
                  ]}},
    "Qty":        {"number": {"format": "number"}},
    "OrderPrice": {"number": {"format": "number"}},
    "FillPrice":  {"number": {"format": "number"}},
    "Amount":     {"number": {"format": "number"}},
    "PnlPct":     {"number": {"format": "number"}},
    "Trigger":    {"select": {"options": [
                    {"name": "Signal",    "color": "blue"},
                    {"name": "StopLoss",  "color": "red"},
                    {"name": "Rebalance", "color": "yellow"},
                    {"name": "Manual",    "color": "gray"},
                  ]}},
    "Date":       {"date": {}},
    "Note":       {"rich_text": {}},
})

# ── Portfolio Snapshot ──────────────────────────────────────────
portfolio_id = create_db("Portfolio Snapshot", {
    "Date":        {"title": {}},
    "TotalValue":  {"number": {"format": "number"}},
    "TotalPnl":    {"number": {"format": "number"}},
    "DailyPnl":    {"number": {"format": "number"}},
    "Cash":        {"number": {"format": "number"}},
    "GeneralPct":  {"number": {"format": "number"}},
    "DividendPct": {"number": {"format": "number"}},
})

# ── Signal Log ──────────────────────────────────────────────────
signals_id = create_db("Signal Log", {
    "Name":        {"title": {}},
    "Action":      {"select": {"options": [
                    {"name": "BUY",   "color": "green"},
                    {"name": "SELL",  "color": "red"},
                    {"name": "WATCH", "color": "yellow"},
                    {"name": "HOLD",  "color": "gray"},
                  ]}},
    "TechScore":   {"number": {"format": "number"}},
    "MarketScore": {"number": {"format": "number"}},
    "NewsScore":   {"number": {"format": "number"}},
    "TotalScore":  {"number": {"format": "number"}},
    "Executed":    {"checkbox": {}},
    "Date":        {"date": {}},
})

# ── News Analysis ───────────────────────────────────────────────
news_id = create_db("News Analysis", {
    "Title":     {"title": {}},
    "Source":    {"select": {"options": [
                  {"name": "Hani",    "color": "green"},
                  {"name": "Khan",    "color": "blue"},
                  {"name": "Hankook", "color": "orange"},
                  {"name": "MBC",     "color": "purple"},
                  {"name": "JTBC",    "color": "red"},
                  {"name": "Yonhap",  "color": "yellow"},
                  {"name": "Policy",  "color": "pink"},
                  {"name": "Other",   "color": "gray"},
                ]}},
    "Sectors":   {"multi_select": {"options": [
                  {"name": "AI_Semicon"}, {"name": "Defense"},
                  {"name": "Nuclear"},    {"name": "Power"},
                  {"name": "Robot"},      {"name": "Finance"},
                  {"name": "China"},      {"name": "Bio"},
                  {"name": "Battery"},    {"name": "Construction"},
                ]}},
    "Sentiment": {"number": {"format": "number"}},
    "Summary":   {"rich_text": {}},
    "URL":       {"url": {}},
    "IsPolicy":  {"checkbox": {}},
    "IsEarnings":{"checkbox": {}},
    "Date":      {"date": {}},
})

# ── Daily Review ────────────────────────────────────────────────
review_id = create_db("Daily Review", {
    "Date":       {"title": {}},
    "KospiChg":   {"number": {"format": "number"}},
    "PortPnl":    {"number": {"format": "number"}},
    "TotalValue": {"number": {"format": "number"}},
    "Bought":     {"rich_text": {}},
    "Sold":       {"rich_text": {}},
    "KeyIssue":   {"rich_text": {}},
    "NextPlan":   {"rich_text": {}},
    "Sentiment":  {"select": {"options": [
                  {"name": "Bullish",  "color": "green"},
                  {"name": "Bearish",  "color": "red"},
                  {"name": "Neutral",  "color": "gray"},
                  {"name": "Volatile", "color": "orange"},
                ]}},
})

print()
print("=" * 60)
print("config/.env 에 아래 내용을 복사하세요:")
print("=" * 60)
for k, v in [
    ("NOTION_DB_TRADES",    trades_id),
    ("NOTION_DB_PORTFOLIO", portfolio_id),
    ("NOTION_DB_SIGNALS",   signals_id),
    ("NOTION_DB_NEWS",      news_id),
    ("NOTION_DB_REVIEW",    review_id),
]:
    print(f"{k}={v}")

print()
print("=" * 60)
print("테스트 (위 ID 복사 후):")
print('python -c "import sys;sys.path.insert(0,\'.\');from notification.notion_logger import NotionLogger;n=NotionLogger();r=n.log_trade({\'name\':\'Test\',\'code\':\'000660\',\'side\':\'BUY\',\'qty\':1,\'price\':70000,\'amount\':70000,\'trigger\':\'Manual\'});print(\'OK\' if r else \'FAIL\')"')
