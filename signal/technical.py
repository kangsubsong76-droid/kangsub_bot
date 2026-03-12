"""기술적 분석 엔진 — RSI, MACD, 볼린저밴드, 이동평균, 거래량"""
import pandas as pd
import numpy as np
from dataclasses import dataclass


@dataclass
class TechnicalSignal:
    code: str
    name: str
    score: float          # 0~100 종합 점수
    rsi: float
    macd_signal: str      # "golden_cross", "death_cross", "above_zero", "below_zero", "neutral"
    bb_position: str      # "below_lower", "near_lower", "middle", "near_upper", "above_upper"
    ma_trend: str         # "bullish", "bearish", "neutral"
    volume_ratio: float   # 20일 평균 대비 배수
    details: dict = None


def calc_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1/period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def calc_macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    ema_fast = series.ewm(span=fast).mean()
    ema_slow = series.ewm(span=slow).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def calc_bollinger(series: pd.Series, period: int = 20, std_dev: float = 2.0):
    sma = series.rolling(period).mean()
    std = series.rolling(period).std()
    upper = sma + std_dev * std
    lower = sma - std_dev * std
    return upper, sma, lower


def analyze(df: pd.DataFrame, code: str, name: str) -> TechnicalSignal:
    """
    df는 최소 60일치 OHLCV 데이터 필요
    columns: ['open', 'high', 'low', 'close', 'volume']
    """
    close = df["close"]
    volume = df["volume"]
    score = 50.0  # 기본 중립

    # RSI
    rsi_series = calc_rsi(close)
    rsi = rsi_series.iloc[-1]
    if rsi < 30:
        score += 15
    elif rsi < 45:
        score += 10
    elif rsi > 70:
        score -= 15
    elif rsi > 60:
        score -= 5

    # MACD
    macd_line, signal_line, hist = calc_macd(close)
    macd_now = macd_line.iloc[-1]
    signal_now = signal_line.iloc[-1]
    hist_now = hist.iloc[-1]
    hist_prev = hist.iloc[-2] if len(hist) > 1 else 0

    if hist_prev < 0 and hist_now > 0:
        macd_signal = "golden_cross"
        score += 15
    elif hist_prev > 0 and hist_now < 0:
        macd_signal = "death_cross"
        score -= 15
    elif macd_now > 0:
        macd_signal = "above_zero"
        score += 5
    elif macd_now < 0:
        macd_signal = "below_zero"
        score -= 5
    else:
        macd_signal = "neutral"

    # 볼린저밴드
    bb_upper, bb_mid, bb_lower = calc_bollinger(close)
    price = close.iloc[-1]
    bb_width = bb_upper.iloc[-1] - bb_lower.iloc[-1]

    if price <= bb_lower.iloc[-1]:
        bb_position = "below_lower"
        score += 12
    elif price <= bb_lower.iloc[-1] + bb_width * 0.2:
        bb_position = "near_lower"
        score += 8
    elif price >= bb_upper.iloc[-1]:
        bb_position = "above_upper"
        score -= 10
    elif price >= bb_upper.iloc[-1] - bb_width * 0.2:
        bb_position = "near_upper"
        score -= 5
    else:
        bb_position = "middle"

    # 이동평균 추세
    ma5 = close.rolling(5).mean().iloc[-1]
    ma20 = close.rolling(20).mean().iloc[-1]
    ma60 = close.rolling(60).mean().iloc[-1] if len(close) >= 60 else ma20

    if ma5 > ma20 > ma60:
        ma_trend = "bullish"
        score += 10
    elif ma5 < ma20 < ma60:
        ma_trend = "bearish"
        score -= 10
    elif ma5 > ma20:
        ma_trend = "neutral"  # 단기 반등 중
        score += 3
    else:
        ma_trend = "neutral"

    # 거래량
    vol_avg20 = volume.rolling(20).mean().iloc[-1]
    vol_ratio = volume.iloc[-1] / vol_avg20 if vol_avg20 > 0 else 1.0
    if vol_ratio >= 2.0:
        score += 8
    elif vol_ratio >= 1.5:
        score += 5
    elif vol_ratio < 0.5:
        score -= 5

    score = max(0, min(100, score))

    return TechnicalSignal(
        code=code, name=name, score=score,
        rsi=round(rsi, 1),
        macd_signal=macd_signal,
        bb_position=bb_position,
        ma_trend=ma_trend,
        volume_ratio=round(vol_ratio, 2),
        details={
            "macd_line": round(macd_now, 2),
            "signal_line": round(signal_now, 2),
            "bb_upper": round(bb_upper.iloc[-1], 0),
            "bb_lower": round(bb_lower.iloc[-1], 0),
            "ma5": round(ma5, 0),
            "ma20": round(ma20, 0),
            "ma60": round(ma60, 0),
            "price": round(price, 0),
        }
    )
