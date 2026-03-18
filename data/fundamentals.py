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

# pykrx 컬럼명 매핑 — 버전에 따라 영문/한글 혼재
_PYKRX_COL_MAP = {
    "per":  ["PER", "주가수익비율", "per"],
    "pbr":  ["PBR", "주가순자산비율", "pbr"],
    "eps":  ["EPS", "주당순이익", "eps"],
    "bps":  ["BPS", "주당순자산가치", "bps"],
    "div":  ["DIV", "배당수익률", "div"],
    "dps":  ["DPS", "주당배당금", "dps"],
}


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


def _safe_float(series_or_val, *col_candidates) -> float | None:
    """Series 또는 dict에서 후보 컬럼명을 순서대로 시도해 float 반환"""
    if col_candidates:
        for col in col_candidates:
            try:
                val = series_or_val[col]
                v = float(val)
                return v if v != 0 else None
            except Exception:
                continue
        return None
    # 직접 값
    try:
        v = float(series_or_val)
        return v if v != 0 else None
    except Exception:
        return None


def _fetch_yfinance(code: str) -> dict | None:
    """yfinance .info로 PER/ROE/배당수익률/PBR 조회 (한국 종목: code.KS)"""
    if not yf:
        return None
    try:
        ticker_sym = f"{code.zfill(6)}.KS"
        t = yf.Ticker(ticker_sym)
        info = t.info or {}

        # 시세 확인 — 기본 데이터 없으면 종료
        if not info.get("regularMarketPrice") and not info.get("currentPrice"):
            return None

        per = info.get("trailingPE") or info.get("forwardPE")
        pbr = info.get("priceToBook")
        roe_raw = info.get("returnOnEquity")
        roe = round(roe_raw * 100, 2) if roe_raw else None
        div_raw = info.get("dividendYield")
        div = round(div_raw * 100, 2) if div_raw else None
        eps = info.get("trailingEps")

        # PBR 보조 계산 — priceToBook이 None이면 직접 계산
        if pbr is None:
            pbr = _calc_pbr_from_balance(t, info)

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
        log.debug(f"yfinance 재무 조회 실패 ({code}): {e}")
        return None


def _calc_pbr_from_balance(ticker_obj, info: dict) -> float | None:
    """
    대차대조표에서 PBR 직접 계산
    PBR = 현재가 / BPS(주당순자산)
        = 현재가 / (총자본 / 발행주식수)
    """
    try:
        price = (info.get("currentPrice")
                 or info.get("regularMarketPrice")
                 or info.get("previousClose"))
        if not price:
            return None

        shares = info.get("sharesOutstanding") or info.get("impliedSharesOutstanding")
        if not shares:
            return None

        # balance_sheet에서 총자본 시도
        bs = ticker_obj.balance_sheet
        if bs is not None and not bs.empty:
            equity_keys = [
                "Stockholders Equity",
                "Total Stockholder Equity",
                "Total Equity",
                "Common Stock Equity",
                "Total Stockholders Equity",
            ]
            for col in bs.index:
                for key in equity_keys:
                    if key.lower() in str(col).lower():
                        equity = float(bs.loc[col].iloc[0])
                        if equity > 0:
                            bps = equity / shares
                            pbr = price / bps
                            log.debug(f"PBR 대차대조표 계산: {price:.0f}/{bps:.0f}={pbr:.2f}")
                            return round(pbr, 2)

        # fast_info 시도
        try:
            fi = ticker_obj.fast_info
            bv = getattr(fi, "book_value", None)
            if bv and bv > 0:
                return round(price / bv, 2)
        except Exception:
            pass

        # bookValue 필드 재시도
        bv2 = info.get("bookValue")
        if bv2 and bv2 > 0:
            return round(price / bv2, 2)

    except Exception as e:
        log.debug(f"PBR 대차대조표 계산 실패: {e}")
    return None


