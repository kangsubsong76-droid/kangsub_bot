"""
급상승 Top50 수집기 — 매일 10:30 기준 스냅샷
우선순위: 키움 ka10027(주식등락률순위) → pykrx(KOSPI+KOSDAQ 합산)

DB 스키마  data/store/surge_db.json
──────────────────────────────────────
{
  "2026-04-21": [
    {"rank": 1, "code": "000123", "name": "씨아이에스",
     "price": 16310, "change_rate": 29.9, "volume": 5000000,
     "market": "KOSPI", "collected_at": "10:30:05"},
    ...
  ]
}

공개 헬퍼 (signal_engine에서 임포트해 사용)
─────────────────────────────────────────
  collect(top_n=50)              -> list[dict]   수집 + DB 저장 (main에서 호출)
  get_surge_count(code, days=20) -> int          최근 N일 중 Top50 등장 일수
  get_surge_score(code, days=20) -> float 0~1    정규화 점수 (signal_engine 입력)
  get_latest_rank(code)          -> int | None   오늘 순위 (비등장시 None)
  get_top50_today()              -> list[dict]   오늘 수집된 Top50 전체
  is_in_top50_today(code)        -> bool
"""
import json
import concurrent.futures
from datetime import datetime, timedelta
from pathlib import Path
from utils.logger import setup_logger

log = setup_logger("surge_tracker")

_DB_PATH = Path(__file__).parent.parent / "data" / "store" / "surge_db.json"
_API_TIMEOUT = 25   # 외부 API 타임아웃 (초) — pykrx KOSPI+KOSDAQ 합산 조회 시간 확보

# pykrx
try:
    from pykrx import stock as krx
except ImportError:
    krx = None

# ── 키움 인스턴스 싱글톤 ────────────────────────────────────
_kiwoom_instance = None

def set_kiwoom(instance):
    global _kiwoom_instance
    _kiwoom_instance = instance

def _get_kiwoom():
    """
    ka10027은 데이터 조회 API이므로 KIWOOM_MOCK(모의투자) 여부와 무관하게 사용 가능.
    실계좌/모의투자 모두 토큰 인증만 성공하면 등락률 순위 조회 동작.
    다만 KIWOOM_APP_KEY/SECRET이 미설정인 경우 인증 실패 → None 반환.
    """
    global _kiwoom_instance
    if _kiwoom_instance is not None:
        return _kiwoom_instance
    try:
        from config.settings import KIWOOM_APP_KEY, KIWOOM_SECRET_KEY
        if not KIWOOM_APP_KEY or not KIWOOM_SECRET_KEY:
            log.debug("KIWOOM_APP_KEY/SECRET 미설정 — ka10027 스킵")
            return None
        from core.kiwoom_rest import KiwoomRestAPI
        _kiwoom_instance = KiwoomRestAPI()
        return _kiwoom_instance
    except Exception as e:
        log.debug(f"Kiwoom 초기화 실패: {e}")
        return None


