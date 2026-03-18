"""텔레그램 봇 — 양방향 알림 + 명령 처리"""
import sys
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

    async def send(self, message: str, parse_mode: str = "HTML"):
        if not self.bot or not self.chat_id:
            log.warning("텔레그램 설정 미완료")
            return
        try:
            await self.bot.send_message(
                chat_id=self.chat_id, text=message, parse_mode=parse_mode
            )
            log.info(f"텔레그램 전송: {message[:50]}...")
        except Exception as e:
            log.error(f"텔레그램 전송 실패: {e}")

    def send_sync(self, message: str):
        """동기 함수에서 호출용"""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(self.send(message))
            else:
                loop.run_until_complete(self.send(message))
        except RuntimeError:
            asyncio.run(self.send(message))

    # === 포맷된 메시지 전송 ===

    async def send_trade_alert(self, trade: dict):
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
        msg = (
            f"🚨 <b>손절매 트리거!</b>\n"
            f"유형: {alert['type']}\n"
            f"종목: {alert['name']} ({alert['code']})\n"
        )
        if alert["type"] == "INDEX_STOP_LOSS":
            msg += (
                f"종목 등락: {alert['stock_change']:+.1%}\n"
                f"코스피: {alert['kospi_change']:+.1%}\n"
                f"갭: {alert['gap']:+.1%} (한도 -10%p)\n"
            )
        elif alert["type"] == "TRAILING_STOP":
            msg += (
                f"수익률: {alert['pnl_pct']:+.1%}\n"
                f"고점: {alert['high_price']:,.0f}원\n"
                f"현재: {alert['current_price']:,.0f}원\n"
                f"하락: {alert['drawdown']:.1%} (한도 {alert['threshold']:.0%})\n"
            )
        elif alert["type"] == "PORTFOLIO_MAX_LOSS":
            msg += (
                f"투자원금: {alert['total_invested']:,.0f}원\n"
                f"현재평가: {alert['total_value']:,.0f}원\n"
                f"손실률: {alert['total_pnl']:.1%}\n"
                f"⚠️ <b>전량 매도 실행</b>\n"
            )
        msg += f"조치: {alert['action']}"
        await self.send(msg)

    async def send_daily_report(self, report: dict):
        msg = (
            f"📊 <b>일일 리포트</b> ({datetime.now():%Y-%m-%d})\n"
            f"{'─' * 28}\n"
            f"총 평가금액: {report['total_value']:,.0f}원\n"
            f"일간 수익률: {report['daily_pnl']:+.1%}\n"
            f"누적 수익률: {report['total_pnl']:+.1%}\n"
            f"현금 잔고: {report['cash']:,.0f}원\n"
            f"보유 종목: {report['num_holdings']}개\n"
            f"{'─' * 28}\n"
            f"오늘 매수: {report.get('buys', 0)}건\n"
            f"오늘 매도: {report.get('sells', 0)}건\n"
            f"실현 손익: {report.get('realized_pnl', 0):+,.0f}원\n"
        )
        await self.send(msg)

    async def send_morning_briefing(self, briefing: dict):
        msg = (
            f"☀️ <b>모닝 브리핑</b> ({datetime.now():%Y-%m-%d})\n"
            f"{'─' * 28}\n"
            f"코스피 전일: {briefing.get('kospi', '-')}\n"
            f"시장상태: {briefing.get('market_status', '-')}\n"
            f"환율: {briefing.get('usdkrw', '-')}\n"
            f"{'─' * 28}\n"
            f"📰 주요 뉴스:\n{briefing.get('news_summary', '없음')}\n"
            f"{'─' * 28}\n"
            f"🎯 오늘의 매매 계획:\n{briefing.get('trade_plan', '없음')}\n"
        )
        await self.send(msg)


class TelegramCommandBot:
    """양방향 명령 처리 봇 (별도 프로세스로 실행)"""

    def __init__(self, token: str = None, engine_callback=None):
        self.token = token or TELEGRAM_TOKEN
        self.engine_callback = engine_callback  # 매매엔진 콜백
        self.app = None

    def build(self):
        self.app = Application.builder().token(self.token).build()
        self.app.add_handler(CommandHandler("status", self.cmd_status))
        self.app.add_handler(CommandHandler("balance", self.cmd_balance))
        self.app.add_handler(CommandHandler("holdings", self.cmd_holdings))
        self.app.add_handler(CommandHandler("signals", self.cmd_signals))
        self.app.add_handler(CommandHandler("risk", self.cmd_risk))
        self.app.add_handler(CommandHandler("pause", self.cmd_pause))
        self.app.add_handler(CommandHandler("resume", self.cmd_resume))
        self.app.add_handler(CommandHandler("sync", self.cmd_sync))
        self.app.add_handler(CommandHandler("help", self.cmd_help))
        return self

    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if self.engine_callback:
            result = self.engine_callback("status")
            await update.message.reply_text(result, parse_mode="HTML")
        else:
            await update.message.reply_text("엔진 미연결")

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
            await update.message.reply_text("⏸ 자동매매 일시정지")

    async def cmd_resume(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if self.engine_callback:
            self.engine_callback("resume")
            await update.message.reply_text("▶️ 자동매매 재개")

    async def cmd_sync(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        import subprocess
        try:
            result = subprocess.run(["git", "pull"], capture_output=True, text=True, timeout=30)
            await update.message.reply_text(f"🔄 Git sync:\n{result.stdout}")
        except Exception as e:
            await update.message.reply_text(f"❌ Sync 실패: {e}")

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        msg = (
            "📌 <b>KangSub Bot 명령어</b>\n"
            "/status — 시스템 상태\n"
            "/balance — 계좌 잔고\n"
            "/holdings — 보유 종목\n"
            "/signals — 오늘의 시그널\n"
            "/risk — 리스크 상태\n"
            "/pause — 자동매매 정지\n"
            "/resume — 자동매매 재개\n"
            "/sync — GitHub 코드 동기화\n"
            "/help — 이 도움말"
        )
        await update.message.reply_text(msg, parse_mode="HTML")

    def run(self):
        if self.app is None:
            self.build()
        log.info("텔레그램 봇 시작")
        self.app.run_polling()

    def run_in_thread(self):
        """
        서브 스레드에서 안전하게 실행 — run_polling() 대신
        저수준 API 사용 (시그널 핸들러 없음)
        """
        import asyncio

        if self.app is None:
            self.build()

        async def _polling():
            async with self.app:
                await self.app.start()
                await self.app.updater.start_polling(drop_pending_updates=True)
                log.info("텔레그램 명령 봇 폴링 시작")
                # 봇이 종료될 때까지 대기
                await asyncio.Event().wait()

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(_polling())
        except Exception as e:
            log.error(f"텔레그램 명령 봇 오류: {e}")
        finally:
            loop.close()
