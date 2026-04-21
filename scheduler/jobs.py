"""APScheduler 작업 정의 — 일일 운영 스케줄"""
import json
from datetime import datetime
from pathlib import Path
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from utils.logger import setup_logger
import traceback

log = setup_logger("scheduler")

# 스케줄러 상태 기록 경로 (대시보드용)
def _status_path():
    try:
        from config.settings import DATA_DIR
        return DATA_DIR / "scheduler_status.json"
    except Exception:
        return Path(r"C:\kangsub_bot\data\store\scheduler_status.json")

def _write_job_status(name: str, status: str, started: datetime, error: str = None):
    """각 잡 실행 결과를 scheduler_status.json에 기록"""
    try:
        p = _status_path()
        data = {}
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                data = {}
        data[name] = {
            "status":   status,          # "completed" | "error" | "running"
            "last_run": started.strftime("%Y-%m-%d %H:%M:%S"),
            "time":     started.strftime("%H:%M"),
            "error":    error,
        }
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass  # 상태 기록 실패는 무시


def safe_job(fn):
    """예외 안전망 래퍼 — 작업 실패 시 스케줄러가 죽지 않도록 + 실행 결과 기록"""
    def wrapper(*args, **kwargs):
        started = datetime.now()
        try:
            result = fn(*args, **kwargs)
            _write_job_status(fn.__name__, "completed", started)
            return result
        except Exception as e:
            log.error(f"[스케줄러 작업 오류] {fn.__name__}: {e}\n{traceback.format_exc()}")
            _write_job_status(fn.__name__, "error", started, str(e)[:200])
    wrapper.__name__ = fn.__name__
    return wrapper


