"""텔레그램 봇 — 양방향 알림 + 명령 처리"""
import sys
import time
import asyncio

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from datetime import datetime
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, ContextTypes
from config.settings import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
from utils.logger import setup_logger

log = setup_logger("telegram_bot")


class TelegramNotifier:
    """단방향 알림 전송용 (매매엔진에서 사용)"""

    def __init__(self, token: str = None, chat_id: str = None):
        self.token = token or TELEGRAM_TOKEN
        self.chat_id = chat_id or TELEGRAM_CHAT_ID
        self.bot = Bot(token=self.token) if self.token else None

    def _send_http(self, message: str, parse_mode: str = "HTML") -> bool:
        """
        requests.post() 직접 호출 — asyncio/event loop 완전 독립.
        asyncio.run()이 event loop를 매번 생성/파괴하면서
        python-telegram-bot의 내부 httpx client가 무효화되는 문제 방지.
        """
        try:
            import requests as _req
            resp = _req.post(
                f"https://api.telegram.org/bot{self.token}/sendMessage",
                json={
                    "chat_id":    self.chat_id,
                    "text":       message[:4096],
                    "parse_mode": parse_mode,
                },
                timeout=10,
            )
            if resp.ok:
                log.info(f"Telegram sent: {message[:50]}...")
                return True
            else:
                log.error(f"Telegram HTTP 오류: {resp.status_code} {resp.text[:100]}")
                return False
        except Exception as e:
            log.error(f"Telegram send failed: {e}")
            return False

    async def send(self, message: str, parse_mode: str = "HTML"):
        """비동기 전송 — 내부적으로 동기 HTTP 사용 (event loop 독립)"""
        if not self.token or not self.chat_id:
            log.warning("Telegram not configured")
            return
        self._send_http(message, parse_mode)

    def send_sync(self, message: str):
        """동기 함수에서 직접 호출용"""
        if not self.token or not self.chat_id:
            return
        self._send_http(message)

    # ═══════════════════════════════════════════════
    # 기본 알림 메서드
    # ═══════════════════════════════════════════════

    async def send_trade_alert(self, trade: dict):
        if trade["side"] in ("NXT매수", "NXT청산", "NXT손절"):
            emoji = "📡🟢" if trade["side"] == "NXT매수" else ("📡🔴" if "손절" in trade["side"] else "📡⬜")
        else:
            emoji = "🟢" if trade["side"] == "매수" else "🔴"
        msg = (
            f"{emoji} <b>{trade['side']} 체결</b>\n"
            f"종목: {trade['name']} ({trade['code']})\n"
            f"수량: {trade['qty']:,}주\n"
            f"단가: {trade['price']:,.0f}원\n"
            f"금액: {trade['amount']:,.0f}원\n"
            f"사유: {trade.get('reason', '-')}\n"
            f"시각: {datetime.now():%H:%M:%S}"
        )
        await self.send(msg)

    async def send_stop_loss_alert(self, alert: dict):
        alert_type = alert.get('type', '?')
        name = alert.get('name', '')
        code = alert.get('code', '')

        if False:  # PORTFOLIO_MAX_LOSS 전량매도 제거됨
            pass
        else:
            stock_line = f"종목: {name} ({code})\n" if name or code else ""
            msg = (
                f"🚨 <b>손절매 트리거!</b>\n"
                f"유형: {alert_type}\n"
                f"{stock_line}"
            )
            if alert_type == "INDEX_STOP_LOSS":
                msg += (
                    f"종목 등락: {alert.get('stock_change', 0):+.1%}\n"
                    f"코스피: {alert.get('kospi_change', 0):+.1%}\n"
                    f"갭: {alert.get('gap', 0):+.1%} (한도 -10%p)\n"
                )
            elif alert_type == "TRAILING_STOP":
                msg += (
                    f"수익률: {alert.get('pnl_pct', 0):+.1%}\n"
                    f"고점: {alert.get('high_price', 0):,.0f}원\n"
                    f"현재: {alert.get('current_price', 0):,.0f}원\n"
                    f"하락: {alert.get('drawdown', 0):.1%} (한도 {alert.get('threshold', 0):.0%})\n"
                )
            msg += f"조치: {alert.get('action', '-')}"
        await self.send(msg)

    # ═══════════════════════════════════════════════
    # 데일리 스케줄 통합 메시지 (정규장 + NXT)
    # ═══════════════════════════════════════════════

    async def send_morning_briefing(self, briefing: dict):
        """08:30 모닝 브리핑 (레거시 호환용)"""
        await self.send_morning_briefing_integrated(briefing)

    async def send_morning_briefing_integrated(self, briefing: dict):
        """08:30 통합 모닝 브리핑 — 정규장 + NXT 현황 포함"""
        nxt_stocks   = briefing.get("nxt_stocks", 0)
        nxt_invested = briefing.get("nxt_invested", 0.0)

        if nxt_stocks > 0:
            nxt_section = (
                f"\n📡 <b>NXT 진행중</b> (08:00~10:30)\n"
                f"매수종목: {nxt_stocks}개 | 투입: {nxt_invested:,.0f}원\n"
            )
        else:
            nxt_section = "\n📡 <b>NXT</b>: 오늘 매수 없음\n"

        msg = (
            f"☀️ <b>통합 모닝 브리핑</b> ({datetime.now():%Y-%m-%d})\n"
            f"{'═' * 28}\n"
            f"📈 <b>시장 현황</b>\n"
            f"코스피: {briefing.get('kospi', '-')}\n"
            f"시장상태: {briefing.get('market_status', '-')}\n"
            f"환율: {briefing.get('usdkrw', '-')}"
            f"{nxt_section}"
            f"{'─' * 28}\n"
            f"📰 <b>주요 뉴스</b>\n{briefing.get('news_summary', '없음')}\n"
            f"{'─' * 28}\n"
            f"🎯 <b>정규장 매매 계획</b>\n{briefing.get('trade_plan', '해당없음 (관망)')}\n"
        )
        await self.send(msg)

    async def send_nxt_buy_summary(self, bought: list, total_invested: float, cash: float):
        """08:00 NXT 장전매수 완료 요약"""
        if not bought:
            await self.send(
                "📡 <b>NXT 장전매수 — 해당없음</b>\n"
                "조건 미충족 또는 후보 없음\n"
                "정규장(09:30)만 운영"
            )
            return
        lines = "\n".join(
            f"  {i+1}. {s['name']} {s['qty']:,}주 @ {s['price']:,.0f}원"
            for i, s in enumerate(bought)
        )
        msg = (
            f"📡🟢 <b>NXT 장전매수 완료</b> (08:00)\n"
            f"{'─' * 28}\n"
            f"{lines}\n"
            f"{'─' * 28}\n"
            f"💰 총 투입: {total_invested:,.0f}원\n"
            f"🏦 현금잔고: {cash:,.0f}원\n"
            f"⏱ 목표: 급등 포착 후 10:30 강제청산"
        )
        await self.send(msg)

    async def send_nxt_close_summary(self, results: list, realized_pnl: float, cash: float):
        """10:30 NXT 강제청산 결과"""
        if not results:
            await self.send(
                f"⏱ <b>NXT 10:30 청산</b>\n"
                f"오늘 NXT 포지션 없음"
            )
            return

        pnl_emoji = "🟢" if realized_pnl >= 0 else "🔴"
        lines = "\n".join(results)
        msg = (
            f"⏱ <b>NXT 10:30 강제청산 완료</b>\n"
            f"{'═' * 28}\n"
            f"{lines}\n"
            f"{'─' * 28}\n"
            f"{pnl_emoji} NXT 실현손익: {realized_pnl:+,.0f}원\n"
            f"💰 현금잔고: {cash:,.0f}원\n"
            f"📌 정규장 전환 완료 (09:30 매수 진행중)"
        )
        await self.send(msg)

    async def send_midday_integrated(self, portfolio: dict, nxt_result: dict):
        """12:00 중간 현황 — 정규장 포지션 + NXT 청산 결과"""
        nxt_pnl    = nxt_result.get("realized_pnl", 0)
        nxt_trades = nxt_result.get("trades", [])

        if nxt_trades:
            trade_lines = " / ".join(
                f"{t.get('name', '?')} {t.get('change_pct', 0):+.1f}%"
                for t in nxt_trades[:4]
            )
            pnl_emoji  = "🟢" if nxt_pnl >= 0 else "🔴"
            nxt_section = (
                f"\n[NXT 결과 — 10:30 청산 완료]\n"
                f"{pnl_emoji} 실현손익: {nxt_pnl:+,.0f}원\n"
                f"종목: {trade_lines}\n"
            )
        else:
            nxt_section = "\n[NXT] 오늘 거래 없음\n"

        msg = (
            f"🕛 <b>중간 현황</b> ({datetime.now():%H:%M})\n"
            f"{'═' * 28}\n"
            f"[정규장]\n"
            f"총 평가: {portfolio['total_value']:,.0f}원\n"
            f"수익률: {portfolio['total_pnl']:+.1%}\n"
            f"보유: {portfolio['num_holdings']}종목"
            f"{nxt_section}"
            f"{'─' * 28}\n"
            f"💰 현금잔고: {portfolio['cash']:,.0f}원"
        )
        await self.send(msg)

    async def send_market_close_snapshot(self, summary: dict, holdings_detail: list):
        """15:40 정규장 마감 스냅샷"""
        hold_lines = ""
        for h in holdings_detail[:6]:
            pct = h.get("pnl_pct", 0.0)
            emoji = "🟢" if pct >= 0 else "🔴"
            hold_lines += f"{emoji} {h['name']}: {pct:+.1f}%\n"

        msg = (
            f"📷 <b>정규장 마감 스냅샷</b> (15:40)\n"
            f"{'═' * 28}\n"
            f"총 평가: {summary['total_value']:,.0f}원\n"
            f"수익률: {summary['total_pnl']:+.1%}\n"
            f"보유: {summary['num_holdings']}종목\n"
        )
        if hold_lines:
            msg += f"{'─' * 28}\n{hold_lines}"
        msg += f"💰 현금: {summary['cash']:,.0f}원"
        await self.send(msg)

    async def send_nxt_pattern_result(self, pattern: dict, today_nxt: dict):
        """16:10 NXT 패턴DB 업데이트 결과"""
        hit_rate   = pattern.get("overall_hit_rate", 0.0)
        total_days = pattern.get("total_days", 0)
        recent_7   = pattern.get("daily_results", [])[-7:]
        dot_row    = " ".join(
            "🟢" if r.get("hit_rate", 0) >= 0.5 else "🔴"
            for r in recent_7
        ) or "데이터 없음"

        today_wins = today_nxt.get("wins", 0)
        today_loss = today_nxt.get("losses", 0)
        today_pnl  = today_nxt.get("realized_pnl", 0)
        pnl_emoji  = "🟢" if today_pnl >= 0 else "🔴"

        msg = (
            f"🔍 <b>NXT 패턴DB 업데이트</b> (16:10)\n"
            f"{'═' * 28}\n"
            f"오늘 성과: 🟢 {today_wins}개 수익 / 🔴 {today_loss}개 손실\n"
            f"{pnl_emoji} 오늘 실현손익: {today_pnl:+,.0f}원\n"
            f"{'─' * 28}\n"
            f"누적 적중률: {hit_rate:.1%} ({total_days}일 기준)\n"
            f"최근 7일: {dot_row}\n"
            f"{'─' * 28}\n"
            f"📅 내일 NXT 일정\n"
            f"07:00 뉴스수집 → 07:30 시간외분석\n"
            f"08:00 장전매수 → 10:30 강제청산"
        )
        await self.send(msg)

    async def send_daily_report(self, report: dict):
        """17:00 일일 리포트 (레거시 호환용)"""
        await self.send_daily_report_integrated(report)

    async def send_daily_report_integrated(self, report: dict):
        """17:00 일일 종합 리포트 — 정규장 + NXT 통합"""
        nxt_pnl    = report.get("nxt_realized_pnl", 0)
        nxt_count  = report.get("nxt_trade_count", 0)
        nxt_emoji  = "🟢" if nxt_pnl >= 0 else "🔴"

        msg = (
            f"📊 <b>일일 종합 리포트</b> ({datetime.now():%Y-%m-%d})\n"
            f"{'═' * 30}\n"
            f"[정규장]\n"
            f"총 평가금액: {report['total_value']:,.0f}원\n"
            f"일간 수익률: {report.get('daily_pnl', 0):+.1%}\n"
            f"누적 수익률: {report['total_pnl']:+.1%}\n"
            f"매수 {report.get('buys', 0)}건 / 매도 {report.get('sells', 0)}건\n"
            f"{'─' * 30}\n"
            f"[NXT 급상승 전략]\n"
            f"{nxt_emoji} 실현손익: {nxt_pnl:+,.0f}원\n"
            f"거래: {nxt_count}건\n"
            f"{'─' * 30}\n"
            f"💰 현금잔고: {report['cash']:,.0f}원\n"
            f"📦 보유종목: {report['num_holdings']}개\n"
            f"{'─' * 30}\n"
            f"📅 내일 예정\n"
            f"06:00 점검 → 07:00 뉴스 → 07:30 NXT분석\n"
            f"08:00 NXT매수 → 09:30 정규매수"
        )
        await self.send(msg)


