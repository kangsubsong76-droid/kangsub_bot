"""
누락된 매매기록 복원 스크립트
EC2에서 1회 실행: python patch_missing_trades.py

동작:
  1) 키움 kt00004 → 현재 실제 보유종목 조회
  2) portfolio_manual.json 과 비교
     - manual 에 있지만 API 에 없는 종목 → 매도된 것으로 간주
     - API 에 있지만 manual 에 없는 종목 → 매수된 것으로 간주
  3) trades.json 에 누락 체결 기록 추가
  4) portfolio_manual.json 을 실제 보유 현황으로 덮어쓰기
  5) 결과 출력
"""
import sys
import json
from pathlib import Path
from datetime import datetime

# 프로젝트 루트
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

DATA_STORE  = ROOT / "data" / "store"
TRADES_PATH = ROOT / "data" / "trades.json"
MANUAL_PATH = DATA_STORE / "portfolio_manual.json"

def load_json(path, default):
    try:
        if Path(path).exists():
            return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except Exception as e:
        print(f"  [경고] {path} 읽기 실패: {e}")
    return default

def save_json(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

# ── 1. 키움 API 실제 보유종목 조회 ─────────────────────
print("=" * 60)
print("  누락 매매기록 복원 스크립트")
print("=" * 60)

api_holdings = {}
api_cash = None

try:
    from core.kiwoom_rest import KiwoomRestAPI
    kiwoom = KiwoomRestAPI()
    result = kiwoom.get_portfolio_holdings()
    if result and result.get("total_value", 0) > 0:
        for h in result.get("holdings", []):
            code = h.get("code", "")
            if code:
                api_holdings[code] = h
        api_cash = result.get("cash", None)
        print(f"\n✅ 키움 kt00004 조회 성공: {len(api_holdings)}종목, 현금 {api_cash:,.0f}원")
    else:
        print("\n⚠️  키움 API 응답 없음 — 수동 입력 모드로 전환")
except Exception as e:
    print(f"\n⚠️  키움 API 오류: {e} — 수동 입력 모드")

# ── 2. portfolio_manual.json 현재 상태 ─────────────────
manual = load_json(MANUAL_PATH, {"holdings": [], "cash": 0, "total_capital": 20_000_000})
manual_holdings = {h["code"]: h for h in manual.get("holdings", [])}
manual_cash = manual.get("cash", 0)

print(f"\n📄 portfolio_manual.json: {len(manual_holdings)}종목")
for code, h in manual_holdings.items():
    print(f"   {h['name']}({code}): {h['qty']}주 @ {h.get('avg_price',0):,.0f}원")

# ── 3. API vs Manual 비교 ──────────────────────────────
print("\n" + "─" * 60)
missing_sells = []   # manual 에 있지만 API 에 없음 → 매도됨
missing_buys  = []   # API 에 있지만 manual 에 없음 → 매수됨

if api_holdings:
    for code, mh in manual_holdings.items():
        if code not in api_holdings:
            missing_sells.append(mh)
            print(f"🔴 [매도 감지] {mh['name']}({code}) — manual에 있으나 API에 없음")

    for code, ah in api_holdings.items():
        if code not in manual_holdings:
            missing_buys.append(ah)
            name = ah.get("name", ah.get("stock_name", code))
            print(f"🟢 [매수 감지] {name}({code}) — API에 있으나 manual에 없음")

    if not missing_sells and not missing_buys:
        print("✅ 차이 없음 — manual과 API 보유종목 일치")
else:
    print("⚠️  API 데이터 없음 — 수동으로 누락 매매를 입력합니다")
    print("\n현재 manual 종목:")
    for i, (code, h) in enumerate(manual_holdings.items()):
        print(f"  {i+1}. {h['name']}({code}): {h['qty']}주")
    print("\n매도된 종목 코드를 입력하세요 (쉼표 구분, 없으면 Enter):")
    sold_input = input("  > ").strip()
    if sold_input:
        for code in [c.strip() for c in sold_input.split(",") if c.strip()]:
            if code in manual_holdings:
                missing_sells.append(manual_holdings[code])
                print(f"  🔴 매도 처리: {manual_holdings[code]['name']}({code})")

# ── 4. trades.json 에 누락 체결 기록 추가 ──────────────
print("\n" + "─" * 60)
trades = load_json(TRADES_PATH, [])
now_str = datetime.now().isoformat()
date_str = datetime.now().strftime("%Y-%m-%d")
added = 0

for mh in missing_sells:
    code = mh["code"]
    name = mh["name"]
    qty  = mh["qty"]
    avg  = mh.get("avg_price", 0)
    cur  = mh.get("current_price", avg)

    # API에서 실제 현재가 가져오기 시도
    if api_holdings:
        sell_price = cur
    else:
        print(f"\n{name}({code}) 매도가를 입력하세요 (Enter = {cur:,.0f}원 사용):")
        inp = input("  > ").strip()
        sell_price = float(inp.replace(",","")) if inp else cur

    pnl = (sell_price - avg) * qty
    trades.append({
        "timestamp": now_str,
        "date":      date_str,
        "side":      "매도",
        "code":      code,
        "name":      name,
        "qty":       qty,
        "price":     round(sell_price),
        "amount":    round(sell_price * qty),
        "pnl":       round(pnl),
        "trigger":   "MANUAL_PATCH",
        "note":      "patch_missing_trades.py 복원",
    })
    added += 1
    print(f"  ✅ 매도 기록 추가: {name} {qty}주 @ {sell_price:,.0f}원 (손익 {pnl:+,.0f}원)")

for ah in missing_buys:
    code = ah.get("code", "")
    name = ah.get("name", ah.get("stock_name", code))
    qty  = ah.get("quantity", ah.get("qty", 0))
    avg  = ah.get("avg_price", 0)
    trades.append({
        "timestamp": now_str,
        "date":      date_str,
        "side":      "매수",
        "code":      code,
        "name":      name,
        "qty":       qty,
        "price":     round(avg),
        "amount":    round(avg * qty),
        "pnl":       0,
        "trigger":   "MANUAL_PATCH",
        "note":      "patch_missing_trades.py 복원",
    })
    added += 1
    print(f"  ✅ 매수 기록 추가: {name} {qty}주 @ {avg:,.0f}원")

if added:
    save_json(TRADES_PATH, trades[-500:])
    print(f"\n💾 trades.json 저장 완료 ({added}건 추가, 총 {len(trades)}건)")
else:
    print("\n추가할 체결 기록 없음")

# ── 5. portfolio_manual.json 실제 보유현황으로 업데이트 ─
print("\n" + "─" * 60)
if api_holdings:
    new_holdings = []
    for code, ah in api_holdings.items():
        name = ah.get("name", ah.get("stock_name", code))
        qty  = ah.get("quantity", ah.get("qty", 0))
        avg  = ah.get("avg_price", 0)
        cur  = ah.get("current_price", ah.get("current", avg))
        val  = cur * qty
        pnl_amt = (cur - avg) * qty
        pnl_pct = (cur - avg) / avg * 100 if avg else 0
        new_holdings.append({
            "code":          code,
            "name":          name,
            "qty":           qty,
            "avg_price":     round(avg),
            "current_price": round(cur),
            "value":         round(val),
            "pnl_amount":    round(pnl_amt),
            "pnl_pct":       round(pnl_pct, 2),
            "category":      manual_holdings.get(code, {}).get("category", "general"),
            "sector":        manual_holdings.get(code, {}).get("sector", ""),
        })

    cash = api_cash if api_cash is not None else manual_cash
    # 매도종목 현금 반영 (API cash가 이미 반영돼 있으므로 별도 계산 불필요)
    total_val = cash + sum(h["value"] for h in new_holdings)

    new_manual = {
        "total_capital": manual.get("total_capital", 20_000_000),
        "cash":          round(cash),
        "total_value":   round(total_val),
        "num_holdings":  len(new_holdings),
        "total_pnl":     0.0,
        "total_pnl_pct": 0.0,
        "holdings":      new_holdings,
        "source":        "kt00004_patch",
        "updated_at":    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    save_json(MANUAL_PATH, new_manual)
    print(f"✅ portfolio_manual.json 업데이트 완료")
    print(f"   보유종목: {len(new_holdings)}개 | 현금: {cash:,.0f}원 | 총자산: {total_val:,.0f}원")
    for h in new_holdings:
        print(f"   └ {h['name']}({h['code']}): {h['qty']}주 @ {h['current_price']:,.0f}원 ({h['pnl_pct']:+.1f}%)")
else:
    # API 없는 경우: manual에서 매도 종목만 제거
    remaining = [h for h in manual.get("holdings", [])
                 if h["code"] not in {mh["code"] for mh in missing_sells}]
    manual["holdings"] = remaining
    manual["num_holdings"] = len(remaining)
    manual["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    save_json(MANUAL_PATH, manual)
    print(f"✅ portfolio_manual.json 업데이트 완료 (매도종목 제거)")
    print(f"   잔여 보유종목: {len(remaining)}개")

print("\n" + "=" * 60)
print("  완료! 대시보드를 새로고침하면 반영됩니다.")
print("=" * 60)
