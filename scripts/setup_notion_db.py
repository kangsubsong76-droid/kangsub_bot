# -*- coding: utf-8 -*-
"""
Notion DB 자동 생성 스크립트
실행: python scripts/setup_notion_db.py

실행 전 .env에 NOTION_TOKEN 설정 필요
생성된 DB ID를 .env의 NOTION_DB_* 항목에 채워넣으세요
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from notion_client import Client
from config.settings import NOTION_TOKEN

client = Client(auth=NOTION_TOKEN)

# ── 부모 페이지 찾기 ──
print("Notion 페이지 목록 검색...")
results = client.search(
    query="KangSub Bot",
    filter={"value": "page", "property": "object"}
).get("results", [])
if not results:
    print("'KangSub Bot' 페이지가 없습니다. Notion에서 먼저 만들어주세요.")
    sys.exit(1)

parent_id = results[0]["id"]
print(f"부모 페이지 발견: {parent_id}")


def create_db(title: str, properties: dict) -> str:
    db = client.databases.create(
        parent={"type": "page_id", "page_id": parent_id},
        title=[{"type": "text", "text": {"content": title}}],
        properties=properties,
    )
    db_id = db["id"]
    print(f"  OK [{title}] -> {db_id}")
    return db_id


# ── 1. Trade Journal ──
trades_id = create_db("Trade Journal", {
    "Name":       {"title": {}},
    "Code":       {"rich_text": {}},
    "Side":       {"select": {"options": [
        {"name": "BUY",      "color": "green"},
        {"name": "SELL",     "color": "red"},
        {"name": "STOP",     "color": "orange"},
    ]}},
    "Qty":        {"number": {"format": "number"}},
    "OrderPrice": {"number": {"format": "number"}},
    "FillPrice":  {"number": {"format": "number"}},
    "Amount":     {"number": {"format": "number"}},
    "PnlPct":     {"number": {"format": "percent"}},
    "Trigger":    {"select": {"options": [
        {"name": "Signal",     "color": "blue"},
        {"name": "StopLoss",   "color": "red"},
        {"name": "Rebalance",  "color": "yellow"},
        {"name": "Manual",     "color": "gray"},
    ]}},
    "Date":       {"date": {}},
    "Note":       {"rich_text": {}},
})

# ── 2. Portfolio Snapshot ──
portfolio_id = create_db("Portfolio Snapshot", {
    "Date":        {"title": {}},
    "TotalValue":  {"number": {"format": "number"}},
    "TotalPnl":    {"number": {"format": "percent"}},
    "DailyPnl":    {"number": {"format": "percent"}},
    "Cash":        {"number": {"format": "number"}},
    "GeneralPct":  {"number": {"format": "percent"}},
    "DividendPct": {"number": {"format": "percent"}},
})

# ── 3. Signal Log ──
signals_id = create_db("Signal Log", {
    "Name":      {"title": {}},
    "Action":    {"select": {"options": [
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

# ── 4. News Analysis ──
news_id = create_db("News Analysis", {
    "Title":      {"title": {}},
    "Source":     {"select": {"options": [
        {"name": "Hani",     "color": "green"},
        {"name": "Khan",     "color": "blue"},
        {"name": "Hankook",  "color": "orange"},
        {"name": "MBC",      "color": "purple"},
        {"name": "JTBC",     "color": "red"},
        {"name": "Other",    "color": "gray"},
    ]}},
    "Sectors":    {"multi_select": {"options": [
        {"name": "AI_Semicon"}, {"name": "Defense"},
        {"name": "Energy"},     {"name": "Robot"},
        {"name": "Finance"},    {"name": "SME"},
    ]}},
    "Sentiment":  {"number": {"format": "number"}},
    "Summary":    {"rich_text": {}},
    "URL":        {"url": {}},
    "Date":       {"date": {}},
})

# ── 5. Daily Review ──
review_id = create_db("Daily Review", {
    "Date":        {"title": {}},
    "KospiChg":    {"number": {"format": "percent"}},
    "PortPnl":     {"number": {"format": "percent"}},
    "TotalValue":  {"number": {"format": "number"}},
    "Bought":      {"rich_text": {}},
    "Sold":        {"rich_text": {}},
    "KeyIssue":    {"rich_text": {}},
    "NextPlan":    {"rich_text": {}},
    "Sentiment":   {"select": {"options": [
        {"name": "Bullish",   "color": "green"},
        {"name": "Bearish",   "color": "red"},
        {"name": "Neutral",   "color": "gray"},
        {"name": "Volatile",  "color": "orange"},
    ]}},
})

# ── 결과 출력 ──
print("\n" + "=" * 55)
print("Notion DB 생성 완료! .env 에 아래 값을 추가하세요:")
print("=" * 55)
print(f"NOTION_DB_TRADES={trades_id}")
print(f"NOTION_DB_PORTFOLIO={portfolio_id}")
print(f"NOTION_DB_SIGNALS={signals_id}")
print(f"NOTION_DB_NEWS={news_id}")
print(f"NOTION_DB_REVIEW={review_id}")
