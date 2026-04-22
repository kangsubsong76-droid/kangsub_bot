"""시장 데이터 수집 — 키움 REST API 우선, pykrx/yfinance 폴백"""
import pandas as pd
import concurrent.futures
from datetime import datetime, timedelta
from utils.logger import setup_logger

log = setup_logger("market_data")

# pykrx/yfinance 폴백 타임아웃 (초)
_API_TIMEOUT = 10

try:
    import yfinance as yf
except ImportError:
    yf = None

try:
    from pykrx import stock as krx
except ImportError:
    krx = None

# ── 키움 API 인스턴스 (싱글톤 캐시) ───────────────────────────
_kiwoom_instance = None

def _get_kiwoom():
    """MainEngine의 kiwoom 인스턴스를 주입받거나 직접 생성"""
    global _kiwoom_instance
    if _kiwoom_instance is not None:
        return _kiwoom_instance
    try:
        from config.settings import KIWOOM_MOCK
        if KIWOOM_MOCK:
            return None
        from core.kiwoom_rest import KiwoomRestAPI
        _kiwoom_instance = KiwoomRestAPI()
        return _kiwoom_instance
    except Exception:
        return None

def set_kiwoom(instance):
    """MainEngine 초기화 시 키움 인스턴스 주입 (권장)"""
    global _kiwoom_instance
    _kiwoom_instance = instance


def _krx_code(code: str) -> str:
    return code.zfill(6)


def _call_with_timeout(fn, timeout=_API_TIMEOUT):
    """함수를 별도 스레드에서 실행, timeout 초 초과 시 None 반환"""
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        future = ex.submit(fn)
        try:
            return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            return None
        except Exception:
            return None


# ══════════════════════════════════════════════════════════════
# ── 종목 OHLCV
# ══════════════════════════════════════════════════════════════

def get_stock_ohlcv(code: str, days: int = 120) -> pd.DataFrame:
    """
    종목 OHLCV 조회
    우선순위: 키움 REST API(ka10081) → pykrx → yfinance
    """
    # 1순위: 키움 REST API
    kiwoom = _get_kiwoom()
    if kiwoom:
        try:
            df = kiwoom.get_stock_ohlcv(code, days)
            if df is not None and not df.empty:
                return df
            log.debug(f"키움 OHLCV 빈 응답 ({code}) — 폴백")
        except Exception as e:
            log.warning(f"키움 OHLCV 실패 ({code}): {e}")

    # 2순위: pykrx (타임아웃 적용)
    if krx:
        end   = datetime.now().strftime("%Y%m%d")
        start = (datetime.now() - timedelta(days=days + 60)).strftime("%Y%m%d")
        result = _call_with_timeout(
            lambda: krx.get_market_ohlcv_by_date(start, end, _krx_code(code))
        )
        if result is not None and not result.empty:
            df = result.iloc[:, :5].copy()
            df.columns = ["open", "high", "low", "close", "volume"]
            df.index.name = "date"
            return df
        if result is None:
            log.warning(f"pykrx timeout ({code})")

    # 3순위: yfinance (타임아웃 적용)
    if yf:
        result = _call_with_timeout(
            lambda: yf.download(f"{_krx_code(code)}.KS", period=f"{days}d", progress=False)
        )
        if result is not None and not result.empty:
            df = result.copy()
            # yfinance >= 0.2 는 MultiIndex columns ('Close', 'TICKER') 반환 → 첫 레벨만 사용
            df.columns = [(c[0] if isinstance(c, tuple) else c).lower() for c in df.columns]
            return df[["open", "high", "low", "close", "volume"]]
        if result is None:
            log.warning(f"yfinance timeout ({code})")

    log.error(f"OHLCV 조회 전체 실패: {code}")
    return pd.DataFrame()


# ══════════════════════════════════════════════════════════════
# ── 코스피 지수 OHLCV
# ══════════════════════════════════════════════════════════════

def get_kospi_ohlcv(days: int = 120) -> pd.DataFrame:
    """
    코스피 지수 OHLCV
    우선순위: 키움 REST API(ka10008) → pykrx → yfinance
    """
    # 1순위: 키움 REST API
    kiwoom = _get_kiwoom()
    if kiwoom:
        try:
            df = kiwoom.get_index_ohlcv("001", days)  # 001=KOSPI
            if df is not None and not df.empty:
                return df
            log.debug("키움 KOSPI 빈 응답 — 폴백")
        except Exception as e:
            log.warning(f"키움 KOSPI 실패: {e}")

    # 2순위: pykrx
    if krx:
        end   = datetime.now().strftime("%Y%m%d")
        start = (datetime.now() - timedelta(days=days + 60)).strftime("%Y%m%d")
        try:
            df = _call_with_timeout(
                lambda: krx.get_index_ohlcv_by_date(start, end, "1001")
            )
            if df is not None and not df.empty:
                df = df.iloc[:, :5].copy()
                df.columns = ["open", "high", "low", "close", "volume"]
                df.index.name = "date"
                return df
        except Exception as e:
            log.warning(f"코스피 pykrx 실패: {e}")

    # 3순위: yfinance
    if yf:
        result = _call_with_timeout(
            lambda: yf.download("^KS11", period=f"{days}d", progress=False)
        )
        if result is not None and not result.empty:
            df = result.copy()
            df.columns = [(c[0] if isinstance(c, tuple) else c).lower() for c in df.columns]
            return df[["open", "high", "low", "close", "volume"]]

    return pd.DataFrame()


# ══════════════════════════════════════════════════════════════
# ── 환율 / V-KOSPI
# ══════════════════════════════════════════════════════════════

def get_usdkrw(days: int = 30) -> pd.DataFrame:
    """USD/KRW 환율 (yfinance)"""
    if yf:
        result = _call_with_timeout(
            lambda: yf.download("USDKRW=X", period=f"{days}d", progress=False)
        )
        if result is not None and not result.empty:
            df = result.copy()
            df.columns = [(c[0] if isinstance(c, tuple) else c).lower() for c in df.columns]
            return df[["close"]]
    return pd.DataFrame()


def get_vkospi() -> float:
    """V-KOSPI 최신값 (pykrx 또는 키움 KOSDAQ 지수로 근사)"""
    if krx:
        try:
            end   = datetime.now().strftime("%Y%m%d")
            start = (datetime.now() - timedelta(days=7)).strftime("%Y%m%d")
            df = _call_with_timeout(
                lambda: krx.get_index_ohlcv_by_date(start, end, "1004")
            )
            if df is not None and not df.empty:
                return float(df["종가"].iloc[-1]) if "종가" in df.columns else float(df.iloc[-1, 3])
        except Exception as e:
            log.warning(f"V-KOSPI 조회 실패: {e}")
    return None


# ══════════════════════════════════════════════════════════════
# ── 편의 함수
# ══════════════════════════════════════════════════════════════

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
