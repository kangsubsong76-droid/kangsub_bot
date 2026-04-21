"""
KangSub Bot — 메인 실행 파일
이재명 정부 정책 연계 10섹터 + 고배당 자동매매 시스템

실행:
  python main.py             # 실전/페이퍼 모드 (settings.py 기반)
  python main.py --paper     # 강제 페이퍼 트레이딩
  python main.py --once      # 1회 시그널 생성 후 종료
"""
import sys
import json
import asyncio
import argparse
import subprocess
import threading
import time

# Windows asyncio 이벤트 루프 정책 (signal 모듈 호환성)
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
from datetime import datetime
from pathlib import Path

from config.settings import DATA_DIR, LOG_DIR
from config.universe import SECTORS, DIVIDEND_TOP12, get_unique_codes

from core.portfolio_manager import PortfolioManager
from core.risk_manager import RiskManager
from core.order_executor import OrderExecutor

from signals.technical import analyze as tech_analyze
from signals.market_condition import analyze_market
from signals.news_analyzer import NewsAnalyzer
from signals.signal_engine import SignalEngine
from signals.dart_client import DartClient

from data.market_data import (
    get_stock_ohlcv, get_kospi_ohlcv, get_usdkrw,
    get_vkospi, get_daily_change, get_kospi_daily_change,
)
from data.fundamentals import refresh_all as refresh_fundamentals_data, get_fundamentals, is_cache_fresh

