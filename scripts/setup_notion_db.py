"""
Notion 데이터베이스 자동 생성 스크립트
실행: python scripts/setup_notion_db.py

실행 전 .env에 NOTION_TOKEN 설정 필요
생성된 DB ID를 .env의 NOTION_DB_* 항목에 채워넣으세요
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from notion_client import Client
from config.settings import NOTION_TOKEN

client = Client(auth=NOTION_TOKEN)

# ── 부모 페이지 찾기 ──
print("Notion 페이지 목록 검색...")
results = client.search(query="KangSub Bot", filter={"value": "page", "property": "object"}).get("results", [])
if not results:
    print("'KangSub Bot' 페이지가 없습니다. Notion에서 'KangSub Bot' 페이지를 먼저 만들어주세요.")
    sys.exit(1)

parent_id = results[0]["id"]
print(f"부모 페이지 발견: {parent_id}")


def create_db(title: str, properties: dict) -> str:
    """DB 생성 후 ID 반환"""
    db = client.databases.create(
        parent={"page_id": parent_id},
        title=[{"type": "text", "text": {"content": title}}],
        properties=properties,
    )
    db_id = db["id"]
    print(f"  ✅ [{title}] 생성: {db_id}")
    return db_id


# ── 1. 매매일지 DB ──
trades_id = create_db("📋 매매일지", {
    "종목명":   {"title": {}},
    "종목코드": {"rich_text": {}},
    "매매구분": {"select": {"options": [
        {"name": "매수", "color": "green"},
        {"name": "매도", "color": "red"},
        {"name": "손절매도", "color": "orange"},
    ]}},
    "수량":     {"number": {"format": "number"}},
    "주문가":   {"number": {"format": "won"}},
    "체결가":   {"number": {"format": "won"}},
    "체결금액": {"number": {"format": "won"}},
    "수익률":   {"number": {"format": "percent"}},
    "트리거":   {"select": {"options": [
        {"name": "시그널", "color": "blue"},
        {"name": "손절", "color": "red"},
        {"name": "리밸런싱", "color": "yellow"},
        {"name": "수동", "color": "gray"},
    ]}},
    "일시":     {"date": {}},
    "비고":     {"rich_text": {}},
})

# ── 2. 포트폴리오 스냅샷 DB ──
portfolio_id = create_db("📊 포트폴리오 스냅샷", {
    "일자":       {"title": {}},
    "총평가금액": {"number": {"format": "won"}},
    "총수익률":   {"number": {"format": "percent"}},
    "일간수익률": {"number": {"format": "percent"}},
    "현금잔고":   {"number": {"format": "won"}},
    "일반비중":   {"number": {"format": "percent"}},
    "배당비중":   {"number": {"format": "percent"}},
})

# ── 3. 시그널 로그 DB ──
signals_id = create_db("🎯 시그널 로그", {
    "종목명":     {"title": {}},
    "시그널유형": {"select": {"options": [
        {"name": "BUY", "color": "green"},
        {"name": "SELL", "color": "red"},
        {"name": "WATCH", "color": "yellow"},
        {"name": "HOLD", "color": "gray"},
    ]}},
    "기술점수":   {"number": {"format": "number"}},
    "시장점수":   {"number": {"format": "number"}},
    "뉴스점수":   {"number": {"format": "number"}},
    "종합점수":   {"number": {"format": "number"}},
    "실행여부":   {"checkbox": {}},
    "일시":       {"date": {}},
})

# ── 4. 뉴스/정책 분석 DB ──
news_id = create_db("📰 뉴스/정책 분석", {
    "제목":     {"title": {}},
    "출처":     {"select": {"options": [
        {"name": "한겨레", "color": "green"},
        {"name": "경향신문", "color": "blue"},
        {"name": "한국일보", "color": "orange"},
        {"name": "MBC", "color": "purple"},
        {"name": "JTBC", "color": "red"},
        {"name": "김어준뉴스공장", "color": "yellow"},
        {"name": "네이버금융", "color": "gray"},
    ]}},
    "관련섹터": {"multi_select": {"options": [
        {"name": "AI_반도체"}, {"name": "K_방산"},
        {"name": "재생에너지"}, {"name": "피지컬AI_로봇"},
        {"name": "외교_한중"}, {"name": "밸류업_금융"},
        {"name": "중소_벤처"}, {"name": "이재명"},
    ]}},
    "감성점수": {"number": {"format": "number"}},
    "요약":     {"rich_text": {}},
    "URL":      {"url": {}},
    "일시":     {"date": {}},
})

# ── .env 업데이트 안내 ──
print("\n" + "=" * 50)
print("✅ Notion DB 생성 완료!")
print("config/.env 파일에 아래 값을 추가하세요:")
print("=" * 50)
print(f"NOTION_DB_TRADES={trades_id}")
print(f"NOTION_DB_PORTFOLIO={portfolio_id}")
print(f"NOTION_DB_SIGNALS={signals_id}")
print(f"NOTION_DB_NEWS={news_id}")
