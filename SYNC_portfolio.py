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
# ★ 여기에 키움 앱 기준 현재 보유 현황을 입력하세요 ★
# ════════════════════════════════════════════════

# 현금 (키움 앱 > 잔고 > 현금 탭 > 주문가능금액)
CASH = 15_071_418

# 총 투자 원금 (처음 넣은 돈 기준, 수익 포함X)
TOTAL_CAPITAL = 20_000_000

# 보유종목 목록
# qty      : 보유 수량 (주)
# avg_price: 평균매입단가 (원) — 키움 앱 > 잔고 > 일반 탭에서 확인
HOLDINGS = [
    {
        "code":      "034020",
        "name":      "두산에너빌리티",
        "qty":       0,          # ★ 수량 입력 필요
        "avg_price": 0,          # ★ 평균단가 입력 필요
        "category":  "general",  # general / dividend / nxt
    },
    # 종목 추가 시 위 형식으로 복사해서 추가
]

# ════════════════════════════════════════════════

def main():
    print("=" * 55)
    print("  KangSub Bot — 포트폴리오 수동 동기화")
    print("  {}".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    print("=" * 55)

    # qty=0 인 종목 체크
    missing = [h["name"] for h in HOLDINGS if h["qty"] == 0 or h["avg_price"] == 0]
    if missing:
        print("\n❌ 수량/평균단가가 0인 종목이 있습니다:")
        for m in missing:
            print("   - {}".format(m))
        print("\n   SYNC_portfolio.py 파일의 HOLDINGS 섹션에")
        print("   qty(수량)와 avg_price(평균단가)를 입력한 뒤 다시 실행하세요.")
        print("   (키움 앱 > 잔고 > 일반 탭에서 확인)")
        return

    # 현재가 조회 (Kiwoom ka10001)
    print("\n[1] 현재가 조회 중 (ka10001)...")
    try:
        from core.kiwoom_rest import KiwoomRestAPI
        kiwoom = KiwoomRestAPI()
        got_prices = True
    except Exception as e:
        print("   ⚠️  Kiwoom API 연결 실패 ({}) — 평균단가로 대체".format(e))
        kiwoom = None
        got_prices = False

    enriched = []
    total_value = 0
    total_pnl_amount = 0

    for h in HOLDINGS:
        code      = h["code"]
        name      = h["name"]
        qty       = int(h["qty"])
        avg_price = float(h["avg_price"])
        cur_price = avg_price  # fallback

        if kiwoom:
            try:
                info = kiwoom.get_stock_info(code)
                if info and info.get("price", 0) > 0:
                    cur_price = float(info["price"])
                    got_prices = True
            except Exception:
                pass

        value      = round(cur_price * qty)
        pnl_amount = round((cur_price - avg_price) * qty)
        pnl_pct    = round((cur_price - avg_price) / avg_price * 100, 2) if avg_price else 0

        total_value      += value
        total_pnl_amount += pnl_amount

        enriched.append({
            "code":          code,
            "name":          name,
            "qty":           qty,
            "avg_price":     avg_price,
            "current_price": cur_price,
            "value":         value,
            "pnl_amount":    pnl_amount,
            "pnl_pct":       pnl_pct,
            "category":      h.get("category", "general"),
        })

        price_src = "API" if got_prices else "평균단가(추정)"
        print("   {} ({})  {}주 @ {:.0f}원  현재가: {:.0f}원 [{}]  평가: {:,.0f}원  {:+.2f}%".format(
            name, code, qty, avg_price, cur_price, price_src, value, pnl_pct))

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