def _get_pykrx_df(date_str: str):
    """
    pykrx get_market_fundamental_by_ticker 시도 — KOSPI/KOSDAQ 순서로
    반환: (DataFrame, 실제_컬럼_dict) or (None, None)
    """
    for market in ("KOSPI", "KOSDAQ"):
        try:
            df = krx.get_market_fundamental_by_ticker(date_str, market=market)
        except TypeError:
            # 일부 구버전은 market 파라미터 없음
            try:
                df = krx.get_market_fundamental_by_ticker(date_str)
            except Exception:
                return None, None
        except Exception:
            return None, None

        if df is None or df.empty:
            continue

        # 실제 컬럼 로그 (최초 1회)
        log.debug(f"pykrx({market}) 컬럼: {list(df.columns)} | 인덱스명: {df.index.name}")
        return df, market

    return None, None


def _extract_pykrx_row(row) -> dict:
    """Series row에서 컬럼명 후보를 시도해 재무 데이터 추출"""
    cols = list(row.index)
    log.debug(f"pykrx row 컬럼: {cols}")

    per = _safe_float(row, *_PYKRX_COL_MAP["per"])
    pbr = _safe_float(row, *_PYKRX_COL_MAP["pbr"])
    eps = _safe_float(row, *_PYKRX_COL_MAP["eps"])
    bps = _safe_float(row, *_PYKRX_COL_MAP["bps"])
    div = _safe_float(row, *_PYKRX_COL_MAP["div"])
    roe = round(eps / bps * 100, 2) if (eps and bps) else None

    return {"per": per, "pbr": pbr, "roe": roe, "eps": eps, "div_yield": div}


def _fetch_pykrx(code: str) -> dict | None:
    """pykrx로 PER/PBR/배당수익률 조회 (보조 소스) — 컬럼명 자동 탐지"""
    if not krx:
        return None

    padded = code.zfill(6)

    # 최근 5 영업일 순서로 시도 (주말/공휴일 대비)
    for days_back in range(0, 7):
        dt = (datetime.now() - timedelta(days=days_back))
        if dt.weekday() >= 5:   # 주말 건너뜀
            continue
        date_str = dt.strftime("%Y%m%d")

        df, market = _get_pykrx_df(date_str)
        if df is None:
            continue

        if padded not in df.index:
            log.debug(f"pykrx: {padded} not in index ({date_str}, {market})")
            # 첫 번째로 데이터가 있는 날짜라면 인덱스 샘플 로그
            log.debug(f"  index 샘플: {list(df.index[:5])}")
            continue

        row = df.loc[padded]
        data = _extract_pykrx_row(row)

        if not any(data.values()):
            log.debug(f"pykrx 데이터 모두 None: {padded} ({date_str})")
            continue

        data.update({
            "source": f"pykrx({market})",
            "as_of": date_str,
            "updated_at": datetime.now().isoformat(),
        })
        log.debug(f"pykrx 성공 {padded} [{date_str}/{market}]: {data}")
        return data

    # 개별 종목 by_date 폴백
    return _fetch_pykrx_by_date(code)


def _fetch_pykrx_by_date(code: str) -> dict | None:
    """pykrx get_market_fundamental_by_date 로 개별 종목 조회 (폴백)"""
    if not krx:
        return None
    padded = code.zfill(6)
    end = datetime.now().strftime("%Y%m%d")
    start = (datetime.now() - timedelta(days=14)).strftime("%Y%m%d")
    try:
        df = krx.get_market_fundamental_by_date(start, end, padded)
        if df is None or df.empty:
            return None
        log.debug(f"pykrx by_date 컬럼: {list(df.columns)}")
        row = df.iloc[-1]   # 가장 최근 행
        data = _extract_pykrx_row(row)
        if not any(data.values()):
            return None
        as_of = str(df.index[-1])[:10].replace("-", "")
        data.update({
            "source": "pykrx(by_date)",
            "as_of": as_of,
            "updated_at": datetime.now().isoformat(),
        })
        log.debug(f"pykrx by_date 성공 {padded}: {data}")
        return data
    except Exception as e:
        log.debug(f"pykrx by_date 실패 ({code}): {e}")
    return None


