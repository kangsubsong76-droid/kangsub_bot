"""
KangSub Bot 대시보드 서버
Flask 기반 API + 정적 파일 서빙
포트 8080, EC2에서 24시간 운영
"""
import sys
import json
from pathlib import Path
from datetime import datetime

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from flask import Flask, jsonify, send_from_directory
from config.universe import SECTORS, DIVIDEND_TOP12

# 키움 REST API (잔고 실시간 조회)
try:
    from core.kiwoom_rest import KiwoomRestAPI
    _kiwoom = KiwoomRestAPI()
except Exception:
    _kiwoom = None

app = Flask(__name__, static_folder=str(Path(__file__).parent / "static"))

DATA_STORE = BASE / "data" / "store"
DATA_DIR   = BASE / "data"


def _read(path, default=None):
    try:
        if Path(path).exists():
            return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        pass
    return default if default is not None else {}


# ── 정적 파일 ──────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")

@app.route("/strategy")
def strategy():
    return send_from_directory(app.static_folder, "strategy.html")


# ── API 엔드포인트 ───────────────────────────────────────

@app.route("/api/portfolio")
def api_portfolio():
    # 1) 수동 동기화 파일 (portfolio_manual.json) — 최우선: 실제 보유 내역 기준
    manual = _read(DATA_STORE / "portfolio_manual.json", None)
    if manual and manual.get("cash", 0) > 0:
        return jsonify(manual)

    # 2) Kiwoom ka01002 — 계좌평가잔고내역 (수동매수 포함 전체 보유종목)
    if _kiwoom:
        try:
            holdings = _kiwoom.get_portfolio_holdings()
            if holdings and holdings.get("total_value", 0) > 0:
                return jsonify(holdings)
        except Exception:
            pass

    # 3) Kiwoom ka01690 — 봇 거래 내역 기반 잔고 (수동매수 미포함)
    if _kiwoom:
        try:
            balance = _kiwoom.get_balance()
            if balance and not balance.get("error") and balance.get("total_value", 0) > 0:
                return jsonify(balance)
        except Exception:
            pass

    # 4) 로컬 캐시 fallback
    data = _read(DATA_STORE / "portfolio.json", {
        "total_capital": 20_000_000,
        "total_value":   0,
        "cash":          0,
        "total_pnl":     0.0,
        "total_pnl_pct": 0.0,
        "num_holdings":  0,
        "holdings":      [],
    })
    return jsonify(data)


@app.route("/api/signals")
def api_signals():
    return jsonify(_read(DATA_STORE / "signals.json", []))


@app.route("/api/trades")
def api_trades():
    trades = _read(DATA_STORE / "trades.json", [])
    today = datetime.now().strftime("%Y-%m-%d")
    today_trades = [t for t in trades if str(t.get("timestamp","")).startswith(today)]
    return jsonify({
        "today": today_trades,
        "recent": trades[-30:] if trades else [],
        "realized_pnl": sum(t.get("pnl", 0) for t in trades if "pnl" in t),
    })


@app.route("/api/fundamentals")
def api_fundamentals():
    return jsonify(_read(DATA_DIR / "fundamentals.json", {}))


@app.route("/api/universe")
def api_universe():
    funds = _read(DATA_DIR / "fundamentals.json", {})
    result = {"sectors": {}, "dividend": {}}

    for sk, sv in SECTORS.items():
        result["sectors"][sk] = {
            "conviction": sv["conviction"],
            "weight":     sv["weight"],
            "stocks":     {},
        }
        for code, info in sv["stocks"].items():
            f = funds.get(code, {})
            result["sectors"][sk]["stocks"][code] = {
                **info,
                "per_live":     f.get("per"),
                "pbr_live":     f.get("pbr"),
                "roe_live":     f.get("roe"),
                "div_yield":    f.get("div_yield"),
                "funds_date":   f.get("as_of"),
            }

    seen = set()
    for gv in DIVIDEND_TOP12.values():
        for code, info in gv.items():
            if code not in seen:
                f = funds.get(code, {})
                result["dividend"][code] = {
                    **info,
                    "div_yield_live": f.get("div_yield"),
                    "pbr_live":       f.get("pbr"),
                    "per_live":       f.get("per"),
                }
                seen.add(code)

    return jsonify(result)


