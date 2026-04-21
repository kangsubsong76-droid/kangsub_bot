"""종목 유니버스 — 10섹터 + 배당 Top12 정의
이재명 정부 정책 수혜 섹터 기반 (2025년 기준)

섹터 구성 원칙:
  주도주 2개 — 정책 모멘텀 + 실적 주도
  가치주 2개 — PBR ≤ 1.5, ROE ≥ 10% 우선 선별

섹터 가중치 합계: 1.00
conviction 5=최강 / 4=강 / 3=중립
"""

SECTORS = {

    # ── Conviction 5 (합계 0.49) ────────────────────────────────────────────

    "AI_반도체": {
        "conviction": 5,
        "weight": 0.18,
        "stocks": {
            "000660": {"name": "SK하이닉스",  "type": "주도주", "per": 12, "pbr": 1.5, "roe": 24, "upside": (30, 45)},
            "042700": {"name": "한미반도체",  "type": "주도주", "per": 22, "pbr": 3.5, "roe": 32, "upside": (25, 35)},
            # 가치주: PBR 0.7·1.2, ROE 12·13 — 소재·전공정 업스트림
            "000990": {"name": "DB하이텍",    "type": "가치주", "per": 11, "pbr": 0.7, "roe": 12, "upside": (45, 60)},
            "357780": {"name": "솔브레인",    "type": "가치주", "per": 13, "pbr": 1.2, "roe": 13, "upside": (40, 55)},
        }
    },

    "K_방산": {
        "conviction": 5,
        "weight": 0.17,
        "stocks": {
            "012450": {"name": "한화에어로스페이스", "type": "주도주", "per": 28, "pbr": 3.2, "roe": 18, "upside": (20, 30)},
            "064350": {"name": "현대로템",           "type": "주도주", "per": 18, "pbr": 2.0, "roe": 16, "upside": (30, 40)},
            # 가치주: PBR 0.4·0.7, ROE 7·11 — 탄약 독점·차량 부품
            "103140": {"name": "풍산",               "type": "가치주", "per":  9, "pbr": 0.7, "roe": 11, "upside": (50, 70)},
            "011210": {"name": "현대위아",           "type": "가치주", "per": 14, "pbr": 0.4, "roe":  7, "upside": (40, 60)},
        }
    },

    "원전_SMR": {
        "conviction": 5,
        "weight": 0.14,
        "stocks": {
            "052690": {"name": "한전기술",       "type": "주도주", "per": 20, "pbr": 4.0, "roe": 25, "upside": (25, 40)},
            "034020": {"name": "두산에너빌리티", "type": "주도주", "per": 22, "pbr": 1.5, "roe": 10, "upside": (30, 50)},
            # 가치주: PBR 1.0·2.0, ROE 12·15 — 정비 독점·열교환기
            "083650": {"name": "비에이치아이",   "type": "가치주", "per": 12, "pbr": 1.0, "roe": 12, "upside": (45, 65)},
            "051600": {"name": "한전KPS",        "type": "가치주", "per": 14, "pbr": 2.0, "roe": 15, "upside": (30, 45)},
        }
    },

    # ── Conviction 4 (합계 0.29) ────────────────────────────────────────────

    "전력_인프라": {
        "conviction": 4,
        "weight": 0.12,
        "stocks": {
            "267260": {"name": "HD현대일렉트릭", "type": "주도주", "per": 35, "pbr": 4.5, "roe": 28, "upside": (20, 30)},
            "010120": {"name": "LS ELECTRIC",    "type": "주도주", "per": 16, "pbr": 1.8, "roe": 15, "upside": (25, 35)},
            # 가치주: PBR 0.8·1.2, ROE 10·14 — 배전변압기·케이블
            "033100": {"name": "제룡전기",        "type": "가치주", "per": 10, "pbr": 0.8, "roe": 10, "upside": (50, 70)},
            "103590": {"name": "일진전기",        "type": "가치주", "per": 13, "pbr": 1.2, "roe": 14, "upside": (45, 65)},
        }
    },

    "피지컬AI_로봇": {
        "conviction": 4,
        "weight": 0.09,
        "stocks": {
            "454910": {"name": "두산로보틱스",    "type": "주도주", "per": None, "pbr": 4.5, "roe": None, "upside": (30, 50)},
            "277810": {"name": "레인보우로보틱스", "type": "주도주", "per": None, "pbr": 8.0, "roe": None, "upside": (25, 40)},
            # 가치주: PBR 1.0·1.8, ROE 12·14 — 감속기·정밀모터
            "058610": {"name": "에스피지",        "type": "가치주", "per": 12, "pbr": 1.0, "roe": 12, "upside": (40, 55)},
            "099190": {"name": "스맥",            "type": "가치주", "per": 15, "pbr": 1.8, "roe": 14, "upside": (35, 50)},
        }
    },

    "바이오헬스": {
        "conviction": 4,
        "weight": 0.08,
        "stocks": {
            "207940": {"name": "삼성바이오로직스", "type": "주도주", "per": 60, "pbr": 5.0, "roe": 12, "upside": (20, 30)},
            "068270": {"name": "셀트리온",         "type": "주도주", "per": 30, "pbr": 2.5, "roe": 10, "upside": (25, 40)},
            # 가치주: PBR 1.2·1.5, ROE 10·15 — 완제의약품·제네릭
            "185750": {"name": "종근당",           "type": "가치주", "per": 12, "pbr": 1.2, "roe": 15, "upside": (35, 50)},
            "000100": {"name": "유한양행",         "type": "가치주", "per": 20, "pbr": 1.5, "roe": 10, "upside": (30, 45)},
        }
    },

    # ── Conviction 3 (합계 0.22) ────────────────────────────────────────────

    "밸류업_금융": {
        "conviction": 3,
        "weight": 0.07,
        "stocks": {
            "105560": {"name": "KB금융",       "type": "주도주", "per": 7, "pbr": 0.70, "roe": 11, "upside": (20, 30)},
            "086790": {"name": "하나금융지주", "type": "주도주", "per": 6, "pbr": 0.60, "roe": 10, "upside": (25, 35)},
            # 가치주: PBR 0.35·0.45, ROE 8·9 — 국책은행·저PBR 극단값
            "024110": {"name": "기업은행",     "type": "가치주", "per": 5, "pbr": 0.35, "roe":  8, "upside": (35, 50)},
            "316140": {"name": "우리금융지주", "type": "가치주", "per": 5, "pbr": 0.45, "roe":  9, "upside": (40, 55)},
        }
    },

    "외교_한중": {
        "conviction": 3,
        "weight": 0.06,
        "stocks": {
            "090430": {"name": "아모레퍼시픽", "type": "주도주", "per": 25, "pbr": 1.8, "roe": 10, "upside": (25, 35)},
            "259960": {"name": "크래프톤",     "type": "주도주", "per": 16, "pbr": 1.5, "roe": 14, "upside": (20, 30)},
            # 가치주: PBR 0.5·1.5, ROE 6·12 — 뷰티·ODM 저평가
            "051900": {"name": "LG생활건강",   "type": "가치주", "per": 18, "pbr": 0.5, "roe":  6, "upside": (40, 60)},
            "161890": {"name": "한국콜마",     "type": "가치주", "per": 14, "pbr": 1.5, "roe": 12, "upside": (30, 45)},
        }
    },

    "건설_SOC": {
        "conviction": 3,
        "weight": 0.05,
        "stocks": {
            "000720": {"name": "현대건설",  "type": "주도주", "per": 12, "pbr": 0.5, "roe":  6, "upside": (30, 50)},
            "375500": {"name": "DL이앤씨",  "type": "주도주", "per": 10, "pbr": 0.4, "roe":  8, "upside": (35, 55)},
            # 가치주: PBR 0.3·0.5, ROE 5·8 — 공공주택 수주 수혜
            "047040": {"name": "대우건설",  "type": "가치주", "per":  8, "pbr": 0.3, "roe":  5, "upside": (45, 65)},
            "013580": {"name": "계룡건설",  "type": "가치주", "per":  8, "pbr": 0.5, "roe":  8, "upside": (40, 60)},
        }
    },

    "2차전지": {
        "conviction": 3,
        "weight": 0.04,
        "stocks": {
            "373220": {"name": "LG에너지솔루션", "type": "주도주", "per": 40, "pbr": 2.0, "roe":  5, "upside": (20, 35)},
            "003670": {"name": "포스코퓨처엠",   "type": "주도주", "per": 25, "pbr": 1.5, "roe":  8, "upside": (25, 40)},
            # 가치주: PBR 0.5·0.8, ROE 3·7 — 다운사이클 저점 매수
            "096770": {"name": "SK이노베이션",   "type": "가치주", "per": 20, "pbr": 0.5, "roe":  3, "upside": (35, 55)},
            "051910": {"name": "LG화학",         "type": "가치주", "per": 15, "pbr": 0.8, "roe":  7, "upside": (30, 50)},
        }
    },
}

