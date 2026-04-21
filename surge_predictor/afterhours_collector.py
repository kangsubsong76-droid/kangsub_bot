"""
afterhours_collector.py
키움 OCX TR 조회로 시간외 단일가 상위 종목 수집
매일 07:30 실행 (시간외 단일가 마감 직후)

기존 자동매매 시스템과 충돌 방지:
- 별도 QApplication 인스턴스 사용 금지
- 기존 실행 중인 OCX에 TR만 추가 조회
- 토큰/로그인 세션 공유 (재로그인 없음)
- 화면번호: 0101~0102 (PAM 시스템과 분리)
"""

import sys
import os
import time
import json
import logging
from datetime import datetime
from pathlib import Path

# ── 경로 설정 ──────────────────────────────────────────────
BASE_DIR    = Path(__file__).resolve().parent.parent
DATA_DIR    = BASE_DIR / "data" / "store"
LOG_DIR     = BASE_DIR / "logs"
DATA_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_PATH = DATA_DIR / "afterhours_result.json"
TOP_N       = 20  # 상위 20종목 수집

# ── 로깅 설정 ──────────────────────────────────────────────
log = logging.getLogger(__name__)


class AfterHoursCollector:
    """
    키움 OCX TR 조회로 시간외 단일가 상위 종목 수집
    기존 자동매매 QApplication 위에서 동작
    """

    def __init__(self):
        self.ocx = None
        self.result = []
        self._temp_result = []
        self._setup_ocx()

    def _setup_ocx(self):
        """기존 자동매매와 별개 OCX 객체 생성 (로그인 세션 공유)"""
        try:
            from PyQt5.QAxContainer import QAxWidget
            from PyQt5.QtCore import QEventLoop
            self.loop = QEventLoop()
            self.ocx  = QAxWidget("KHOPENAPI.KHOpenAPICtrl.1")
            self.ocx.OnReceiveTrData.connect(self._on_receive_tr)
            log.info("OCX 초기화 완료")
        except Exception as e:
            log.error(f"OCX 초기화 실패: {e}")
            self.ocx = None

    def login(self):
        """로그인 상태 확인 (이미 로그인된 경우 재사용)"""
        if not self.ocx:
            return False
        state = self.ocx.dynamicCall("GetConnectState()")
        if state == 1:
            log.info("이미 로그인 상태 — 세션 재사용")
            return True
        log.error("키움 미연결 — OCX 수집 불가")
        return False

    def get_afterhours_top(self, market="0"):
        """
        OPT10045 — 시간외 단일가 상승 상위 종목 조회
        market: "0" = 코스피, "1" = 코스닥
        """
        from PyQt5.QtCore import QTimer
        self.current_market = market
        self._temp_result   = []

        self.ocx.dynamicCall("SetInputValue(QString, QString)", "시장구분", market)
        self.ocx.dynamicCall("SetInputValue(QString, QString)", "정렬구분", "1")
        self.ocx.dynamicCall("SetInputValue(QString, QString)", "거래량조건", "0")

        ret = self.ocx.dynamicCall(
            "CommRqData(QString, QString, int, QString)",
            "시간외단일가상위", "OPT10045", 0, "0101"
        )
        if ret != 0:
            log.error(f"TR 요청 실패: {ret}")
            return []

        timer = QTimer()
        timer.singleShot(5000, self.loop.quit)
        self.loop.exec_()
        return self._temp_result

    def _on_receive_tr(self, screen, rq_name, tr_code, record_name, prev_next, *args):
        if rq_name != "시간외단일가상위":
            return

        count = self.ocx.dynamicCall(
            "GetRepeatCnt(QString, QString)", tr_code, rq_name
        )
        count = min(count, TOP_N)

        for i in range(count):
            def get(field):
                return self.ocx.dynamicCall(
                    "GetCommData(QString, QString, int, QString)",
                    tr_code, rq_name, i, field
                ).strip()

            code        = get("종목코드").lstrip("A")
            name        = get("종목명")
            cur_price   = get("현재가").lstrip("+-")
            change_rate = get("등락률")
            volume      = get("거래량")
            prev_volume = get("전일거래량")

            try:
                rate_f = float(change_rate.replace("%", "").replace("+", ""))
                vol_i  = int(volume.replace(",", "")) if volume else 0
                prev_i = int(prev_volume.replace(",", "")) if prev_volume else 1

                # 필터: 시간외 +1%~+15%, 거래량 전일 200% 이상
                if 1.0 <= rate_f <= 15.0 and vol_i >= prev_i * 2:
                    self._temp_result.append({
                        "code":        code,
                        "name":        name,
                        "price":       cur_price,
                        "change_rate": rate_f,
                        "volume":      vol_i,
                        "prev_volume": prev_i,
                        "vol_ratio":   round(vol_i / prev_i, 1) if prev_i else 0,
                        "market":      "코스피" if self.current_market == "0" else "코스닥"
                    })
            except Exception as e:
                log.warning(f"파싱 오류 [{name}]: {e}")

        self._temp_result.sort(key=lambda x: x["change_rate"], reverse=True)
        self.loop.quit()

    def collect_all(self):
        """코스피 + 코스닥 시간외 상위 통합 수집"""
        log.info("=== 시간외 데이터 수집 시작 ===")
        all_stocks = []

        for market, label in [("0", "코스피"), ("1", "코스닥")]:
            log.info(f"{label} 시간외 조회 중...")
            stocks = self.get_afterhours_top(market)
            log.info(f"{label}: {len(stocks)}개 종목 (필터 후)")
            all_stocks.extend(stocks)
            time.sleep(0.5)

        seen, unique = set(), []
        for s in all_stocks:
            if s["code"] not in seen:
                seen.add(s["code"])
                unique.append(s)

        unique.sort(key=lambda x: x["change_rate"], reverse=True)
        log.info(f"최종 수집: {len(unique)}개 종목")

        output = {
            "collected_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "count":        len(unique),
            "stocks":       unique
        }
        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

        log.info(f"저장 완료: {OUTPUT_PATH}")
        return output


