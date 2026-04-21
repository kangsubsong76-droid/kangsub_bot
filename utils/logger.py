"""로깅 유틸리티"""
import logging
import sys
from pathlib import Path
from logging.handlers import TimedRotatingFileHandler

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
        fh = TimedRotatingFileHandler(
            log_dir / f"{name}.log",
            when="midnight",
            interval=1,
            backupCount=30,
            encoding="utf-8",
        )
        fh.suffix = "%Y%m%d"          # 백업 파일명: main.log.20260422
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(fmt)
        logger.addHandler(fh)

    return logger