def fetch_fundamentals(code: str) -> dict | None:
    """yfinance 우선 → pykrx 폴백으로 재무 데이터 조회"""
    result = _fetch_yfinance(code)
    if result:
        # PBR이 여전히 None이면 pykrx 보조 시도
        if result.get("pbr") is None:
            pykrx_data = _fetch_pykrx(code)
            if pykrx_data and pykrx_data.get("pbr"):
                result["pbr"] = pykrx_data["pbr"]
                result["source"] = "yfinance+pykrx"
        # PER도 None이면 pykrx에서 보충
        if result.get("per") is None:
            pykrx_data = _fetch_pykrx(code) if result.get("pbr") is not None else None
            if pykrx_data and pykrx_data.get("per"):
                result["per"] = pykrx_data["per"]
        return result

    # yfinance 실패 시 pykrx로 폴백
    return _fetch_pykrx(code)


def get_fundamentals(code: str, force_refresh: bool = False) -> dict | None:
    """캐시 확인 → 7일 경과 시 자동 갱신"""
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
    """전체 유니버스 재무 데이터 일괄 갱신 (매주 월요일 자동 호출)"""
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
    return d["per"] if d else None

def get_pbr(code: str) -> float | None:
    d = get_fundamentals(code)
    return d["pbr"] if d else None

def get_roe(code: str) -> float | None:
    d = get_fundamentals(code)
    return d["roe"] if d else None

def get_div_yield(code: str) -> float | None:
    d = get_fundamentals(code)
    return d["div_yield"] if d else None


def print_summary():
    """캐시된 재무 데이터 요약 출력"""
    cache = _load_cache()
    if not cache:
        print("캐시 없음 — refresh_all() 먼저 실행하세요.")
        return
    print(f"\n{'='*75}")
    print(f"{'종목코드':<10} {'PER':>7} {'PBR':>7} {'ROE%':>7} {'배당%':>7} {'기준일':<12} 출처")
    print(f"{'-'*75}")
    for code, d in sorted(cache.items()):
        per = f"{d['per']:.1f}" if d.get('per') else "-"
        pbr = f"{d['pbr']:.2f}" if d.get('pbr') else "-"
        roe = f"{d['roe']:.1f}" if d.get('roe') else "-"
        div = f"{d['div_yield']:.1f}" if d.get('div_yield') else "-"
        src = d.get('source', '')[:14]
        print(f"{code:<10} {per:>7} {pbr:>7} {roe:>7} {div:>7} {d.get('as_of',''):<12} {src}")
    print(f"{'='*75}")
    sample = next(iter(cache.values()))
    print(f"마지막 갱신: {sample.get('updated_at','?')[:10]}\n")


def diagnose():
    """pykrx/yfinance 진단 — EC2에서 직접 실행용"""
    print("\n=== pykrx 진단 ===")
    if krx:
        from datetime import datetime, timedelta
        for days_back in range(0, 7):
            dt = datetime.now() - timedelta(days=days_back)
            if dt.weekday() >= 5:
                continue
            date_str = dt.strftime("%Y%m%d")
            try:
                df = krx.get_market_fundamental_by_ticker(date_str)
                if df is not None and not df.empty:
                    print(f"기준일: {date_str}")
                    print(f"컬럼: {list(df.columns)}")
                    print(f"인덱스명: {df.index.name}")
                    print(f"인덱스 샘플: {list(df.index[:5])}")
                    # 삼성전자 조회
                    if "005930" in df.index:
                        print(f"삼성전자(005930):\n{df.loc['005930']}")
                    break
            except Exception as e:
                print(f"{date_str} 오류: {e}")
    else:
        print("pykrx 미설치")

    print("\n=== yfinance 진단 (SK하이닉스 000660) ===")
    if yf:
        t = yf.Ticker("000660.KS")
        info = t.info or {}
        keys = ["regularMarketPrice", "currentPrice", "trailingPE", "forwardPE",
                "priceToBook", "bookValue", "returnOnEquity", "dividendYield",
                "trailingEps", "sharesOutstanding"]
        for k in keys:
            print(f"  {k}: {info.get(k)}")
        print(f"\n  balance_sheet columns: {list(t.balance_sheet.index) if not t.balance_sheet.empty else 'empty'}")
    else:
        print("yfinance 미설치")
