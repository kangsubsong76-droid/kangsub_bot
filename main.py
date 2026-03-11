"""
KangSub Bot — 메인 실행 파일
이재명 정부 정책 연계 7섹터 + 고배당 자동매매 시스템

실행:
  python main.py             # 실전/페이퍼 모드 (settings.py 기반)
  python main.py --paper     # 강제 페이퍼 트레이딩
  python main.py --once      # 1회 시그널 생성 후 종료
"""
import sys
import asyncio

# Windows asyncio 이벤트 루프 정책 (signal 모듈 호환성)
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
import json
import asyncio
import argparse
from datetime import datetime
from pathlib import Path

from config.settings import DATA_DIR, LOG_DIR
from config.universe import SECTORS, DIVIDEND_TOP12, get_unique_codes

from core.portfolio_manager import PortfolioManager
from core.risk_manager import RiskManager
from core.order_executor import OrderExecutor

from signal.technical import analyze as tech_analyze
from signal.market_condition import analyze_market
from signal.news_analyzer import NewsAnalyzer
from signal.signal_engine import SignalEngine
from signal.dart_client import DartClient

from data.market_data import (
    get_stock_ohlcv, get_kospi_ohlcv, get_usdkrw,
    get_vkospi, get_daily_change, get_kospi_daily_change,
)

from notification.telegram_bot import TelegramNotifier
from notification.notion_logger import NotionLogger
from scheduler.jobs import TradingScheduler
from utils.logger import setup_logger

log = setup_logger("main", LOG_DIR)

PAPER_TRADING = "--paper" in sys.argv


