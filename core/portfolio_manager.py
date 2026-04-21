"""포트폴리오 매니저 — 보유종목 관리, 비중 계산, 배분 엔진"""
import json
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional
from config.settings import (
    TOTAL_CAPITAL, GENERAL_RATIO, DIVIDEND_RATIO,
    MAX_GENERAL_STOCKS, MAX_DIVIDEND_STOCKS, SPLIT_BUY_RATIOS, DATA_DIR,
)
from config.universe import SECTORS, DIVIDEND_TOP12, get_stock_name
from core.risk_manager import StockPosition
from utils.logger import setup_logger

log = setup_logger("portfolio_mgr")


@dataclass
class Holding:
    code: str
    name: str
    category: str           # "general" or "dividend"
    sector: str
    avg_price: float
    quantity: int
    buy_dates: list[str] = field(default_factory=list)
    split_stage: int = 0    # 0=미매수, 1=1차, 2=2차, 3=3차(완료)
    high_since_buy: float = 0.0
    current_price: float = 0.0

    @property
    def invested(self) -> float:
        return self.avg_price * self.quantity

    @property
    def market_value(self) -> float:
        return self.current_price * self.quantity

    @property
    def pnl(self) -> float:
        return self.market_value - self.invested

    @property
    def pnl_pct(self) -> float:
        return self.pnl / self.invested if self.invested > 0 else 0

    def to_risk_position(self) -> StockPosition:
        return StockPosition(
            code=self.code, name=self.name,
            buy_price=self.avg_price, quantity=self.quantity,
            buy_date=datetime.fromisoformat(self.buy_dates[0]) if self.buy_dates else datetime.now(),
            current_price=self.current_price,
            high_since_buy=self.high_since_buy,
        )


