"""전역 설정 — 환경변수 로드 및 시스템 상수"""
import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / "config" / ".env")

# === API Keys (환경변수에서 로드) ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
NOTION_TOKEN = os.getenv("NOTION_TOKEN", "")
DART_API_KEY = os.getenv("DART_API_KEY", "")
KIWOOM_ACCOUNT = os.getenv("KIWOOM_ACCOUNT", "65947113")
KIWOOM_APP_KEY = os.getenv("KIWOOM_APP_KEY", "")
KIWOOM_SECRET_KEY = os.getenv("KIWOOM_SECRET_KEY", "")
KIWOOM_MOCK = os.getenv("KIWOOM_MOCK", "true").lower() == "true"  # True=모의투자

# === API Keys (추가) ===
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")  # NXT 예측용

# === PAM 투자 설정 (Policy-Aware Market) ===
TOTAL_CAPITAL = 10_000_000           # 1000만원 (2026-04-21 기준 실입금액)

# === NXT 매매 규칙 (장전거래 08:00) ===
NXT_MAX_STOCKS    = 3                # NXT 최대 매수 종목 수
NXT_BUDGET_RATIO  = 0.40             # 총 예산의 40% = 1200만원
NXT_STOP_LOSS_PCT = 0.02             # 갭다운 -2% 즉시 손절
NXT_DEADLINE      = "10:30"          # 강제 청산 시각

# === PAM 매매 규칙 (정규장 09:30) ===
PAM_MORNING_STOCKS = 5               # 오전 선정 주도주 수
PAM_MAX_HOLDINGS = 7                 # 최대 보유 종목 수 (7종목 cap)
PAM_BUY_RATIO = 0.50                 # 총 운용 자본의 50% 이내 매수
PAM_MORNING_PROFIT = 0.05            # 09:30 익절 기준 +5%
PAM_AFTERNOON_PROFIT = 0.07          # 15:00 익절 기준 +7%
PAM_STOP_LOSS = 0.10                 # 상시 손절 -10%
PAM_FALLING_BUY_STOCKS = 3          # 하락장 추가 매수 종목 수
PAM_KOSPI_RISE = 0.01                # 상승장 기준 +1%
PAM_KOSPI_FALL = -0.01               # 하락장 기준 -1%

# === 손절매 설정 (기존 호환 유지) ===
INDEX_STOP_LOSS_THRESHOLD = -0.10   # 지수 대비 -10%p
TRAILING_STOP = {
    (0.00, 0.10): 0.12,            # 0~10%  수익: 고점 대비 -12%
    (0.10, 0.30): 0.15,            # 10~30% 수익: 고점 대비 -15%
    (0.30, 0.50): 0.18,            # 30~50% 수익: 고점 대비 -18%
    (0.50, float("inf")): 0.20,    # 50%+   수익: 고점 대비 -20%
}
PORTFOLIO_MAX_LOSS = -0.20          # 전체 -20% 시 전량 매도

# === 기타 설정 ===
GENERAL_RATIO = 0.60
DIVIDEND_RATIO = 0.40
MAX_GENERAL_STOCKS = 10
MAX_DIVIDEND_STOCKS = 6
SPLIT_BUY_RATIOS = [0.40, 0.30, 0.30]
TWAP_INTERVALS = 5
TWAP_INTERVAL_MINUTES = 30
REBALANCE_MONTHS = [1, 4, 7, 10]
REBALANCE_TOLERANCE = 0.05
RSI_OVERSOLD = 45
VOLUME_MULTIPLIER = 1.5
NEWS_SENTIMENT_THRESHOLD = 0.6

# === 시장 운영시간 (KST) ===
MARKET_OPEN = "09:00"
MARKET_CLOSE = "15:30"
TWAP_START = "09:30"
TWAP_END = "15:00"

# === 뉴스 소스 ===
NEWS_SOURCES = {
    "한겨레": "https://www.hani.co.kr",
    "경향신문": "https://www.khan.co.kr",
    "한국일보": "https://www.hankookilbo.com",
    "MBC": "https://imnews.imbc.com",
    "JTBC": "https://news.jtbc.co.kr",
    "김어준뉴스공장": "https://humblefactory.co.kr/",
}

# === Notion DB IDs (생성 후 채울 것) ===
NOTION_DB_TRADES = os.getenv("NOTION_DB_TRADES", "")
NOTION_DB_PORTFOLIO = os.getenv("NOTION_DB_PORTFOLIO", "")
NOTION_DB_SIGNALS = os.getenv("NOTION_DB_SIGNALS", "")
NOTION_DB_NEWS = os.getenv("NOTION_DB_NEWS", "")

# === 경로 ===
DATA_DIR = BASE_DIR / "data" / "store"
LOG_DIR  = BASE_DIR / "logs"
DATA_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)
