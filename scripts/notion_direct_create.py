# -*- coding: utf-8 -*-
"""
Notion DB 직접 생성 — requests 라이브러리로 API 직접 호출
notion_client 라이브러리 버전 문제 우회
실행: python scripts/notion_direct_create.py
"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import requests
from config.settings import NOTION_TOKEN

HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}
BASE = "https://api.notion.com/v1"


def api(method, path, body=None):
    url = BASE + path
    resp = requests.request(method, url, headers=HEADERS, json=body, timeout=15)
    data = resp.json()
    if not resp.ok:
        raise RuntimeError(f"{resp.status_code} {data.get('message', data)}")
    return data


# ── 부모 페이지 찾기 ─────────────────────────────────────────────
print("KangSub Bot 페이지 검색...")
search = api("POST", "/search", {
    "query": "KangSub Bot",
    "filter": {"value": "page", "property": "object"},
})
pages = search.get("results", [])
if not pages:
    print("ERR: 'KangSub Bot' 페이지를 찾을 수 없습니다.")
    sys.exit(1)
pid = pages[0]["id"]
print(f"  부모 페이지 ID: {pid}\n")


def create_db(title: str, properties: dict) -> str:
    body = {
        "parent": {"type": "page_id", "page_id": pid},
        "title": [{"type": "text", "text": {"content": title}}],
        "properties": properties,
    }
    db = api("POST", "/databases", body)
    db_id = db["id"]
    # 즉시 검증
    verify = api("GET", f"/databases/{db_id}")
    props = list(verify.get("properties", {}).keys())
    print(f"  OK [{title}]")
    print(f"     id   = {db_id}")
    print(f"     속성 = {props}")
    return db_id


print("=" * 60)
print("DB 생성 (requests 직접 호출)")
print("=" * 60)

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

portfolio_id = create_db("Portfolio Snapshot", {
    "Date":        {"title": {}},
    "TotalValue":  {"number": {"format": "number"}},
    "TotalPnl":    {"number": {"format": "number"}},
    "DailyPnl":    {"number": {"format": "number"}},
    "Cash":        {"number": {"format": "number"}},
    "GeneralPct":  {"number": {"format": "number"}},
    "DividendPct": {"number": {"format": "number"}},
})

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

news_id = create_db("News Analysis", {
    "Title":      {"title": {}},
    "Source":     {"select": {"options": [
                   {"name": "Yonhap",  "color": "yellow"},
                   {"name": "Policy",  "color": "pink"},
                   {"name": "Naver",   "color": "green"},
                   {"name": "Hankook", "color": "orange"},
                   {"name": "Other",   "color": "gray"},
                 ]}},
    "Sectors":    {"multi_select": {"options": [
                   {"name": "AI_Semicon"}, {"name": "Defense"},
                   {"name": "Nuclear"},    {"name": "Power"},
                   {"name": "Robot"},      {"name": "Finance"},
                   {"name": "Bio"},        {"name": "Battery"},
                 ]}},
    "Sentiment":  {"number": {"format": "number"}},
    "Summary":    {"rich_text": {}},
    "URL":        {"url": {}},
    "IsPolicy":   {"checkbox": {}},
    "IsEarnings": {"checkbox": {}},
    "Date":       {"date": {}},
})

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
print("config/.env 에 아래 5줄을 붙여넣으세요:")
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
print("완료 후 테스트:")
print('python -c "import sys;sys.path.insert(0,\'.\');from notification.notion_logger import NotionLogger;n=NotionLogger();r=n.log_trade({\'name\':\'Test\',\'code\':\'000660\',\'side\':\'BUY\',\'qty\':1,\'price\':70000,\'amount\':70000,\'trigger\':\'Manual\'});print(\'OK:\',r[\'id\'] if r else \'FAIL\')"')