class MainEngine:
    """KangSub Bot 핵심 실행 엔진"""

    def __init__(self, paper: bool = True):
        self.paper = paper
        self.running = False
        self.auto_trading = True

        log.info(f"{'=' * 50}")
        log.info(f"KangSub Bot 시작 ({'페이퍼트레이딩' if paper else '실전매매'})")
        log.info(f"{'=' * 50}")

        # 모듈 초기화
        self.portfolio = PortfolioManager()
        self.risk = RiskManager()
        self.executor = OrderExecutor(kiwoom_api=None, paper_trading=paper)
        self.news_analyzer = NewsAnalyzer()
        self.signal_engine = SignalEngine()
        self.dart = DartClient()
        self.notifier = TelegramNotifier()
        self.notion = NotionLogger()

        # 캐시
        self._cached_news = []
        self._cached_signals = []

        log.info("모든 모듈 초기화 완료")

    # ── 스케줄 작업 ──

    def morning_health_check(self):
        log.info("[06:00] 시스템 상태 점검")
        summary = self.portfolio.get_summary()
        msg = (
            f"☀️ <b>시스템 점검</b> ({datetime.now():%Y-%m-%d})\n"
            f"포트폴리오: {summary['num_holdings']}종목\n"
            f"현금: {summary['cash']:,.0f}원\n"
            f"총평가: {summary['total_value']:,.0f}원\n"
            f"자동매매: {'ON ✅' if self.auto_trading else 'OFF ⏸'}"
        )
        asyncio.run(self.notifier.send(msg))

    def collect_news(self):
        log.info("[07:00] 뉴스 크롤링 시작")
        codes = list(get_unique_codes())[:10]
        self._cached_news = self.news_analyzer.collect_all_news(codes)
        self._cached_news = self.news_analyzer.process_news(self._cached_news)
        log.info(f"뉴스 {len(self._cached_news)}건 수집 완료")
        for news in self._cached_news[:5]:
            self.notion.log_news({
                "title": news.title,
                "source": news.source,
                "sectors": news.sectors,
                "sentiment": news.sentiment,
                "summary": news.summary,
                "url": news.url,
            })

    def analyze_news_signals(self):
        log.info("[08:00] 뉴스 시그널 분석")
        if not self._cached_news:
            self.collect_news()
        codes = get_unique_codes()
        news_scores = {
            code: self.news_analyzer.get_stock_news_score(code, self._cached_news)
            for code in codes
        }
        log.info(f"뉴스 시그널 {len(news_scores)}종목 분석 완료")
        return news_scores

    def morning_briefing(self):
        log.info("[08:30] 모닝 브리핑")
        kospi_df = get_kospi_ohlcv(30)
        usdkrw_df = get_usdkrw(7)
        vkospi = get_vkospi()
        market = analyze_market(kospi_df, vkospi, usdkrw_df) if not kospi_df.empty else None

        # 뉴스 요약 (긍정 뉴스 top3)
        news_summary = ""
        positive = sorted(self._cached_news, key=lambda n: n.sentiment, reverse=True)[:3]
        for n in positive:
            news_summary += f"• {n.title[:40]}\n"

        briefing = {
            "kospi": f"{kospi_df['close'].iloc[-1]:,.2f}" if not kospi_df.empty else "-",
            "market_status": f"{market.kospi_trend} / 점수 {market.score:.0f}" if market else "-",
            "usdkrw": f"{usdkrw_df['close'].iloc[-1]:,.1f}" if not usdkrw_df.empty else "-",
            "news_summary": news_summary or "수집된 뉴스 없음",
            "trade_plan": self._get_trade_plan(),
        }
        asyncio.run(self.notifier.send_morning_briefing(briefing))

    def start_realtime(self):
        log.info("[09:00] 실시간 시세 수신 시작")
        # 키움 실시간 데이터 구독 (키움 API 연동 후 구현)

    def stop_realtime(self):
        log.info("[15:30] 실시간 시세 수신 종료")

    def execute_buy_signals(self):
        if not self.auto_trading:
            return
        log.info("[09:30] 매수 시그널 실행")
        signals = self._generate_signals()
        buy_signals = [s for s in signals if s.action == "BUY"]

        for sig in buy_signals[:3]:  # 하루 최대 3종목 매수
            code = sig.code
            holding = self.portfolio.holdings.get(code)
            stage = (holding.split_stage + 1) if holding else 1
            if stage > 3:
                continue

            # 섹터 예산 계산
            from config.universe import get_stock_name
            sector = self._get_sector(code)
            budget = self.portfolio.calc_sector_budget(sector) if sector else 0

            if budget > 0 and self.portfolio.cash > 0:
                ohlcv = get_stock_ohlcv(code, 5)
                if ohlcv.empty:
                    continue
                price = ohlcv["close"].iloc[-1]
                result = self.executor.split_buy(code, sig.name, budget, price, stage)
                if result.status in ("FILLED", "PARTIAL"):
                    cat = "dividend" if code in self._get_all_dividend_codes() else "general"
                    self.portfolio.add_holding(code, sig.name, cat, sector or "", result.avg_price, result.total_qty, stage)
                    trade_data = {
                        "code": code, "name": sig.name, "side": "매수",
                        "qty": result.total_qty, "price": result.avg_price,
                        "amount": result.total_amount,
                        "trigger": "시그널", "reason": " | ".join(sig.reasons[:2]),
                    }
                    asyncio.run(self.notifier.send_trade_alert(trade_data))
                    self.notion.log_trade(trade_data)

    def monitor_stop_loss(self):
        if not self.portfolio.holdings:
            return
        kospi_change = get_kospi_daily_change()
        for code, holding in list(self.portfolio.holdings.items()):
            ohlcv = get_stock_ohlcv(code, 5)
            if ohlcv.empty:
                continue
            current = ohlcv["close"].iloc[-1]
            stock_change = get_daily_change(code)
            holding.current_price = current
            if current > holding.high_since_buy:
                holding.high_since_buy = current

            pos = holding.to_risk_position()
            self.risk.add_position(pos)
            alerts = self.risk.run_all_checks(code, stock_change, kospi_change)

            for alert in alerts:
                asyncio.run(self.notifier.send_stop_loss_alert(alert))
                if alert["action"] == "SELL_NOW":
                    result = self.executor.sell(code, holding.name, holding.quantity, current, alert["type"])
                    if result.status == "FILLED":
                        pnl = self.portfolio.remove_holding(code, result.total_qty, result.avg_price)
                        trade_data = {
                            "code": code, "name": holding.name, "side": "손절매도",
                            "qty": result.total_qty, "price": result.avg_price,
                            "amount": result.total_amount,
                            "trigger": alert["type"],
                            "pnl_pct": pnl.get("pnl_pct") if pnl else None,
                        }
                        self.notion.log_trade(trade_data)
                elif alert["action"] == "SELL_ALL":
                    results = self.executor.sell_all(dict(self.portfolio.holdings))
                    asyncio.run(self.notifier.send(
                        "🚨 <b>포트폴리오 전량 매도 완료</b>\n사유: 전체 손실 한도 -20% 도달"
                    ))

    def save_portfolio_snapshot(self):
        summary = self.portfolio.get_summary()
        self.notion.log_portfolio_snapshot({
            "total_value": summary["total_value"],
            "total_pnl": summary["total_pnl"],
            "daily_pnl": 0,  # TODO: 전일 대비 계산
            "cash": summary["cash"],
            "general_ratio": summary["general_value"] / summary["total_value"] if summary["total_value"] else 0,
            "dividend_ratio": summary["dividend_value"] / summary["total_value"] if summary["total_value"] else 0,
        })
        # 대시보드용 JSON 저장
        path = DATA_DIR / "portfolio.json"
        path.write_text(json.dumps({**summary, "total_capital": self.portfolio.total_capital}, ensure_ascii=False, indent=2))
        log.info("포트폴리오 스냅샷 저장 완료")

    def check_dart_disclosures(self):
        log.info("[16:00] DART 공시 체크")
        for code in get_unique_codes():
            corp_code = self.dart.get_corp_code(code)
            if corp_code:
                negatives = self.dart.check_negative_disclosures(corp_code)
                for d in negatives:
                    asyncio.run(self.notifier.send(
                        f"⚠️ <b>부정 공시 감지</b>\n{d.corp_name}: {d.report_nm}\n{d.url}"
                    ))

    def daily_report(self):
        summary = self.portfolio.get_summary()
        trades = self._load_today_trades()
        report = {
            "total_value": summary["total_value"],
            "daily_pnl": 0,
            "total_pnl": summary["total_pnl"],
            "cash": summary["cash"],
            "num_holdings": summary["num_holdings"],
            "buys": sum(1 for t in trades if t.get("side") == "매수"),
            "sells": sum(1 for t in trades if "매도" in t.get("side", "")),
        }
        asyncio.run(self.notifier.send_daily_report(report))

    def midday_report(self):
        summary = self.portfolio.get_summary()
        msg = (
            f"🕛 <b>중간 현황</b>\n"
            f"총 평가: {summary['total_value']:,.0f}원\n"
            f"수익률: {summary['total_pnl']:+.1%}\n"
            f"보유: {summary['num_holdings']}종목"
        )
        asyncio.run(self.notifier.send(msg))

    def pre_close_check(self):
        log.info("[14:50] 마감 전 확인")

    def check_global_market(self):
        log.info("[22:00] 글로벌 시장 체크")

    def weekly_report(self):
        log.info("주간 리포트 생성")

    def quarterly_rebalance(self):
        log.info("분기 리밸런싱 시작")
        # TODO: 리밸런싱 로직 구현

    def update_technical_signals(self):
        log.info("[18:00] 기술적 분석 업데이트")
        signals = self._generate_signals()
        path = DATA_DIR / "signals.json"
        path.write_text(json.dumps([
            {"code": s.code, "name": s.name, "action": s.action,
             "technical_score": s.technical_score, "market_score": s.market_score,
             "news_score": s.news_score, "weighted_score": s.weighted_score,
             "reasons": s.reasons}
            for s in signals
        ], ensure_ascii=False, indent=2))

    # ── 텔레그램 명령 콜백 ──

    def handle_telegram_command(self, command: str) -> str:
        summary = self.portfolio.get_summary()
        if command == "status":
            return (
                f"📊 시스템 상태\n"
                f"자동매매: {'ON' if self.auto_trading else 'OFF'}\n"
                f"보유종목: {summary['num_holdings']}개\n"
                f"현금: {summary['cash']:,.0f}원\n"
                f"총평가: {summary['total_value']:,.0f}원\n"
                f"수익률: {summary['total_pnl']:+.1%}"
            )
        elif command == "pause":
            self.auto_trading = False
        elif command == "resume":
            self.auto_trading = True
        elif command == "balance":
            return f"현금: {summary['cash']:,.0f}원"
        return "OK"

    # ── 내부 헬퍼 ──

    def _generate_signals(self):
        kospi_df = get_kospi_ohlcv(60)
        usdkrw_df = get_usdkrw(14)
        vkospi = get_vkospi()
        market = analyze_market(kospi_df, vkospi, usdkrw_df) if not kospi_df.empty else None
        if market is None:
            log.warning("시장 데이터 없음 — 시그널 생성 스킵")
            return []

        news_scores = {
            code: self.news_analyzer.get_stock_news_score(code, self._cached_news)
            for code in get_unique_codes()
        }

        tech_signals = []
        for code in get_unique_codes():
            ohlcv = get_stock_ohlcv(code, 120)
            if len(ohlcv) < 30:
                continue
            from config.universe import get_stock_name
            ts = tech_analyze(ohlcv, code, get_stock_name(code))
            tech_signals.append(ts)

        return self.signal_engine.generate_batch_signals(tech_signals, market, news_scores)

    def _get_sector(self, code: str) -> str:
        for sec_key, sec in SECTORS.items():
            if code in sec["stocks"]:
                return sec_key
        return ""

    def _get_all_dividend_codes(self):
        codes = set()
        for group in DIVIDEND_TOP12.values():
            codes.update(group.keys())
        return codes

    def _get_trade_plan(self) -> str:
        signals = self._cached_signals or []
        buy = [s for s in signals if s.action == "BUY"]
        if not buy:
            return "해당 없음 (관망)"
        return "\n".join(f"• {s.name} 매수 ({s.weighted_score:.0f}점)" for s in buy[:3])

    def _load_today_trades(self):
        path = DATA_DIR / "trades.json"
        if path.exists():
            trades = json.loads(path.read_text(encoding="utf-8"))
            today = datetime.now().strftime("%Y-%m-%d")
            return [t for t in trades if t.get("timestamp", "").startswith(today)]
        return []


# ── 진입점 ──

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="KangSub Bot")
    parser.add_argument("--paper", action="store_true", help="페이퍼 트레이딩 모드")
    parser.add_argument("--once", action="store_true", help="1회 시그널 생성 후 종료")
    args = parser.parse_args()

    engine = MainEngine(paper=args.paper or PAPER_TRADING)

    if args.once:
        log.info("1회 실행 모드")
        engine.collect_news()
        engine.update_technical_signals()
        log.info("완료")
        sys.exit(0)

    # 스케줄러 시작
    scheduler = TradingScheduler(engine)
    scheduler.start()
    engine.running = True

    log.info("KangSub Bot 가동 중... (Ctrl+C 로 종료)")
    try:
        import time
        while engine.running:
            time.sleep(60)
    except KeyboardInterrupt:
        log.info("종료 신호 수신")
        scheduler.stop()
        log.info("KangSub Bot 종료")
