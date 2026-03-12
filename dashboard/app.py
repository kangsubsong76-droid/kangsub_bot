"""Streamlit 실시간 대시보드 — EC2에서 24시간 운영"""
import json
import time
from datetime import datetime
from pathlib import Path
import streamlit as st
import pandas as pd

# ── 페이지 설정 ──
st.set_page_config(
    page_title="KangSub Bot 대시보드",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

DATA_DIR = Path(__file__).parent.parent / "data" / "store"

# ── 데이터 로드 ──
def load_portfolio():
    path = DATA_DIR / "portfolio.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}

def load_signals():
    path = DATA_DIR / "signals.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return []

def load_trades():
    path = DATA_DIR / "trades.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return []

# ── 사이드바 ──
st.sidebar.title("⚙️ KangSub Bot")
st.sidebar.markdown(f"**업데이트:** {datetime.now():%Y-%m-%d %H:%M:%S}")
auto_refresh = st.sidebar.checkbox("자동 새로고침 (30초)", value=True)
page = st.sidebar.radio("페이지", ["📊 포트폴리오", "🎯 시그널", "📋 매매 이력", "⚠️ 리스크"])

# ── 메인 헤더 ──
st.title("📈 KangSub Bot — 자동 주식매매 대시보드")
st.caption("이재명 정부 정책 연계 · 7섹터 + 고배당 포트폴리오")

# ── 공통 지표 ──
portfolio = load_portfolio()

if portfolio:
    col1, col2, col3, col4, col5 = st.columns(5)
    total_capital = portfolio.get("total_capital", 100_000_000)
    total_value = portfolio.get("total_value", total_capital)
    cash = portfolio.get("cash", total_capital)
    invested = total_value - cash
    pnl_pct = (total_value - total_capital) / total_capital

    col1.metric("총 평가금액", f"{total_value:,.0f}원", f"{pnl_pct:+.1%}")
    col2.metric("투자금액", f"{invested:,.0f}원")
    col3.metric("현금 잔고", f"{cash:,.0f}원")
    col4.metric("누적 수익률", f"{pnl_pct:+.1%}")
    col5.metric("보유 종목", f"{len(portfolio.get('holdings', {}))}개")
    st.divider()

# ── 포트폴리오 페이지 ──
if page == "📊 포트폴리오":
    st.subheader("📊 보유 종목 현황")
    holdings = portfolio.get("holdings", {})
    if holdings:
        rows = []
        for code, h in holdings.items():
            rows.append({
                "종목코드": code,
                "종목명": h.get("name"),
                "구분": "배당" if h.get("category") == "dividend" else "일반",
                "섹터": h.get("sector", "-"),
                "보유수량": h.get("quantity"),
                "평균단가": f'{h.get("avg_price", 0):,.0f}',
                "현재가": f'{h.get("current_price", 0):,.0f}',
                "수익률": f'{h.get("pnl_pct", 0):+.1%}',
                "분할단계": f'{h.get("split_stage", 0)}차',
            })
        df = pd.DataFrame(rows)

        def color_pnl(val):
            if isinstance(val, str) and "%" in val:
                v = float(val.replace("%", "").replace("+", ""))
                color = "color: #e74c3c" if v < 0 else "color: #27ae60" if v > 0 else ""
                return color
            return ""

        st.dataframe(df.style.applymap(color_pnl, subset=["수익률"]), use_container_width=True)

        # 섹터 배분 차트
        st.subheader("섹터 배분")
        if rows:
            sector_data = pd.DataFrame(rows).groupby("섹터")["보유수량"].count().reset_index()
            st.bar_chart(sector_data.set_index("섹터"))
    else:
        st.info("보유 종목 없음")

# ── 시그널 페이지 ──
elif page == "🎯 시그널":
    st.subheader("🎯 오늘의 매매 시그널")
    signals = load_signals()
    if signals:
        for sig in sorted(signals, key=lambda x: x.get("weighted_score", 0), reverse=True):
            action = sig.get("action", "HOLD")
            emoji = {"BUY": "🟢", "SELL": "🔴", "WATCH": "🟡", "HOLD": "⚪"}.get(action, "⚪")
            with st.expander(f"{emoji} {sig.get('name')} ({sig.get('code')}) — {action} | 점수: {sig.get('weighted_score'):.0f}"):
                c1, c2, c3 = st.columns(3)
                c1.metric("기술점수", f"{sig.get('technical_score', 0):.0f}")
                c2.metric("시장점수", f"{sig.get('market_score', 0):.0f}")
                c3.metric("뉴스점수", f"{sig.get('news_score', 0):.0f}")
                st.markdown("**판단 근거:**")
                for r in sig.get("reasons", []):
                    st.markdown(f"- {r}")
    else:
        st.info("오늘의 시그널이 없습니다")

# ── 매매 이력 페이지 ──
elif page == "📋 매매 이력":
    st.subheader("📋 매매 이력")
    trades = load_trades()
    if trades:
        df = pd.DataFrame(trades)
        df = df.sort_values("timestamp", ascending=False)
        st.dataframe(df, use_container_width=True)

        realized = sum(t.get("pnl", 0) for t in trades if t.get("side") == "SELL")
        st.metric("총 실현 손익", f"{realized:+,.0f}원")
    else:
        st.info("매매 이력 없음")

# ── 리스크 페이지 ──
elif page == "⚠️ 리스크":
    st.subheader("⚠️ 리스크 모니터링")
    holdings = portfolio.get("holdings", {})
    if holdings:
        risk_rows = []
        for code, h in holdings.items():
            pnl = h.get("pnl_pct", 0)
            high = h.get("high_since_buy", h.get("avg_price", 0))
            current = h.get("current_price", 0)
            dd = (current - high) / high if high > 0 else 0

            # 추적손절 한도
            if pnl <= 0.05:
                stop = -0.10
            elif pnl <= 0.20:
                stop = -0.15
            elif pnl <= 0.50:
                stop = -0.20
            else:
                stop = -0.30
            distance = dd - stop

            risk_rows.append({
                "종목명": h.get("name"),
                "현재수익률": f"{pnl:+.1%}",
                "고점대비하락": f"{dd:.1%}",
                "손절한도": f"{stop:.0%}",
                "손절여유": f"{distance:+.1%}",
                "상태": "🚨위험" if distance < 0.02 else "⚠️주의" if distance < 0.05 else "✅안전",
            })
        st.dataframe(pd.DataFrame(risk_rows), use_container_width=True)

        pnl_pct = (portfolio.get("total_value", 0) - portfolio.get("total_capital", 1)) / portfolio.get("total_capital", 1)
        portfolio_distance = pnl_pct - (-0.20)
        if portfolio_distance < 0.05:
            st.error(f"⚠️ 포트폴리오 전체 손실한도 임박! 현재 {pnl_pct:.1%} (한도 -20%)")
        else:
            st.success(f"포트폴리오 안전 | 현재 {pnl_pct:+.1%} (한도까지 {portfolio_distance:.1%} 여유)")
    else:
        st.info("보유 종목 없음")

# ── 자동 새로고침 ──
if auto_refresh:
    time.sleep(30)
    st.rerun()
