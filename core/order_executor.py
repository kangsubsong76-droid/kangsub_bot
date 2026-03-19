"""주문 실행 엔진 — TWAP 분산매수/매도, 분할매수 관리"""
import time
from datetime import datetime, timedelta
from dataclasses import dataclass
from config.settings import (
    TWAP_INTERVALS, TWAP_INTERVAL_MINUTES, TWAP_START, TWAP_END,
    SPLIT_BUY_RATIOS, KIWOOM_MOCK, LOG_DIR,
)
from utils.logger import setup_logger

log = setup_logger("order_executor", LOG_DIR)


@dataclass
class OrderResult:
    code: str
    name: str
    side: str          # "BUY" or "SELL"
    total_qty: int
    total_amount: float
    avg_price: float
    status: str        # "FILLED", "PARTIAL", "FAILED"
    executions: list   # 개별 체결 내역


class OrderExecutor:
    """
    키움 API 주문 실행기 (페이퍼 트레이딩 포함)
    kiwoom_api가 None이면 시뮬레이션 모드로 동작
    """

    def __init__(self, kiwoom_api=None, paper_trading: bool = False):
        # kiwoom_api가 KiwoomRestAPI 인스턴스이거나 None
        self.kiwoom = kiwoom_api
        self.paper_trading = paper_trading or (kiwoom_api is None)
        mode = "페이퍼트레이딩" if self.paper_trading else ("모의투자" if KIWOOM_MOCK else "실전매매")
        log.info(f"주문 실행기 초기화 [{mode}]")

    def _is_market_open(self) -> bool:
        now = datetime.now().strftime("%H:%M")
        return TWAP_START <= now <= TWAP_END

    def _calc_qty(self, amount: float, price: float) -> int:
        """주문금액 / 주가 → 수량 (100주 단위 아님, 1주 단위)"""
        if price <= 0:
            return 0
        return max(1, int(amount / price))

    # ── TWAP 매수 ──

    def twap_buy(
        self, code: str, name: str, total_amount: float, current_price: float
    ) -> OrderResult:
        """
        TWAP 매수: total_amount를 TWAP_INTERVALS회로 나눠 TWAP_INTERVAL_MINUTES 간격으로 주문
        """
        if not self._is_market_open():
            log.warning(f"장 운영시간 외 매수 요청 ({name})")
            return OrderResult(code, name, "BUY", 0, 0, 0, "FAILED", [])

        slice_amount = total_amount / TWAP_INTERVALS
        executions = []
        total_qty = 0
        total_cost = 0.0

        log.info(f"TWAP 매수 시작: {name}({code}) {total_amount:,.0f}원 / {TWAP_INTERVALS}회 분할")

        for i in range(TWAP_INTERVALS):
            qty = self._calc_qty(slice_amount, current_price)
            if qty <= 0:
                continue

            exec_price = self._execute_order(code, "BUY", qty, current_price)
            if exec_price > 0:
                executions.append({"qty": qty, "price": exec_price, "time": datetime.now().isoformat()})
                total_qty += qty
                total_cost += exec_price * qty
                log.info(f"  [{i+1}/{TWAP_INTERVALS}] {name} {qty}주 @ {exec_price:,.0f}원")

            if i < TWAP_INTERVALS - 1:
                time.sleep(TWAP_INTERVAL_MINUTES * 60) if not self.paper_trading else time.sleep(0.1)

        avg_price = total_cost / total_qty if total_qty > 0 else 0
        status = "FILLED" if len(executions) == TWAP_INTERVALS else "PARTIAL" if executions else "FAILED"
        return OrderResult(code, name, "BUY", total_qty, total_cost, avg_price, status, executions)

    # ── 분할매수 ──

    def split_buy(
        self, code: str, name: str, budget: float, current_price: float, stage: int
    ) -> OrderResult:
        """
        분할매수 단계별 실행
        stage: 1=1차(40%), 2=2차(30%), 3=3차(30%)
        """
        ratio = SPLIT_BUY_RATIOS[stage - 1] if 1 <= stage <= 3 else 0
        amount = budget * ratio
        log.info(f"분할매수 {stage}차: {name} {amount:,.0f}원 (전체예산 {budget:,.0f}원 × {ratio:.0%})")
        return self.twap_buy(code, name, amount, current_price)

    # ── 매도 ──

    def sell(
        self, code: str, name: str, qty: int, current_price: float, reason: str = ""
    ) -> OrderResult:
        """시장가 즉시 매도 (손절 등 긴급 상황)"""
        log.info(f"매도 실행: {name}({code}) {qty}주 @ {current_price:,.0f}원 [{reason}]")
        exec_price = self._execute_order(code, "SELL", qty, current_price)
        if exec_price > 0:
            return OrderResult(
                code, name, "SELL", qty, exec_price * qty, exec_price, "FILLED",
                [{"qty": qty, "price": exec_price, "time": datetime.now().isoformat(), "reason": reason}]
            )
        return OrderResult(code, name, "SELL", 0, 0, 0, "FAILED", [])

    def sell_all(self, holdings: dict, reason: str = "포트폴리오 한도 초과") -> list[OrderResult]:
        """전량 매도"""
        log.warning(f"⚠️ 전량 매도 실행: {reason}")
        results = []
        for code, holding in holdings.items():
            result = self.sell(code, holding.name, holding.quantity, holding.current_price, reason)
            results.append(result)
        return results

    # ── 저수준 주문 실행 ──

    def _execute_order(self, code: str, side: str, qty: int, price: float) -> float:
        """실제 주문 실행 (키움 API 또는 시뮬레이션)"""
        if self.paper_trading:
            # 페이퍼 트레이딩: 슬리피지 0.05% 적용
            slippage = 1.0005 if side == "BUY" else 0.9995
            return round(price * slippage, 0)

        if self.kiwoom:
            try:
                # KiwoomRestAPI 사용 (REST API)
                if side == "BUY":
                    result = self.kiwoom.buy_market(code, qty)
                else:
                    result = self.kiwoom.sell_market(code, qty)

                if result and result.get("rt_cd") == "0":
                    log.info(f"REST API 주문 성공: {code} {side} {qty}주")
                    return price
                else:
                    msg = result.get("msg1", "알 수 없는 오류") if result else "응답 없음"
                    log.error(f"REST API 주문 실패: {code} {side} {qty}주 — {msg}")
                    return 0
            except Exception as e:
                log.error(f"키움 REST API 주문 오류: {e}")
                return 0

        log.warning("키움 API 미연결 — 주문 스킵")
        return 0