# ── 고배당 유니버스 (DIVIDEND_TOP12) ─────────────────────────────────────────

DIVIDEND_TOP12 = {
    "high_yield": {
        # 배당수익률 5% 이상 — 분기 배당 우선
        "316140": {"name": "우리금융지주", "yield_pct": 7.0, "dps": 1360,  "pbr": 0.45, "weight": 0.22, "freq": "분기"},
        "005830": {"name": "DB손해보험",   "yield_pct": 7.0, "dps": 6800,  "pbr": 0.65, "weight": 0.20, "freq": "연1회"},
        "024110": {"name": "기업은행",     "yield_pct": 6.9, "dps": 1065,  "pbr": 0.37, "weight": 0.18, "freq": "분기"},
        "088980": {"name": "맥쿼리인프라", "yield_pct": 6.7, "dps":  760,  "pbr": 1.20, "weight": 0.15, "freq": "반기"},
        "000810": {"name": "삼성화재",     "yield_pct": 4.8, "dps": 19500, "pbr": 1.10, "weight": 0.13, "freq": "분기"},
        "138040": {"name": "메리츠금융지주", "yield_pct": 4.5, "dps": 2000, "pbr": 1.30, "weight": 0.12, "freq": "분기"},
    },
    "sector_dividend": {
        # 섹터 연계 + 배당 — 수익률 2~6%
        "086790": {"name": "하나금융지주", "yield_pct": 5.9, "dps": 3600,  "pbr": 0.60, "weight": 0.18, "freq": "분기"},
        "105560": {"name": "KB금융",       "yield_pct": 4.0, "dps": 3174,  "pbr": 0.70,               "freq": "분기"},
        "055550": {"name": "신한지주",     "yield_pct": 4.5, "dps": 2160,  "pbr": 0.70,               "freq": "분기"},
        "051600": {"name": "한전KPS",      "yield_pct": 3.5, "dps": 1800,  "pbr": 2.00,               "freq": "연1회"},
        "103140": {"name": "풍산",         "yield_pct": 2.2, "dps": 2600,  "pbr": 0.70,               "freq": "연1회"},
        "000810": {"name": "삼성화재",     "yield_pct": 4.8, "dps": 19500, "pbr": 1.10,               "freq": "분기"},
        "051900": {"name": "LG생활건강",   "yield_pct": 1.2, "dps": 3500,  "pbr": 0.50,               "freq": "연1회"},
    }
}


