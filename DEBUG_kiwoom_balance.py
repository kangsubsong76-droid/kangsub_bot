"""
DEBUG_kiwoom_balance.py
ka01690 실제 응답 필드명 확인용
py C:/kangsub_bot/DEBUG_kiwoom_balance.py
"""
import sys, json
from pathlib import Path
from datetime import date, datetime

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from core.kiwoom_rest import KiwoomRestAPI

kiwoom = KiwoomRestAPI()
today  = date.today().strftime("%Y%m%d")

print("=" * 60)
print("ka01690 RAW 응답 덤프")
print("=" * 60)

data = kiwoom._post("/api/dostk/acnt", {"qry_dt": today}, "ka01690")

if not data:
    print("응답 없음")
    sys.exit()

print(f"return_code: {data.get('return_code')}")
print(f"최상위 키: {list(data.keys())}")
print()

# 리스트 타입 키 찾기 (보유종목 배열)
for k, v in data.items():
    if isinstance(v, list):
        print(f"[LIST] '{k}' — {len(v)}건")
        if v:
            print(f"  첫 번째 항목 키: {list(v[0].keys())}")
            print(f"  첫 번째 항목 값:")
            for fk, fv in v[0].items():
                print(f"    {fk}: {fv}")
        print()
    elif isinstance(v, (int, float, str)) and v not in (None, "", " ", 0):
        print(f"[SCALAR] '{k}': {v}")

print()
print("전체 raw JSON:")
print(json.dumps(data, ensure_ascii=False, indent=2)[:3000])
