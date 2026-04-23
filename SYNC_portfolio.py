"""
SYNC_portfolio.py
-------------------------------------------------
포트폴리오 수동 동기화 -> portfolio_manual.json
EC2에서 직접 실행:  py C:/kangsub_bot/SYNC_portfolio.py

사용법:
  1. 키움 앱에서 보유종목 수량/평균단가 확인
  2. 아래 HOLDINGS 섹션에 입력
  3. 스크립트 실행
-------------------------------------------------
"""
import json
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).parent
STORE = ROOT / "data" / "store"
STORE.mkdir(parents=True, exist_ok=True)
MANUAL_PATH = STORE / "portfolio_manual.json"

# ════════════════════════════════════════════════
# ★ 키움 앱 스크린샷 기준값 입력 (수량 불필요)  ★
# ════════════════════════════════════════════════

# 현금 (키움 앱 > 잔고 > 현금 탭 > 주문가능금액)
CASH = 15_071_418

# 총 투자 원금
TOTAL_CAPITAL = 20_000_000

# 보유종목 — 평가금액과 수익금만 입력하면 수량/평균단가 자동 역산
# eval_amount : 키움 앱 평가금액
# pnl_amount  : 수익금 (+ 이익 / - 손실)
HOLDINGS = [
    {
        "code":         "034020",
        "name":         "두산에너빌리티",
        "eval_amount":  6_476_600,   # 키움 앱 평가금액
        "pnl_amount":   1_532_848,   # 수익금 (+이면 이익)
        "category":     "general",
    },
    # 종목 추가 시 위 형식으로 복사
]

# ════════════════════════════════════════════════

def main():
    print("=" * 55)
    print("  KangSub Bot — 포트폴리오 수동 동기화")
    print("  {}".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    print("=" * 55)

    # 현재가 조회 (ka10001) → 수량 역산
    print("\n[1] ka10001 현재가 조회 중...")
    try:
        from core.kiwoom_rest import KiwoomRestAPI
        kiwoom = KiwoomRestAPI()
    except Exception as e:
        print("   ⚠️  Kiwoom API 연결 실패: {}".format(e))
        kiwoom = None

    enriched = []
    total_value = 0
    total_pnl_amount = 0

    for h in HOLDINGS:
        code        = h["code"]
        name        = h["name"]
        eval_amount = int(h["eval_amount"])   # 스크린샷 평가금액
        pnl_amount  = int(h["pnl_amount"])    # 스크린샷 수익금
        cost_amount = eval_amount - pnl_amount  # 매입원가 총액

        # ka10001 현재가 조회
        cur_price = 0
        if kiwoom:
            try:
                info = kiwoom.get_stock_info(code)
                if info and info.get("price", 0) > 0:
                    cur_price = float(info["price"])
            except Exception:
                pass

        if cur_price > 0:
            # 현재가 → 수량 역산 (반올림)
            qty       = round(eval_amount / cur_price)
            avg_price = round(cost_amount / qty) if qty else 0
            price_src = "ka10001"
        else:
            # 현재가 미조회 — 평가금액 = 현재가로 가정 (단주 수량 역산 불가)
            cur_price = eval_amount
            qty       = 1
            avg_price = cost_amount
            price_src = "추정(현재가조회실패)"

        pnl_pct = round(pnl_amount / cost_amount * 100, 2) if cost_amount else 0

        total_value      += eval_amount
        total_pnl_amount += pnl_amount

        enriched.append({
            "code":          code,
            "name":          name,
            "qty":           qty,
            "avg_price":     avg_price,
            "current_price": cur_price,
            "value":         eval_amount,
            "pnl_amount":    pnl_amount,
            "pnl_pct":       pnl_pct,
            "category":      h.get("category", "general"),
        })

        print("   {} ({})  {}주  평균단가: {:,.0f}원  현재가: {:,.0f}원 [{}]".format(
            name, code, qty, avg_price, cur_price, price_src))
        print("   평가: {:,.0f}원  수익: {:+,.0f}원 ({:+.2f}%)".format(
            eval_amount, pnl_amount, pnl_pct))

    total_pnl_pct = round(total_pnl_amount / total_value * 100, 2) if total_value else 0

    # ── 스크린샷 대조 ──
    print("\n[2] 스크린샷 대조")
    SS_CASH  = 15_071_418
    SS_STOCK = 6_476_600

    cash_diff  = CASH - SS_CASH
    stock_diff = total_value - SS_STOCK
    cash_tag   = "✅ 일치" if abs(cash_diff) < 1000 else "⚠️ 차이 {:+,.0f}원".format(cash_diff)
    stock_tag  = "✅ 일치" if abs(stock_diff) < 50_000 else "⚠️ 차이 {:+,.0f}원 (현재가 변동)".format(stock_diff)

    print("  현금       — 입력: {:>12,.0f}원  스샷: {:>12,.0f}원  {}".format(CASH, SS_CASH, cash_tag))
    print("  주식평가액 — 계산: {:>12,.0f}원  스샷: {:>12,.0f}원  {}".format(total_value, SS_STOCK, stock_tag))
    print("  합계       — 계산: {:>12,.0f}원  스샷: {:>12,.0f}원".format(
        CASH + total_value, SS_CASH + SS_STOCK))

    # ── 저장 ──
    out = {
        "total_capital": TOTAL_CAPITAL,
        "cash":          CASH,
        "total_value":   total_value,
        "num_holdings":  len(enriched),
        "total_pnl":     total_pnl_pct,
        "total_pnl_pct": total_pnl_pct,
        "holdings":      enriched,
        "source":        "manual",
        "updated_at":    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    MANUAL_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n✅ portfolio_manual.json 저장 완료")
    print("   경로        : {}".format(MANUAL_PATH))
    print("   total_capital: {:>15,.0f}원".format(TOTAL_CAPITAL))
    print("   cash         : {:>15,.0f}원".format(CASH))
    print("   stock_value  : {:>15,.0f}원".format(total_value))
    print("   합계         : {:>15,.0f}원".format(CASH + total_value))
    print("   수익률       : {:>+.2f}%".format(total_pnl_pct))
    print("=" * 55)


if __name__ == "__main__":
    main()
