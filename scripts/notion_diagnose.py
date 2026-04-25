# -*- coding: utf-8 -*-
"""
Notion 연결 진단 스크립트
실행: python scripts/notion_diagnose.py
"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from notion_client import Client
from config.settings import (
    NOTION_TOKEN, NOTION_DB_TRADES, NOTION_DB_PORTFOLIO,
    NOTION_DB_SIGNALS, NOTION_DB_NEWS,
)
try:
    from config.settings import NOTION_DB_REVIEW
except Exception:
    NOTION_DB_REVIEW = ""

print("=" * 60)
print("Notion 진단 시작")
print("=" * 60)

if not NOTION_TOKEN:
    print("ERR: NOTION_TOKEN 이 비어 있습니다. .env 확인하세요.")
    sys.exit(1)

client = Client(auth=NOTION_TOKEN)

# 1) 인테그레이션 정체 확인
print("\n[1] 인테그레이션 토큰 확인...")
try:
    me = client.users.me()
    print(f"  OK: {me.get('name','?')} / type={me.get('type','?')}")
except Exception as e:
    print(f"  ERR: {e}")
    print("  → NOTION_TOKEN 이 잘못됐거나 만료됐습니다.")

# 2) 각 DB ID 점검
DB_MAP = {
    "NOTION_DB_TRADES":    NOTION_DB_TRADES,
    "NOTION_DB_PORTFOLIO": NOTION_DB_PORTFOLIO,
    "NOTION_DB_SIGNALS":   NOTION_DB_SIGNALS,
    "NOTION_DB_NEWS":      NOTION_DB_NEWS,
    "NOTION_DB_REVIEW":    NOTION_DB_REVIEW,
}

print("\n[2] DB 접근 확인...")
for name, db_id in DB_MAP.items():
    if not db_id:
        print(f"  SKIP {name}: ID 없음")
        continue
    try:
        db = client.databases.retrieve(database_id=db_id)
        obj_type = db.get("object", "?")
        if obj_type == "error":
            print(f"  ERR  {name}: status={db.get('status')} msg={db.get('message')}")
        elif obj_type == "database":
            props = list(db.get("properties", {}).keys())
            print(f"  OK   {name}: 속성={props}")
        else:
            print(f"  WARN {name}: object={obj_type} (DB가 아님?)")
            print(f"       raw keys={list(db.keys())}")
    except Exception as e:
        err_str = str(e)
        print(f"  ERR  {name}: {err_str}")
        if "Could not find" in err_str or "object_not_found" in err_str:
            print(f"       → DB ID가 잘못됐거나, 인테그레이션이 이 페이지에 연결 안 됨")
        elif "unauthorized" in err_str or "401" in err_str:
            print(f"       → 인테그레이션 권한 부족. Notion에서 페이지 공유 필요")

# 3) 인테그레이션이 볼 수 있는 DB 목록
print("\n[3] 인테그레이션이 접근 가능한 DB 목록 (최근 20개)...")
try:
    results = client.search(filter={"value": "database", "property": "object"}).get("results", [])
    if not results:
        print("  접근 가능한 DB 없음 — Notion 페이지에 인테그레이션을 연결하세요!")
        print("  방법: Notion 페이지 우상단 ··· → Connections → 인테그레이션 선택")
    else:
        for db in results[:20]:
            title_arr = db.get("title", [])
            title = title_arr[0]["plain_text"] if title_arr else "(제목없음)"
            print(f"  {db['id']} | {title}")
except Exception as e:
    print(f"  ERR: {e}")

print("\n" + "=" * 60)
print("진단 완료")
print("=" * 60)