class TelegramCommandBot:
    """양방향 명령 처리 봇 (별도 스레드로 실행)"""

    def __init__(self, token: str = None, engine_callback=None):
        self.token = token or TELEGRAM_TOKEN
        self.engine_callback = engine_callback
        self.app = None

    def build(self):
        self.app = Application.builder().token(self.token).build()
        self.app.add_handler(CommandHandler("status",   self.cmd_status))
        self.app.add_handler(CommandHandler("balance",  self.cmd_balance))
        self.app.add_handler(CommandHandler("holdings", self.cmd_holdings))
        self.app.add_handler(CommandHandler("signals",  self.cmd_signals))
        self.app.add_handler(CommandHandler("risk",     self.cmd_risk))
        self.app.add_handler(CommandHandler("pause",    self.cmd_pause))
        self.app.add_handler(CommandHandler("resume",   self.cmd_resume))
        self.app.add_handler(CommandHandler("sync",     self.cmd_sync))
        self.app.add_handler(CommandHandler("help",     self.cmd_help))
        self.app.add_handler(CommandHandler("audit",    self.cmd_audit))
        self.app.add_handler(CommandHandler("run_now",  self.cmd_run_now))
        self.app.add_handler(CommandHandler("buy_now",  self.cmd_buy_now))
        self.app.add_handler(CommandHandler("signal",   self.cmd_signal_check))
        self.app.add_handler(CommandHandler("set_cash", self.cmd_set_cash))
        return self

    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if self.engine_callback:
            result = self.engine_callback("status")
            await update.message.reply_text(result, parse_mode="HTML")
        else:
            await update.message.reply_text("Engine not connected")

    async def cmd_balance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if self.engine_callback:
            result = self.engine_callback("balance")
            await update.message.reply_text(result, parse_mode="HTML")

    async def cmd_holdings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if self.engine_callback:
            result = self.engine_callback("holdings")
            await update.message.reply_text(result, parse_mode="HTML")

    async def cmd_signals(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if self.engine_callback:
            result = self.engine_callback("signals")
            await update.message.reply_text(result, parse_mode="HTML")

    async def cmd_risk(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if self.engine_callback:
            result = self.engine_callback("risk")
            await update.message.reply_text(result, parse_mode="HTML")

    async def cmd_pause(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if self.engine_callback:
            self.engine_callback("pause")
            await update.message.reply_text("Paused auto-trading")

    async def cmd_resume(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if self.engine_callback:
            self.engine_callback("resume")
            await update.message.reply_text("Resumed auto-trading")

    async def cmd_sync(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """git pull → 봇 재시작 (Task Scheduler Stop/Start)"""
        import subprocess, sys
        BOT_DIR = "C:\\kangsub_bot"
        GIT_EXE = "C:\\Program Files\\Git\\bin\\git.exe"

        await update.message.reply_text("🔄 git pull 시작...")

        # 1) git pull (절대경로 + 작업 디렉토리 명시)
        git_cmd = GIT_EXE if __import__("os").path.exists(GIT_EXE) else "git"
        try:
            r = subprocess.run(
                [git_cmd, "-C", BOT_DIR, "pull"],
                capture_output=True, text=True, timeout=30
            )
            out = (r.stdout + r.stderr).strip()[:400] or "변경 없음"
        except Exception as e:
            await update.message.reply_text(f"❌ git pull 실패: {e}")
            return

        await update.message.reply_text(f"📥 git pull 완료:\n{out}\n\n⏳ 봇 재시작 중... (30초 후 재가동)")

        # 2) Task Scheduler Stop → Start (5초 후 실행 → reply 전달 시간 확보)
        restart_cmd = (
            "Start-Sleep 5; "
            "Stop-ScheduledTask -TaskName KangSubBot -ErrorAction SilentlyContinue; "
            "Start-Sleep 5; "
            "Start-ScheduledTask -TaskName KangSubBot"
        )
        subprocess.Popen(
            ["powershell", "-NonInteractive", "-Command", restart_cmd],
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )

    async def cmd_audit(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("Running audit...")
        if self.engine_callback:
            result = self.engine_callback("audit")
            await update.message.reply_text(result, parse_mode="HTML")
        else:
            await update.message.reply_text("Engine not connected")

    async def cmd_run_now(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """뉴스수집→시그널분석→PAM매수 전체 체인 수동 실행"""
        if self.engine_callback:
            result = self.engine_callback("run_now")
            await update.message.reply_text(result, parse_mode="HTML")

    async def cmd_buy_now(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """즉시 PAM 매수 실행 (시그널 재생성 없이)"""
        if self.engine_callback:
            result = self.engine_callback("buy_now")
            await update.message.reply_text(result, parse_mode="HTML")

    async def cmd_signal_check(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """현재 BUY 시그널 조회"""
        if self.engine_callback:
            result = self.engine_callback("signal")
            await update.message.reply_text(result, parse_mode="HTML")

    async def cmd_set_cash(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """현금 수동 업데이트: /set_cash 15071418"""
        args = context.args
        if not args:
            await update.message.reply_text("사용법: /set_cash 15071418")
            return
        if self.engine_callback:
            result = self.engine_callback(f"set_cash {args[0]}")
            await update.message.reply_text(result, parse_mode="HTML")

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        msg = (
            "📌 <b>KangSub Bot Commands</b>\n"
            "/status — 시스템 상태\n"
            "/balance — 현금 잔고\n"
            "/holdings — 보유 종목\n"
            "/signals — 오늘 시그널\n"
            "/signal — BUY 시그널 즉시 조회\n"
            "/risk — 리스크 상태\n"
            "/pause — 자동매매 일시정지\n"
            "/resume — 자동매매 재개\n"
            "/run_now — 잡 체인 즉시 실행 (뉴스→시그널→매수)\n"
            "/buy_now — PAM 매수 즉시 실행\n"
            "/set_cash 15071418 — 현금 수동 업데이트\n"
            "/sync — Git pull 업데이트\n"
            "/audit — 통합 점검\n"
            "/help — 이 도움말"
        )
        await update.message.reply_text(msg, parse_mode="HTML")

    def run(self):
        if self.app is None:
            self.build()
        log.info("Telegram bot starting")
        self.app.run_polling()

    def run_in_thread(self):
        """서브 스레드에서 안전하게 실행 — Conflict 자동 재시도"""
        import asyncio
        from telegram.error import Conflict

        retry_delay = 90   # 첫 재시도: 90초
        attempt = 0

        while True:
            attempt += 1
            # 재시도 시 app 재생성 (이전 세션 상태 초기화)
            if attempt > 1:
                self.app = None
            if self.app is None:
                self.build()

            async def _polling():
                async with self.app:
                    await self.app.start()
                    await self.app.updater.start_polling(drop_pending_updates=True)
                    log.info(f"Telegram bot polling started (attempt {attempt})")
                    await asyncio.Event().wait()

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(_polling())
                break  # 정상 종료
            except Conflict:
                log.warning(
                    f"Telegram Conflict 감지 (attempt {attempt}) — "
                    f"{retry_delay}초 후 자동 재시도"
                )
                try:
                    loop.close()
                except Exception:
                    pass
                time.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 300)  # 최대 5분까지 증가
            except Exception as e:
                log.error(f"Telegram bot error: {e}")
                break
            finally:
                try:
                    loop.close()
                except Exception:
                    pass
