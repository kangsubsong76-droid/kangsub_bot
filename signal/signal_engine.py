"""종합 시그널 엔진 — 기술적 + 시장 + 뉴스 시그널 통합 판단"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from signal.technical import TechnicalSignal
from signal.market_condition import MarketCondition
from utils.logger import setup_logger

log = setup_logger("signal_engine")


@dataclass
class CompositeSignal:
    code: str
    name: str
    action: str              # "BUY", "SELL", "HOLD", "WATCH"
    confidence: float        # 0~100
    technical_score: float
    market_score: float
    news_score: float
    weighted_score: float
    reasons: list[str]
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


class SignalEngine:
    # 가중치: 기술적 40%, 시장 30%, 뉴스 30%
    WEIGHT_TECHNICAL = 0.40
    WEIGHT_MARKET = 0.30
    WEIGHT_NEWS = 0.30

    # 임계값
    BUY_THRESHOLD = 65
    STRONG_BUY_THRESHOLD = 80
    SELL_THRESHOLD = 35
    WATCH_THRESHOLD = 55

    def generate_signal(
        self,
        tech: TechnicalSignal,
        market: MarketCondition,
        news_score: float = 50.0,  # 0~100, 기본 중립
        news_reasons: list[str] = None,
    ) -> CompositeSignal:
        weighted = (
            tech.score * self.WEIGHT_TECHNICAL
            + market.score * self.WEIGHT_MARKET
            + news_score * self.WEIGHT_NEWS
        )
        reasons = []

        # 기술적 분석 이유
        if tech.rsi < 30:
            reasons.append(f"RSI {tech.rsi} 과매도 구간")
        elif tech.rsi < 45:
            reasons.append(f"RSI {tech.rsi} 매수 근접")
        elif tech.rsi > 70:
            reasons.append(f"RSI {tech.rsi} 과매수 주의")

        if tech.macd_signal == "golden_cross":
            reasons.append("MACD 골든크로스")
        elif tech.macd_signal == "death_cross":
            reasons.append("MACD 데드크로스")

        if tech.bb_position in ("below_lower", "near_lower"):
            reasons.append(f"볼린저밴드 하단 ({tech.bb_position})")

        if tech.volume_ratio >= 1.5:
            reasons.append(f"거래량 급증 ({tech.volume_ratio}배)")

        # 시장 상태 이유
        if market.kospi_trend == "bullish":
            reasons.append("코스피 상승추세")
        elif market.kospi_trend == "bearish":
            reasons.append("코스피 하락추세 — 매수 주의")

        if market.vkospi_level in ("high", "extreme"):
            reasons.append(f"V-KOSPI {market.vkospi:.1f} 변동성 높음")

        if not market.usdkrw_stable:
            reasons.append(f"환율 불안정 (3일 {market.usdkrw_3d_change:+.1%})")

        # 뉴스 이유
        if news_reasons:
            reasons.extend(news_reasons[:3])

        # 매매 판단
        if weighted >= self.STRONG_BUY_THRESHOLD:
            action = "BUY"
            reasons.insert(0, f"★ 강력 매수 시그널 (점수 {weighted:.0f})")
        elif weighted >= self.BUY_THRESHOLD:
            action = "BUY"
            reasons.insert(0, f"매수 시그널 (점수 {weighted:.0f})")
        elif weighted <= self.SELL_THRESHOLD:
            action = "SELL"
            reasons.insert(0, f"매도 시그널 (점수 {weighted:.0f})")
        elif weighted >= self.WATCH_THRESHOLD:
            action = "WATCH"
            reasons.insert(0, f"관심 (점수 {weighted:.0f})")
        else:
            action = "HOLD"
            reasons.insert(0, f"관망 (점수 {weighted:.0f})")

        # 시장 하락추세에서는 매수 시그널 하향 조정
        if action == "BUY" and market.kospi_trend == "bearish":
            action = "WATCH"
            reasons.insert(0, "⚠ 시장 하락추세로 매수→관심 하향")

        return CompositeSignal(
            code=tech.code,
            name=tech.name,
            action=action,
            confidence=min(100, weighted),
            technical_score=tech.score,
            market_score=market.score,
            news_score=news_score,
            weighted_score=round(weighted, 1),
            reasons=reasons,
        )

    def generate_batch_signals(
        self,
        tech_signals: list[TechnicalSignal],
        market: MarketCondition,
        news_scores: dict[str, tuple[float, list[str]]] = None,
    ) -> list[CompositeSignal]:
        """여러 종목 일괄 시그널 생성"""
        if news_scores is None:
            news_scores = {}
        signals = []
        for tech in tech_signals:
            ns, nr = news_scores.get(tech.code, (50.0, []))
            sig = self.generate_signal(tech, market, ns, nr)
            signals.append(sig)
        signals.sort(key=lambda s: s.weighted_score, reverse=True)
        return signals