from notification.telegram_bot import TelegramNotifier, TelegramCommandBot
from core.kiwoom_rest import KiwoomRestAPI
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

        # 키움 REST API 연결
        self.kiwoom = KiwoomRestAPI()
        kiwoom_connected = self.kiwoom.test_connection() if not paper else False
        kiwoom_api = self.kiwoom if kiwoom_connected else None
        self.executor = OrderExecutor(kiwoom_api=kiwoom_api, paper_trading=paper)

        # market_data / fundamentals / surge_tracker 키움 인스턴스 주입
        if kiwoom_connected:
            from data.market_data import set_kiwoom
            set_kiwoom(self.kiwoom)
            log.info("market_data: 키움 REST API OHLCV 활성화")
            from data.fundamentals import set_kiwoom as set_kiwoom_funda
            set_kiwoom_funda(self.kiwoom)
            log.info("fundamentals: 키움 REST API 재무(ka10001) 활성화")
            from data.surge_tracker import set_kiwoom as set_kiwoom_surge
            set_kiwoom_surge(self.kiwoom)
            log.info("surge_tracker: 키움 REST API 급상승순위(ka10027) 활성화")
        self.news_analyzer = NewsAnalyzer()
        self.signal_engine = SignalEngine()
        self.dart = DartClient()
        self.notifier = TelegramNotifier()
        self.notion = NotionLogger()
        self.cmd_bot = TelegramCommandBot(engine_callback=self.handle_telegram_command)

        # 캐시
        self._cached_news = []
        self._cached_signals = []
        # 손절 알림 중복 방지 (같은 종목 30분 내 재발송 금지)
        self._stop_loss_alerted: dict = {}  # {code: datetime}

        log.info("모든 모듈 초기화 완료")

        # 재무 데이터 캐시가 없거나 오래됐으면 즉시 갱신
        if not is_cache_fresh():
            log.info("재무 데이터 캐시 없음 또는 오래됨 — 즉시 갱신")
            self.refresh_fundamentals()

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
        log.info("[08:30] Morning briefing")
        kospi_df  = get_kospi_ohlcv(30)
        usdkrw_df = get_usdkrw(7)
        vkospi    = get_vkospi()
        market    = analyze_market(kospi_df, vkospi, usdkrw_df) if not kospi_df.empty else None

        # 뉴스 요약 (긍정 뉴스 top3)
        news_summary = ""
        positive = sorted(self._cached_news, key=lambda n: n.sentiment, reverse=True)[:3]
        for n in positive:
            news_summary += f"• {n.title[:40]}\n"

        # NXT 현황: 현재 보유 중인 nxt 카테고리 종목 수 + 투입금액
        nxt_holdings = {
            code: h for code, h in self.portfolio.holdings.items()
            if getattr(h, "category", "") == "nxt"
        }
        nxt_invested = sum(
            getattr(h, "avg_price", 0) * getattr(h, "quantity", 0)
            for h in nxt_holdings.values()
        )

        briefing = {
            "kospi":         f"{kospi_df['close'].iloc[-1]:,.2f}" if not kospi_df.empty else "-",
            "market_status": f"{market.kospi_trend} / 점수 {market.score:.0f}" if market else "-",
            "usdkrw":        f"{usdkrw_df['close'].iloc[-1]:,.1f}" if not usdkrw_df.empty else "-",
            "news_summary":  news_summary or "수집된 뉴스 없음",
            "trade_plan":    self._get_trade_plan(),
            "nxt_stocks":    len(nxt_holdings),
            "nxt_invested":  nxt_invested,
        }
        asyncio.run(self.notifier.send_morning_briefing_integrated(briefing))

    def start_realtime(self):
        log.info("[09:00] 실시간 시세 수신 시작")
        # 키움 실시간 데이터 구독 (키움 API 연동 후 구현)

    def stop_realtime(self):
        log.info("[15:30] 실시간 시세 수신 종료")

    def execute_buy_signals(self):
        """
        PAM Phase 2 — 09:00 매수 실행
        ① 총 운용자본의 50% 이내 한도
        ② 선택 종목 균등 배분 (예산 재배분 로직 포함)
           - 고가 종목(1주 > 종목당 예산)은 스킵 후 예산을 나머지에 재배분
           - 최대 2회 재배분 반복으로 예산 최대 활용
        ③ 7종목 cap 확인
        """
        if not self.auto_trading:
            return
        log.info("[09:00] PAM Phase 2 — 매수 실행")

        from config.settings import PAM_BUY_RATIO, PAM_MAX_HOLDINGS, TOTAL_CAPITAL
        signals = self._generate_signals()
        buy_signals = [s for s in signals if s.action == "BUY"]
        if not buy_signals:
            log.info("매수 시그널 없음 — 매수 스킵")
            return

        # 7종목 cap 확인
        current_holdings = len(self.portfolio.holdings)
        available_slots = PAM_MAX_HOLDINGS - current_holdings
        if available_slots <= 0:
            log.info(f"7종목 cap 도달 ({current_holdings}종목) — 매수 불가")
            asyncio.run(self.notifier.send(
                f"⚠️ 보유 종목 {current_holdings}개로 7종목 cap 도달 — 신규 매수 없음"
            ))
            return

        # 이미 보유 중인 종목 제외
        new_signals = [s for s in buy_signals if s.code not in self.portfolio.holdings]
        candidates = new_signals[:min(5, available_slots)]  # 최대 5종목 선정

        if not candidates:
            log.info("신규 매수 가능 종목 없음")
            return

        # 총 매수 한도
        # 최초 매수 (보유종목 0): 한도 없이 현금 전액 사용 가능
        # 추가 매수 (보유종목 있음): 총 운용자본의 50% 이내 제한
        is_first_buy = (current_holdings == 0)
        if is_first_buy:
            cash_available = self.portfolio.cash
            log.info("최초 매수 — 50% 한도 미적용, 현금 전액 사용 가능")
        else:
            total_buy_limit = TOTAL_CAPITAL * PAM_BUY_RATIO  # 250만원
            cash_available = min(self.portfolio.cash, total_buy_limit)
            log.info(f"추가 매수 — 50% 한도 적용 ({total_buy_limit:,.0f}원)")

        # ── 예산 재배분 로직 ──
        # 1회차: 균등 배분 → 1주도 못 사는 종목 제외 → 2회차 재배분
        codes_to_buy = [s.code for s in candidates]
        for _ in range(3):  # 최대 3회 재배분 반복
            per_stock = cash_available / len(codes_to_buy) if codes_to_buy else 0
            skippable = []
            for code in codes_to_buy:
                ohlcv = get_stock_ohlcv(code, 5)
                if ohlcv.empty:
                    skippable.append(code)
                    continue
                price = ohlcv["close"].iloc[-1]
                if price > per_stock:
                    skippable.append(code)
            if not skippable:
                break  # 모든 종목 매수 가능 → 재배분 완료
            codes_to_buy = [c for c in codes_to_buy if c not in skippable]
            if not codes_to_buy:
                log.warning("모든 종목 고가로 매수 불가 — 예산 부족")
                asyncio.run(self.notifier.send(
                    f"⚠️ 전 종목 1주 가격 > 종목당 예산 ({per_stock:,.0f}원) — 매수 불가"
                ))
                return

        # ── 실제 매수 실행 ──
        per_stock_final = cash_available / len(codes_to_buy)
        sig_map = {s.code: s for s in candidates}
        bought_count = 0

        log.info(f"매수 대상: {len(codes_to_buy)}종목 / 종목당 예산: {per_stock_final:,.0f}원")

        for code in codes_to_buy:
            sig = sig_map[code]
            ohlcv = get_stock_ohlcv(code, 5)
            if ohlcv.empty:
                continue
            price = ohlcv["close"].iloc[-1]
            qty = int(per_stock_final // price)
            if qty == 0:
                log.warning(f"{sig.name}: 1주({price:,.0f}원) > 예산({per_stock_final:,.0f}원) — 스킵")
                continue

            result = self.executor.split_buy(code, sig.name, per_stock_final, price, 1)
            if result.status in ("FILLED", "PARTIAL"):
                sector = self._get_sector(code)
                cat = "dividend" if code in self._get_all_dividend_codes() else "general"
                self.portfolio.add_holding(code, sig.name, cat, sector or "", result.avg_price, result.total_qty, 1)
                trade_data = {
                    "code": code, "name": sig.name, "side": "매수",
                    "qty": result.total_qty, "price": result.avg_price,
                    "amount": result.total_amount,
                    "trigger": "PAM Phase2", "reason": " | ".join(sig.reasons[:2]),
                }
                asyncio.run(self.notifier.send_trade_alert(trade_data))
                self.notion.log_trade(trade_data)
                bought_count += 1

        log.info(f"PAM Phase 2 완료: {bought_count}종목 매수, "
                 f"현금 잔고 {self.portfolio.cash:,.0f}원")

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
                # 같은 종목 30분 내 중복 알림 방지 (SELL_ALL은 항상 전송)
                now = datetime.now()
                last = self._stop_loss_alerted.get(code)
                if alert["action"] != "SELL_ALL" and last and (now - last).seconds < 1800:
                    log.debug(f"손절 알림 중복 스킵: {code} (마지막: {last:%H:%M})")
                    continue
                self._stop_loss_alerted[code] = now
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
            "total_value":   summary["total_value"],
            "total_pnl":     summary["total_pnl"],
            "daily_pnl":     0,
            "cash":          summary["cash"],
            "general_ratio": summary["general_value"] / summary["total_value"] if summary["total_value"] else 0,
            "dividend_ratio":summary["dividend_value"] / summary["total_value"] if summary["total_value"] else 0,
        })
        # 대시보드용 JSON 저장
        path = DATA_DIR / "portfolio_snapshot.json"
        path.write_text(json.dumps({**summary, "total_capital": self.portfolio.total_capital}, ensure_ascii=False, indent=2))
        self.portfolio._save()
        log.info("Portfolio snapshot saved")

        # 15:40 텔레그램 — 정규장 마감 스냅샷
        holdings_detail = []
        for code, h in self.portfolio.holdings.items():
            if getattr(h, "category", "") == "nxt":
                continue  # NXT는 이미 10:30에 청산됨
            try:
                from data.market_data import get_stock_ohlcv as _ohlcv
                df = _ohlcv(code, 5)
                current = df["close"].iloc[-1] if not df.empty else getattr(h, "avg_price", 0)
            except Exception:
                current = getattr(h, "avg_price", 0)
            avg  = getattr(h, "avg_price", 0)
            pnl_pct = (current - avg) / avg * 100 if avg else 0
            holdings_detail.append({"name": getattr(h, "name", code), "pnl_pct": pnl_pct})
        asyncio.run(self.notifier.send_market_close_snapshot(summary, holdings_detail))

    def check_dart_disclosures(self):
        log.info("[16:00] DART 공시 체크")
        from config.settings import DART_API_KEY
        if not DART_API_KEY:
            log.info("DART API 키 미설정 — 공시 체크 스킵")
            return

        for code in get_unique_codes():
            corp_code = self.dart.get_corp_code(code)
            if not corp_code:
                continue

            # 부정 공시 (횡령·상장폐지 등 실제 위험만)
            for d in self.dart.check_negative_disclosures(corp_code):
                asyncio.run(self.notifier.send(
                    f"🚨 <b>중요 부정 공시</b>\n"
                    f"종목: {d.corp_name}\n"
                    f"공시: {d.report_nm}\n"
                    f"일자: {d.rcept_dt}\n"
                    f"🔗 {d.url}"
                ))

            # 긍정 공시 (자사주·배당 등 매수 기회)
            for d in self.dart.check_positive_disclosures(corp_code):
                asyncio.run(self.notifier.send(
                    f"📢 <b>주요 공시</b>\n"
                    f"종목: {d.corp_name}\n"
                    f"공시: {d.report_nm}\n"
                    f"일자: {d.rcept_dt}\n"
                    f"🔗 {d.url}"
                ))

    def daily_report(self):
        summary = self.portfolio.get_summary()
        trades  = self._load_today_trades()

        # NXT 거래 집계
        nxt_trades = [t for t in trades if t.get("trigger", "").startswith("NXT")
                      and t.get("side") in ("NXT청산", "NXT손절")]
        nxt_pnl    = sum(t.get("pnl", 0) for t in nxt_trades if "pnl" in t)

        report = {
            "total_value":       summary["total_value"],
            "daily_pnl":         0,
            "total_pnl":         summary["total_pnl"],
            "cash":              summary["cash"],
            "num_holdings":      summary["num_holdings"],
            "buys":              sum(1 for t in trades if t.get("side") == "매수"),
            "sells":             sum(1 for t in trades if "매도" in t.get("side", "")),
            "realized_pnl":      sum(t.get("pnl", 0) for t in trades if "pnl" in t),
            "nxt_realized_pnl":  nxt_pnl,
            "nxt_trade_count":   len(nxt_trades),
        }
        asyncio.run(self.notifier.send_daily_report_integrated(report))

    def midday_report(self):
        summary = self.portfolio.get_summary()
        trades  = self._load_today_trades()

        # 오늘 NXT 청산 내역 집계
        nxt_close_trades = [
            t for t in trades
            if t.get("trigger", "").startswith("NXT")
            and t.get("side") in ("NXT청산", "NXT손절")
        ]
        nxt_pnl = sum(t.get("pnl", 0) for t in nxt_close_trades if "pnl" in t)

        # 종목별 수익률 계산 (청산 거래 기준)
        nxt_result_trades = []
        for t in nxt_close_trades:
            buy_price  = t.get("buy_price", t.get("price", 0))
            sell_price = t.get("price", 0)
            chg = (sell_price - buy_price) / buy_price * 100 if buy_price else 0
            nxt_result_trades.append({"name": t.get("name", "?"), "change_pct": chg})

        nxt_result = {
            "realized_pnl": nxt_pnl,
            "trades":       nxt_result_trades,
        }
        asyncio.run(self.notifier.send_midday_integrated(summary, nxt_result))

    def sync_manual_portfolio_prices(self):
        """
        portfolio_manual.json 현재가 자동 동기화
        — 장 시작(09:00), 장 마감 후(15:40) 스케줄러에서 호출
        — Kiwoom ka10001 로 각 종목 현재가 조회 후 평가금액/손익 갱신
        """
        from config.settings import DATA_DIR as _DATA_DIR
        manual_path = _DATA_DIR / "portfolio_manual.json"   # DATA_DIR = data/store 이미 포함
        if not manual_path.exists():
            log.info("portfolio_manual.json 없음 — 동기화 스킵")
            return
        try:
            data = json.loads(manual_path.read_text(encoding="utf-8"))
            holdings = data.get("holdings", [])
            if not holdings:
                return

            total_value = 0
            total_capital = data.get("total_capital", 30_000_000)
            synced = 0
            for h in holdings:
                code = h.get("code", "")
                if not code:
                    continue
                # ka10001 현재가 조회
                info = self.kiwoom.get_stock_info(code) if self.kiwoom else None
                if info and info.get("price", 0) > 0:
                    cur = info["price"]
                    h["current_price"] = cur
                    synced += 1
                else:
                    cur = h.get("current_price", h.get("avg_price", 0))
                avg = h.get("avg_price", 0)
                qty = h.get("qty", 0)
                value      = cur * qty
                pnl_amount = (cur - avg) * qty
                pnl_pct    = (cur - avg) / avg * 100 if avg else 0
                h["value"]      = round(value)
                h["pnl_amount"] = round(pnl_amount)
                h["pnl_pct"]    = round(pnl_pct, 2)
                total_value += value

            total_pnl_amount = sum(h.get("pnl_amount", 0) for h in holdings)
            data["total_value"]   = round(total_value)
            data["total_pnl"]     = round(total_pnl_amount / total_value * 100, 2) if total_value else 0
            data["total_pnl_pct"] = data["total_pnl"]
            data["num_holdings"]  = len(holdings)
            data["updated_at"]    = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            manual_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            log.info(f"portfolio_manual.json sync done: {synced}/{len(holdings)} prices updated, total={total_value:,.0f}KRW")

            # PortfolioManager 현재가도 갱신
            for h in holdings:
                code = h.get("code", "")
                if code in self.portfolio.holdings:
                    self.portfolio.holdings[code].current_price = h.get("current_price", 0)

        except Exception as e:
            log.error(f"sync_manual_portfolio_prices error: {e}")

    def reconcile_portfolio(self):
        """
        실 API 데이터 vs portfolio_manual.json 대조 검증
        — 09:10, 15:45 스케줄러에서 호출
        — 현금 또는 총평가 차이 1% 초과 시 텔레그램 경고 + 자동 수정

        검증 흐름:
          1) ka01002 (get_portfolio_holdings) 로 실 계좌 조회
          2) portfolio_manual.json 값과 비교
          3) 차이 > 1% → 자동 수정 + 텔레그램 알림
          4) 차이 ≤ 1% → "일치 확인" 로그만
        """
        from config.settings import DATA_DIR as _DATA_DIR
        manual_path = _DATA_DIR / "portfolio_manual.json"   # DATA_DIR = data/store 이미 포함
        if not manual_path.exists():
            log.info("reconcile: portfolio_manual.json 없음 — 스킵")
            return

        try:
            manual = json.loads(manual_path.read_text(encoding="utf-8"))
        except Exception as e:
            log.error(f"reconcile: manual 파일 읽기 실패 — {e}")
            return

        manual_total = manual.get("total_value", 0)
        manual_cash  = manual.get("cash", 0)

        # ── ka01002 실 API 조회 ──
        api_data = None
        if self.kiwoom:
            try:
                api_data = self.kiwoom.get_portfolio_holdings()
            except Exception as e:
                log.warning(f"reconcile: ka01002 조회 실패 — {e}")

        if not api_data or api_data.get("total_value", 0) == 0:
            log.info("reconcile: API 데이터 없음 — 검증 스킵")
            return

        api_total = api_data.get("total_value", 0)
        api_cash  = api_data.get("cash", 0)

        # ── 차이 계산 ──
        total_diff     = api_total - manual_total
        total_diff_pct = abs(total_diff) / api_total * 100 if api_total else 0
        cash_diff      = api_cash - manual_cash if api_cash else 0
        cash_diff_abs  = abs(cash_diff)

        mismatch = total_diff_pct > 1.0 or cash_diff_abs > 50_000

        lines = [
            f"🔍 <b>포트폴리오 대조 검증</b>",
            f"{'⚠️ 불일치' if mismatch else '✅ 일치'} | {datetime.now():%H:%M}",
            f"",
            f"<b>총평가</b>",
            f"  API    : {api_total:>12,.0f}원",
            f"  수동   : {manual_total:>12,.0f}원",
            f"  차이   : {total_diff:>+12,.0f}원  ({total_diff_pct:.1f}%)",
        ]
        if api_cash:
            lines += [
                f"",
                f"<b>현금</b>",
                f"  API    : {api_cash:>12,.0f}원",
                f"  수동   : {manual_cash:>12,.0f}원",
                f"  차이   : {cash_diff:>+12,.0f}원",
            ]

        if mismatch:
            # ── 자동 수정 ──
            if api_cash:
                manual["cash"] = api_cash
            manual["total_value"] = api_total

            api_holdings = api_data.get("holdings", [])
            if api_holdings:
                manual["holdings"]     = api_holdings
                manual["num_holdings"] = len(api_holdings)

            manual["updated_at"]    = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            manual["reconciled_at"] = manual["updated_at"]
            manual_path.write_text(
                json.dumps(manual, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            lines.append(f"")
            lines.append(f"🔧 portfolio_manual.json 자동 수정 완료")
            log.warning(
                f"reconcile: 불일치 수정 — total_diff={total_diff:+,.0f}원 ({total_diff_pct:.1f}%), "
                f"cash_diff={cash_diff:+,.0f}원"
            )
        else:
            log.info(
                f"reconcile OK: api={api_total:,.0f} manual={manual_total:,.0f} "
                f"diff={total_diff_pct:.2f}%"
            )

        asyncio.run(self.notifier.send("\n".join(lines)))

    def pre_close_check(self):
        log.info("[14:50] 마감 전 확인")

    def check_global_market(self):
        log.info("[22:00] 글로벌 시장 체크")

    def refresh_fundamentals(self):
        """매주 월요일 — PER/PBR/ROE 실시간 갱신 (pykrx KRX 공식 데이터)"""
        log.info("[주간] 재무 데이터 갱신 시작 (PER/PBR/ROE)")
        codes = list(get_unique_codes())
        results = refresh_fundamentals_data(codes)
        msg = (
            f"📊 <b>재무 데이터 갱신 완료</b>\n"
            f"갱신: {len(results)}종목\n"
            f"기준일: {datetime.now():%Y-%m-%d}\n"
        )
        # 주요 종목 PER/PBR 요약
        for code in list(results.keys())[:5]:
            d = results[code]
            msg += f"• {get_unique_codes() and code}: PER {d.get('per') or '-'}, PBR {d.get('pbr') or '-'}\n"
        asyncio.run(self.notifier.send(msg))
        log.info(f"재무 데이터 갱신 완료: {len(results)}종목")

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

    # ── NXT 전략 (장전거래 08:00) ──────────────────────────

    def _filter_nxt_eligible(self, stocks: list) -> tuple[list, list]:
        """종목 리스트에서 장전거래 적격 종목만 분리. (eligible, skipped) 반환"""
        if not (self.kiwoom and not self.paper):
            return stocks, []
        eligible, skipped = [], []
        for s in stocks:
            ok, reason = self.kiwoom.is_nxt_eligible(s["code"])
            if ok:
                eligible.append(s)
                log.info(f"  ✅ 적격: {s['name']}({s['code']})")
            else:
                skipped.append((s, reason))
                log.warning(f"  ❌ 부적격: {s['name']}({s['code']}) — {reason}")
        return eligible, skipped

    def _nxt_fallback_from_afterhours(self, tried_codes: set) -> list:
        """
        Claude 재시도에서도 적격 종목이 없을 때 최후 수단:
        원본 시간외 전체 풀(afterhours_raw.json)을 변동률 순으로 스캔해 적격 1종목 반환.
        tried_codes: 이미 시도했던 종목코드 집합 (제외 대상)

        ※ STEP1.5 이후 afterhours_result.json 은 적격 종목만 포함되어 있으므로
          원본 백업인 afterhours_raw.json 을 우선 사용.
        """
        import json as _json
        # 원본 백업 우선, 없으면 현재 파일 사용
        raw_path = DATA_DIR / "afterhours_raw.json"
        ah_path  = DATA_DIR / "afterhours_result.json"
        src_path = raw_path if raw_path.exists() else ah_path
        try:
            ah = _json.loads(src_path.read_text(encoding="utf-8"))
        except Exception:
            return []

        pool = [s for s in ah.get("stocks", []) if s.get("code") not in tried_codes]
        # 변동률 내림차순 정렬
        pool.sort(key=lambda x: float(str(x.get("change_rate", 0)).replace("%", "") or 0), reverse=True)

        for s in pool:
            ok, reason = self.kiwoom.is_nxt_eligible(s["code"]) if (self.kiwoom and not self.paper) else (True, "페이퍼")
            if ok:
                log.info(f"  ✅ 폴백 적격: {s['name']}({s['code']})")
                return [{
                    "rank": 1,
                    "code": s["code"],
                    "name": s["name"],
                    "confidence": "MID",
                    "afterhours_price": s.get("price"),
                    "change_rate": s.get("change_rate"),
                    "vol_ratio": s.get("vol_ratio"),
                }]
        return []

    def _pre_filter_afterhours(self) -> tuple[int, int]:
        """
        [STEP 1.5] Claude 분석 前 NXT 사전 적격 필터링
        afterhours_result.json 종목 중 장전거래 불가 종목을 제거하고
        적격 종목만 남겨 Claude 가 처음부터 올바른 풀만 보도록 함.

        - 페이퍼 모드 / Kiwoom 미연결: 필터 생략, 원본 그대로 사용
        - 적격 < 5개: _expand_eligible_pool() 로 ka10027 확장 조회
        - 원본은 afterhours_raw.json 에 백업 (당일 디버깅용)

        반환: (eligible_count, total_count)
        """
        import json as _json
        ah_path = DATA_DIR / "afterhours_result.json"
        if not ah_path.exists():
            return 0, 0

        try:
            ah_data = _json.loads(ah_path.read_text(encoding="utf-8"))
            stocks  = ah_data.get("stocks", [])
            total   = len(stocks)

            if not (self.kiwoom and not self.paper):
                log.info(f"  사전 필터 생략(페이퍼/미연결) — {total}종목 그대로 사용")
                return total, total

            eligible, ineligible = [], []
            for s in stocks:
                ok, reason = self.kiwoom.is_nxt_eligible(s["code"])
                if ok:
                    eligible.append(s)
                    log.info(f"  ✅ 적격: {s['name']}({s['code']})")
                else:
                    ineligible.append((s, reason))
                    log.info(f"  ⛔ 사전제외: {s['name']}({s['code']}) — {reason}")

            log.info(f"사전 적격 필터: {len(eligible)}/{total}종목 통과")

            # 적격 < 5개 → 확장 조회 (ka10027 등락률순위에서 추가)
            MIN_POOL = 5
            if len(eligible) < MIN_POOL:
                excluded = {s["code"] for s in stocks}  # 이미 검사한 종목 재검사 방지
                log.warning(
                    f"사전 적격 종목 부족 ({len(eligible)}개 < {MIN_POOL}) "
                    f"— 확장 조회 시작"
                )
                eligible = self._expand_eligible_pool(eligible, excluded, target=MIN_POOL)

            # afterhours_result.json 을 적격 종목만으로 덮어씀
            # 원본은 afterhours_raw.json 에 백업
            raw_path = DATA_DIR / "afterhours_raw.json"
            raw_path.write_text(ah_path.read_text(encoding="utf-8"), encoding="utf-8")

            ah_data["stocks"]               = eligible
            ah_data["pre_filtered"]         = True
            ah_data["pre_filter_total"]     = total
            ah_data["pre_filter_eligible"]  = len(eligible)
            ah_path.write_text(
                _json.dumps(ah_data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            log.info(f"afterhours_result.json → 적격 {len(eligible)}종목으로 갱신")
            return len(eligible), total

        except Exception as e:
            log.error(f"사전 적격 필터 오류: {e}")
            return 0, 0

    def _expand_eligible_pool(
        self, current: list, excluded: set, target: int = 5
    ) -> list:
        """
        적격 종목 부족 시 ka10027 등락률순위에서 추가 탐색.

        current  : 이미 확보된 적격 종목 리스트 (in-place 확장)
        excluded : 이미 검사한 종목코드 집합 (재검사/재선정 방지)
        target   : 확보 목표 종목 수
        """
        if not (self.kiwoom and not self.paper):
            return current

        log.info(f"[확장 조회] 목표 {target}개 / 현재 {len(current)}개")
        try:
            candidates = []
            for market in ["0", "1"]:  # 코스피, 코스닥
                rows  = self.kiwoom.get_surge_ranking(market=market, top_n=100)
                label = "코스피" if market == "0" else "코스닥"
                for r in rows:
                    code = str(r.get("code", "")).zfill(6)
                    if not code or code in excluded:
                        continue
                    try:
                        rate_f    = float(
                            str(r.get("change_rate", 0)).replace("%", "").replace("+", "")
                        )
                        vol_i     = int(str(r.get("volume", 0)).replace(",", ""))
                        prev_v    = int(str(r.get("prev_volume", 1)).replace(",", "") or 1) or 1
                        vol_ratio = round(vol_i / prev_v, 1)
                        # 시간외 필터 조건 준용
                        if 1.0 <= rate_f <= 15.0 and vol_ratio >= 1.5:
                            candidates.append({
                                "code":        code,
                                "name":        r.get("name", ""),
                                "price":       str(r.get("price", "0")),
                                "change_rate": rate_f,
                                "volume":      vol_i,
                                "prev_volume": prev_v,
                                "vol_ratio":   vol_ratio,
                                "market":      label,
                                "source":      "ka10027_expand",
                            })
                            excluded.add(code)
                    except Exception:
                        pass

            # 등락률 내림차순 정렬 후 적격 확인
            candidates.sort(key=lambda x: x["change_rate"], reverse=True)
            for s in candidates:
                if len(current) >= target:
                    break
                ok, reason = self.kiwoom.is_nxt_eligible(s["code"])
                if ok:
                    current.append(s)
                    log.info(
                        f"  ✅ 확장 적격: {s['name']}({s['code']}) "
                        f"+{s['change_rate']}% 거래량{s['vol_ratio']}배"
                    )
                else:
                    log.info(f"  ⛔ 확장 부적격: {s['name']}({s['code']}) — {reason}")

            log.info(f"[확장 조회] 완료: {len(current)}종목 확보")
        except Exception as e:
            log.error(f"확장 조회 실패: {e}")
        return current

    def collect_afterhours(self):
        """[07:30] 시간외 단일가 수집 → 사전 적격 필터 → Claude 분석 → NXT 후보 확정

        플로우:
          STEP1   : afterhours_collector — 시간외 상위 20종목 수집
          STEP1.5 : _pre_filter_afterhours — 부적격 제거 → 적격 풀만 Claude에 전달
                    (적격 < 5개면 ka10027 확장 조회로 보충)
          STEP2   : signal_analyzer (Claude) — 적격 풀에서 3종목 선정
          STEP3   : _filter_nxt_eligible — 이중 안전장치 (STEP1.5 통과 후에도 확인)
          STEP4   : 폴백 — 시간외 전체 풀(afterhours_raw.json) 직접 스캔
        """
        log.info("[07:30] NXT STEP1 — 시간외 수집 시작")
        try:
            from surge_predictor.afterhours_collector import run as collect
            from surge_predictor.signal_analyzer import run as analyze, CANDIDATES_PATH
            import json as _json

            result = collect()
            if not result or result.get("count", 0) == 0:
                log.warning("시간외 종목 없음 — Claude 직접 분석으로 전환")

            # ── STEP1.5: Claude 분석 前 NXT 사전 적격 필터링 ──────────────
            # 부적격 종목을 afterhours_result.json 에서 미리 제거
            # → Claude 가 처음부터 장전거래 가능 종목만 보고 선정
            log.info("[07:30] NXT STEP1.5 — 사전 적격 필터링")
            eligible_pre, total_pre = self._pre_filter_afterhours()
            log.info(f"  사전 필터 완료: 적격 {eligible_pre} / 전체 {total_pre}종목")

            if total_pre > 0 and eligible_pre == 0:
                asyncio.run(self.notifier.send(
                    "⚠️ NXT 사전 필터: 시간외 종목 전원 장전거래 불가\n"
                    "확장 조회 결과도 0개 → 오늘 NXT 매수 없음 가능성 높음"
                ))
            elif eligible_pre < total_pre:
                asyncio.run(self.notifier.send(
                    f"🔍 NXT 사전 필터 완료\n"
                    f"적격 {eligible_pre}종목 / 전체 {total_pre}종목 "
                    f"({total_pre - eligible_pre}종목 사전제외)\n"
                    f"Claude 분석 시작 →"
                ))

            # ── STEP2: Claude 분석 (최대 3회 시도) ────────────────────────
            MAX_ATTEMPTS = 3
            candidates = None
            eligible_stocks: list = []
            all_skipped: list = []
            tried_codes: set = set()

            for attempt in range(1, MAX_ATTEMPTS + 1):
                log.info(f"[07:30] NXT STEP2 — Claude 시그널 분석 (시도 {attempt}/{MAX_ATTEMPTS})")
                analysis = analyze()
                if not analysis:
                    asyncio.run(self.notifier.send(f"⚠️ NXT 분석 실패 ({attempt}회차)"))
                    continue

                candidates = analysis.get("candidates", {})
                if candidates and candidates.get("stop"):
                    asyncio.run(self.notifier.send(
                        f"🚫 NXT 매매 중단\n"
                        f"사유: 나스닥 {candidates.get('nasdaq_change', 0):+.2f}% / "
                        f"VIX {candidates.get('vix', 0):.1f}"
                    ))
                    return

                stocks = candidates.get("stocks", []) if candidates else []
                # 이미 시도한 종목 제외
                new_stocks = [s for s in stocks if s["code"] not in tried_codes]
                tried_codes.update(s["code"] for s in stocks)

                if not new_stocks:
                    log.warning(f"  시도 {attempt}: 새 종목 없음 — 재시도")
                    continue

                # ── STEP3: 적격 필터링 ──────────────────────────────────
                log.info(f"[07:30] NXT STEP3 — 적격 필터링 (시도 {attempt})")
                eligible, skipped = self._filter_nxt_eligible(new_stocks)
                all_skipped.extend(skipped)

                if eligible:
                    eligible_stocks = eligible
                    log.info(f"  ✅ {attempt}회차에서 적격 종목 {len(eligible)}개 확보")
                    break
                else:
                    log.warning(f"  시도 {attempt}: 적격 종목 0개 — 재시도")
                    if attempt < MAX_ATTEMPTS:
                        asyncio.run(self.notifier.send(
                            f"🔄 NXT 재분석 중 ({attempt}/{MAX_ATTEMPTS})\n"
                            f"이전 후보 전원 부적격 — Claude 재시도"
                        ))

            # ── STEP4: 폴백 — 시간외 전체 풀 직접 스캔 ─────────────────
            if not eligible_stocks:
                log.warning("[07:30] NXT STEP4 — 폴백: 시간외 전체 풀 스캔")
                asyncio.run(self.notifier.send(
                    f"⚠️ Claude 후보 전원 부적격\n"
                    f"시간외 전체 풀에서 적격 종목 직접 탐색 중..."
                ))
                eligible_stocks = self._nxt_fallback_from_afterhours(tried_codes)
                if eligible_stocks:
                    log.info(f"  폴백 성공: {eligible_stocks[0]['name']} 선정")
                else:
                    log.error("  폴백 실패: 적격 종목 없음")

            # ── 부적격 알림 ───────────────────────────────────────────
            if all_skipped:
                skip_lines = "\n".join(
                    f"  ❌ {s['name']} ({s['code']}): {r}"
                    for s, r in all_skipped
                )
                asyncio.run(self.notifier.send(
                    f"⚠️ <b>NXT 부적격 제외 목록</b>\n{skip_lines}"
                ))

            # ── nxt_candidates.json 저장 ──────────────────────────────
            if candidates:
                updated = dict(candidates)
                updated["stocks"] = eligible_stocks
                updated["filtered_at"] = datetime.now().strftime("%H:%M:%S")
                CANDIDATES_PATH.write_text(
                    _json.dumps(updated, ensure_ascii=False, indent=2),
                    encoding="utf-8"
                )

            # ── 최종 결과 텔레그램 ────────────────────────────────────
            if eligible_stocks:
                stock_list = "\n".join(
                    f"  {i+1}. {s['name']} ({s['code']}) [{s['confidence']}]"
                    for i, s in enumerate(eligible_stocks)
                )
                asyncio.run(self.notifier.send(
                    f"✅ <b>NXT 최종 매수 대상</b>\n"
                    f"━━━━━━━━━━━━━━━━━\n"
                    f"{stock_list}\n\n"
                    f"⏰ 08:00 장전거래 매수 예정"
                ))
            else:
                asyncio.run(self.notifier.send(
                    "🚫 NXT 적격 종목 없음 — 오늘 매수 없음\n"
                    "(거래정지/관리종목/코넥스만 존재)"
                ))
            log.info(f"NXT 최종 후보: {len(eligible_stocks)}종목")

        except Exception as e:
            log.error(f"collect_afterhours 오류: {e}")
            asyncio.run(self.notifier.send(f"⚠️ NXT 수집 오류: {e}"))

    def execute_nxt_buy(self):
        """[08:00] NXT 장전거래 즉시 매수 — 총 예산의 40% 사용

        핵심 변경사항:
        - split_buy(TWAP, 09:30~15:00 전용) → nxt_buy(즉시매수, 장전거래용)
        - 예산 전액 1회 투입 (분할 없음)
        - 시간외 단일가 가격 우선 사용 (없으면 전일 종가 fallback)
        """
        if not self.auto_trading:
            return
        log.info("[08:00] NXT 매수 실행")

        from config.settings import TOTAL_CAPITAL, NXT_BUDGET_RATIO, NXT_MAX_STOCKS

        # 후보 종목 로드
        candidates_path = DATA_DIR / "nxt_candidates.json"
        if not candidates_path.exists():
            log.info("NXT 후보 없음 — 매수 스킵")
            return

        try:
            import json as _json
            candidates = _json.loads(candidates_path.read_text(encoding="utf-8-sig"))
        except Exception as e:
            log.error(f"NXT 후보 로드 실패: {e}")
            return

        if candidates.get("stop") or not candidates.get("stocks"):
            log.info("NXT 매매 중단 또는 후보 없음 — 스킵")
            return

        # 날짜 확인 — 오늘 분석된 후보인지 검증
        today = datetime.now().strftime("%Y-%m-%d")
        if candidates.get("date", "") != today:
            log.warning(f"NXT 후보 날짜 불일치: {candidates.get('date')} ≠ {today} — 오늘 07:30 분석 미실행 가능성")
            asyncio.run(self.notifier.send(
                f"⚠️ NXT 후보 날짜 불일치\n"
                f"후보날짜: {candidates.get('date', '없음')} / 오늘: {today}\n"
                f"07:30 수집이 정상 실행됐는지 확인하세요"
            ))
            return

        # 시간외 가격 + 갭 정보 맵 로드 (afterhours_result.json)
        # code → {"price": int, "change_rate": float, "vol_ratio": float}
        afterhours_prices = {}   # code → int (하위호환)
        afterhours_info   = {}   # code → 전체 정보 (갭 필터용)
        try:
            ah_path = DATA_DIR / "afterhours_result.json"
            if ah_path.exists():
                ah_data = _json.loads(ah_path.read_text(encoding="utf-8-sig"))
                for s in ah_data.get("stocks", []):
                    raw = str(s.get("price", "0")).replace(",", "").replace("+", "").replace("-", "")
                    try:
                        p = int(raw)
                        afterhours_prices[s["code"]] = p
                        afterhours_info[s["code"]] = {
                            "price":       p,
                            "change_rate": float(s.get("change_rate", 0)),
                            "vol_ratio":   float(s.get("vol_ratio", 0)),
                        }
                    except Exception:
                        pass
        except Exception as e:
            log.warning(f"시간외 가격 로드 실패: {e}")

        # NXT 예산 계산 (총 운용자본의 40%, 현금 초과 불가)
        nxt_budget = TOTAL_CAPITAL * NXT_BUDGET_RATIO   # 1000만 × 0.40 = 400만원
        cash_avail = min(self.portfolio.cash, nxt_budget)
        stocks     = candidates["stocks"][:NXT_MAX_STOCKS]
        per_stock  = cash_avail / len(stocks) if stocks else 0

        log.info(f"NXT 예산: {cash_avail:,.0f}원 / {len(stocks)}종목 / 종목당: {per_stock:,.0f}원")

        # 예산 부족 조기 종료 — portfolio.cash가 0이면 전량 스킵 방지
        if cash_avail <= 0:
            log.warning(f"NXT 매수 중단: 가용 현금 {self.portfolio.cash:,.0f}원 / 예산한도 {nxt_budget:,.0f}원 → 현금 부족")
            asyncio.run(self.notifier.send(
                f"⚠️ NXT 매수 불가\n"
                f"현금 잔고: {self.portfolio.cash:,.0f}원\n"
                f"portfolio.json 현금 확인 필요"
            ))
            return

        bought_list = []   # 텔레그램 요약용

        for s in stocks:
            code, name = s["code"], s["name"]
            if code in self.portfolio.holdings:
                log.info(f"{name} 이미 보유 — 스킵")
                continue

            # ── NXT 장전거래(08:00~08:50) 적격 여부 확인 ──
            if self.kiwoom and not self.paper:
                eligible, reason = self.kiwoom.is_nxt_eligible(code)
                if not eligible:
                    log.warning(f"NXT 부적격 종목 스킵: {name}({code}) — {reason}")
                    asyncio.run(self.notifier.send(
                        f"⚠️ <b>NXT 매수 스킵</b>\n"
                        f"종목: {name} ({code})\n"
                        f"사유: {reason}"
                    ))
                    continue
                log.info(f"NXT 적격 확인: {name}({code})")

            # ── 갭 크기 기반 예산 조정 (시간외 상관성 핵심 로직) ──────
            # 전일 종가 대비 시간외 등락률에 따라 매수 전략 차별화
            #   3~8%  : 최적 (추가 상승 여력 충분)  → 정상 예산
            #   8~15% : 주의 (차익실현 리스크 증가) → 예산 50%
            #   15%+  : 위험 (갭 과도, 정규장 매물 폭증 예상) → 스킵
            #   0~3%  : 신호 약함 → 뉴스/정책 트리거 강할 때만 진행
            ah_info   = afterhours_info.get(code) or {}
            # candidates.json의 change_rate 우선, afterhours_info 보조
            gap_rate  = float(s.get("change_rate") or ah_info.get("change_rate") or 0)
            vol_ratio = float(s.get("vol_ratio")   or ah_info.get("vol_ratio")   or 0)

            if gap_rate >= 15.0:
                log.warning(f"갭 필터: {name} 갭 {gap_rate:.1f}% 과도 → 스킵 (정규장 차익매물 위험)")
                asyncio.run(self.notifier.send(
                    f"⚠️ <b>NXT 갭 과도 스킵</b>\n"
                    f"종목: {name} ({code})\n"
                    f"갭: {gap_rate:.1f}% → 15% 초과, 정규장 차익매물 위험"
                ))
                continue
            elif gap_rate >= 8.0:
                stock_budget_ratio = s.get("budget_ratio", 0.5)
                log.info(f"갭 주의: {name} 갭 {gap_rate:.1f}% → 예산 {stock_budget_ratio*100:.0f}% 투입")
            else:
                stock_budget_ratio = s.get("budget_ratio", 1.0)
                if gap_rate > 0:
                    log.info(f"갭 정상: {name} 갭 {gap_rate:.1f}% / 거래량비율 {vol_ratio:.1f}배 → 전액 투입")

            stock_budget = per_stock * stock_budget_ratio

            # ── 진입가: 시간외 단일가 → 전일 종가 fallback ────────────
            price = afterhours_prices.get(code, 0)
            if not price:
                ohlcv = get_stock_ohlcv(code, 5)
                if ohlcv.empty:
                    log.warning(f"{name}: 가격 데이터 없음 — 스킵")
                    continue
                price = int(ohlcv["close"].iloc[-1])
                log.info(f"{name}: 시간외 가격 없음 → 전일 종가 {price:,}원 사용")

            # NXT 즉시매수 (장전거래 전용, TWAP/분할 없음)
            result = self.executor.nxt_buy(code, name, stock_budget, price)
            if result.status in ("FILLED", "PARTIAL"):
                self.portfolio.add_holding(
                    code, name, "nxt", "NXT",
                    result.avg_price, result.total_qty, 1
                )
                trade_data = {
                    "code": code, "name": name, "side": "NXT매수",
                    "qty": result.total_qty, "price": result.avg_price,
                    "amount": result.total_amount,
                    "trigger": "NXT Phase1",
                    "reason": f"신뢰도 {s.get('confidence', '-')}",
                }
                asyncio.run(self.notifier.send_trade_alert(trade_data))
                bought_list.append({
                    "name": name,
                    "qty":  result.total_qty,
                    "price": result.avg_price,
                })
            else:
                log.error(f"{name} NXT 매수 실패")

        bought = len(bought_list)
        log.info(f"NXT buy done: {bought}/{len(stocks)}종목 / 현금: {self.portfolio.cash:,.0f}원")

        total_invested = sum(b["qty"] * b["price"] for b in bought_list)
        asyncio.run(self.notifier.send_nxt_buy_summary(
            bought_list,
            total_invested=total_invested,
            cash=self.portfolio.cash,
        ))

    def monitor_nxt_positions(self):
        """
        [08:00~10:30] NXT 포지션 갭다운 손절 모니터링 (2분 간격)

        손절 주문 타입 자동 선택:
          08:00~08:50 — nxt_sell()  trde_tp=61 (장전시간외 단일가)
          09:00~10:30 — sell()      trde_tp=3  (정규장 시장가)
        """
        nxt_holdings = {
            code: h for code, h in self.portfolio.holdings.items()
            if getattr(h, "category", "") == "nxt"
        }
        if not nxt_holdings:
            return

        from config.settings import NXT_STOP_LOSS_PCT
        now_str = datetime.now().strftime("%H:%M")
        if now_str > "10:30":
            return  # close_nxt_positions 가 처리

        # 현재 장전거래 시간(08:00~08:50)인지 정규장 시간(09:00~)인지 판별
        is_premarket = now_str < "08:50"

        for code, holding in list(nxt_holdings.items()):
            ohlcv = get_stock_ohlcv(code, 5)
            if ohlcv.empty:
                continue
            current = ohlcv["close"].iloc[-1]
            change  = (current - holding.avg_price) / holding.avg_price

            if change <= -NXT_STOP_LOSS_PCT:
                log.warning(f"NXT 손절 [{holding.name}]: {change:.1%} ({'장전' if is_premarket else '정규장'})")
                if is_premarket:
                    # 08:00~08:50 장전거래 — trde_tp=61 (장전시간외)
                    result = self.executor.nxt_sell(
                        code, holding.name, holding.quantity, current, "NXT_STOP_LOSS"
                    )
                else:
                    # 09:00~10:30 정규장 — trde_tp=3 (시장가)
                    result = self.executor.sell(
                        code, holding.name, holding.quantity, current, "NXT_STOP_LOSS"
                    )
                if result.status == "FILLED":
                    pnl = self.portfolio.remove_holding(code, result.total_qty, result.avg_price)
                    asyncio.run(self.notifier.send(
                        f"🔴 <b>NXT 손절</b> {holding.name}\n"
                        f"수익률: {change:+.1%}\n"
                        f"{'장전시간외' if is_premarket else '정규장 시장가'} 체결"
                    ))

    def close_nxt_positions(self):
        """[10:30] NXT 잔여 포지션 전량 강제 청산"""
        nxt_holdings = {
            code: h for code, h in self.portfolio.holdings.items()
            if getattr(h, "category", "") == "nxt"
        }
        if not nxt_holdings:
            log.info("[10:30] NXT 포지션 없음")
            return

        log.info(f"[10:30] NXT 강제 청산: {len(nxt_holdings)}종목")
        results_summary = []

        for code, holding in list(nxt_holdings.items()):
            ohlcv = get_stock_ohlcv(code, 5)
            if ohlcv.empty:
                continue
            current = ohlcv["close"].iloc[-1]
            change  = (current - holding.avg_price) / holding.avg_price

            result = self.executor.sell(
                code, holding.name, holding.quantity, current, "NXT_DEADLINE"
            )
            if result.status == "FILLED":
                pnl = self.portfolio.remove_holding(code, result.total_qty, result.avg_price)
                results_summary.append(
                    f"{'🟢' if change >= 0 else '🔴'} {holding.name}: {change:+.1%}"
                )

        realized_pnl = sum(
            (self.portfolio.cash - h.avg_price * h.quantity)
            for h in nxt_holdings.values()
            if hasattr(h, "avg_price")
        )
        asyncio.run(self.notifier.send_nxt_close_summary(
            results_summary,
            realized_pnl=0,  # 실제 PNL은 portfolio.remove_holding 반환값에서 집계 필요
            cash=self.portfolio.cash,
        ))

    def collect_surge_top50(self):
        """
        [10:30] 급상승 Top50 스냅샷 수집 → data/store/surge_db.json 누적 저장
        - 키움 ka10027(주식등락률순위) 우선, pykrx 폴백
        - signal_engine._generate_signals() 에서 surge_score 를 추가 가중치로 활용
        - NXT collect_afterhours() 에서 surge_count 로 종목 신뢰도 보강 가능
        """
        log.info("[10:30] 급상승 Top50 수집 시작")
        try:
            from data.surge_tracker import collect as surge_collect
            stocks = surge_collect(top_n=50)
            if not stocks:
                log.warning("급상승 Top50 데이터 없음 — 소스 응답 실패")
                asyncio.run(self.notifier.send("⚠️ 급상승 Top50 수집 실패 (ka10027 + pykrx 모두 응답 없음)"))
                return

            top5 = "\n".join(
                f"  {s['rank']}. {s['name']} ({s['code']}) {s['change_rate']:+.1f}%"
                for s in stocks[:5]
            )
            asyncio.run(self.notifier.send(
                f"📈 <b>급상승 Top50 수집 완료</b> [{datetime.now():%H:%M}]\n"
                f"{top5}\n"
                f"  … 외 {len(stocks)-5}종목 / DB 누적 저장"
            ))
            log.info(f"급상승 Top50 저장 완료 (1위: {stocks[0]['name']} {stocks[0]['change_rate']:+.1f}%)")
        except Exception as e:
            log.error(f"collect_surge_top50 오류: {e}")

    def update_nxt_result(self):
        """[16:10] NXT 청산 결과 → 패턴DB 업데이트 + 텔레그램 결과 전송"""
        log.info("[16:10] NXT pattern DB update")
        today_nxt_summary = {"wins": 0, "losses": 0, "realized_pnl": 0}
        try:
            trades_path = DATA_DIR / "trades.json"
            if not trades_path.exists():
                asyncio.run(self.notifier.send(
                    "🔍 <b>NXT 패턴DB</b>\n오늘 거래 기록 없음"
                ))
                return
            trades = json.loads(trades_path.read_text(encoding="utf-8-sig"))
            today  = datetime.now().strftime("%Y-%m-%d")
            nxt_trades = [
                t for t in trades
                if t.get("trigger", "").startswith("NXT")
                and t.get("date", t.get("timestamp", ""))[:10] == today
                and t.get("side") in ("NXT청산", "NXT손절")
            ]

            # 오늘 NXT 성과 집계
            for t in nxt_trades:
                pnl = t.get("pnl", 0)
                today_nxt_summary["realized_pnl"] += pnl
                if pnl >= 0:
                    today_nxt_summary["wins"] += 1
                else:
                    today_nxt_summary["losses"] += 1

            if nxt_trades:
                from surge_predictor.pattern_updater import update_with_nxt_result
                update_with_nxt_result(nxt_trades)

        except Exception as e:
            log.error(f"NXT pattern update error: {e}")

        # 패턴DB 읽어서 텔레그램 전송
        try:
            pattern_path = DATA_DIR / "store" / "pattern_db.json"
            pattern_data = {}
            if pattern_path.exists():
                pattern_data = json.loads(pattern_path.read_text(encoding="utf-8-sig"))
            asyncio.run(self.notifier.send_nxt_pattern_result(pattern_data, today_nxt_summary))
        except Exception as e:
            log.error(f"NXT pattern result send error: {e}")
            asyncio.run(self.notifier.send(
                f"🔍 <b>NXT 패턴DB 업데이트 완료</b>\n"
                f"오늘 손익: {today_nxt_summary['realized_pnl']:+,.0f}원"
            ))

    # ── 텔레그램 명령 콜백 ──

    def handle_telegram_command(self, command: str) -> str:
        if command == "audit":
            try:
                from core.audit import run_audit
                return run_audit(self)
            except Exception as e:
                log.error(f"audit 오류: {e}")
                return f"❌ 통합점검 오류: {e}"

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
        log.info("[signal] 시장 데이터 조회 시작")
        kospi_df = get_kospi_ohlcv(60)
        usdkrw_df = get_usdkrw(14)
        vkospi = get_vkospi()
        log.info(f"[signal] 코스피 {len(kospi_df)}행 / VKOSPI {vkospi}")
        market = analyze_market(kospi_df, vkospi, usdkrw_df) if not kospi_df.empty else None
        if market is None:
            log.warning("[signal] 시장 데이터 없음 — 시그널 생성 스킵")
            return []
        log.info(f"[signal] 시장 판단: {market.kospi_trend} / 점수 {market.score:.0f}")

        news_scores = {
            code: self.news_analyzer.get_stock_news_score(code, self._cached_news)
            for code in get_unique_codes()
        }

        from config.universe import get_stock_name
        codes = get_unique_codes()
        # 급상승 DB 로드 (surge_score 보정용)
        try:
            from data.surge_tracker import get_surge_score
            _surge_score_fn = get_surge_score
        except Exception:
            _surge_score_fn = None

        log.info(f"[signal] 종목 OHLCV 조회 시작: {len(codes)}종목")
        tech_signals = []
        for i, code in enumerate(codes, 1):
            ohlcv = get_stock_ohlcv(code, 120)
            if len(ohlcv) < 30:
                log.debug(f"[signal] {code} 데이터 부족({len(ohlcv)}행) — 스킵")
                continue
            ts = tech_analyze(ohlcv, code, get_stock_name(code))
            funda = get_fundamentals(code)
            if funda:
                ts.per = funda.get("per")
                ts.pbr = funda.get("pbr")
                ts.roe = funda.get("roe")
                ts.div_yield = funda.get("div_yield")
            # 급상승 이력 보정: 최근 20일 surge_score → news_score 에 최대 +10 가산
            if _surge_score_fn:
                try:
                    sc = _surge_score_fn(code, days=20)
                    if sc > 0:
                        ts.news_score = getattr(ts, "news_score", 0) + sc * 10
                        log.debug(f"[signal] {code} surge_score={sc:.3f} → news_score 보정")
                except Exception:
                    pass
            tech_signals.append(ts)
            if i % 10 == 0:
                log.info(f"[signal] OHLCV 진행: {i}/{len(codes)}")

        log.info(f"[signal] 시그널 생성: {len(tech_signals)}종목 분석 완료")
        signals = self.signal_engine.generate_batch_signals(tech_signals, market, news_scores)
        buy_count = sum(1 for s in signals if s.action == "BUY")
        log.info(f"[signal] 결과 — BUY:{buy_count} / 전체:{len(signals)}")
        return signals

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


# ── 대시보드 Watchdog ──

_dashboard_proc = None  # 전역 참조 (종료 시 정리용)


def _start_dashboard_proc() -> subprocess.Popen:
    """대시보드 서버 subprocess 시작"""
    script = Path(__file__).parent / "dashboard" / "server.py"
    return subprocess.Popen(
        [sys.executable, str(script)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )


def _dashboard_watchdog():
    """
    대시보드 프로세스 감시 — 10초 주기로 살아있는지 확인
    죽었으면 자동 재시작. main.py 가 살아있는 한 대시보드도 살아있다.
    """
    global _dashboard_proc
    while True:
        if _dashboard_proc is None or _dashboard_proc.poll() is not None:
            if _dashboard_proc is not None:
                log.warning("대시보드 프로세스 종료 감지 — 자동 재시작")
            try:
                _dashboard_proc = _start_dashboard_proc()
                log.info(f"대시보드 서버 기동 (PID: {_dashboard_proc.pid}, 포트 8080)")
            except Exception as e:
                log.error(f"대시보드 재시작 실패: {e}")
        time.sleep(10)


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

    # 대시보드 서버 — watchdog 스레드로 24/7 유지
    dash_thread = threading.Thread(target=_dashboard_watchdog, daemon=True, name="DashboardWatchdog")
    dash_thread.start()
    log.info("대시보드 watchdog 시작 (포트 8080, 자동 재시작)")

    # 텔레그램 명령 봇 — 별도 스레드로 실행
    def run_cmd_bot():
        try:
            engine.cmd_bot.run_in_thread()
        except Exception as e:
            log.error(f"텔레그램 명령 봇 오류: {e}")

    cmd_thread = threading.Thread(target=run_cmd_bot, daemon=True, name="TelegramCmdBot")
    cmd_thread.start()
    log.info("텔레그램 명령 봇 시작 (/help, /status, /balance 등 사용 가능)")

    log.info("KangSub Bot 가동 중... (Ctrl+C 로 종료)")
    try:
        while engine.running:
            time.sleep(60)
    except KeyboardInterrupt:
        log.info("종료 신호 수신")
        scheduler.stop()
        if _dashboard_proc and _dashboard_proc.poll() is None:
            _dashboard_proc.terminate()
            log.info("대시보드 서버 종료")
        log.info("KangSub Bot 종료")
