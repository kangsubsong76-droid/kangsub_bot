"""
종목 재무 데이터 모듈 — yfinance 주 / pykrx 보조
PER, PBR, ROE, 배당수익률을 주간 자동 갱신

갱신 주기: 7일
캐시 위치: data/fundamentals.json
"""
import json
from datetime import datetime, timedelta
from pathlib import Path
from utils.logger import setup_logger

log = setup_logger("fundamentals")

try:
    import yfinance as yf
except ImportError:
    yf = None

try:
    from pykrx import stock as krx
except ImportError:
    krx = None

_CACHE_PATH = Path(__file__).parent.parent / "data" / "fundamentals.json"
_STALE_DAYS = 7

# pykrx 컬럼명 후보 매핑 (버전별 영문/한글 혼재 대응)
_COL_MAP = {
    "per": ["PER", "주가수익비율", "per"],
    "pbr": ["PBR", "주가순자산비율", "pbr"],
    "eps": ["EPS", "주당순이익", "eps"],
    "bps": ["BPS", "주당순자산가치", "bps"],
    "div": ["DIV", "배당수익률", "div"],
}


# ──────────────────────────────────────────
# 캐시 유틸
# ──────────────────────────────────────────
def _load_cache() -> dict:
    if _CACHE_PATH.exists():
        try:
            return json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_cache(data: dict):
    _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CACHE_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _is_stale(updated_at: str) -> bool:
    try:
        return (datetime.now() - datetime.fromisoformat(updated_at)).days >= _STALE_DAYS
    except Exception:
        return True


# ──────────────────────────────────────────
# 헬퍼
# ──────────────────────────────────────────
def _safe_float(row, *candidates):
    """Series/dict에서 후보 키를 순서대로 시도해 0이 아닌 float 반환"""
    for key in candidates:
        try:
            v = float(row[key])
            if v != 0:
                return v
        except Exception:
            continue
    return None


def _row_to_fund(row) -> dict:
    """pykrx DataFrame row -> 재무 dict"""
    per = _safe_float(row, *_COL_MAP["per"])
    pbr = _safe_float(row, *_COL_MAP["pbr"])
    eps = _safe_float(row, *_COL_MAP["eps"])
    bps = _safe_float(row, *_COL_MAP["bps"])
    div = _safe_float(row, *_COL_MAP["div"])
    roe = round(eps / bps * 100, 2) if (eps and bps) else None
    return {"per": per, "pbr": pbr, "roe": roe, "eps": eps, "div_yield": div}


# ──────────────────────────────────────────
# pykrx — get_market_fundamental_by_date 사용
# (get_market_fundamental_by_ticker 는 내부 버그로 사용 안 함)
# ──────────────────────────────────────────
def _fetch_pykrx(code: str) -> dict | None:
    if not krx:
        return None
    padded = code.zfill(6)
    end = datetime.now().strftime("%Y%m%d")
    start = (datetime.now() - timedelta(days=20)).strftime("%Y%m%d")

    try:
        df = krx.get_market_fundamental_by_date(start, end, padded)
        if df is None or df.empty:
            log.debug(f"pykrx by_date: 데이터 없음 ({padded})")
            return None

        log.debug(f"pykrx by_date 컬럼: {list(df.columns)}")
        row = df.iloc[-1]
        data = _row_to_fund(row)

        if not any(v for v in data.values() if v):
            log.debug(f"pykrx by_date: 모든 값 None ({padded})")
            return None

        as_of = str(df.index[-1])[:10].replace("-", "")
        data.update({
            "source": "pykrx",
            "as_of": as_of,
            "updated_at": datetime.now().isoformat(),
        })
        log.debug(f"pykrx 성공 {padded}: PER={data['per']}, PBR={data['pbr']}")
        return data

    except Exception as e:
        log.debug(f"pykrx by_date 실패 ({code}): {e}")
        return None