@app.route("/api/market")
def api_market():
    try:
        import yfinance as yf
        tickers = {
            "kospi":  "^KS11",
            "kosdaq": "^KQ11",
            "usdkrw": "USDKRW=X",
            "sp500":  "^GSPC",
        }
        out = {}
        for key, sym in tickers.items():
            try:
                fi = yf.Ticker(sym).fast_info
                prev = fi.previous_close or fi.last_price
                chg  = (fi.last_price - prev) / prev * 100 if prev else 0
                out[key] = {"price": round(fi.last_price, 2), "change_pct": round(chg, 2)}
            except Exception:
                out[key] = None
        out["updated"] = datetime.now().strftime("%H:%M:%S")
        return jsonify(out)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/status")
def api_status():
    port_data = _read(DATA_STORE / "portfolio.json", {})
    funds     = _read(DATA_DIR / "fundamentals.json", {})
    sigs      = _read(DATA_STORE / "signals.json", [])

    # 실전/페이퍼 여부: bot_status.json → 기본값 False (실전)
    bot_status = _read(DATA_STORE / "bot_status.json", {})
    paper = bot_status.get("paper_trading", False)

    return jsonify({
        "bot_running":    True,
        "paper_trading":  paper,
        "last_portfolio": port_data.get("updated_at", "-"),
        "last_signal":    len(sigs),
        "funds_stocks":   len(funds),
        "funds_date":     next(iter(funds.values()), {}).get("as_of", "-") if funds else "-",
        "server_time":    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })


@app.route("/api/nxt")
def api_nxt():
    """NXT 급상승 예측 — 후보종목 + 패턴DB 요약"""
    candidates = _read(DATA_STORE / "nxt_candidates.json", {})
    prediction = _read(DATA_STORE / "prediction_result.json", {})
    pattern    = _read(DATA_STORE / "pattern_db.json", {})

    daily = pattern.get("daily_results", [])
    recent_7 = daily[-7:] if daily else []

    return jsonify({
        "candidates": candidates,
        "analysis_text": prediction.get("analysis", "")[:800] if prediction else "",
        "analysis_time": prediction.get("time", "-"),
        "analysis_date": prediction.get("date", "-"),
        "pattern": {
            "total_days":      pattern.get("total_days", 0),
            "overall_hit_rate": pattern.get("overall_hit_rate", 0.0),
            "recent_7":        recent_7,
        },
    })


@app.route("/api/scheduler")
def api_scheduler():
    """스케줄러 실행 현황 — scheduler_status.json 기반 동적 응답"""
    status = _read(DATA_STORE / "scheduler_status.json", {})

    # 함수명 → 표시명 + 예정 시각 매핑 (jobs.py 기준)
    JOB_META = [
        ("morning_health_check",    "시스템 점검",        "06:00"),
        ("collect_news",            "뉴스 크롤링",        "07:00"),
        ("collect_afterhours",      "NXT 시간외 수집",    "07:30"),
        ("execute_nxt_buy",         "NXT 매수",           "08:00"),
        ("analyze_news_signals",    "뉴스 시그널 분석",   "08:00"),
        ("morning_briefing",        "모닝 브리핑",        "08:30"),
        ("sync_manual_portfolio_prices", "현재가 동기화", "09:05"),
        ("reconcile_portfolio",     "포트폴리오 검증",    "09:10"),
        ("execute_buy_signals",     "PAM 매수",           "09:30"),
        ("monitor_stop_loss",       "리스크 점검",        "5분간격"),
        ("midday_report",           "중간 리포트",        "12:00"),
        ("pre_close_check",         "마감 전 확인",       "14:50"),
        ("save_portfolio_snapshot", "포트폴리오 스냅샷",  "15:40"),
        ("reconcile_portfolio",     "마감 검증",          "15:45"),
        ("check_dart_disclosures",  "DART 공시 체크",     "16:00"),
        ("update_nxt_result",       "NXT 패턴DB 업데이트","16:10"),
        ("daily_report",            "일일 리포트",        "17:00"),
        ("update_technical_signals","기술적 분석 업데이트","18:00"),
        ("check_global_market",     "글로벌 시장 체크",   "22:00"),
    ]

    now_str = datetime.now().strftime("%H:%M")
    result  = []
    seen    = set()
    for fn_name, display_name, scheduled in JOB_META:
        # reconcile_portfolio 두 번 등록 → 두 번째는 별도 표시
        key = fn_name if fn_name not in seen else fn_name + "_close"
        seen.add(fn_name)

        s     = status.get(fn_name, {})
        state = s.get("status", "pending")
        # 오늘 실행 여부 확인 (last_run 날짜)
        last  = s.get("last_run", "")
        today = datetime.now().strftime("%Y-%m-%d")
        ran_today = last.startswith(today) if last else False
        if not ran_today:
            state = "pending"

        result.append({
            "name":      display_name,
            "scheduled": scheduled,
            "status":    state,           # completed | error | running | pending
            "last_run":  s.get("time", "-") if ran_today else "-",
            "error":     s.get("error") if state == "error" else None,
        })

    return jsonify(result)