# ── DB 유틸 ────────────────────────────────────────────────
def _load_db() -> dict:
    if _DB_PATH.exists():
        try:
            return json.loads(_DB_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_db(data: dict):
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    _DB_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ── 타임아웃 래퍼 ───────────────────────────────────────────
def _call_with_timeout(fn, timeout=_API_TIMEOUT):
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(fn)
        try:
            return fut.result(timeout=timeout)
        except (concurrent.futures.TimeoutError, Exception):
            return None


# ── 1순위: 키움 REST API (ka10027) ─────────────────────────
def _fetch_kiwoom(top_n: int = 50) -> list | None:
    """
    키움 ka10027 — 주식등락률순위
    전체 시장(KOSPI+KOSDAQ) 등락률 상위 top_n 반환
    """
    kiwoom = _get_kiwoom()
    if not kiwoom:
        return None
    try:
        rows = kiwoom.get_surge_ranking(market="0", top_n=top_n)
        if not rows:
            log.debug("ka10027 응답 비어있음 — pykrx 폴백")
            return None
        log.info(f"ka10027 급상승 {len(rows)}종목 수신")
        return rows
    except Exception as e:
        log.debug(f"ka10027 실패: {e}")
        return None


# ── 2순위: pykrx (KOSPI + KOSDAQ 합산 등락률순) ─────────────
def _fetch_pykrx(top_n: int = 50) -> list | None:
    if not krx:
        return None
    today = datetime.now().strftime("%Y%m%d")

    def _get_both():
        import pandas as pd
        dfs = []
        for market, mname in [("KOSPI", "KOSPI"), ("KOSDAQ", "KOSDAQ")]:
            try:
                df = krx.get_market_ohlcv_by_ticker(today, market=market)
                if df is None or df.empty:
                    continue
                # 필드명 정규화 (한글/영문 혼재 대응)
                col_map = {}
                for c in df.columns:
                    c_lower = str(c).lower().replace(" ", "")
                    if "등락률" in str(c) or "changeratio" in c_lower or "chgratio" in c_lower:
                        col_map[c] = "change_rate"
                    elif "종가" in str(c) or "close" in c_lower:
                        col_map[c] = "price"
                    elif "거래량" in str(c) or "volume" in c_lower:
                        col_map[c] = "volume"
                df = df.rename(columns=col_map)
                if "change_rate" not in df.columns:
                    # 직접 계산
                    open_col = next((c for c in df.columns if "시가" in str(c) or "open" in str(c).lower()), None)
                    close_col = next((c for c in df.columns if "종가" in str(c) or "close" in str(c).lower()), None)
                    if open_col and close_col:
                        df["change_rate"] = (df[close_col] - df[open_col]) / df[open_col].replace(0, float("nan")) * 100
                df["market"] = mname
                dfs.append(df)
            except Exception as e:
                log.debug(f"pykrx {market} 실패: {e}")
        if not dfs:
            return None
        combined = pd.concat(dfs)
        return combined

    result = _call_with_timeout(_get_both)
    if result is None or result.empty:
        log.warning(f"pykrx 급상승 조회 실패 (타임아웃 또는 빈 응답)")
        return None

    # 등락률 기준 정렬
    if "change_rate" not in result.columns:
        log.warning("pykrx change_rate 컬럼 없음")
        return None

    result = result.sort_values("change_rate", ascending=False)

    # 종목명 조회 (krx.get_market_ticker_name)
    stocks = []
    for i, (code, row) in enumerate(result.head(top_n).iterrows(), 1):
        try:
            name = krx.get_market_ticker_name(str(code))
        except Exception:
            name = str(code)

        stocks.append({
            "rank":        i,
            "code":        str(code).zfill(6),
            "name":        name,
            "price":       int(row.get("price", row.get("종가", 0))),
            "change_rate": round(float(row.get("change_rate", 0)), 2),
            "volume":      int(row.get("volume", row.get("거래량", 0))),
            "market":      row.get("market", ""),
        })

    log.info(f"pykrx 급상승 Top{top_n} 수집 완료 (1위: {stocks[0]['name'] if stocks else '-'})")
    return stocks


# ── 3순위: yfinance 폴백 (KOSPI+KOSDAQ 전체, 당일 등락률순) ────
def _fetch_yfinance(top_n: int = 50) -> list | None:
    """
    pykrx 실패 시 최후 폴백.
    yfinance 로 KOSPI 대형주 유니버스를 조회해 등락률 상위 top_n 반환.
    """
    try:
        import yfinance as yf
        import pandas as pd
    except ImportError:
        log.debug("yfinance 미설치 — 폴백 불가")
        return None

    # 주요 KOSPI 종목 샘플 (유니버스 없을 때 최소 커버리지)
    try:
        from config.universe import get_unique_codes
        codes = get_unique_codes()
    except Exception:
        codes = []

    if not codes:
        log.debug("yfinance: 유니버스 없음 — 폴백 스킵")
        return None

    tickers = [f"{c}.KS" for c in codes] + [f"{c}.KQ" for c in codes]

    def _dl():
        data = yf.download(
            tickers, period="2d", interval="1d",
            group_by="ticker", auto_adjust=True, progress=False, threads=True
        )
        return data

    data = _call_with_timeout(_dl, timeout=_API_TIMEOUT)
    if data is None or data.empty:
        log.warning("yfinance 데이터 없음")
        return None

    rows = []
    for ticker in tickers:
        try:
            code_raw = ticker.replace(".KS", "").replace(".KQ", "")
            mkt = "KOSPI" if ticker.endswith(".KS") else "KOSDAQ"
            if ticker in data.columns.get_level_values(0):
                df = data[ticker]
            else:
                continue
            if len(df) < 2:
                continue
            prev_close = float(df["Close"].iloc[-2])
            today_close = float(df["Close"].iloc[-1])
            if prev_close <= 0:
                continue
            change_rate = (today_close - prev_close) / prev_close * 100
            volume = int(df["Volume"].iloc[-1])
            rows.append({
                "code":        code_raw.zfill(6),
                "name":        code_raw,
                "price":       int(today_close),
                "change_rate": round(change_rate, 2),
                "volume":      volume,
                "market":      mkt,
            })
        except Exception:
            continue

    if not rows:
        return None

    rows.sort(key=lambda r: r["change_rate"], reverse=True)
    for i, r in enumerate(rows[:top_n], 1):
        r["rank"] = i

    log.info(f"yfinance 급상승 폴백: Top{top_n} 중 {len(rows[:top_n])}종목 수집")
    return rows[:top_n]


# ── 공개: 수집 메인 ─────────────────────────────────────────
def collect(top_n: int = 50) -> list:
    """
    10:30 호출 → 키움 ka10027 → pykrx 폴백 → yfinance 최종 폴백 → DB 저장
    반환: 수집된 Top50 리스트 (실패 시 빈 리스트)
    """
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    collected_at = now.strftime("%H:%M:%S")

    log.info(f"[surge_tracker] Top{top_n} 급상승 수집 시작 ({collected_at})")

    stocks = _fetch_kiwoom(top_n) or _fetch_pykrx(top_n) or _fetch_yfinance(top_n)

    if not stocks:
        log.error("[surge_tracker] 급상승 데이터 수집 실패 — 전체 소스 응답 없음")
        return []

    # collected_at 태그 추가
    for s in stocks:
        s["collected_at"] = collected_at

    # DB 저장
    db = _load_db()
    db[today] = stocks
    _save_db(db)

    log.info(
        f"[surge_tracker] DB 저장 완료: {today} / {len(stocks)}종목 "
        f"(1위 {stocks[0]['name']} {stocks[0]['change_rate']:+.1f}%)"
    )
    return stocks


# ── 공개: 조회 헬퍼 ─────────────────────────────────────────
def get_top50_today() -> list:
    """오늘 수집된 Top50 전체 반환 (없으면 빈 리스트)"""
    db = _load_db()
    return db.get(datetime.now().strftime("%Y-%m-%d"), [])


def is_in_top50_today(code: str) -> bool:
    code = code.zfill(6)
    return any(s["code"] == code for s in get_top50_today())


def get_latest_rank(code: str) -> int | None:
    """오늘 Top50 내 순위 반환 (없으면 None)"""
    code = code.zfill(6)
    for s in get_top50_today():
        if s["code"] == code:
            return s["rank"]
    return None


def get_surge_count(code: str, days: int = 20) -> int:
    """최근 days 거래일 중 Top50에 등장한 일수"""
    code = code.zfill(6)
    db = _load_db()
    if not db:
        return 0

    # 최근 days개 날짜 키만 조회 (역순 정렬)
    sorted_dates = sorted(db.keys(), reverse=True)[:days]
    count = 0
    for date_key in sorted_dates:
        if any(s["code"] == code for s in db[date_key]):
            count += 1
    return count


def get_surge_score(code: str, days: int = 20) -> float:
    """
    0~1 정규화 급상승 점수 (signal_engine 입력용)
    최근 N일 중 Top50 출현 비율 × 순위 가중치 평균
    - 1위 출현 = 1.0, 50위 출현 = 0.5 (선형 보간)
    """
    code = code.zfill(6)
    db = _load_db()
    if not db:
        return 0.0

    sorted_dates = sorted(db.keys(), reverse=True)[:days]
    scores = []
    for date_key in sorted_dates:
        for s in db[date_key]:
            if s["code"] == code:
                rank = s.get("rank", 50)
                # 1위=1.0, 50위=0.5, 50위 이하=0.5 하한
                rank_weight = max(0.5, 1.0 - (rank - 1) / (50 * 2))
                scores.append(rank_weight)
                break

    if not scores:
        return 0.0

    # 출현 빈도 × 평균 순위가중치
    freq_ratio = len(scores) / days
    avg_weight = sum(scores) / len(scores)
    return round(freq_ratio * avg_weight, 3)


def get_surge_history(code: str, days: int = 20) -> list[dict]:
    """특정 종목의 최근 출현 이력 반환 (날짜·순위·등락률)"""
    code = code.zfill(6)
    db = _load_db()
    history = []
    for date_key in sorted(db.keys(), reverse=True)[:days]:
        for s in db[date_key]:
            if s["code"] == code:
                history.append({
                    "date":        date_key,
                    "rank":        s.get("rank"),
                    "change_rate": s.get("change_rate"),
                    "price":       s.get("price"),
                })
                break
    return history


def print_summary(days: int = 10):
    """최근 N일 Top10 요약 출력 (디버그용)"""
    db = _load_db()
    if not db:
        print("DB 없음 — collect() 먼저 실행하세요.")
        return
    for date_key in sorted(db.keys(), reverse=True)[:days]:
        stocks = db[date_key]
        print(f"\n{'='*60}")
        print(f"{date_key}  급상승 Top10 ({stocks[0].get('collected_at', '')} 기준)")
        print(f"{'-'*60}")
        for s in stocks[:10]:
            print(
                f"  {s['rank']:>2}. {s['name']:<12} ({s['code']}) "
                f"{s['change_rate']:>+6.1f}%  "
                f"{s['price']:>8,}원  {s['market']}"
            )
    print(f"{'='*60}\n")
