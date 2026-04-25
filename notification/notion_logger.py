# -*- coding: utf-8 -*-
"""Notion 데이터베이스 로거 — 영문 속성명 사용 (Windows 인코딩 안전)"""
from datetime import datetime
from notion_client import Client
from config.settings import (
    NOTION_TOKEN, NOTION_DB_TRADES, NOTION_DB_PORTFOLIO,
    NOTION_DB_SIGNALS, NOTION_DB_NEWS,
)
from utils.logger import setup_logger

log = setup_logger("notion_logger")

try:
    from config.settings import NOTION_DB_REVIEW
except ImportError:
    NOTION_DB_REVIEW = ""


class NotionLogger:
    def __init__(self, token: str = None):
        self.token = token or NOTION_TOKEN
        self.client = Client(auth=self.token) if self.token else None

    def _ok(self) -> bool:
        if not self.client:
            log.warning("Notion 토큰 미설정")
            return False
        return True

    def _create_page(self, db_id: str, properties: dict):
        if not self._ok() or not db_id:
            log.warning("Notion DB ID 미설정")
            return None
        try:
            return self.client.pages.create(
                parent={"database_id": db_id},
                properties=properties,
            )
        except Exception as e:
            log.error(f"Notion 기록 실패: {e}")
            return None

    # ── 매매일지 (Trade Journal) ──
    def log_trade(self, trade: dict):
        props = {
            "Name":       {"title": [{"text": {"content": trade.get("name", "")}}]},
            "Code":       {"rich_text": [{"text": {"content": trade.get("code", "")}}]},
            "Side":       {"select": {"name": trade.get("side", "BUY")}},
            "Qty":        {"number": trade.get("qty", 0)},
            "OrderPrice": {"number": trade.get("order_price", trade.get("price", 0))},
            "FillPrice":  {"number": trade.get("price", 0)},
            "Amount":     {"number": trade.get("amount", 0)},
            "Trigger":    {"select": {"name": trade.get("trigger", "Manual")}},
            "Date":       {"date": {"start": datetime.now().isoformat()}},
        }
        if trade.get("pnl_pct") is not None:
            props["PnlPct"] = {"number": round(float(trade["pnl_pct"]) / 100, 4)}
        if trade.get("reason"):
            props["Note"] = {"rich_text": [{"text": {"content": str(trade["reason"])[:2000]}}]}
        return self._create_page(NOTION_DB_TRADES, props)

    # ── 포트폴리오 스냅샷 (Portfolio Snapshot) ──
    def log_portfolio_snapshot(self, snapshot: dict):
        props = {
            "Date":        {"title": [{"text": {"content": datetime.now().strftime("%Y-%m-%d")}}]},
            "TotalValue":  {"number": snapshot.get("total_value", 0)},
            "TotalPnl":    {"number": round(snapshot.get("total_pnl", 0) / 100, 4)},
            "DailyPnl":    {"number": round(snapshot.get("daily_pnl", 0) / 100, 4)},
            "Cash":        {"number": snapshot.get("cash", 0)},
            "GeneralPct":  {"number": round(snapshot.get("general_ratio", 0) / 100, 4)},
            "DividendPct": {"number": round(snapshot.get("dividend_ratio", 0) / 100, 4)},
        }
        return self._create_page(NOTION_DB_PORTFOLIO, props)

    # ── 시그널 로그 (Signal Log) ──
    def log_signal(self, signal: dict):
        props = {
            "Name":        {"title": [{"text": {"content": signal.get("name", "")}}]},
            "Action":      {"select": {"name": signal.get("action", "HOLD")}},
            "TechScore":   {"number": signal.get("technical_score", 0)},
            "MarketScore": {"number": signal.get("market_score", 0)},
            "NewsScore":   {"number": signal.get("news_score", 0)},
            "TotalScore":  {"number": signal.get("weighted_score", signal.get("score", 0))},
            "Executed":    {"checkbox": signal.get("executed", False)},
            "Date":        {"date": {"start": datetime.now().isoformat()}},
        }
        return self._create_page(NOTION_DB_SIGNALS, props)

    # ── 뉴스 분석 (News Analysis) ──
    def log_news(self, news: dict):
        props = {
            "Title":     {"title": [{"text": {"content": str(news.get("title", ""))[:100]}}]},
            "Source":    {"select": {"name": news.get("source", "Other")}},
            "Sentiment": {"number": round(float(news.get("sentiment", 0)), 3)},
            "Summary":   {"rich_text": [{"text": {"content": str(news.get("summary", ""))[:2000]}}]},
            "URL":       {"url": news.get("url", "") or "https://notion.so"},
            "Date":      {"date": {"start": datetime.now().isoformat()}},
        }
        sectors = news.get("sectors", [])
        if sectors:
            sector_map = {
                "AI_반도체": "AI_Semicon", "K_방산": "Defense",
                "재생에너지": "Energy",    "피지컬AI_로봇": "Robot",
                "밸류업_금융": "Finance",  "중소_벤처": "SME",
            }
            props["Sectors"] = {"multi_select": [
                {"name": sector_map.get(s, s[:50])} for s in sectors
            ]}
        return self._create_page(NOTION_DB_NEWS, props)

    # ── 일일 리뷰 (Daily Review) ──
    def log_daily_review(self, review: dict):
        sentiment_map = {"강세": "Bullish", "약세": "Bearish", "보합": "Neutral", "변동성확대": "Volatile"}
        raw_sent = review.get("sentiment", "Neutral")
        sent = sentiment_map.get(raw_sent, raw_sent)
        props = {
            "Date":       {"title": [{"text": {"content": datetime.now().strftime("%Y-%m-%d")}}]},
            "KospiChg":   {"number": round(review.get("kospi_chg", 0) / 100, 4)},
            "PortPnl":    {"number": round(review.get("port_pnl", 0) / 100, 4)},
            "TotalValue": {"number": review.get("total_value", 0)},
            "Bought":     {"rich_text": [{"text": {"content": review.get("bought", "")[:2000]}}]},
            "Sold":       {"rich_text": [{"text": {"content": review.get("sold", "")[:2000]}}]},
            "KeyIssue":   {"rich_text": [{"text": {"content": review.get("key_issue", "")[:2000]}}]},
            "NextPlan":   {"rich_text": [{"text": {"content": review.get("next_plan", "")[:2000]}}]},
            "Sentiment":  {"select": {"name": sent}},
        }
        return self._create_page(NOTION_DB_REVIEW, props)
