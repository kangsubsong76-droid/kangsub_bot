"""
signal_analyzer.py
시간외 데이터 + Claude API 분석으로 NXT 매수 3종목 확정
매일 07:30 (afterhours_collector.py 이후) 실행
"""

import os
import json
import re
import requests
import logging
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)

# ── 경로 설정 ──────────────────────────────────────────────
BASE_DIR        = Path(__file__).resolve().parent.parent
DATA_DIR        = BASE_DIR / "data" / "store"
AFTERHOURS_PATH = DATA_DIR / "afterhours_result.json"
PATTERN_DB_PATH = DATA_DIR / "pattern_db.json"
PREDICTION_PATH = DATA_DIR / "prediction_result.json"
CANDIDATES_PATH = DATA_DIR / "nxt_candidates.json"  # 파싱된 종목코드

# ── API 설정 ──────────────────────────────────────────────
ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
MODEL             = "claude-sonnet-4-6"


def _get_api_key():
    key = os.getenv("ANTHROPIC_API_KEY", "")
    if not key:
        try:
            from config.settings import ANTHROPIC_API_KEY
            key = ANTHROPIC_API_KEY
        except ImportError:
            pass
    return key


def load_afterhours():
    try:
        with open(AFTERHOURS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log.error(f"시간외 데이터 로드 실패: {e}")
        return None


def load_pattern_db():
    try:
        with open(PATTERN_DB_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def build_prompt(afterhours_data, pattern_db):
    stocks_text = ""
    for i, s in enumerate(afterhours_data.get("stocks", [])[:20], 1):
        stocks_text += (
            f"{i}. {s['name']} ({s['code']}) [{s['market']}] "
            f"시간외등락: +{s['change_rate']}% "
            f"거래량비율: {s['vol_ratio']}배\n"
        )

    pattern_text = json.dumps(pattern_db, ensure_ascii=False, indent=2) if pattern_db else "없음 (초기 실행)"
    today = datetime.now().strftime("%Y-%m-%d")

    prompt = f"""
# ROLE
당신은 한국 주식시장 NXT(장전거래) 급등 종목 예측 전문 AI입니다.

핵심 철학:
"권력자 발언과 글로벌 이벤트가 정책을 만들고
 정책이 수급을 만들고, 수급이 주가를 만든다"

오늘 날짜: {today}
실행 시각: 07:30 (시간외 단일가 마감 직후)
목표: NXT 매수 종목 3개 확정 (08:00 매수)

━━━━━━━━━━━━━━━━━━━━━━━━━━━
# STAGE 0. 시장 환경 확인
나스닥 전일 등락률, VIX를 검색하여 확인하세요.
- 나스닥 -1% 이하 OR VIX 30 이상 → "매매 중단" 출력 후 종료
- VIX 20~30 → 종목 1개만
- 정상 → 종목 3개

━━━━━━━━━━━━━━━━━━━━━━━━━━━
# STAGE 1. 시그널 캐치
다음을 검색하세요:
- 이재명 대통령 최근 48시간 발언/행보
- 주요 장관 정책 발표
- 글로벌 빅테크 CEO 발언 (엔비디아/구글/MS 등)
- 미국 대통령/연준 발언
- 지정학 변화

시그널 점수:
- 대통령 직접 발언 + 섹터 명시: 5점
- 글로벌 빅테크 CEO 투자 선언: 4점
- 장관 정책 + 예산: 4점
- 미국 정부/연준 발언: 3점
- 기타: 1~2점

━━━━━━━━━━━━━━━━━━━━━━━━━━━
# STAGE 2. 정책 호응 확인
S1 테마에 대해 정부 정책 호응 여부 확인
2개 이상 확인 → HIGH / 1개 → MID / 0개 → 신뢰도 하향

━━━━━━━━━━━━━━━━━━━━━━━━━━━
# STAGE 3. 시간외 수급 확인 + 갭 분석 (NXT 핵심)

## 시간외 거래와 정규장의 상관 메커니즘
전날 장마감 후 뉴스/공시 → 장후 시간외 첫 반응 → 다음날 장전 시간외 갭 형성
→ 09:00 정규장 추가 상승(모멘텀 지속) OR 차익실현(갭 되돌림) 분기

## 오늘 07:30 마감 기준 시간외 데이터:

{stocks_text}

## 갭 크기별 매수 전략 분류 (필수 적용):

| 시간외 등락 | 전략 | budget_ratio | 근거 |
|-----------|------|-------------|------|
| 3~8%      | 최적 매수 | 1.0 | 검증된 모멘텀 + 추가 상승 여력 충분 |
| 8~15%     | 주의 매수 | 0.5 | 이미 많이 올랐으나 테마 강세 시 추가 가능 / 차익매물 주의 |
| 15% 초과  | 스킵     | 0.0 | 갭 과도 — 09:00 정규장 즉시 차익매물 폭증 위험 |
| 1~3%      | 약한 신호 | 0.8 | 정책/뉴스 트리거 강할 때만 선정 |

## 추가 수급 신호:
- 거래량비율 5배 이상: 강한 수급 확인 → confidence UP
- 거래량비율 2~5배: 보통
- 거래량비율 2배 미만: 신호 약함 → confidence DOWN

위 종목과 S1 테마를 교차 검증:
- 테마 일치 + 갭 3~8% + 거래량 5배↑ → HIGH
- 테마 일치 + 갭 8~15%         → MID (budget_ratio=0.5)
- 테마 불일치 또는 갭 15%↑     → 제외

━━━━━━━━━━━━━━━━━━━━━━━━━━━
# STAGE 4. NXT 종목 확정 및 출력

아래 형식으로 정확히 출력하세요:

[분석일자] {today} 07:30
[시장판단] 진행/축소/중단
[나스닥] X.XX% / [VIX] XX.X

[핵심시그널]
국내: (대통령/장관 발언 1줄)
글로벌: (빅이벤트 1줄)
정책호응: Y/N + 근거 1줄

[핵심테마]
1순위: [테마명] / 점수: N점
2순위: [테마명] / 점수: N점

[NXT매수종목]
| 순위 | 종목명 | 코드 | 신뢰도 | 시간외등락 | 거래량비율 | 진입 | 손절기준 | 선정근거 |
|------|--------|------|--------|-----------|-----------|------|---------|---------|
|  1   |        |      |  HIGH  |           |           | 08:00즉시 | 갭다운즉시 | |
|  2   |        |      |  HIGH  |           |           | 08:00즉시 | 갭다운즉시 | |
|  3   |        |      |  MID   |           |           | 08:10확인 | -2% | |

[매도원칙]
- 갭다운 → 즉시 전량 손절
- 고점 -3% 이탈 → 전량 매도
- 10:30 데드라인 → 잔여 전량 청산

[리스크메모] (특이사항)

━━━━━━━━━━━━━━━━━━━━━━━━━━━
# STAGE 5. 패턴DB 참조
{pattern_text}

패턴 반영:
- 적중률 60% 이상 패턴 → 해당 섹터 +2점
- 적중률 30% 미만 패턴 → -2점
- 샘플 3개 미만 → 참고만

━━━━━━━━━━━━━━━━━━━━━━━━━━━
# IMPORTANT: 분석 마지막에 아래 JSON 블록을 반드시 추가하세요.
시장 중단인 경우 stop=true, stocks=[].

```json
{{
  "stop": false,
  "market_status": "진행",
  "nasdaq_change": 0.0,
  "vix": 0.0,
  "stocks": [
    {{
      "rank": 1, "code": "000000", "name": "종목명", "confidence": "HIGH",
      "gap_rate": 5.2,
      "budget_ratio": 1.0,
      "gap_reason": "테마일치+갭최적+거래량5배"
    }},
    {{
      "rank": 2, "code": "000000", "name": "종목명", "confidence": "HIGH",
      "gap_rate": 4.1,
      "budget_ratio": 1.0,
      "gap_reason": "정책호응+갭최적"
    }},
    {{
      "rank": 3, "code": "000000", "name": "종목명", "confidence": "MID",
      "gap_rate": 9.8,
      "budget_ratio": 0.5,
      "gap_reason": "테마일치+갭주의구간"
    }}
  ]
}}
```
"""
    return prompt


def call_claude_api(prompt):
    api_key = _get_api_key()
    if not api_key:
        log.error("ANTHROPIC_API_KEY 미설정")
        return None

    headers = {
        "Content-Type":      "application/json",
        "x-api-key":         api_key,
        "anthropic-version": "2023-06-01",
        "anthropic-beta":    "web-search-2025-03-05",  # web_search_20250305 툴 활성화 필수
    }
    body = {
        "model":      MODEL,
        "max_tokens": 2500,
        "tools":      [{"type": "web_search_20250305", "name": "web_search"}],
        "messages":   [{"role": "user", "content": prompt}]
    }

    try:
        log.info("Claude API 호출 중...")
        resp = requests.post(ANTHROPIC_API_URL, headers=headers, json=body, timeout=90)
        if not resp.ok:
            # 오류 상세 로깅 (400/401/429 등 원인 파악용)
            try:
                err_body = resp.json()
                log.error(f"Claude API HTTP {resp.status_code}: {err_body.get('error', {}).get('message', resp.text[:300])}")
            except Exception:
                log.error(f"Claude API HTTP {resp.status_code}: {resp.text[:300]}")
            return None
        resp.raise_for_status()
        data = resp.json()
        full_text = "".join(
            b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"
        )
        if not full_text:
            log.warning(f"Claude 응답 텍스트 없음 — content 블록 수: {len(data.get('content', []))}")
        log.info("Claude API 응답 수신 완료")
        return full_text or None
    except Exception as e:
        log.error(f"Claude API 오류: {e}")
        return None


def _enrich_with_afterhours_price(stocks: list) -> list:
    """
    nxt_candidates의 종목 리스트에 시간외 단일가 가격 주입
    afterhours_result.json에서 code 매칭 → price, change_rate, vol_ratio 추가
    """
    try:
        with open(AFTERHOURS_PATH, "r", encoding="utf-8") as f:
            ah = json.load(f)
        ah_map = {s["code"]: s for s in ah.get("stocks", [])}
        for stock in stocks:
            code = stock.get("code", "")
            if code in ah_map:
                s = ah_map[code]
                raw_price = str(s.get("price", "0")).replace(",", "").replace("+", "").replace("-", "")
                try:
                    stock["afterhours_price"] = int(raw_price)
                except Exception:
                    pass
                stock["change_rate"] = s.get("change_rate")
                stock["vol_ratio"]   = s.get("vol_ratio")
    except Exception as e:
        log.warning(f"시간외 가격 주입 실패: {e}")
    return stocks


def parse_nxt_candidates(analysis_text):
    """분석 결과에서 JSON 블록 파싱 → nxt_candidates.json 저장"""
    try:
        match = re.search(r'```json\s*(\{.*?\})\s*```', analysis_text, re.DOTALL)
        if not match:
            log.warning("JSON 블록을 찾지 못함 — 테이블 파싱 시도")
            return _parse_table_fallback(analysis_text)

        data = json.loads(match.group(1))
        stocks = _enrich_with_afterhours_price(data.get("stocks", []))
        candidates = {
            "date":          datetime.now().strftime("%Y-%m-%d"),
            "time":          datetime.now().strftime("%H:%M"),
            "stop":          data.get("stop", False),
            "market_status": data.get("market_status", "진행"),
            "nasdaq_change": data.get("nasdaq_change", 0.0),
            "vix":           data.get("vix", 0.0),
            "stocks":        stocks,
        }
        with open(CANDIDATES_PATH, "w", encoding="utf-8") as f:
            json.dump(candidates, f, ensure_ascii=False, indent=2)
        log.info(f"NXT 후보 저장: {len(stocks)}종목 (시간외 가격 포함)")
        return candidates
    except Exception as e:
        log.error(f"NXT 후보 파싱 실패: {e}")
        return None


def _parse_table_fallback(text):
    """JSON 블록 없을 때 마크다운 테이블에서 코드 추출"""
    stocks = []
    pattern = re.compile(r'\|\s*(\d)\s*\|\s*(.+?)\s*\|\s*(\d{6})\s*\|\s*(HIGH|MID|LOW)\s*\|')
    for m in pattern.finditer(text):
        stocks.append({
            "rank":       int(m.group(1)),
            "name":       m.group(2).strip(),
            "code":       m.group(3).strip(),
            "confidence": m.group(4).strip()
        })
    stocks = _enrich_with_afterhours_price(stocks)
    candidates = {
        "date":          datetime.now().strftime("%Y-%m-%d"),
        "time":          datetime.now().strftime("%H:%M"),
        "stop":          "매매 중단" in text,
        "market_status": "중단" if "매매 중단" in text else "진행",
        "stocks":        stocks,
    }
    with open(CANDIDATES_PATH, "w", encoding="utf-8") as f:
        json.dump(candidates, f, ensure_ascii=False, indent=2)
    return candidates


def save_prediction(analysis_text, afterhours_data):
    result = {
        "date":             datetime.now().strftime("%Y-%m-%d"),
        "time":             datetime.now().strftime("%H:%M:%S"),
        "analysis":         analysis_text,
        "afterhours_input": afterhours_data.get("stocks", [])[:10]
    }
    with open(PREDICTION_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    log.info(f"예측 결과 저장: {PREDICTION_PATH}")
    return result


def run():
    """메인 실행 — main.py 스케줄러에서 호출"""
    log.info("=== NXT 시그널 분석 시작 ===")

    afterhours = load_afterhours()
    if not afterhours:
        log.error("시간외 데이터 없음 — 분석 중단")
        return None

    pattern_db = load_pattern_db()
    prompt     = build_prompt(afterhours, pattern_db)
    analysis   = call_claude_api(prompt)

    if not analysis:
        log.error("분석 실패")
        return None

    result     = save_prediction(analysis, afterhours)
    candidates = parse_nxt_candidates(analysis)

    log.info("=== 분석 완료 ===")
    return {"result": result, "candidates": candidates}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
