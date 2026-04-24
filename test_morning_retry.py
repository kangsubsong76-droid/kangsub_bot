"""
오전 루틴 수동 재시도 테스트 스크립트
실행: python test_morning_retry.py

테스트 항목:
  1. 급상승 Top50 수집 (pykrx → yfinance fallback)
  2. 기술적 시그널 생성 + signals.json 저장
  3. nxt_candidates.json 날짜 확인
  4. 텔레그램 테스트 메시지 발송
"""
import sys
import os
import asyncio
from pathlib import Path
from datetime import datetime

# ── 경로 설정 ───────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from config.settings import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
import requests as _req

def tg(msg: str):
    """텔레그램 직접 전송"""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print(f"[TG] {msg}")
        return
    _req.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"},
        timeout=10,
    )
    print(f"[TG] {msg[:80]}")


def sep(title: str):
    print(f"\n{'='*50}")
    print(f"  {title}")
    print(f"{'='*50}")


# ══════════════════════════════════════════════════════════════
# 테스트 1 — 급상승 Top50 수집
# ══════════════════════════════════════════════════════════════
sep("TEST 1: 급상승 Top50 수집")
try:
    from data.surge_tracker import collect, get_top50_today
    print("collect() 호출 중... (최대 30초)")
    stocks = collect(top_n=50)
    if stocks:
        print(f"✅ 수집 성공: {len(stocks)}종목")
        print(f"   1위: {stocks[0]['name']} {stocks[0]['change_rate']:+.1f}%")
        print(f"   2위: {stocks[1]['name']} {stocks[1]['change_rate']:+.1f}%" if len(stocks) > 1 else "")
        tg(
            f"✅ <b>급상승 Top50 수집 성공</b>\n"
            f"1위: {stocks[0]['name']} {stocks[0]['change_rate']:+.1f}%\n"
            f"2위: {stocks[1]['name'] if len(stocks)>1 else '-'}\n"
            f"총 {len(stocks)}종목 수집"
        )
    else:
        print("❌ 수집 실패: 빈 리스트 반환")
        tg("❌ <b>급상승 Top50 수집 실패</b> — 빈 리스트")
except Exception as e:
    print(f"❌ 예외 발생: {e}")
    import traceback; traceback.print_exc()
    tg(f"❌ <b>급상승 Top50 예외</b>: {e}")


# ══════════════════════════════════════════════════════════════
# 테스트 2 — 기술적 시그널 생성
# ══════════════════════════════════════════════════════════════
sep("TEST 2: 기술적 시그널 생성 (signals.json)")
try:
    from core.signal_engine import generate_signals
    from config.universe import get_unique_codes
    from market.data_fetcher import get_kospi_ohlcv, get_usdkrw, get_vkospi, get_stock_ohlcv
    from market.market_analyzer import analyze_market
    import json

    DATA_DIR = BASE_DIR / "data"

    print("시장 데이터 조회 중...")
    kospi_df  = get_kospi_ohlcv(60)
    usdkrw_df = get_usdkrw(14)
    vkospi    = get_vkospi()
    market    = analyze_market(kospi_df, vkospi, usdkrw_df) if not kospi_df.empty else None

    if market is None:
        print("⚠️ 시장 데이터 없음 — 장 마감 후 또는 데이터 오류")
        tg("⚠️ <b>시그널 생성</b>: 시장 데이터 없음 (장 마감 후 정상)")
    else:
        print(f"시장 판단: {market.kospi_trend} / 점수 {market.score:.0f}")
        codes = get_unique_codes()
        print(f"종목 수: {len(codes)}개 — OHLCV 조회 중...")

        signals = generate_signals(market, codes)
        buy_sigs = [s for s in signals if s.action == "BUY"]

        path = DATA_DIR / "signals.json"
        path.write_text(json.dumps([
            {"code": s.code, "name": s.name, "action": s.action,
             "technical_score": s.technical_score, "market_score": s.market_score,
             "news_score": s.news_score, "weighted_score": s.weighted_score,
             "reasons": s.reasons}
            for s in signals
        ], ensure_ascii=False, indent=2), encoding='utf-8')

        print(f"✅ signals.json 저장 완료: 총 {len(signals)}종목, BUY {len(buy_sigs)}개")
        buy_names = ", ".join(s.name for s in buy_sigs[:5]) or "없음"
        tg(
            f"✅ <b>시그널 생성 성공</b>\n"
            f"총 {len(signals)}종목 / BUY {len(buy_sigs)}개\n"
            f"매수 대상: {buy_names}"
        )
except Exception as e:
    print(f"❌ 예외 발생: {e}")
    import traceback; traceback.print_exc()
    tg(f"❌ <b>시그널 생성 예외</b>: {e}")


# ══════════════════════════════════════════════════════════════
# 테스트 3 — nxt_candidates.json 날짜 확인
# ══════════════════════════════════════════════════════════════
sep("TEST 3: nxt_candidates.json 날짜 확인")
try:
    import json
    DATA_DIR = BASE_DIR / "data"
    cand_path = DATA_DIR / "nxt_candidates.json"
    today = datetime.now().strftime("%Y-%m-%d")

    if not cand_path.exists():
        print("⚠️ nxt_candidates.json 없음 (07:30 분석 미실행)")
        tg("⚠️ <b>NXT 후보 파일 없음</b> — 07:30 분석 실행 필요")
    else:
        cand = json.loads(cand_path.read_text(encoding="utf-8"))
        cand_date = cand.get("date", "없음")
        stocks = cand.get("stocks", [])
        match = "✅" if cand_date == today else "❌"
        print(f"{match} nxt_candidates 날짜: {cand_date} (오늘: {today})")
        print(f"   후보 종목: {len(stocks)}개")
        if stocks:
            for s in stocks[:3]:
                print(f"   - {s.get('name')} ({s.get('code')}) [{s.get('confidence','')}]")
        tg(
            f"{match} <b>NXT 후보 날짜</b>: {cand_date}\n"
            f"오늘: {today} {'일치' if cand_date == today else '불일치'}\n"
            f"후보 {len(stocks)}종목"
        )
except Exception as e:
    print(f"❌ 예외 발생: {e}")
    tg(f"❌ <b>NXT 날짜 확인 예외</b>: {e}")


# ══════════════════════════════════════════════════════════════
# 완료
# ══════════════════════════════════════════════════════════════
sep("완료")
print(f"테스트 완료 — {datetime.now():%H:%M:%S}")
tg(f"🧪 <b>오전 루틴 수동 재시도 완료</b> [{datetime.now():%H:%M:%S}]\n위 결과를 확인하세요.")