def get_unique_codes():
    """전체 유니버스의 고유 종목코드 목록"""
    codes = set()
    for sector in SECTORS.values():
        codes.update(sector["stocks"].keys())
    for group in DIVIDEND_TOP12.values():
        codes.update(group.keys())
    return sorted(codes)


def get_stock_name(code: str) -> str:
    """종목코드로 종목명 조회"""
    for sector in SECTORS.values():
        if code in sector["stocks"]:
            return sector["stocks"][code]["name"]
    for group in DIVIDEND_TOP12.values():
        if code in group:
            return group[code]["name"]
    return code


def get_sector_stocks(sector_key: str, stock_type: str = None) -> dict:
    """
    섹터 내 종목 필터링
    stock_type: "주도주" | "가치주" | None(전체)
    """
    sector = SECTORS.get(sector_key, {})
    stocks = sector.get("stocks", {})
    if stock_type is None:
        return stocks
    return {k: v for k, v in stocks.items() if v.get("type") == stock_type}


def get_value_stocks() -> dict:
    """
    전 섹터 가치주 목록 (PBR ≤ 1.5 종목)
    반환: {code: {name, sector, pbr, roe, ...}}
    """
    result = {}
    for sector_key, sector in SECTORS.items():
        for code, info in sector["stocks"].items():
            if info.get("type") == "가치주":
                result[code] = {**info, "sector": sector_key}
    return result