@app.route("/api/afterhours")
def api_afterhours():
    """시간외 단일가 수집 결과"""
    data = _read(DATA_STORE / "afterhours_result.json", {})
    return jsonify(data)


@app.route("/api/trading_plan")
def api_trading_plan():
    """오늘의 매매 계획 — PAM(정규장) + NXT(장전거래) 통합"""
    manual   = _read(DATA_STORE / "portfolio_manual.json", {})
    signals  = _read(DATA_STORE / "signals.json", [])
    nxt_data = _read(DATA_STORE / "nxt_candidates.json", {})

    cash          = manual.get("cash", 0)
    total_capital = manual.get("total_capital", 10_000_000)
    n_holdings    = manual.get("num_holdings", 0)

    # ── PAM ──
    buy_sigs = sorted(
        [s for s in signals if s.get("action") == "BUY"],
        key=lambda s: s.get("weighted_score", 0), reverse=True
    )[:5]
    pam_budget    = round(min(cash, total_capital * 0.5))
    pam_per_stock = round(pam_budget / len(buy_sigs)) if buy_sigs else 0

    # ── NXT ──
    nxt_stocks = nxt_data.get("stocks", [])
    nxt_budget    = round(min(cash, total_capital * 0.40))
    nxt_per_stock = round(nxt_budget / len(nxt_stocks)) if nxt_stocks else 0

    # 갭 비율 적용 실효 예산 계산
    nxt_effective = round(sum(
        nxt_per_stock * float(s.get("budget_ratio") or 1.0)
        for s in nxt_stocks
    ))

    # 갭존 분류 요약 (스킵/주의/최적/약신호 종목 수)
    gap_summary = {"skip": 0, "caution": 0, "optimal": 0, "weak": 0}
    for s in nxt_stocks:
        g = float(s.get("gap_rate") or s.get("change_rate") or 0)
        if g >= 15:      gap_summary["skip"] += 1
        elif g >= 8:     gap_summary["caution"] += 1
        elif g >= 3:     gap_summary["optimal"] += 1
        else:            gap_summary["weak"] += 1

    return jsonify({
        "pam": {
            "signals":          signals[:10],   # BUY + HOLD 모두 포함
            "budget":           pam_budget,
            "per_stock":        pam_per_stock,
            "cash":             round(cash),
            "current_holdings": n_holdings,
        },
        "nxt": {
            "stocks":           nxt_stocks,
            "stop":             nxt_data.get("stop", False),
            "market_status":    nxt_data.get("market_status", "진행"),
            "nasdaq_change":    nxt_data.get("nasdaq_change"),
            "vix":              nxt_data.get("vix"),
            "analysis_date":    nxt_data.get("date", "-"),
            "analysis_time":    nxt_data.get("time", "-"),
            "budget":           nxt_budget,
            "per_stock":        nxt_per_stock,
            "effective_budget": nxt_effective,
            "gap_summary":      gap_summary,
        },
        "cash":          round(cash),
        "total_capital": total_capital,
        "updated":       datetime.now().strftime("%H:%M:%S"),
    })


