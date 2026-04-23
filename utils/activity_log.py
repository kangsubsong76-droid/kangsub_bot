"""
봇 실시간 활동 로그 — 대시보드 ③패널 live feed용
bot_activity.json 에 append-only 기록
"""
import json
import threading
from datetime import datetime
from pathlib import Path

try:
    from config.settings import DATA_DIR
    _ACTIVITY_FILE = DATA_DIR / "bot_activity.json"
except Exception:
    _ACTIVITY_FILE = Path(__file__).resolve().parent.parent / "data" / "store" / "bot_activity.json"

MAX_ENTRIES = 120
_lock = threading.Lock()


def _append(entry: dict):
    with _lock:
        try:
            existing = []
            if _ACTIVITY_FILE.exists():
                try:
                    existing = json.loads(_ACTIVITY_FILE.read_text(encoding="utf-8"))
                except Exception:
                    existing = []
            existing.append(entry)
            if len(existing) > MAX_ENTRIES:
                existing = existing[-MAX_ENTRIES:]
            _ACTIVITY_FILE.write_text(
                json.dumps(existing, ensure_ascii=False), encoding="utf-8"
            )
        except Exception:
            pass


def log(msg: str, level: str = "INFO"):
    _append({
        "time": datetime.now().strftime("%H:%M:%S"),
        "date": datetime.now().strftime("%Y-%m-%d"),
        "level": level,
        "msg": msg,
    })


def info(msg: str):     log(msg, "INFO")
def warn(msg: str):     log(msg, "WARN")
def error(msg: str):    log(msg, "ERROR")
def trade(msg: str):    log(msg, "TRADE")
def ai(msg: str):       log(msg, "AI")


def clear_old():
    """오늘 날짜 이전 항목 제거 (매일 06:00 호출)"""
    today = datetime.now().strftime("%Y-%m-%d")
    with _lock:
        try:
            if _ACTIVITY_FILE.exists():
                data = json.loads(_ACTIVITY_FILE.read_text(encoding="utf-8"))
                data = [e for e in data if e.get("date", today) >= today]
                _ACTIVITY_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass
