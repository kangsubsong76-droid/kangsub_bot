"""시장 상태 판단 엔진 — 코스피 추세, VIX, 환율"""
import pandas as pd
from dataclasses import dataclass
from utils.logger import setup_logger

log = setup_logger("market_condition")


@dataclass
class MarketCondition:
    score: float          # 0~100
    kospi_trend: str      # "bullish", "bearish", "neutral"
    kospi_above_ma20: bool
    vkospi: float
    vkospi_level: str     # "low", "normal", "high", "extreme"
    usdkrw_stable: bool
    usdkrw_3d_change: float
    details: dict = None


def analyze_market(
    kospi_df: pd.DataFrame,
    vkospi: float = None,
    usdkrw_df: pd.DataFrame = None,
) -> MarketCondition:
    """
    kospi_df: 최소 30일 OHLCV (columns: close)
    vkospi: V-KOSPI 지수 (변동성)
    usdkrw_df: 환율 데이터 (columns: close)
    """
    score = 50.0
    close = kospi_df["close"]

    # 코스피 20일 이동평균 위/아래
    ma20 = close.rolling(20).mean().iloc[-1]
    current = close.iloc[-1]
    kospi_above_ma20 = current > ma20

    # 코스피 추세 (5일선 vs 20일선)
    ma5 = close.rolling(5).mean().iloc[-1]
    if ma5 > ma20 and current > ma20:
        kospi_trend = "bullish"
        score += 15
    elif ma5 < ma20 and current < ma20:
        kospi_trend = "bearish"
        score -= 15
    else:
        kospi_trend = "neutral"

    if kospi_above_ma20:
        score += 10
    else:
        score -= 10

    # V-KOSPI (한국 변동성 지수)
    if vkospi is not None:
        if vkospi < 15:
            vkospi_level = "low"
            score += 10
        elif vkospi < 25:
            vkospi_level = "normal"
            score += 5
        elif vkospi < 35:
            vkospi_level = "high"
            score -= 10
        else:
            vkospi_level = "extreme"
            score -= 20
    else:
        vkospi_level = "unknown"
        vkospi = 0

    # 환율 안정성 (3일 내 2% 이하)
    usdkrw_stable = True
    usdkrw_3d_change = 0.0
    if usdkrw_df is not None and len(usdkrw_df) >= 4:
        fx_close = usdkrw_df["close"]
        usdkrw_3d_change = (fx_close.iloc[-1] - fx_close.iloc[-4]) / fx_close.iloc[-4]
        usdkrw_stable = abs(usdkrw_3d_change) <= 0.02
        if usdkrw_stable:
            score += 5
        else:
            score -= 10
            if usdkrw_3d_change > 0:
                score -= 5  # 원화약세 추가 감점

    score = max(0, min(100, score))

    return MarketCondition(
        score=score,
        kospi_trend=kospi_trend,
        kospi_above_ma20=kospi_above_ma20,
        vkospi=vkospi,
        vkospi_level=vkospi_level,
        usdkrw_stable=usdkrw_stable,
        usdkrw_3d_change=round(usdkrw_3d_change, 4),
        details={
            "kospi_price": round(current, 2),
            "kospi_ma5": round(ma5, 2),
            "kospi_ma20": round(ma20, 2),
        }
    )
