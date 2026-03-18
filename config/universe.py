"""종목 유니버스 — 7섹터 + 배당 Top12 정의"""

SECTORS = {
    "AI_반도체": {
        "conviction": 5,
        "weight": 0.22,
        "stocks": {
            "000660": {"name": "SK하이닉스", "type": "주도주", "per": 14, "pbr": 1.5, "roe": 24, "upside": (35, 45)},
            "042700": {"name": "한미반도체", "type": "주도주", "per": 22, "pbr": 3.5, "roe": 32, "upside": (25, 35)},
            "357780": {"name": "솔브레인", "type": "보너스", "per": 13, "pbr": 1.2, "roe": 13, "upside": (40, 55)},
        }
    },
    "K_방산": {
        "conviction": 5,
        "weight": 0.20,
        "stocks": {
            "012450": {"name": "한화에어로스페이스", "type": "주도주", "per": 28, "pbr": 3.2, "roe": 18, "upside": (20, 30)},
            "064350": {"name": "현대로템", "type": "주도주", "per": 18, "pbr": 2.0, "roe": 16, "upside": (30, 40)},
            "103140": {"name": "풍산", "type": "보너스", "per": 9, "pbr": 0.7, "roe": 11, "upside": (50, 70)},
        }
    },
    "재생에너지": {
        "conviction": 4,
        "weight": 0.16,
        "stocks": {
            "267260": {"name": "HD현대일렉트릭", "type": "주도주", "per": 35, "pbr": 4.5, "roe": 28, "upside": (20, 30)},
            "112610": {"name": "씨에스윈드", "type": "주도주", "per": 22, "pbr": 2.2, "roe": 16, "upside": (25, 35)},
            "103590": {"name": "일진전기", "type": "보너스", "per": 13, "pbr": 1.2, "roe": 14, "upside": (45, 65)},
        }
    },
    "중소_벤처": {
        "conviction": 3,
        "weight": 0.06,
        "stocks": {
            "042700": {"name": "한미반도체", "type": "주도주", "per": 22, "pbr": 3.5, "roe": 32, "upside": (25, 35)},
            "039030": {"name": "이오테크닉스", "type": "주도주", "per": 20, "pbr": 2.5, "roe": 16, "upside": (30, 45)},
            "357780": {"name": "솔브레인", "type": "보너스", "per": 13, "pbr": 1.2, "roe": 13, "upside": (40, 55)},
        }
    },
    "피지컬AI_로봇": {
        "conviction": 4,
        "weight": 0.14,
        "stocks": {
            "454910": {"name": "두산로보틱스", "type": "주도주", "per": None, "pbr": 4.5, "roe": None, "upside": (30, 50)},
            "277810": {"name": "레인보우로보틱스", "type": "주도주", "per": None, "pbr": 8.0, "roe": None, "upside": (25, 40)},
            "099190": {"name": "스맥", "type": "보너스", "per": 15, "pbr": 1.8, "roe": 14, "upside": (35, 50)},
        }
    },
    "외교_한중": {
        "conviction": 3,
        "weight": 0.12,
        "stocks": {
            "090430": {"name": "아모레퍼시픽", "type": "주도주", "per": 25, "pbr": 1.8, "roe": 10, "upside": (25, 35)},
            "259960": {"name": "크래프톤", "type": "주도주", "per": 16, "pbr": 1.5, "roe": None, "upside": (20, 30)},
            "051900": {"name": "LG생활건강", "type": "보너스", "per": 11, "pbr": 1.3, "roe": 9, "upside": (40, 60)},
        }
    },
    "밸류업_금융": {
        "conviction": 3,
        "weight": 0.10,
        "stocks": {
            "105560": {"name": "KB금융", "type": "주도주", "per": 7, "pbr": 0.7, "roe": None, "upside": (20, 30)},
            "055550": {"name": "신한지주", "type": "주도주", "per": 7, "pbr": 0.7, "roe": None, "upside": (20, 30)},
            "086790": {"name": "하나금융지주", "type": "보너스", "per": 6, "pbr": 0.6, "roe": 10, "upside": (40, 60)},
        }
    },
}

DIVIDEND_TOP12 = {
    "high_yield": {
        "316140": {"name": "우리금융지주", "yield_pct": 7.0, "dps": 1360, "pbr": 0.45, "weight": 0.22, "freq": "분기"},
        "005830": {"name": "DB손해보험", "yield_pct": 7.0, "dps": 6800, "pbr": 0.65, "weight": 0.20, "freq": "연1회"},
        "024110": {"name": "기업은행", "yield_pct": 6.9, "dps": 1065, "pbr": 0.37, "weight": 0.18, "freq": "분기(2026~)"},
        "088980": {"name": "맥쿼리인프라", "yield_pct": 6.7, "dps": 760, "pbr": 1.2, "weight": 0.15, "freq": "반기"},
        "000810": {"name": "삼성화재", "yield_pct": 4.8, "dps": 19500, "pbr": 1.1, "weight": 0.13, "freq": "분기"},
    },
    "sector_dividend": {
        "086790": {"name": "하나금융지주", "yield_pct": 5.9, "dps": 3600, "pbr": 0.6, "weight": 0.12, "freq": "분기"},
        "105560": {"name": "KB금융", "yield_pct": 4.0, "dps": 3174, "pbr": 0.7, "freq": "분기"},
        "055550": {"name": "신한지주", "yield_pct": 4.5, "dps": 2160, "pbr": 0.7, "freq": "분기"},
        "103140": {"name": "풍산", "yield_pct": 2.2, "dps": 2600, "pbr": 0.7, "freq": "연1회"},
        "000810": {"name": "삼성화재", "yield_pct": 4.8, "dps": 19500, "pbr": 1.1, "freq": "분기"},
        "051900": {"name": "LG생활건강", "yield_pct": 1.2, "dps": 3500, "pbr": 0.5, "freq": "연1회"},
        "090430": {"name": "아모레퍼시픽", "yield_pct": 1.0, "dps": None, "pbr": 1.8, "freq": "연1회"},
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
