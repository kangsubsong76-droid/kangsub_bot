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
    # 1) 키움 REST API 실시간 잔고 조회 시도
    if _kiwoom:
        try:
            balance = _kiwoom.get_balance()
            if balance and not balance.get("error"):
                return jsonify(balance)
        except Exception:
            pass
    # 2) 로컬 캐시 파일 fallback
    data = _read(DATA_STORE / "portfolio.json", {
        "total_capital": 100_000_000,
        "total_value":   100_000_000,
        "cash":          100_000_000,
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
    return jsonify({
        "bot_running":    True,
        "paper_trading":  True,
        "last_portfolio": port_data.get("updated_at", "-"),
        "last_signal":    len(sigs),
        "funds_stocks":   len(funds),
        "funds_date":     next(iter(funds.values()), {}).get("as_of", "-") if funds else "-",
        "server_time":    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })


if __name__ == "__main__":
    print("=" * 50)
    print("KangSub Bot 대시보드 서버 시작")
    print("http://0.0.0.0:8080")
    print("=" * 50)
    app.run(host="0.0.0.0", port=8080, debug=False, threaded=True)
