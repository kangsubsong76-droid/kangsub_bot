"""로깅 유틸리티"""
import logging
import sys
from pathlib import Path
from logging.handlers import TimedRotatingFileHandler


class SafeTimedRotatingFileHandler(TimedRotatingFileHandler):
    """
    Windows WinError 32 방지용 안전 핸들러.
    다른 프로세스가 로그 파일을 열고 있을 때 doRollover()가
    PermissionError를 던지는 문제를 무시하고 계속 현재 파일에 기록.
    """
    def doRollover(self):
        try:
            super().doRollover()
        except PermissionError:
            pass  # 파일 잠금 중 — 로테이션 스킵, 현재 파일에 계속 기록

    def emit(self, record):
        try:
            super().emit(record)
        except PermissionError:
            pass  # 파일 잠금 중 — 해당 로그 레코드 스킵


def setup_logger(name: str, log_dir: Path = None) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter("[%(asctime)s] %(name)s | %(levelname)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

    sh = logging.StreamHandler(sys.stdout)
    sh.setLevel(logging.INFO)
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    if log_dir:
        log_dir.mkdir(parents=True, exist_ok=True)
        # 자정마다 날짜별 새 파일 자동 생성 (backup 30일 보관)
        fh = SafeTimedRotatingFileHandler(
            log_dir / f"{name}.log",
            when="midnight",
            interval=1,
            backupCount=30,
            encoding="utf-8",
            delay=True,   # 첫 기록 시점까지 파일 열기 지연 (시작 충돌 방지)
        )
        fh.suffix = "%Y%m%d"          # 백업 파일명: main.log.20260422
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(fmt)
        logger.addHandler(fh)

    return logger
