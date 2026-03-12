"""Notion 데이터베이스 로거"""
from datetime import datetime
from notion_client import Client
from config.settings import (
    NOTION_TOKEN, NOTION_DB_TRADES, NOTION_DB_PORTFOLIO,
    NOTION_DB_SIGNALS, NOTION_DB_NEWS,
)
from utils.logger import setup_logger

log = setup_logger("notion_logger")


class NotionLogger:
    def __init__(self, token: str = None):
        self.token = token or NOTION_TOKEN
        self.client = Client(auth=self.token) if self.token else None

    def _create_page(self, db_id: str, properties: dict):
        if not self.client or not db_id:
            log.warning("Notion 설정 미완료")
            return None
        try:
            page = self.client.pages.create(parent={"database_id": db_id}, properties=properties)
            return page
        except Exception as e:
            log.error(f"Notion 기록 실패: {e}")
            return None

    def log_trade(self, trade: dict):
        """매매일지 기록"""
        props = {
            "종목명": {"title": [{"text": {"content": trade["name"]}}]},
            "종목코드": {"rich_text": [{"text": {"content": trade["code"]}}]},
            "매매구분": {"select": {"name": trade["side"]}},
            "수량": {"number": trade["qty"]},
            "주문가": {"number": trade.get("order_price", 0)},
            "체결가": {"number": trade["price"]},
            "체결금액": {"number": trade["amount"]},
            "트리거": {"select": {"name": trade.get("trigger", "시그널")}},
            "일시": {"date": {"start": datetime.now().isoformat()}},
        }
        if trade.get("pnl_pct") is not None:
            props["수익률"] = {"number": trade["pnl_pct"]}
        if trade.get("reason"):
            props["비고"] = {"rich_text": [{"text": {"content": trade["reason"][:2000]}}]}
        return self._create_page(NOTION_DB_TRADES, props)

    def log_portfolio_snapshot(self, snapshot: dict):
        """일일 포트폴리오 스냅샷"""
        props = {
            "일자": {"title": [{"text": {"content": datetime.now().strftime("%Y-%m-%d")}}]},
            "총평가금액": {"number": snapshot["total_value"]},
            "총수익률": {"number": snapshot["total_pnl"]},
            "일간수익률": {"number": snapshot["daily_pnl"]},
            "현금잔고": {"number": snapshot["cash"]},
            "일반비중": {"number": snapshot.get("general_ratio", 0)},
            "배당비중": {"number": snapshot.get("dividend_ratio", 0)},
        }
        return self._create_page(NOTION_DB_PORTFOLIO, props)

    def log_signal(self, signal: dict):
        """시그널 로그"""
        props = {
            "종목명": {"title": [{"text": {"content": signal["name"]}}]},
            "시그널유형": {"select": {"name": signal["action"]}},
            "기술점수": {"number": signal["technical_score"]},
            "시장점수": {"number": signal["market_score"]},
            "뉴스점수": {"number": signal["news_score"]},
            "종합점수": {"number": signal["weighted_score"]},
            "실행여부": {"checkbox": signal.get("executed", False)},
            "일시": {"date": {"start": datetime.now().isoformat()}},
        }
        return self._create_page(NOTION_DB_SIGNALS, props)

    def log_news(self, news: dict):
        """뉴스/정책 분석 기록"""
        props = {
            "제목": {"title": [{"text": {"content": news["title"][:100]}}]},
            "출처": {"select": {"name": news["source"]}},
            "관련섹터": {"multi_select": [{"name": s} for s in news.get("sectors", [])]},
            "감성점수": {"number": news.get("sentiment", 0)},
            "요약": {"rich_text": [{"text": {"content": news.get("summary", "")[:2000]}}]},
            "URL": {"url": news.get("url", "")},
            "일시": {"date": {"start": datetime.now().isoformat()}},
        }
        return self._create_page(NOTION_DB_NEWS, props)