# ──────────────────────────────────────────
# yfinance — PBR은 balance_sheet에서 직접 계산
# ──────────────────────────────────────────
def _calc_pbr(t, info: dict) -> float | None:
    """
    PBR = 현재가 / BPS
    BPS = Common Stock Equity / sharesOutstanding
    balance_sheet.index 에 'Common Stock Equity' 또는 'Stockholders Equity' 존재 확인됨
    """
    price = info.get("currentPrice") or info.get("regularMarketPrice") or info.get("previousClose")
    if not price:
        return None
    shares = info.get("sharesOutstanding") or info.get("impliedSharesOutstanding")
    if not shares:
        return None

    # balance_sheet에서 자본 항목 탐색 (index = 재무항목명, columns = 날짜)
    try:
        bs = t.balance_sheet
        if bs is not None and not bs.empty:
            equity_keys = [
                "Common Stock Equity",
                "Stockholders Equity",
                "Total Stockholder Equity",
                "Total Equity Gross Minority Interest",
                "Tangible Book Value",
            ]
            for item in bs.index:
                for key in equity_keys:
                    if key.lower() == str(item).lower():
                        equity = float(bs.loc[item].iloc[0])
                        if equity > 0:
                            bps = equity / shares
                            pbr = round(price / bps, 2)
                            log.debug(f"PBR 계산: {price:.0f} / ({equity:.0f}/{shares:.0f}) = {pbr}")
                            return pbr
    except Exception as e:
        log.debug(f"PBR balance_sheet 계산 실패: {e}")

    # bookValue 직접 시도
    bv = info.get("bookValue")
    if bv and bv > 0:
        return round(price / bv, 2)

    return None


def _fetch_yfinance(code: str) -> dict | None:
    if not yf:
        return None
    try:
        t = yf.Ticker(f"{code.zfill(6)}.KS")
        info = t.info or {}

        if not info.get("currentPrice") and not info.get("regularMarketPrice"):
            return None

        per = info.get("trailingPE") or info.get("forwardPE")
        pbr = info.get("priceToBook") or _calc_pbr(t, info)
        roe_raw = info.get("returnOnEquity")
        roe = round(roe_raw * 100, 2) if roe_raw else None
        div_raw = info.get("dividendYield")
        div = round(div_raw * 100, 2) if div_raw else None
        eps = info.get("trailingEps")

        return {
            "per": round(per, 2) if per else None,
            "pbr": round(pbr, 2) if pbr else None,
            "roe": roe,
            "eps": round(eps, 0) if eps else None,
            "div_yield": div,
            "source": "yfinance",
            "as_of": datetime.now().strftime("%Y-%m-%d"),
            "updated_at": datetime.now().isoformat(),
        }
    except Exception as e:
        log.debug(f"yfinance 실패 ({code}): {e}")
        return None


# ──────────────────────────────────────────
# 공개 API
# ──────────────────────────────────────────
def fetch_fundamentals(code: str) -> dict | None:
    """yfinance 우선 → pykrx 폴백"""
    result = _fetch_yfinance(code)
    if result:
        # PBR 또는 PER가 None이면 pykrx 보충
        if result.get("pbr") is None or result.get("per") is None:
            pk = _fetch_pykrx(code)
            if pk:
                if result.get("pbr") is None and pk.get("pbr"):
                    result["pbr"] = pk["pbr"]
                    result["source"] = "yfinance+pykrx"
                if result.get("per") is None and pk.get("per"):
                    result["per"] = pk["per"]
                    result["source"] = result.get("source", "yfinance+pykrx")
        return result

    return _fetch_pykrx(code)


def get_fundamentals(code: str, force_refresh: bool = False) -> dict | None:
    cache = _load_cache()
    entry = cache.get(code)

    if not force_refresh and entry and not _is_stale(entry.get("updated_at", "")):
        return entry

    fresh = fetch_fundamentals(code)
    if fresh:
        cache[code] = fresh
        _save_cache(cache)
        return fresh

    if entry:
        log.warning(f"{code} 갱신 실패 — 기존 캐시 사용 ({entry.get('as_of')})")
        return entry
    return None


