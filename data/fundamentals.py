"""
종목 재무 데이터 모듈
우선순위: 키움 REST API(ka10001) → yfinance → pykrx

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

# ── 키움 인스턴스 (market_data와 공유) ────────────────────────
_kiwoom_instance = None

def set_kiwoom(instance):
    """MainEngine 초기화 시 키움 인스턴스 주입"""
    global _kiwoom_instance
    _kiwoom_instance = instance

def _get_kiwoom():
    global _kiwoom_instance
    if _kiwoom_instance is not None:
        return _kiwoom_instance
    try:
        from config.settings import KIWOOM_MOCK
        if KIWOOM_MOCK:
            return None
        from core.kiwoom_rest import KiwoomRestAPI
        _kiwoom_instance = KiwoomRestAPI()
        return _kiwoom_instance
    except Exception:
        return None


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
    for key in candidates:
        try:
            v = float(row[key])
            if v != 0:
                return v
        except Exception:
            continue
    return None


def _row_to_fund(row) -> dict:
    per = _safe_float(row, *_COL_MAP["per"])
    pbr = _safe_float(row, *_COL_MAP["pbr"])
    eps = _safe_float(row, *_COL_MAP["eps"])
    bps = _safe_float(row, *_COL_MAP["bps"])
    div = _safe_float(row, *_COL_MAP["div"])
    roe = round(eps / bps * 100, 2) if (eps and bps) else None
    return {"per": per, "pbr": pbr, "roe": roe, "eps": eps, "div_yield": div}


# ──────────────────────────────────────────
# 1순위: 키움 REST API (ka10001)
# ──────────────────────────────────────────
def _fetch_kiwoom(code: str) -> dict | None:
    """
    키움 ka10001로 PER / PBR / ROE / EPS 조회
    ka10001은 이미 get_stock_info()에서 per/roe/pbr/eps 반환
    """
    kiwoom = _get_kiwoom()
    if not kiwoom:
        return None
    try:
        info = kiwoom.get_stock_info(code)
        if not info:
            return None

        per = info.get("per") or None
        pbr = info.get("pbr") or None
        roe = info.get("roe") or None
        eps = info.get("eps") or None

        # 모두 0이면 의미 없음
        if not any([per, pbr, roe, eps]):
            log.debug(f"키움 ka10001 재무값 전부 0 ({code})")
            return None

        return {
            "per":       round(float(per), 2) if per else None,
            "pbr":       round(float(pbr), 2) if pbr else None,
            "roe":       round(float(roe), 2) if roe else None,
            "eps":       round(float(eps), 0) if eps else None,
            "div_yield": None,   # ka10001에 배당수익률 없음 → yfinance 보충
            "source":    "kiwoom_ka10001",
            "as_of":     datetime.now().strftime("%Y-%m-%d"),
            "updated_at": datetime.now().isoformat(),
        }
    except Exception as e:
        log.debug(f"키움 재무 조회 실패 ({code}): {e}")
        return None


# ──────────────────────────────────────────
# 2순위: yfinance (PBR balance_sheet 계산 + 배당수익률)
# ──────────────────────────────────────────
def _calc_pbr(t, info: dict) -> float | None:
    price = info.get("currentPrice") or info.get("regularMarketPrice") or info.get("previousClose")
    if not price:
        return None
    shares = info.get("sharesOutstanding") or info.get("impliedSharesOutstanding")
    if not shares:
        return None
    try:
        bs = t.balance_sheet
        if bs is not None and not bs.empty:
            equity_keys = [
                "Common Stock Equity", "Stockholders Equity",
                "Total Stockholder Equity", "Total Equity Gross Minority Interest",
                "Tangible Book Value",
            ]
            for item in bs.index:
                for key in equity_keys:
                    if key.lower() == str(item).lower():
                        equity = float(bs.loc[item].iloc[0])
                        if equity > 0:
                            return round(price / (equity / shares), 2)
    except Exception as e:
        log.debug(f"PBR balance_sheet 계산 실패: {e}")
    bv = info.get("bookValue")
    if bv and bv > 0:
        return round(price / bv, 2)
    return None


def _fetch_yfinance_ticker(ticker_sym: str) -> tuple:
    try:
        t = yf.Ticker(ticker_sym)
        info = t.info or {}
        if info.get("currentPrice") or info.get("regularMarketPrice"):
            return t, info
    except Exception as e:
        log.debug(f"yfinance ticker 조회 실패 ({ticker_sym}): {e}")
    return None, None


def _fetch_yfinance(code: str) -> dict | None:
    if not yf:
        return None
    try:
        padded = code.zfill(6)
        t, info = _fetch_yfinance_ticker(f"{padded}.KS")
        used_suffix = ".KS"
        if info is not None:
            has_fundamentals = info.get("trailingPE") or info.get("forwardPE") or info.get("returnOnEquity")
            if not has_fundamentals:
                t2, info2 = _fetch_yfinance_ticker(f"{padded}.KQ")
                if info2 is not None and (info2.get("trailingPE") or info2.get("forwardPE") or info2.get("returnOnEquity")):
                    t, info, used_suffix = t2, info2, ".KQ"
        else:
            t, info = _fetch_yfinance_ticker(f"{padded}.KQ")
            used_suffix = ".KQ"
        if info is None:
            return None
        per     = info.get("trailingPE") or info.get("forwardPE")
        pbr     = info.get("priceToBook") or _calc_pbr(t, info)
        roe_raw = info.get("returnOnEquity")
        roe     = round(roe_raw * 100, 2) if roe_raw else None
        div_raw = info.get("dividendYield")
        div     = round(div_raw, 2) if div_raw else None
        eps     = info.get("trailingEps")
        return {
            "per":       round(per, 2) if per else None,
            "pbr":       round(pbr, 2) if pbr else None,
            "roe":       roe,
            "eps":       round(eps, 0) if eps else None,
            "div_yield": div,
            "source":    f"yfinance{used_suffix}",
            "as_of":     datetime.now().strftime("%Y-%m-%d"),
            "updated_at": datetime.now().isoformat(),
        }
    except Exception as e:
        log.debug(f"yfinance 실패 ({code}): {e}")
        return None


# ──────────────────────────────────────────
# 3순위: pykrx
# ──────────────────────────────────────────
def _fetch_pykrx(code: str) -> dict | None:
    if not krx:
        return None
    padded = code.zfill(6)
    end   = datetime.now().strftime("%Y%m%d")
    start = (datetime.now() - timedelta(days=20)).strftime("%Y%m%d")
    try:
        df = krx.get_market_fundamental_by_date(start, end, padded)
        if df is None or df.empty:
            return None
        row  = df.iloc[-1]
        data = _row_to_fund(row)
        if not any(v for v in data.values() if v):
            return None
        data.update({
            "source":     "pykrx",
            "as_of":      str(df.index[-1])[:10].replace("-", ""),
            "updated_at": datetime.now().isoformat(),
        })
        return data
    except Exception as e:
        log.debug(f"pykrx 실패 ({code}): {e}")
        return None


# ──────────────────────────────────────────
# 공개 API
# ──────────────────────────────────────────
def fetch_fundamentals(code: str) -> dict | None:
    """
    키움 ka10001 우선 → yfinance 폴백 → pykrx 폴백
    배당수익률은 키움에 없으므로 yfinance에서 보충
    """
    # 1순위: 키움
    result = _fetch_kiwoom(code)
    if result:
        # 배당수익률은 키움 ka10001 미제공 → yfinance에서 보충
        if result.get("div_yield") is None and yf:
            try:
                padded = code.zfill(6)
                _, info = _fetch_yfinance_ticker(f"{padded}.KS")
                if info is None:
                    _, info = _fetch_yfinance_ticker(f"{padded}.KQ")
                if info:
                    div_raw = info.get("dividendYield")
                    if div_raw:
                        result["div_yield"] = round(div_raw, 2)
                        result["source"] = "kiwoom+yfinance_div"
            except Exception:
                pass
        log.debug(f"재무 조회 성공 ({code}): {result.get('source')} PER={result.get('per')} PBR={result.get('pbr')} ROE={result.get('roe')}")
        return result

    # 2순위: yfinance
    result = _fetch_yfinance(code)
    if result:
        if result.get("pbr") is None or result.get("per") is None:
            pk = _fetch_pykrx(code)
            if pk:
                if result.get("pbr") is None and pk.get("pbr"):
                    result["pbr"] = pk["pbr"]
                    result["source"] = "yfinance+pykrx"
                if result.get("per") is None and pk.get("per"):
                    result["per"] = pk["per"]
        return result

    # 3순위: pykrx
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
    results, failed = {}, []
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
        src = d.get("source", "")[:18]
        print(f"{code:<10} {per:>7} {pbr:>7} {roe:>7} {div:>7} {d.get('as_of',''):<12} {src}")
    print(f"{'='*75}\n")