class PortfolioManager:
    def __init__(self):
        self.holdings: dict[str, Holding] = {}
        self.cash = float(TOTAL_CAPITAL)
        self.total_capital = float(TOTAL_CAPITAL)
        self._load()

    # === 배분 계산 ===

    def calc_sector_budget(self, sector_key: str) -> float:
        """섹터별 목표 투자금액"""
        if sector_key in [s for s in SECTORS]:
            weight = SECTORS[sector_key]["weight"]
            return TOTAL_CAPITAL * GENERAL_RATIO * weight
        return 0

    def calc_dividend_budget(self, code: str) -> float:
        """배당종목별 목표 투자금액"""
        for group in DIVIDEND_TOP12.values():
            if code in group and "weight" in group[code]:
                return TOTAL_CAPITAL * DIVIDEND_RATIO * group[code]["weight"]
        return 0

    def calc_split_amount(self, total_budget: float, stage: int) -> float:
        """분할매수 단계별 금액 (stage: 0=1차, 1=2차, 2=3차)"""
        if 0 <= stage < len(SPLIT_BUY_RATIOS):
            return total_budget * SPLIT_BUY_RATIOS[stage]
        return 0

    # === 보유 종목 관리 ===

    def add_holding(self, code: str, name: str, category: str, sector: str,
                    price: float, qty: int, stage: int = 1):
        if code in self.holdings:
            h = self.holdings[code]
            total_cost = h.avg_price * h.quantity + price * qty
            total_qty = h.quantity + qty
            h.avg_price = total_cost / total_qty
            h.quantity = total_qty
            h.split_stage = stage
            h.buy_dates.append(datetime.now().isoformat())
        else:
            self.holdings[code] = Holding(
                code=code, name=name, category=category, sector=sector,
                avg_price=price, quantity=qty, split_stage=stage,
                buy_dates=[datetime.now().isoformat()],
                high_since_buy=price, current_price=price,
            )
        cost = price * qty
        self.cash -= cost
        log.info(f"매수: {name} {qty}주 @ {price:,.0f}원 (잔고 {self.cash:,.0f}원)")
        self._save()

    def remove_holding(self, code: str, qty: int = None, price: float = 0):
        if code not in self.holdings:
            return
        h = self.holdings[code]
        sell_qty = qty or h.quantity
        sell_qty = min(sell_qty, h.quantity)
        proceeds = price * sell_qty
        self.cash += proceeds
        pnl = (price - h.avg_price) * sell_qty
        log.info(f"매도: {h.name} {sell_qty}주 @ {price:,.0f}원 (손익 {pnl:+,.0f}원)")

        h.quantity -= sell_qty
        if h.quantity <= 0:
            del self.holdings[code]
        self._save()
        return {"pnl": pnl, "pnl_pct": pnl / (h.avg_price * sell_qty) if h.avg_price else 0}

    def update_prices(self, prices: dict[str, float]):
        """실시간 가격 업데이트"""
        for code, price in prices.items():
            if code in self.holdings:
                h = self.holdings[code]
                h.current_price = price
                if price > h.high_since_buy:
                    h.high_since_buy = price

    # === 상태 조회 ===

    @property
    def total_value(self) -> float:
        return self.cash + sum(h.market_value for h in self.holdings.values())

    @property
    def total_pnl_pct(self) -> float:
        return (self.total_value - self.total_capital) / self.total_capital

    @property
    def general_holdings(self) -> list[Holding]:
        return [h for h in self.holdings.values() if h.category == "general"]

    @property
    def dividend_holdings(self) -> list[Holding]:
        return [h for h in self.holdings.values() if h.category == "dividend"]

    @property
    def general_value(self) -> float:
        return sum(h.market_value for h in self.general_holdings)

    @property
    def dividend_value(self) -> float:
        return sum(h.market_value for h in self.dividend_holdings)

    def can_buy_general(self) -> bool:
        return len(self.general_holdings) < MAX_GENERAL_STOCKS

    def can_buy_dividend(self) -> bool:
        return len(self.dividend_holdings) < MAX_DIVIDEND_STOCKS

    def get_summary(self) -> dict:
        return {
            "total_value": self.total_value,
            "total_pnl": self.total_pnl_pct,
            "cash": self.cash,
            "num_holdings": len(self.holdings),
            "general_count": len(self.general_holdings),
            "dividend_count": len(self.dividend_holdings),
            "general_value": self.general_value,
            "dividend_value": self.dividend_value,
            "holdings": [
                {
                    "code": h.code, "name": h.name, "category": h.category,
                    "qty": h.quantity, "avg_price": h.avg_price,
                    "current": h.current_price, "pnl_pct": h.pnl_pct,
                    "sector": h.sector, "stage": h.split_stage,
                }
                for h in self.holdings.values()
            ],
        }

    # === 영속화 ===

    def _save(self):
        data = {
            "cash": self.cash,
            "total_capital": self.total_capital,
            "holdings": {
                code: asdict(h) for code, h in self.holdings.items()
            },
            "updated": datetime.now().isoformat(),
        }
        path = DATA_DIR / "portfolio.json"
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _load(self):
        path = DATA_DIR / "portfolio.json"
        manual_path = DATA_DIR / "portfolio_manual.json"   # DATA_DIR = data/store 이미 포함

        # 1) bot 관리 포트폴리오 로드
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                self.cash = data.get("cash", TOTAL_CAPITAL)
                self.total_capital = data.get("total_capital", TOTAL_CAPITAL)
                for code, hd in data.get("holdings", {}).items():
                    self.holdings[code] = Holding(**hd)
                log.info(f"포트폴리오 로드: {len(self.holdings)}종목, 현금 {self.cash:,.0f}원")
            except Exception as e:
                log.error(f"포트폴리오 로드 실패: {e}")

        # 2) 수동 보유 종목 병합 (portfolio_manual.json) — bot 미관리 종목만 추가
        if manual_path.exists():
            try:
                manual = json.loads(manual_path.read_text(encoding="utf-8"))
                merged = 0
                for h in manual.get("holdings", []):
                    code = h.get("code", "")
                    if not code or code in self.holdings:
                        continue
                    qty = int(h.get("qty", 0))
                    if qty <= 0:
                        continue
                    avg   = float(h.get("avg_price", 0))
                    cur   = float(h.get("current_price", avg))
                    self.holdings[code] = Holding(
                        code=code,
                        name=h.get("name", code),
                        category=h.get("category", "general"),
                        sector=h.get("sector", ""),
                        avg_price=avg,
                        quantity=qty,
                        buy_dates=h.get("buy_dates", []),
                        split_stage=h.get("split_stage", 1),
                        high_since_buy=max(cur, avg),
                        current_price=cur,
                    )
                    merged += 1
                    log.info(f"수동 보유 병합: {h.get('name', code)} {qty}주 @ {avg:,.0f}원")
                # bot 포트폴리오가 비어있으면 수동 파일의 현금도 반영
                if not path.exists() or self.cash >= TOTAL_CAPITAL:
                    manual_cash = manual.get("cash", None)
                    if manual_cash is not None:
                        self.cash = float(manual_cash)
                if merged:
                    log.info(f"수동 보유 {merged}종목 병합 완료 — portfolio.json 갱신")
                    self._save()  # 병합 결과를 portfolio.json 에 즉시 저장
            except Exception as e:
                log.error(f"manual portfolio 병합 실패: {e}")