def refresh_all(codes: list) -> dict:
    log.info(f"전체 재무 데이터 갱신 시작 ({len(codes)}종목)")
    results = {}
    failed = []

    for code in codes:
        data = fetch_fundamentals(code)
        if data:
            results[code] = data
            log.info(
                f"  {code}: PER={data.get('per')}, PBR={data.get('pbr')}, "
                f"ROE={data.get('roe')}%, 배당={data.get('div_yield')}% [{data.get('source')}]"
            )
        else:
            failed.append(code)

    if results:
        cache = _load_cache()
        cache.update(results)
        _save_cache(cache)

    log.info(f"갱신 완료: {len(results)}건 성공, {len(failed)}건 실패")
    if failed:
        log.warning(f"실패 종목: {failed}")
    return results


def is_cache_fresh() -> bool:
    cache = _load_cache()
    if not cache:
        return False
    sample = next(iter(cache.values()))
    return not _is_stale(sample.get("updated_at", ""))


def get_per(code: str) -> float | None:
    d = get_fundamentals(code)
    return d.get("per") if d else None

def get_pbr(code: str) -> float | None:
    d = get_fundamentals(code)
    return d.get("pbr") if d else None

def get_roe(code: str) -> float | None:
    d = get_fundamentals(code)
    return d.get("roe") if d else None

def get_div_yield(code: str) -> float | None:
    d = get_fundamentals(code)
    return d.get("div_yield") if d else None


def print_summary():
    cache = _load_cache()
    if not cache:
        print("캐시 없음 — refresh_all() 먼저 실행하세요.")
        return
    print(f"\n{'='*75}")
    print(f"{'종목코드':<10} {'PER':>7} {'PBR':>7} {'ROE%':>7} {'배당%':>7} {'기준일':<12} 출처")
    print(f"{'-'*75}")
    for code, d in sorted(cache.items()):
        per = f"{d['per']:.1f}" if d.get("per") else "-"
        pbr = f"{d['pbr']:.2f}" if d.get("pbr") else "-"
        roe = f"{d['roe']:.1f}" if d.get("roe") else "-"
        div = f"{d['div_yield']:.1f}" if d.get("div_yield") else "-"
        src = d.get("source", "")[:14]
        print(f"{code:<10} {per:>7} {pbr:>7} {roe:>7} {div:>7} {d.get('as_of',''):<12} {src}")
    print(f"{'='*75}")
    sample = next(iter(cache.values()))
    print(f"마지막 갱신: {sample.get('updated_at','?')[:10]}\n")


def diagnose():
    """pykrx/yfinance 진단 — EC2에서 직접 실행용"""
    print("\n=== pykrx 진단 (get_market_fundamental_by_date) ===")
    if krx:
        end = datetime.now().strftime("%Y%m%d")
        start = (datetime.now() - timedelta(days=14)).strftime("%Y%m%d")
        for ticker in ["005930", "000660"]:
            try:
                df = krx.get_market_fundamental_by_date(start, end, ticker)
                if df is not None and not df.empty:
                    print(f"[{ticker}] OK - 기준일: {df.index[-1]}")
                    print(f"  컬럼: {list(df.columns)}")
                    print(f"  최신값:\n{df.iloc[-1]}")
                else:
                    print(f"[{ticker}] 데이터 없음")
            except Exception as e:
                print(f"[{ticker}] 오류: {e}")
    else:
        print("pykrx 미설치")

    print("\n=== yfinance PBR 계산 진단 (SK하이닉스 000660) ===")
    if yf:
        t = yf.Ticker("000660.KS")
        info = t.info or {}
        price = info.get("currentPrice") or info.get("regularMarketPrice")
        shares = info.get("sharesOutstanding")
        print(f"  현재가: {price}")
        print(f"  발행주식수: {shares}")
        print(f"  priceToBook(직접): {info.get('priceToBook')}")
        pbr = _calc_pbr(t, info)
        print(f"  PBR(계산값): {pbr}")
        print(f"  ROE: {info.get('returnOnEquity')}")
        print(f"  배당수익률: {info.get('dividendYield')}")

    print("\n=== 전체 조회 테스트 (삼성전자 005930) ===")
    result = fetch_fundamentals("005930")
    if result:
        print(f"  PER: {result.get('per')}")
        print(f"  PBR: {result.get('pbr')}")
        print(f"  ROE: {result.get('roe')}%")
        print(f"  배당: {result.get('div_yield')}%")
        print(f"  출처: {result.get('source')}")
    else:
        print("  삼성전자 조회 실패")