@app.route("/api/bot_log")
def api_bot_log():
    """봇 실시간 활동 로그 — bot_activity.json + 스케줄러 + 체결 내역 합성"""
    today = datetime.now().strftime("%Y-%m-%d")
    entries = []

    # 1) 명시적 활동 로그 (utils/activity_log.py 기록)
    for e in _read(DATA_STORE / "bot_activity.json", []):
        if e.get("date", today) == today:
            e["_sort"] = e.get("time", "")
            entries.append(e)

    # 2) 스케줄러 완료 항목
    JOB_NAMES = {
        "morning_health_check":      ("✅", "시스템 점검 완료"),
        "collect_news":              ("📰", "뉴스 크롤링 완료"),
        "collect_afterhours":        ("🕐", "시간외 단일가 수집 완료"),
        "execute_nxt_buy":           ("⚡", "NXT 장전매수 실행"),
        "analyze_news_signals":      ("🧠", "뉴스 시그널 분석 완료"),
        "morning_briefing":          ("☀️", "모닝 브리핑 발송"),
        "sync_manual_portfolio_prices": ("🔄", "현재가 동기화 완료"),
        "reconcile_portfolio":       ("🔍", "포트폴리오 검증 완료"),
        "execute_buy_signals":       ("💹", "PAM 매수 시그널 처리"),
        "monitor_stop_loss":         ("🛡", "리스크 점검 완료"),
        "midday_report":             ("🕛", "중간 리포트 발송"),
        "pre_close_check":           ("⚠️", "마감 전 확인 완료"),
        "save_portfolio_snapshot":   ("📷", "포트폴리오 스냅샷 저장"),
        "check_dart_disclosures":    ("📋", "DART 공시 체크 완료"),
        "update_nxt_result":         ("📊", "NXT 패턴DB 업데이트"),
        "daily_report":              ("📈", "일일 리포트 발송"),
        "update_technical_signals":  ("📡", "기술적 분석 업데이트"),
        "check_global_market":       ("🌍", "글로벌 시장 체크 완료"),
        "collect_surge_top50":       ("🚀", "급상승 Top50 수집 완료"),
    }
    status = _read(DATA_STORE / "scheduler_status.json", {})
    for fn_name, (icon, label) in JOB_NAMES.items():
        s = status.get(fn_name, {})
        last = s.get("last_run", "")
        if not last.startswith(today):
            continue
        time_str = s.get("time", last[11:19] if len(last) > 19 else "--:--:--")
        st = s.get("status", "completed")
        level = "ERROR" if st == "error" else "INFO"
        err_txt = f" — {s['error'][:40]}" if st == "error" and s.get("error") else ""
        entries.append({
            "time": time_str[:8] if len(time_str) >= 8 else time_str,
            "level": level,
            "msg": f"{icon} {label}{err_txt}",
            "_sort": time_str,
        })

    # 3) 오늘 체결 내역
    trades = _read(DATA_STORE / "trades.json", [])
    for t in trades:
        ts = str(t.get("timestamp", ""))
        if not ts.startswith(today):
            continue
        side = t.get("side", t.get("type", "?"))
        name = t.get("name", t.get("stock_name", t.get("code", "?")))
        qty  = t.get("qty", t.get("quantity", 0))
        price = t.get("price", 0)
        pnl   = t.get("pnl", t.get("pnl_amount"))
        time_str = ts[11:19] if len(ts) > 19 else ts[11:] if len(ts) > 11 else "--:--:--"
        pnl_txt = f" ({'+' if pnl >= 0 else ''}{pnl:,.0f}원)" if pnl is not None else ""
        entries.append({
            "time": time_str,
            "level": "TRADE",
            "msg": f"🔵 {side} — {name} {qty:,}주 @ {price:,.0f}원{pnl_txt}",
            "_sort": ts,
        })

    # 시간 순 정렬 + _sort 제거
    entries.sort(key=lambda x: x.get("_sort", ""))
    for e in entries:
        e.pop("_sort", None)

    return jsonify(entries[-80:])


def run_dashboard(host="0.0.0.0", port=8080):
    """main.py thread entry point (waitress preferred)"""
    try:
        from waitress import serve
        import logging
        logging.getLogger("waitress").setLevel(logging.WARNING)
        serve(app, host=host, port=port, threads=4)
    except ImportError:
        # fallback to Flask dev server
        app.run(host=host, port=port, debug=False, threaded=True)


if __name__ == "__main__":
    run_dashboard()
