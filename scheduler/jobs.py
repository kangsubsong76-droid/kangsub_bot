"""APScheduler 작업 정의 — 일일 운영 스케줄"""
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from utils.logger import setup_logger

log = setup_logger("scheduler")


class TradingScheduler:
    def __init__(self, engine):
        """engine: MainEngine 인스턴스"""
        self.engine = engine
        self.scheduler = BackgroundScheduler(timezone="Asia/Seoul")
        self._register_jobs()

    def _register_jobs(self):
        s = self.scheduler
        e = self.engine

        # 06:00 — 시스템 상태 점검
        s.add_job(e.morning_health_check, CronTrigger(hour=6, minute=0), id="health_check")

        # 07:00 — 뉴스 크롤링
        s.add_job(e.collect_news, CronTrigger(hour=7, minute=0), id="news_collect")

        # 08:00 — NLP 감성분석 + 시그널 생성
        s.add_job(e.analyze_news_signals, CronTrigger(hour=8, minute=0), id="news_analyze")

        # 08:30 — 시장 상태 판단 + 모닝 브리핑 전송
        s.add_job(e.morning_briefing, CronTrigger(hour=8, minute=30), id="morning_briefing")

        # 09:00 — 장 시작: 실시간 시세 수신 시작
        s.add_job(e.start_realtime, CronTrigger(hour=9, minute=0), id="market_open", day_of_week="mon-fri")

        # 09:30 — TWAP 매수 실행
        s.add_job(e.execute_buy_signals, CronTrigger(hour=9, minute=30), id="execute_buys", day_of_week="mon-fri")

        # 09:00~15:20 — 손절매 모니터링 (5분 간격)
        s.add_job(e.monitor_stop_loss, CronTrigger(hour="9-15", minute="*/5"), id="stop_loss", day_of_week="mon-fri")

        # 12:00 — 점심 상태 체크 + 텔레그램 중간 리포트
        s.add_job(e.midday_report, CronTrigger(hour=12, minute=0), id="midday_report", day_of_week="mon-fri")

        # 14:50 — 마감 전 포지션 확인
        s.add_job(e.pre_close_check, CronTrigger(hour=14, minute=50), id="pre_close", day_of_week="mon-fri")

        # 15:30 — 장 마감: 실시간 종료
        s.add_job(e.stop_realtime, CronTrigger(hour=15, minute=30), id="market_close", day_of_week="mon-fri")

        # 15:40 — 포트폴리오 스냅샷 → Notion
        s.add_job(e.save_portfolio_snapshot, CronTrigger(hour=15, minute=40), id="snapshot", day_of_week="mon-fri")

        # 16:00 — DART 공시 체크
        s.add_job(e.check_dart_disclosures, CronTrigger(hour=16, minute=0), id="dart_check", day_of_week="mon-fri")

        # 17:00 — 일일 리포트 텔레그램 전송
        s.add_job(e.daily_report, CronTrigger(hour=17, minute=0), id="daily_report", day_of_week="mon-fri")

        # 18:00 — 기술적 분석 업데이트 (일봉)
        s.add_job(e.update_technical_signals, CronTrigger(hour=18, minute=0), id="tech_update", day_of_week="mon-fri")

        # 22:00 — 글로벌 시장 체크 (미국 프리마켓)
        s.add_job(e.check_global_market, CronTrigger(hour=22, minute=0), id="global_check")

        # 매주 월요일 06:30 — 재무 데이터(PER/PBR/ROE) 주간 갱신
        s.add_job(e.refresh_fundamentals, CronTrigger(day_of_week="mon", hour=6, minute=30), id="fundamentals_refresh")

        # 매주 월요일 09:05 — 주간 리포트
        s.add_job(e.weekly_report, CronTrigger(day_of_week="mon", hour=9, minute=5), id="weekly_report")

        # 분기 첫째 주 월요일 10:00 — 리밸런싱
        s.add_job(e.quarterly_rebalance, CronTrigger(month="1,4,7,10", day="1-7", day_of_week="mon", hour=10), id="rebalance")

        log.info(f"스케줄러 등록 완료: {len(s.get_jobs())}개 작업")

    def start(self):
        self.scheduler.start()
        log.info("스케줄러 시작")

    def stop(self):
        self.scheduler.shutdown()
        log.info("스케줄러 종료")
