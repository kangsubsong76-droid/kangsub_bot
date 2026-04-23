"""
SYNC_portfolio.py
─────────────────────────────────────────────────────
Kiwoom ka01002 → portfolio_manual.json 동기화
EC2에서 직접 실행:  py C:\kangsub_bot\SYNC_portfolio.py
─────────────────────────────────────────────────────
"""
import sys
import json
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

STORE = ROOT / "data" / "store"
STORE.mkdir(parents=True, exist_ok=True)
MANUAL_PATH = STORE / "portfolio_manual.json"

# ── 현재 total_capital 로드 (기존 파일 우선, 없으면 설정값) ──
def _load_total_capital() -> int:
    if MANUAL_PATH.exists():
        try:
            d = json.loads(MANUAL_PATH.read_text(encoding="utf-8"))
            tc = d.get("total_capital", 0)
            if tc > 0:
                return tc
        except Exception:
            pass
    try:
        from config.settings import TOTAL_CAPITAL
        return TOTAL_CAPITAL
    except Exception:
        return 20_000_000

def main():
    print("=" * 55)
    print("  KangSub Bot — 포트폴리오 수동 동기화")
    print(f"  {datetime.now():%Y-%m-%d %H:%M:%S}")
    print("=" * 55)

    # ── Kiwoom API 초기화 ──
    try:
        from core.kiwoom_rest import KiwoomRestAPI
        kiwoom = KiwoomRestAPI()
        print("✅ Kiwoom REST API 연결")
    except Exception as e:
        print(f"❌ Kiwoom API 초기화 실패: {e}")
        sys.exit(1)

    # ── ka01002 — 계좌평가잔고내역 (수동매수 포함 전체) ──
    print("\n[1] ka01002 계좌평가잔고내역 조회 중...")
    holdings_data = kiwoom.get_portfolio_holdings()

    if not holdings_data or not holdings_data.get("holdings") and holdings_data.get("total_value", 0) == 0:
        print("⚠️  ka01002 응답 없음 — ka01690(일별잔고) 폴백 시도...")
        holdings_data = kiwoom.get_balance()

    if not holdings_data or holdings_data.get("error"):
        print("❌ API 조회 실패. 네트워크 또는 API 키를 확인하세요.")
        sys.exit(1)

    holdings  = holdings_data.get("holdings", [])
    cash      = int(holdings_data.get("cash", 0))
    total_val = int(holdings_data.get("total_value", 0))
    total_pnl = float(holdings_data.get("total_pnl_pct", 0))
    source    = holdings_data.get("source", "?")

    # ── 결과 출력 ──
    print(f"\n[2] API 응답 ({source})")
    print(f"  현금(주문가능):  {cash:>15,.0f}원")
    print(f"  주식 평가총액:   {total_val:>15,.0f}원")
    print(f"  합계:           {cash + total_val:>15,.0f}원")
    print(f"  수익률:          {total_pnl:>+.2f}%")
    print(f"  보유종목수:       {len(holdings)}종목")

    if holdings:
        print("\n  ─── 보유종목 ───")
        for h in holdings:
            pnl_s = f"{h.get('pnl_pct', 0):+.2f}%"
            print(f"    {h['name'][:10]:<10} ({h['code']})  "
                  f"수량: {h['qty']:>5,}주  "
                  f"평균단가: {h['avg_price']:>8,.0f}원  "
                  f"현재가: {h['current_price']:>8,.0f}원  "
                  f"평가: {h['value']:>10,.0f}원  {pnl_s}")

    # ── 스크린샷 값과 대조 ──
    SCREENSHOT = {
        "두산에너빌리티": {"value": 6_476_600, "pnl_pct": 31.10, "pnl_amount": 1_532_848},
        "cash": 15_071_418,
    }
    print("\n[3] 스크린샷 대조")
    print(f"  현금  — API: {cash:>12,.0f}원  스샷: {SCREENSHOT['cash']:>12,.0f}원  "
          f"{'✅ 일치' if abs(cash - SCREENSHOT['cash']) < 1000 else f'⚠️ 차이 {cash - SCREENSHOT[\"cash\"]:+,.0f}원'}")
    for h in holdings:
        if h["name"].replace(" ", "") in SCREENSHOT:
            ss = SCREENSHOT[h["name"].replace(" ", "")]
            diff = h["value"] - ss["value"]
            print(f"  {h['name']} — API: {h['value']:>10,.0f}원  스샷: {ss['value']:>10,.0f}원  "
                  f"{'✅ 일치' if abs(diff) < 1000 else f'⚠️ 차이 {diff:+,.0f}원 (현재가 변동 정상)'}")

    # ── portfolio_manual.json 저장 ──
    total_capital = _load_total_capital()
    # cash + 주식 평가액 합계가 original capital보다 크면 total_capital 재설정
    implied_capital = cash + sum(h.get("value", 0) for h in holdings)
    if implied_capital > total_capital:
        print(f"\n  ℹ️  implied capital({implied_capital:,.0f}) > total_capital({total_capital:,.0f})")
        total_capital = implied_capital
        print(f"     total_capital을 {total_capital:,.0f}으로 조정")

    # 실현손익(total_pnl_amount)은 holdings 기준으로 계산
    total_pnl_amount = sum(h.get("pnl_amount", 0) for h in holdings)
    pnl_pct_calc = round(total_pnl_amount / (total_val) * 100, 2) if total_val else 0

    out = {
        "total_capital": total_capital,
        "cash":          cash,
        "total_value":   total_val,
        "num_holdings":  len(holdings),
        "total_pnl":     pnl_pct_calc,
        "total_pnl_pct": pnl_pct_calc,
        "holdings":      holdings,
        "source":        source,
        "updated_at":    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    MANUAL_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✅ portfolio_manual.json 저장 완료")
    print(f"   경로: {MANUAL_PATH}")
    print(f"   total_capital : {total_capital:,.0f}원")
    print(f"   cash          : {cash:,.0f}원")
    print(f"   total_value   : {total_val:,.0f}원")
    print(f"   total         : {cash + total_val:,.0f}원")
    print("=" * 55)


if __name__ == "__main__":
    main()
