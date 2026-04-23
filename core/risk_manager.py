"""리스크 관리 엔진 — 이광수 대표 손절매 전략 구현"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from config.settings import (
    INDEX_STOP_LOSS_THRESHOLD, TRAILING_STOP, PORTFOLIO_MAX_LOSS
)
from utils.logger import setup_logger

log = setup_logger("risk_manager")


@dataclass
class StockPosition:
    code: str
    name: str
    buy_price: float
    quantity: int
    buy_date: datetime
    current_price: float = 0.0
    high_since_buy: float = 0.0  # 매수 후 최고가

    @property
    def pnl_pct(self) -> float:
        if self.buy_price == 0:
            return 0.0
        return (self.current_price - self.buy_price) / self.buy_price

    @property
    def drawdown_from_high(self) -> float:
        if self.high_since_buy == 0:
            return 0.0
        return (self.current_price - self.high_since_buy) / self.high_since_buy

    def update_price(self, price: float):
        self.current_price = price
        if price > self.high_since_buy:
            self.high_since_buy = price


class RiskManager:
    def __init__(self):
        self.positions: dict[str, StockPosition] = {}
        self.total_invested = 0.0
        self.alerts: list[dict] = []

    def add_position(self, pos: StockPosition):
        self.positions[pos.code] = pos
        self.total_invested += pos.buy_price * pos.quantity
        log.info(f"포지션 추가: {pos.name}({pos.code}) {pos.quantity}주 @ {pos.buy_price:,.0f}원")

    def remove_position(self, code: str):
        if code in self.positions:
            pos = self.positions.pop(code)
            self.total_invested -= pos.buy_price * pos.quantity
            log.info(f"포지션 제거: {pos.name}({code})")

    # ── 1단계: 지수 대비 절대 손절 ──
    def check_index_stop_loss(self, code: str, stock_change_pct: float, kospi_change_pct: float) -> Optional[dict]:
        """
        [내 종목 등락률] - [코스피 당일 등락률] ≤ -10%p → 즉시 매도
        """
        gap = stock_change_pct - kospi_change_pct
        if gap <= INDEX_STOP_LOSS_THRESHOLD:
            pos = self.positions.get(code)
            name = pos.name if pos else code
            alert = {
                "type": "INDEX_STOP_LOSS",
                "code": code,
                "name": name,
                "stock_change": stock_change_pct,
                "kospi_change": kospi_change_pct,
                "gap": gap,
                "action": "SELL_NOW",
                "timestamp": datetime.now(),
            }
            self.alerts.append(alert)
            log.warning(f"[지수대비 손절] {name} 종목{stock_change_pct:+.1%} vs 코스피{kospi_change_pct:+.1%} = 갭{gap:+.1%}")
            return alert
        return None

    # ── 2단계: 추적 손절매 ──
    def check_trailing_stop(self, code: str) -> Optional[dict]:
        """
        수익 구간별 고점 대비 허용 하락폭 체크
        ~5%: -10%, 5~20%: -15%, 20~50%: -20%, 50%~: -30%
        """
        pos = self.positions.get(code)
        if not pos or pos.high_since_buy == 0:
            return None

        pnl = pos.pnl_pct
        drawdown = pos.drawdown_from_high
        threshold = None

        for (low, high), stop_pct in TRAILING_STOP.items():
            if low <= pnl < high:
                threshold = -stop_pct
                break

        if threshold is None:
            return None

        if drawdown <= threshold:
            alert = {
                "type": "TRAILING_STOP",
                "code": code,
                "name": pos.name,
                "pnl_pct": pnl,
                "high_price": pos.high_since_buy,
                "current_price": pos.current_price,
                "drawdown": drawdown,
                "threshold": threshold,
                "action": "SELL_NOW",
                "timestamp": datetime.now(),
            }
            self.alerts.append(alert)
            log.warning(
                f"[추적손절] {pos.name} 수익{pnl:+.1%} 구간, "
                f"고점{pos.high_since_buy:,.0f}→현재{pos.current_price:,.0f} "
                f"하락{drawdown:.1%} (한도{threshold:.0%})"
            )
            return alert
        return None

    def run_all_checks(self, code: str, stock_change_pct: float = 0, kospi_change_pct: float = 0) -> list[dict]:
        """모든 리스크 체크를 순서대로 실행"""
        results = []
        r1 = self.check_index_stop_loss(code, stock_change_pct, kospi_change_pct)
        if r1:
            results.append(r1)
            return results  # 지수대비 손절은 즉시 매도

        r2 = self.check_trailing_stop(code)
        if r2:
            results.append(r2)

        return results

    def get_risk_summary(self) -> dict:
        """현재 리스크 상태 요약"""
        if not self.positions:
            return {"status": "NO_POSITIONS", "positions": []}

        total_value = sum(p.current_price * p.quantity for p in self.positions.values())
        total_pnl = (total_value - self.total_invested) / self.total_invested if self.total_invested else 0

        position_risks = []
        for code, pos in self.positions.items():
            pnl = pos.pnl_pct
            dd = pos.drawdown_from_high
            threshold = 0
            for (low, high), stop_pct in TRAILING_STOP.items():
                if low <= pnl < high:
                    threshold = -stop_pct
                    break

            position_risks.append({
                "code": code,
                "name": pos.name,
                "pnl_pct": pnl,
                "drawdown": dd,
                "stop_threshold": threshold,
                "distance_to_stop": dd - threshold if threshold else None,
            })

        return {
            "status": "OK" if total_pnl > PORTFOLIO_MAX_LOSS else "DANGER",
            "total_pnl": total_pnl,
            "portfolio_stop_distance": total_pnl - PORTFOLIO_MAX_LOSS,
            "positions": position_risks,
        }
