"""시장 데이터 수집 — yfinance + pykrx 기반"""
import pandas as pd
from datetime import datetime, timedelta
from utils.logger import setup_logger

log = setup_logger("market_data")

try:
    import yfinance as yf
except ImportError:
    yf = None

try:
    from pykrx import stock as krx
except ImportError:
    krx = None


def _krx_code(code: str) -> str:
    """6자리 코드 보장"""
    return code.zfill(6)


def get_stock_ohlcv(code: str, days: int = 120) -> pd.DataFrame:
    """종목 OHLCV 조회 (pykrx 우선, yfinance 폴백)"""
    end = datetime.now().strftime("%Y%m%d")
    start = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")

    if krx:
        try:
            df = krx.get_market_ohlcv_by_date(start, end, _krx_code(code))
            if not df.empty:
                df = df.iloc[:, :5]  # 시가/고가/저가/종가/거래량 (7컬럼 중 앞 5개만)
                df.columns = ["open", "high", "low", "close", "volume"]
                df.index.name = "date"
                return df
        except Exception as e:
            log.warning(f"pykrx 조회 실패 ({code}): {e}")

    if yf:
        try:
            ticker = f"{_krx_code(code)}.KS"
            df = yf.download(ticker, period=f"{days}d", progress=False)
            if not df.empty:
                df.columns = [c.lower() for c in df.columns]
                df = df[["open", "high", "low", "close", "volume"]]
                return df
        except Exception as e:
            log.warning(f"yfinance 조회 실패 ({code}): {e}")

    log.error(f"데이터 조회 실패: {code}")
    return pd.DataFrame()


def get_kospi_ohlcv(days: int = 120) -> pd.DataFrame:
    """코스피 지수 OHLCV"""
    end = datetime.now().strftime("%Y%m%d")
    start = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")

    if krx:
        try:
            df = krx.get_index_ohlcv_by_date(start, end, "1001")  # 코스피
            if not df.empty:
                df = df.iloc[:, :5]  # 시가/고가/저가/종가/거래량 (7컬럼 중 앞 5개만)
                df.columns = ["open", "high", "low", "close", "volume"]
                df.index.name = "date"
                return df
        except Exception as e:
            log.warning(f"코스피 pykrx 실패: {e}")

    if yf:
        try:
            df = yf.download("^KS11", period=f"{days}d", progress=False)
            if not df.empty:
                df.columns = [c.lower() for c in df.columns]
                df = df[["open", "high", "low", "close", "volume"]]
                return df
        except Exception as e:
            log.warning(f"코스피 yfinance 실패: {e}")

    return pd.DataFrame()


def get_usdkrw(days: int = 30) -> pd.DataFrame:
    """USD/KRW 환율"""
    if yf:
        try:
            df = yf.download("USDKRW=X", period=f"{days}d", progress=False)
            if not df.empty:
                df.columns = [c.lower() for c in df.columns]
                return df[["close"]]
        except Exception as e:
            log.warning(f"환율 조회 실패: {e}")
    return pd.DataFrame()


def get_vkospi() -> float:
    """V-KOSPI (변동성 지수) 최신 값"""
    if krx:
        try:
            end = datetime.now().strftime("%Y%m%d")
            start = (datetime.now() - timedelta(days=7)).strftime("%Y%m%d")
            df = krx.get_index_ohlcv_by_date(start, end, "1004")  # V-KOSPI200
            if not df.empty:
                return float(df["종가"].iloc[-1]) if "종가" in df.columns else float(df.iloc[-1, 3])
        except Exception as e:
            log.warning(f"V-KOSPI 조회 실패: {e}")
    return None


def get_daily_change(code: str) -> float:
    """종목 당일 등락률"""
    df = get_stock_ohlcv(code, days=5)
    if len(df) < 2:
        return 0.0
    return (df["close"].iloc[-1] - df["close"].iloc[-2]) / df["close"].iloc[-2]


def get_kospi_daily_change() -> float:
    """코스피 당일 등락률"""
    df = get_kospi_ohlcv(days=5)
    if len(df) < 2:
        return 0.0
    return (df["close"].iloc[-1] - df["close"].iloc[-2]) / df["close"].iloc[-2]
