# -*- coding: utf-8 -*-
"""
Notion DB 설정 스크립트
- DB가 없으면 생성, 있으면 속성 추가(update)
실행: python scripts/setup_notion_db.py
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from notion_client import Client
from config.settings import NOTION_TOKEN, NOTION_DB_TRADES, NOTION_DB_PORTFOLIO, NOTION_DB_SIGNALS, NOTION_DB_NEWS

client = Client(auth=NOTION_TOKEN)

try:
    from config.settings import NOTION_DB_REVIEW
except Exception:
    NOTION_DB_REVIEW = ""


def add_properties(db_id: str, label: str, properties: dict):
    """기존 DB에 속성 추가 (update)"""
    try:
        client.databases.update(database_id=db_id, properties=properties)
        print(f"  OK [{label}] 속성 추가 완료")
        return db_id
    except Exception as e:
        print(f"  ERR [{label}]: {e}")
        return None


def create_db(parent_id: str, title: str, properties: dict) -> str:
    """새 DB 생성"""
    try:
        db = client.databases.create(
            parent={"type": "page_id", "page_id": parent_id},
            title=[{"type": "text", "text": {"content": title}}],
            properties=properties,
        )
        db_id = db["id"]
        print(f"  OK [{title}] 생성: {db_id}")
        return db_id
    except Exception as e:
        print(f"  ERR [{title}]: {e}")
        return None


# ── 속성 스키마 정의 (number format = "number" 만 사용) ──

TRADES_PROPS = {
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
}

PORTFOLIO_PROPS = {
    "TotalValue":  {"number": {"format": "number"}},
    "TotalPnl":    {"number": {"format": "number"}},
    "DailyPnl":    {"number": {"format": "number"}},
    "Cash":        {"number": {"format": "number"}},
    "GeneralPct":  {"number": {"format": "number"}},
    "DividendPct": {"number": {"format": "number"}},
}

SIGNALS_PROPS = {
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
}

NEWS_PROPS = {
    "Source":    {"select": {"options": [
                  {"name": "Hani",    "color": "green"},
                  {"name": "Khan",    "color": "blue"},
                  {"name": "Hankook", "color": "orange"},
                  {"name": "MBC",     "color": "purple"},
                  {"name": "JTBC",    "color": "red"},
                  {"name": "Other",   "color": "gray"},
                ]}},
    "Sectors":   {"multi_select": {"options": [
                  {"name": "AI_Semicon"}, {"name": "Defense"},
                  {"name": "Energy"},     {"name": "Robot"},
                  {"name": "Finance"},    {"name": "SME"},
                ]}},
    "Sentiment": {"number": {"format": "number"}},
    "Summary":   {"rich_text": {}},
    "URL":       {"url": {}},
    "Date":      {"date": {}},
}

REVIEW_PROPS = {
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
}

print("=" * 55)

# 기존 DB가 있으면 속성 추가, 없으면 생성
if NOTION_DB_TRADES:
    print(f"Trade Journal: {NOTION_DB_TRADES}")
    add_properties(NOTION_DB_TRADES, "Trade Journal", TRADES_PROPS)
    trades_id = NOTION_DB_TRADES
else:
    print("Notion 부모 페이지 검색...")
    results = client.search(query="KangSub Bot", filter={"value": "page", "property": "object"}).get("results", [])
    if not results:
        print("'KangSub Bot' 페이지를 먼저 만들어주세요.")
        sys.exit(1)
    pid = results[0]["id"]
    trades_id     = create_db(pid, "Trade Journal",     {"Name": {"title": {}}, **TRADES_PROPS})
    portfolio_id  = create_db(pid, "Portfolio Snapshot",{"Date": {"title": {}}, **PORTFOLIO_PROPS})
    signals_id    = create_db(pid, "Signal Log",        {"Name": {"title": {}}, **SIGNALS_PROPS})
    news_id       = create_db(pid, "News Analysis",     {"Title": {"title": {}}, **NEWS_PROPS})
    review_id     = create_db(pid, "Daily Review",      {"Date": {"title": {}}, **REVIEW_PROPS})
    print("\n.env 에 추가:")
    for k, v in [("NOTION_DB_TRADES", trades_id), ("NOTION_DB_PORTFOLIO", portfolio_id),
                 ("NOTION_DB_SIGNALS", signals_id), ("NOTION_DB_NEWS", news_id),
                 ("NOTION_DB_REVIEW", review_id)]:
        print(f"{k}={v}")
    sys.exit(0)

if NOTION_DB_PORTFOLIO:
    add_properties(NOTION_DB_PORTFOLIO, "Portfolio Snapshot", PORTFOLIO_PROPS)
if NOTION_DB_SIGNALS:
    add_properties(NOTION_DB_SIGNALS, "Signal Log", SIGNALS_PROPS)
if NOTION_DB_NEWS:
    add_properties(NOTION_DB_NEWS, "News Analysis", NEWS_PROPS)
if NOTION_DB_REVIEW:
    add_properties(NOTION_DB_REVIEW, "Daily Review", REVIEW_PROPS)

print("=" * 55)
print("완료! 테스트: python -c \"import sys;sys.path.insert(0,'.');from notification.notion_logger import NotionLogger;n=NotionLogger();print(n.log_trade({'name':'T','code':'0','side':'BUY','qty':1,'price':1,'amount':1,'trigger':'Manual'}))\"")