def _run_rest_api_fallback() -> dict | None:
    """
    OCX 실패 시 키움 REST API(ka10027) 폴백
    — 등락률 상위 종목에서 시간외 조건 필터링
    — ka10027: 주식등락률순위 (장중/장전 모두 지원)
    """
    log.info("REST API 폴백 — ka10027 등락률순위로 시간외 데이터 대체")
    try:
        sys.path.insert(0, str(BASE_DIR))
        from core.kiwoom_rest import KiwoomRestAPI
        kiwoom = KiwoomRestAPI()

        all_stocks = []
        for market in ["0", "1"]:  # 0=코스피, 1=코스닥
            rows = kiwoom.get_surge_ranking(market=market, top_n=50)
            if not rows:
                continue
            label = "코스피" if market == "0" else "코스닥"
            for r in rows:
                try:
                    rate_f  = float(str(r.get("change_rate", 0)).replace("%", "").replace("+", ""))
                    vol_i   = int(str(r.get("volume", 0)).replace(",", ""))
                    prev_vol = int(str(r.get("prev_volume", 1)).replace(",", "") or 1) or 1
                    vol_ratio = round(vol_i / prev_vol, 1)
                    # 시간외 조건 준용: 1~29% 등락, 거래량비율 1.5배 이상
                    if 1.0 <= rate_f <= 29.0 and vol_ratio >= 1.5:
                        all_stocks.append({
                            "code":        r.get("code", "").zfill(6),
                            "name":        r.get("name", ""),
                            "price":       str(r.get("price", "0")),
                            "change_rate": rate_f,
                            "volume":      vol_i,
                            "prev_volume": prev_vol,
                            "vol_ratio":   vol_ratio,
                            "market":      label,
                        })
                except Exception:
                    pass

        if not all_stocks:
            log.warning("REST API 폴백: 필터 통과 종목 없음")
            return None

        all_stocks.sort(key=lambda x: x["change_rate"], reverse=True)
        unique, seen = [], set()
        for s in all_stocks:
            if s["code"] not in seen:
                seen.add(s["code"])
                unique.append(s)

        output = {
            "collected_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "count":        len(unique),
            "source":       "kiwoom_rest_ka10027",
            "stocks":       unique[:TOP_N],
        }
        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        log.info(f"REST API 폴백 완료: {len(unique[:TOP_N])}종목 저장")
        return output

    except Exception as e:
        log.error(f"REST API 폴백 실패: {e}")
        return None


def run():
    """메인 실행 — main.py 스케줄러에서 호출
    1순위: OCX(OPT10045) 시간외 단일가 — 장전 시간외 전용 정확한 데이터
    2순위: REST API(ka10027) — OCX 실패 시 등락률순위로 대체
    """
    # 1순위: OCX 시도
    try:
        from PyQt5.QtWidgets import QApplication
        app = QApplication.instance() or QApplication(sys.argv)
        collector = AfterHoursCollector()
        if collector.login():
            result = collector.collect_all()
            if result and result.get("count", 0) > 0:
                return result
            log.warning("OCX 수집 결과 없음 — REST API 폴백")
        else:
            log.warning("OCX 로그인 실패 — REST API 폴백")
    except ImportError:
        log.warning("PyQt5 미설치 — REST API 폴백")
    except Exception as e:
        log.warning(f"OCX 오류: {e} — REST API 폴백")

    # 2순위: REST API 폴백
    return _run_rest_api_fallback()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