class TradingScheduler:
    def __init__(self, engine):
        """engine: MainEngine 인스턴스"""
        self.engine = engine
        self.scheduler = BackgroundScheduler(timezone="Asia/Seoul")
        self._register_jobs()

    def _register_jobs(self):
        s = self.scheduler
        e = self.engine
        TZ = "Asia/Seoul"  # 모든 CronTrigger에 명시적으로 KST 지정 (EC2 UTC 방어)

        # 06:00 — 시스템 상태 점검
        s.add_job(safe_job(e.morning_health_check), CronTrigger(hour=6, minute=0, timezone=TZ), id="health_check")

        # 07:00 — 뉴스 크롤링
        s.add_job(safe_job(e.collect_news), CronTrigger(hour=7, minute=0, timezone=TZ), id="news_collect")

        # 07:30 — [NXT] 시간외 수집 + Claude 분석
        s.add_job(safe_job(e.collect_afterhours), CronTrigger(hour=7, minute=30, timezone=TZ, day_of_week="mon-fri"), id="nxt_collect")

        # 08:00 — [NXT] 장전거래 매수 + NLP 감성분석
        s.add_job(safe_job(e.execute_nxt_buy), CronTrigger(hour=8, minute=0, timezone=TZ, day_of_week="mon-fri"), id="nxt_buy")
        s.add_job(safe_job(e.analyze_news_signals), CronTrigger(hour=8, minute=0, timezone=TZ), id="news_analyze")

        # 08:00~10:30 — [NXT] 갭다운 손절 모니터링 (2분 간격)
        s.add_job(safe_job(e.monitor_nxt_positions), CronTrigger(hour="8-10", minute="*/2", timezone=TZ, day_of_week="mon-fri"), id="nxt_monitor")

        # 08:30 — 시장 상태 판단 + 모닝 브리핑 전송
        s.add_job(safe_job(e.morning_briefing), CronTrigger(hour=8, minute=30, timezone=TZ), id="morning_briefing")

        # 09:00 — 장 시작: 실시간 시세 수신 시작
        s.add_job(safe_job(e.start_realtime), CronTrigger(hour=9, minute=0, timezone=TZ, day_of_week="mon-fri"), id="market_open")

        # 09:05 — 수동 보유 현재가 동기화 (ka10001)
        s.add_job(safe_job(e.sync_manual_portfolio_prices), CronTrigger(hour=9, minute=5, timezone=TZ, day_of_week="mon-fri"), id="manual_sync_open")

        # 09:10 — 실 API vs portfolio_manual.json 대조 검증
        s.add_job(safe_job(e.reconcile_portfolio), CronTrigger(hour=9, minute=10, timezone=TZ, day_of_week="mon-fri"), id="reconcile_open")

        # 09:30 — [PAM] 정규장 매수 실행
        s.add_job(safe_job(e.execute_buy_signals), CronTrigger(hour=9, minute=30, timezone=TZ, day_of_week="mon-fri"), id="execute_buys")

        # 09:00~15:20 — [PAM] 손절매 모니터링 (5분 간격)
        s.add_job(safe_job(e.monitor_stop_loss), CronTrigger(hour="9-15", minute="*/5", timezone=TZ, day_of_week="mon-fri"), id="stop_loss")

        # 10:30 — [NXT] 잔여 포지션 강제 청산
        s.add_job(safe_job(e.close_nxt_positions), CronTrigger(hour=10, minute=30, timezone=TZ, day_of_week="mon-fri"), id="nxt_close")

        # 12:00 — 점심 상태 체크 + 텔레그램 중간 리포트
        s.add_job(safe_job(e.midday_report), CronTrigger(hour=12, minute=0, timezone=TZ, day_of_week="mon-fri"), id="midday_report")

        # 14:50 — 마감 전 포지션 확인
        s.add_job(safe_job(e.pre_close_check), CronTrigger(hour=14, minute=50, timezone=TZ, day_of_week="mon-fri"), id="pre_close")

        # 15:30 — 장 마감: 실시간 종료
        s.add_job(safe_job(e.stop_realtime), CronTrigger(hour=15, minute=30, timezone=TZ, day_of_week="mon-fri"), id="market_close")

        # 15:40 — 포트폴리오 스냅샷 → Notion + 수동 보유 현재가 최종 동기화
        s.add_job(safe_job(e.save_portfolio_snapshot), CronTrigger(hour=15, minute=40, timezone=TZ, day_of_week="mon-fri"), id="snapshot")
        s.add_job(safe_job(e.sync_manual_portfolio_prices), CronTrigger(hour=15, minute=42, timezone=TZ, day_of_week="mon-fri"), id="manual_sync_close")

        # 15:45 — 실 API vs portfolio_manual.json 마감 대조 검증
        s.add_job(safe_job(e.reconcile_portfolio), CronTrigger(hour=15, minute=45, timezone=TZ, day_of_week="mon-fri"), id="reconcile_close")

        # 16:00 — DART 공시 체크
        s.add_job(safe_job(e.check_dart_disclosures), CronTrigger(hour=16, minute=0, timezone=TZ, day_of_week="mon-fri"), id="dart_check")

        # 16:10 — [NXT] 패턴DB 업데이트
        s.add_job(safe_job(e.update_nxt_result), CronTrigger(hour=16, minute=10, timezone=TZ, day_of_week="mon-fri"), id="nxt_patterns")

        # 17:00 — 일일 리포트 텔레그램 전송
        s.add_job(safe_job(e.daily_report), CronTrigger(hour=17, minute=0, timezone=TZ, day_of_week="mon-fri"), id="daily_report")

        # 18:00 — 기술적 분석 업데이트 (일봉)
        s.add_job(safe_job(e.update_technical_signals), CronTrigger(hour=18, minute=0, timezone=TZ, day_of_week="mon-fri"), id="tech_update")

        # 22:00 — 글로벌 시장 체크 (미국 프리마켓)
        s.add_job(safe_job(e.check_global_market), CronTrigger(hour=22, minute=0, timezone=TZ), id="global_check")

        # 매주 월요일 06:30 — 재무 데이터(PER/PBR/ROE) 주간 갱신
        s.add_job(safe_job(e.refresh_fundamentals), CronTrigger(day_of_week="mon", hour=6, minute=30, timezone=TZ), id="fundamentals_refresh")

        # 매주 월요일 09:05 — 주간 리포트
        s.add_job(safe_job(e.weekly_report), CronTrigger(day_of_week="mon", hour=9, minute=5, timezone=TZ), id="weekly_report")

        # 분기 첫째 주 월요일 10:00 — 리밸런싱
        s.add_job(safe_job(e.quarterly_rebalance), CronTrigger(month="1,4,7,10", day="1-7", day_of_week="mon", hour=10, timezone=TZ), id="rebalance")

        log.info(f"스케줄러 등록 완료: {len(s.get_jobs())}개 작업")

    def start(self):
        self.scheduler.start()
        log.info("스케줄러 시작")

    def stop(self):
        self.scheduler.shutdown()
        log.info("스케줄러 종료")
