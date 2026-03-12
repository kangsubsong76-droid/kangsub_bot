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
KIWOOM_ACCOUNT = os.getenv("KIWOOM_ACCOUNT", "")
KIWOOM_PASSWORD = os.getenv("KIWOOM_PASSWORD", "")

# === 투자 설정 ===
TOTAL_CAPITAL = 100_000_000          # 1억원
GENERAL_RATIO = 0.60                 # 일반 60%
DIVIDEND_RATIO = 0.40                # 배당 40%
MAX_GENERAL_STOCKS = 10
MAX_DIVIDEND_STOCKS = 6

# === 매매 설정 ===
SPLIT_BUY_RATIOS = [0.40, 0.30, 0.30]  # 3회 분할매수 비율
TWAP_INTERVALS = 5                       # TWAP 분할 횟수
TWAP_INTERVAL_MINUTES = 30               # TWAP 간격(분)

# === 손절매 설정 ===
INDEX_STOP_LOSS_THRESHOLD = -0.10   # 지수 대비 -10%p
TRAILING_STOP = {
    (0, 0.05): 0.10,     # ~5% 수익: 고점 대비 -10%
    (0.05, 0.20): 0.15,  # 5~20% 수익: 고점 대비 -15%
    (0.20, 0.50): 0.20,  # 20~50% 수익: 고점 대비 -20%
    (0.50, float("inf")): 0.30,  # 50%~: 고점 대비 -30%
}
PORTFOLIO_MAX_LOSS = -0.20          # 전체 -20% 시 전량 매도

# === 리밸런싱 ===
REBALANCE_MONTHS = [1, 4, 7, 10]    # 분기 첫째 주
REBALANCE_TOLERANCE = 0.05           # ±5% 초과 시 조정

# === 매수 시그널 임계값 ===
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
LOG_DIR = BASE_DIR / "logs"
DATA_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)
