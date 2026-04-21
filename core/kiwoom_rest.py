"""
키움증권 REST API 클라이언트
공식 문서: 키움 REST API 개발가이드 (528p)

운영  도메인: https://api.kiwoom.com
모의투자 도메인: https://mockapi.kiwoom.com  (KRX만 지원)

모든 API: POST 방식, JSON, Content-Type: application/json;charset=UTF-8

헤더 구조:
  api-id        : TR명 (예: "ka10001")       [필수]
  authorization : "Bearer {토큰}"           [필수, 토큰발급 제외]
  cont-yn       : 연속조회여부 ("Y"/"N")     [선택]
  next-key      : 연속조회키                [선택]

주요 API 목록:
  au10001  접근토큰발급   POST /oauth2/token
  ka00001  계좌번호조회   POST /api/dostk/acnt
  ka01690  일별잔고수익률 POST /api/dostk/acnt
  ka10001  주식기본정보   POST /api/dostk/stkinfo
  ka10002  주식거래원요청 POST /api/dostk/stkinfo
  ka10081  주식일봉차트   POST /api/dostk/chart
  ka10008  업종일봉차트   POST /api/dostk/chart  (001=KOSPI, 101=KOSDAQ)
  ka10075  미체결요청     POST /api/dostk/acnt
  kt10000  주식 매수주문  POST /api/dostk/ordr
  kt10001  주식 매도주문  POST /api/dostk/ordr
  kt10002  주식 정정주문  POST /api/dostk/ordr
  kt10003  주식 취소주문  POST /api/dostk/ordr
"""
import time
import requests
from datetime import datetime, timedelta, date
from utils.logger import setup_logger
from config.settings import (
    KIWOOM_APP_KEY, KIWOOM_SECRET_KEY,
    KIWOOM_ACCOUNT, KIWOOM_MOCK, LOG_DIR,
)

log = setup_logger("kiwoom_rest", LOG_DIR)

# ── API 도메인 ───────────────────────────────────────────────
BASE_REAL = "https://api.kiwoom.com"
BASE_MOCK = "https://mockapi.kiwoom.com"   # KRX만 지원


class KiwoomRestAPI:
    """키움 REST API 래퍼 (공식 문서 기반)"""

    def __init__(self):
        self.app_key    = KIWOOM_APP_KEY
        self.secret_key = KIWOOM_SECRET_KEY
        self.account    = KIWOOM_ACCOUNT.replace("-", "")  # 예: "65947112"
        self.mock       = KIWOOM_MOCK
        self.base_url   = BASE_MOCK if KIWOOM_MOCK else BASE_REAL

        self._access_token  = None
        self._token_expire  = datetime.min

        mode = "모의투자" if self.mock else "실전매매"
        log.info(f"KiwoomRestAPI 초기화 ({mode}) 계좌: {self.account}")
        log.info(f"API 서버: {self.base_url}")

        if not self.app_key or not self.secret_key:
            log.warning("KIWOOM_APP_KEY / KIWOOM_SECRET_KEY 미설정 — .env 확인 필요")

    # ════════════════════════════════════════════════════════
    # ── 토큰 관리 (au10001)
    # ════════════════════════════════════════════════════════
    def _get_token(self) -> str | None:
        """
        접근토큰 발급 (au10001) — 만료 전 자동 갱신
        POST /oauth2/token
        Body: grant_type="client_credentials", appkey, secretkey
        Response: expires_dt, token_type="bearer", token, return_code=0
        """
        if self._access_token and datetime.now() < self._token_expire:
            return self._access_token

        url = f"{self.base_url}/oauth2/token"
        headers = {
            "Content-Type": "application/json;charset=UTF-8",
            "api-id": "au10001",
        }
        body = {
            "grant_type": "client_credentials",
            "appkey":     self.app_key,
            "secretkey":  self.secret_key,
        }
        try:
            resp = requests.post(url, json=body, headers=headers, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            if data.get("return_code", -1) != 0:
                log.error(f"키움 토큰 발급 실패: {data.get('return_msg')}")
                return None

            self._access_token = data.get("token")
            # expires_dt 형식: "20241107083713" (YYYYMMDDHHmmss)
            expires_dt_str = data.get("expires_dt", "")
            try:
                self._token_expire = datetime.strptime(expires_dt_str, "%Y%m%d%H%M%S") - timedelta(minutes=5)
            except Exception:
                self._token_expire = datetime.now() + timedelta(hours=23)

            log.info(f"키움 토큰 발급 완료 (만료: {self._token_expire.strftime('%m/%d %H:%M')})")
            return self._access_token

        except Exception as e:
            log.error(f"키움 토큰 발급 실패: {e}")
            return None

    # ── 공통 헤더 생성 ──
    def _headers(self, api_id: str, cont_yn: str = "", next_key: str = "") -> dict:
        token = self._get_token()
        h = {
            "Content-Type": "application/json;charset=UTF-8",
            "api-id":       api_id,
            "authorization": f"Bearer {token}" if token else "",
        }
        if cont_yn:  h["cont-yn"]  = cont_yn
        if next_key: h["next-key"] = next_key
        return h

    # ── 공통 POST 호출 ──
    def _post(self, path: str, body: dict, api_id: str,
              cont_yn: str = "", next_key: str = "") -> dict | None:
        url = f"{self.base_url}{path}"
        try:
            resp = requests.post(
                url, json=body,
                headers=self._headers(api_id, cont_yn, next_key),
                timeout=15
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("return_code", -1) != 0:
                log.warning(f"API 오류 [{api_id}]: {data.get('return_msg')}")
            return data
        except Exception as e:
            log.error(f"POST {path} [{api_id}] 실패: {e}")
            return None

    # ════════════════════════════════════════════════════════
    # ── 계좌번호 조회 (ka00001)
    # ════════════════════════════════════════════════════════
    def get_account_no(self) -> str | None:
        """현재 토큰의 계좌번호 조회"""
        data = self._post("/api/dostk/acnt", {}, "ka00001")
        if data and data.get("return_code") == 0:
            return data.get("acctNo", "")
        return None

    # ════════════════════════════════════════════════════════
    # ── 일별잔고수익률 (ka01690) — 잔고 + 보유종목 조회
    # ════════════════════════════════════════════════════════
    def get_balance(self) -> dict:
        """
        일별잔고수익률 조회 (ka01690)
        ※ 모의투자 미지원 — 실전전용
        반환: {cash, holdings, total_value, total_pnl, total_pnl_pct, ...}
        """
        if self.mock:
            log.warning("ka01690은 모의투자 미지원 — 빈 잔고 반환")
            return self._empty_balance()

        today = date.today().strftime("%Y%m%d")
        body = {"qry_dt": today}
        data = self._post("/api/dostk/acnt", body, "ka01690")

        if not data or data.get("return_code") != 0:
            return self._empty_balance()

        def _i(v, d=0):
            """빈 문자열/None 안전 int 변환"""
            try:
                return int(v) if v not in (None, "", " ") else d
            except (ValueError, TypeError):
                return d

        def _f(v, d=0.0):
            """빈 문자열/None 안전 float 변환"""
            try:
                return float(v) if v not in (None, "", " ") else d
            except (ValueError, TypeError):
                return d

        try:
            holdings = []
            for item in data.get("day_bal_rt", []):
                qty = _i(item.get("rmnd_qty", 0))
                if qty == 0:
                    continue
                avg     = _f(item.get("buy_uv", 0))
                cur     = _f(item.get("cur_prc", 0))
                pnl     = _f(item.get("evlv_prft", item.get("evltv_prft", 0)))
                pnl_pct = _f(item.get("prft_rt", 0))
                holdings.append({
                    "code":          item.get("stk_cd", ""),
                    "name":          item.get("stk_nm", ""),
                    "qty":           qty,
                    "avg_price":     avg,
                    "current_price": cur,
                    "pnl_pct":       round(pnl_pct, 2),
                    "pnl_amount":    round(pnl),
                    "eval_amount":   round(_f(item.get("evlt_amt", cur * qty))),
                })

            total_eval = _f(data.get("tot_evlt_amt", 0))
            total_pnl  = _f(data.get("tot_evlv_prft", 0))
            cash       = _f(data.get("dbst_bal", 0))
            pnl_rt     = _f(data.get("tot_prft_rt", 0))

            return {
                "cash":          cash,
                "total_value":   total_eval,
                "total_pnl":     total_pnl,
                "total_pnl_pct": round(pnl_rt, 2),
                "num_holdings":  len(holdings),
                "holdings":      holdings,
                "updated_at":    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        except Exception as e:
            log.error(f"잔고 파싱 오류: {e}")
            return self._empty_balance()

    # ════════════════════════════════════════════════════════
    # ── 계좌평가잔고내역 (ka01002) — 전체 보유종목 (수동매수 포함)
    # ════════════════════════════════════════════════════════
    def get_portfolio_holdings(self) -> dict:
        """
        계좌평가잔고내역 (ka01002)
        ka01690 와 달리 수동 매수 종목도 포함
        반환: {cash, holdings, total_value, ...} 또는 빈 dict
        """
        body = {"qry_tp": "1"}   # 1=전체
        data = self._post("/api/dostk/acnt", body, "ka01002")

        if not data or data.get("return_code") != 0:
            log.warning(f"ka01002 조회 실패 — return_code: {data.get('return_code') if data else 'None'}")
            return {}

        def _i(v, d=0):
            try:
                return int(v) if v not in (None, "", " ") else d
            except (ValueError, TypeError):
                return d

        def _f(v, d=0.0):
            try:
                return float(v) if v not in (None, "", " ") else d
            except (ValueError, TypeError):
                return d

        try:
            # ka01002 응답 필드 (Kiwoom 문서 기준 예상 필드명)
            # 실제 필드명은 API 응답 확인 후 조정 필요
            holdings = []
            item_list = (
                data.get("acnt_evlt_remn_indv_tot", []) or
                data.get("output", []) or
                data.get("list", []) or
                []
            )
            for item in item_list:
                qty = _i(item.get("rmnd_qty") or item.get("hldg_qty") or 0)
                if qty == 0:
                    continue
                avg     = _f(item.get("buy_uv") or item.get("avg_uv") or 0)
                cur     = _f(item.get("cur_prc") or item.get("prst_pric") or 0)
                val     = _f(item.get("evlt_amt") or item.get("eval_amt") or cur * qty)
                pnl     = _f(item.get("evlv_prft") or item.get("prft") or (val - avg * qty))
                pnl_pct = _f(item.get("prft_rt") or item.get("earn_rt") or 0)
                holdings.append({
                    "code":          item.get("stk_cd") or item.get("pdno", ""),
                    "name":          item.get("stk_nm") or item.get("prdt_name", ""),
                    "qty":           qty,
                    "avg_price":     avg,
                    "current_price": cur,
                    "pnl_pct":       round(pnl_pct, 2),
                    "pnl_amount":    round(pnl),
                    "value":         round(val),
                })

            total_eval = _f(data.get("tot_evlt_amt") or data.get("evlt_remn_tot") or 0)
            total_pnl  = _f(data.get("tot_evlv_prft") or data.get("tot_prft") or 0)
            cash       = _f(data.get("dbst_bal") or data.get("dnca_tot_amt") or 0)
            pnl_rt     = _f(data.get("tot_prft_rt") or 0)

            if not holdings and total_eval == 0:
                log.warning("ka01002 응답은 성공이나 보유종목 없음 (필드명 불일치 가능)")
                log.debug(f"ka01002 raw keys: {list(data.keys())}")
                return {}

            log.info(f"ka01002 계좌잔고 조회 성공: {len(holdings)}종목, 평가총액 {total_eval:,.0f}원")
            return {
                "cash":          cash,
                "total_value":   total_eval,
                "total_pnl":     total_pnl,
                "total_pnl_pct": round(pnl_rt, 2),
                "num_holdings":  len(holdings),
                "holdings":      holdings,
                "source":        "ka01002",
                "updated_at":    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        except Exception as e:
            log.error(f"ka01002 파싱 오류: {e}")
            return {}

    def _empty_balance(self) -> dict:
        return {
            "cash": 0, "total_value": 0, "total_pnl": 0,
            "total_pnl_pct": 0, "num_holdings": 0, "holdings": [],
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "error": "API 조회 실패",
        }

    # ════════════════════════════════════════════════════════
    # ── 주식기본정보 (ka10001) — 현재가 + PER/ROE/PBR
    # ════════════════════════════════════════════════════════
    def get_stock_info(self, code: str) -> dict | None:
        """
        주식기본정보요청 (ka10001)
        반환: {code, name, price, change_pct, high, low, open, per, roe, pbr}
        """
        body = {"stk_cd": code.zfill(6)}
        data = self._post("/api/dostk/stkinfo", body, "ka10001")
        if not data or data.get("return_code") != 0:
            return None
        try:
            # 등락부호: 1=상한, 2=상승, 3=보합, 4=하한, 5=하락
            flu_smbol = data.get("flu_smbol", "3")
            flu_rt = float(data.get("flu_rt", 0))
            if flu_smbol in ("4", "5"):
                flu_rt = -abs(flu_rt)

            return {
                "code":       code,
                "name":       data.get("stk_nm", ""),
                "price":      int(data.get("cur_prc", 0)),
                "change_pct": round(flu_rt, 2),
                "volume":     int(data.get("trde_qty", 0)),
                "high":       int(data.get("high_pric", 0)),
                "low":        int(data.get("low_pric", 0)),
                "open":       int(data.get("open_pric", 0)),
                "per":        float(data.get("per", 0) or 0),
                "roe":        float(data.get("roe", 0) or 0),
                "pbr":        float(data.get("pbr", 0) or 0),
                "eps":        float(data.get("eps", 0) or 0),
                "cap":        data.get("cap", ""),       # 자본금
                "flo_stk":    data.get("flo_stk", ""),  # 상장주식수
            }
        except Exception as e:
            log.error(f"주식정보 파싱 오류 ({code}): {e}")
            return None

    # ── 현재가 조회 (ka10001 래핑) ──
    def get_current_price(self, code: str) -> dict | None:
        """get_stock_info 의 간소화 래퍼 — 현재가 위주"""
        info = self.get_stock_info(code)
        if not info:
            return None
        return {
            "code":       info["code"],
            "name":       info["name"],
            "price":      info["price"],
            "change_pct": info["change_pct"],
            "volume":     info["volume"],
            "high":       info["high"],
            "low":        info["low"],
            "open":       info["open"],
        }

    # ── NXT 장전거래 적격 여부 확인 (ka10001) ──
    def is_nxt_eligible(self, code: str) -> tuple[bool, str]:
        """
        NXT 장전거래(08:00~08:50) 가능 여부 확인 (ka10001 원시 응답 기반)

        거래 불가 조건:
          - 거래정지 (trde_halt_tp / trde_halt_yn)
          - 관리종목 / 투자위험 / 투자경고 / 투자주의 (stk_stat_tp)
          - 코넥스 시장 (mkt_tp = KNX / K3) — 장전거래 미지원
          - ka10001 조회 자체 실패

        불명확한 필드는 매수 허용(True) 처리 — API 오류로 인한 기회 손실 방지.
        실제 API 응답에서 필드명이 확인되면 조건 추가 가능.

        반환: (eligible: bool, reason: str)
        """
        body = {"stk_cd": code.zfill(6)}
        data = self._post("/api/dostk/stkinfo", body, "ka10001")
        if not data:
            # 네트워크 오류 — 기회 손실 방지를 위해 통과 허용
            log.warning(f"is_nxt_eligible [{code}]: API 응답 없음 → 매수 허용")
            return True, "API 무응답(통과허용)"
        rc = data.get("return_code", -1)
        if rc != 0:
            # return_code: 3 = 데이터 없음 (거래정지 아님) → 통과 허용
            # return_code: -1, 1, 2 등 명시적 오류만 차단하지 않음
            # 단, 명백한 인증 오류(return_code: 1)는 경고만 남기고 통과
            log.warning(f"is_nxt_eligible [{code}]: return_code={rc} → 확인불가, 매수 허용")
            return True, f"API확인불가(rc={rc},통과허용)"

        # ── 1) 거래정지 확인 ──────────────────────────────
        # 키움 API 필드명 후보: trde_halt_tp, trde_halt_yn, halt_yn
        for field in ("trde_halt_tp", "trde_halt_yn", "halt_yn"):
            val = str(data.get(field, "")).strip()
            # "0", "N", "" → 정상 / 그 외 → 정지
            if val and val not in ("0", "N", ""):
                reason = f"거래정지 ({field}={val})"
                log.info(f"NXT 부적격 [{code}]: {reason}")
                return False, reason

        # ── 2) 관리종목 / 투자위험·경고·주의 확인 ─────────
        # 키움 API 필드명 후보: stk_stat_tp, manage_tp, supervise_tp
        for field in ("stk_stat_tp", "manage_tp", "supervise_tp", "invst_caut_tp"):
            val = str(data.get(field, "")).strip()
            # "00", "0", "" → 정상
            if val and val not in ("0", "00", ""):
                reason = f"비정상 상태 ({field}={val})"
                log.info(f"NXT 부적격 [{code}]: {reason}")
                return False, reason

        # ── 3) 코넥스 시장 확인 (장전거래 미지원) ──────────
        # 키움 API 필드명 후보: mkt_tp, stex_tp, mrkt_tp
        for field in ("mkt_tp", "stex_tp", "mrkt_tp"):
            val = str(data.get(field, "")).strip().upper()
            if val in ("KNX", "K3", "KONEX"):
                reason = f"코넥스 종목 NXT 불가 ({field}={val})"
                log.info(f"NXT 부적격 [{code}]: {reason}")
                return False, reason

        log.debug(f"NXT 적격 [{code}]: 정상 거래 가능")
        return True, "정상"

    # ════════════════════════════════════════════════════════
    # ── 주식 매수주문 (kt10000)
    # ════════════════════════════════════════════════════════
    # trde_tp: 0=보통(지정가), 3=시장가, 5=조건부지정가
    # dmst_stex_tp: KRX (일반적으로 KRX 사용)

    def buy_market(self, code: str, qty: int) -> dict | None:
        """시장가 매수 (kt10000, trde_tp=3) — 정규장 09:00~15:30 전용"""
        body = {
            "dmst_stex_tp": "KRX",
            "stk_cd":  code.zfill(6),
            "ord_qty": str(qty),
            "ord_uv":  "",        # 시장가 — 단가 미입력
            "trde_tp": "3",       # 3=시장가
            "cond_uv": "",
        }
        data = self._post("/api/dostk/ordr", body, "kt10000")
        if data and data.get("return_code") == 0:
            log.info(f"매수(시장가) 완료: {code} {qty}주 — 주문번호: {data.get('ord_no')}")
        return data

    def buy_premarket(self, code: str, qty: int, price: int) -> dict | None:
        """
        장전 시간외 종가 매수 (kt10000, trde_tp=61)
        — 07:30~08:30 장전시간외 종가매매 전용 (코스피/코스닥 모두 지원)
        — trde_tp=61: 전일 종가로 자동 거래 → ord_uv 반드시 공백 ("") 입력
          가격 지정 시 Kiwoom 오류: [2000](571557:장개시전 시간외종가 주문시에는 단가를 입력하지 않습니다)
        — price 파라미터는 수량 계산/로그용으로만 사용, 실제 주문에는 미전송
        """
        body = {
            "dmst_stex_tp": "KRX",
            "stk_cd":  code.zfill(6),
            "ord_qty": str(qty),
            "ord_uv":  "",           # 장전시간외 종가 — 단가 입력 금지 (전일 종가 자동 적용)
            "trde_tp": "61",         # 61=장전시간외 종가
            "cond_uv": "",
        }
        data = self._post("/api/dostk/ordr", body, "kt10000")
        if data and data.get("return_code") == 0:
            log.info(f"매수(장전시간외) 완료: {code} {qty}주 @전일종가 — 주문번호: {data.get('ord_no')}")
        else:
            log.error(f"매수(장전시간외) 실패: {code} {qty}주 — {data.get('return_msg') if data else '응답없음'}")
        return data

    def sell_premarket(self, code: str, qty: int, price: int) -> dict | None:
        """
        장전 시간외 단일가 매도 (kt10001, trde_tp=61)
        — NXT 갭다운 손절 전용
        """
        body = {
            "dmst_stex_tp": "KRX",
            "stk_cd":  code.zfill(6),
            "ord_qty": str(qty),
            "ord_uv":  str(price),
            "trde_tp": "61",
            "cond_uv": "",
        }
        data = self._post("/api/dostk/ordr", body, "kt10001")
        if data and data.get("return_code") == 0:
            log.info(f"매도(장전시간외) 완료: {code} {qty}주 @{price:,}원 — 주문번호: {data.get('ord_no')}")
        else:
            log.error(f"매도(장전시간외) 실패: {code} — {data.get('return_msg') if data else '응답없음'}")
        return data

    def sell_market(self, code: str, qty: int) -> dict | None:
        """시장가 매도 (kt10001, trde_tp=3)"""
        body = {
            "dmst_stex_tp": "KRX",
            "stk_cd":  code.zfill(6),
            "ord_qty": str(qty),
            "ord_uv":  "",
            "trde_tp": "3",
            "cond_uv": "",
        }
        data = self._post("/api/dostk/ordr", body, "kt10001")
        if data and data.get("return_code") == 0:
            log.info(f"매도(시장가) 완료: {code} {qty}주 — 주문번호: {data.get('ord_no')}")
        return data

    def buy_limit(self, code: str, qty: int, price: int) -> dict | None:
        """지정가 매수 (kt10000, trde_tp=0)"""
        body = {
            "dmst_stex_tp": "KRX",
            "stk_cd":  code.zfill(6),
            "ord_qty": str(qty),
            "ord_uv":  str(price),
            "trde_tp": "0",       # 0=보통(지정가)
            "cond_uv": "",
        }
        data = self._post("/api/dostk/ordr", body, "kt10000")
        if data and data.get("return_code") == 0:
            log.info(f"매수(지정가) 완료: {code} {qty}주 @{price:,}원 — 주문번호: {data.get('ord_no')}")
        return data

    def sell_limit(self, code: str, qty: int, price: int) -> dict | None:
        """지정가 매도 (kt10001, trde_tp=0)"""
        body = {
            "dmst_stex_tp": "KRX",
            "stk_cd":  code.zfill(6),
            "ord_qty": str(qty),
            "ord_uv":  str(price),
            "trde_tp": "0",
            "cond_uv": "",
        }
        data = self._post("/api/dostk/ordr", body, "kt10001")
        if data and data.get("return_code") == 0:
            log.info(f"매도(지정가) 완료: {code} {qty}주 @{price:,}원 — 주문번호: {data.get('ord_no')}")
        return data

    # ════════════════════════════════════════════════════════
    # ── 주식 취소주문 (kt10003)
    # ════════════════════════════════════════════════════════
    def cancel_order(self, orig_ord_no: str, code: str, qty: int = 0) -> dict | None:
        """
        주식 취소주문 (kt10003)
        qty=0 → '0' 입력 시 잔량 전부 취소
        """
        body = {
            "dmst_stex_tp": "KRX",
            "orig_ord_no": orig_ord_no,
            "stk_cd":      code.zfill(6),
            "cncl_qty":    "0" if qty == 0 else str(qty),
        }
        data = self._post("/api/dostk/ordr", body, "kt10003")
        if data and data.get("return_code") == 0:
            log.info(f"주문취소 완료: 원주문번호={orig_ord_no}, 취소수량={data.get('cncl_qty')}")
        return data

    # ════════════════════════════════════════════════════════
    # ── 미체결 주문 조회 (ka10075)
    # ════════════════════════════════════════════════════════
    def get_pending_orders(self) -> list:
        """
        미체결요청 (ka10075)
        반환: 미체결 주문 리스트
        """
        data = self._post("/api/dostk/acnt", {}, "ka10075")
        if not data or data.get("return_code") != 0:
            return []
        # 응답 필드는 문서 p.187 참조 — 리스트 필드명 확인 후 수정
        return data.get("ord_list", data.get("output", []))

    # ════════════════════════════════════════════════════════
    # ── 주식 일봉 차트 (ka10081)
    # ════════════════════════════════════════════════════════
    def get_stock_ohlcv(self, code: str, days: int = 120) -> "pd.DataFrame":
        """
        주식일봉차트조회 (ka10081)
        반환: DataFrame [open, high, low, close, volume] index=date(str)
        days: 최근 N일치 요청 (API는 최대 연속조회로 다량 수신 가능)
        """
        import pandas as pd
        from datetime import datetime, timedelta
        end_dt   = datetime.now()
        start_dt = end_dt - timedelta(days=days + 60)  # 영업일 여유분 포함
        body = {
            "stk_cd":    code.zfill(6),
            "base_dt":   end_dt.strftime("%Y%m%d"),
            "upd_stkpc_tp": "1",   # 수정주가 적용
        }
        data = self._post("/api/dostk/chart", body, "ka10081")
        if not data or data.get("return_code") != 0:
            log.warning(f"ka10081 조회 실패 ({code}): {data.get('return_msg') if data else 'None'}")
            return pd.DataFrame()
        rows = data.get("stk_dt_pole_chart_qry", [])
        if not rows:
            return pd.DataFrame()
        records = []
        for r in rows:
            try:
                dt   = str(r.get("dt", ""))
                # 종가 부호 처리 (등락부호 flu_smbol 없으면 cur_prc 그대로)
                close = abs(int(str(r.get("cur_prc", r.get("close_pric", 0))).replace(",", "")))
                records.append({
                    "date":   dt,
                    "open":   abs(int(str(r.get("open_pric",  0)).replace(",", ""))),
                    "high":   abs(int(str(r.get("high_pric",  0)).replace(",", ""))),
                    "low":    abs(int(str(r.get("low_pric",   0)).replace(",", ""))),
                    "close":  close,
                    "volume": abs(int(str(r.get("acml_vol",   r.get("trde_qty", 0))).replace(",", ""))),
                })
            except Exception:
                continue
        if not records:
            return pd.DataFrame()
        df = pd.DataFrame(records).set_index("date")
        df = df.sort_index()
        # 최근 days 영업일만 잘라서 반환
        return df.tail(days)

    # ════════════════════════════════════════════════════════
    # ── 업종 일봉 차트 (ka10008) — KOSPI/KOSDAQ 지수
    # ════════════════════════════════════════════════════════
    def get_index_ohlcv(self, index_code: str = "001", days: int = 120) -> "pd.DataFrame":
        """
        업종일봉차트조회 (ka10008)
        index_code: "001"=KOSPI, "101"=KOSDAQ
        반환: DataFrame [open, high, low, close, volume] index=date(str)
        """
        import pandas as pd
        from datetime import datetime
        body = {
            "upjong_cd": index_code,
            "base_dt":   datetime.now().strftime("%Y%m%d"),
        }
        data = self._post("/api/dostk/chart", body, "ka10008")
        if not data or data.get("return_code") != 0:
            log.warning(f"ka10008 조회 실패 ({index_code}): {data.get('return_msg') if data else 'None'}")
            return pd.DataFrame()
        rows = data.get("upjong_dt_pole_chart_qry", [])
        if not rows:
            return pd.DataFrame()
        records = []
        for r in rows:
            try:
                records.append({
                    "date":   str(r.get("dt", "")),
                    "open":   float(str(r.get("open_pric",  0)).replace(",", "")),
                    "high":   float(str(r.get("high_pric",  0)).replace(",", "")),
                    "low":    float(str(r.get("low_pric",   0)).replace(",", "")),
                    "close":  float(str(r.get("cur_prc",    r.get("close_pric", 0))).replace(",", "")),
                    "volume": float(str(r.get("acml_vol",   r.get("trde_qty",   0))).replace(",", "")),
                })
            except Exception:
                continue
        if not records:
            return pd.DataFrame()
        df = pd.DataFrame(records).set_index("date")
        df = df.sort_index()
        return df.tail(days)

    # ════════════════════════════════════════════════════════
    # ── 급상승 순위 조회 (ka10027) — 주식등락률순위
    # ════════════════════════════════════════════════════════
    def get_surge_ranking(self, market: str = "0", top_n: int = 50) -> list:
        """
        주식등락률순위 (ka10027)
        market: "0"=전체, "1"=KOSPI, "2"=KOSDAQ
        top_n : 반환할 최대 종목 수 (API는 보통 100건 단위 연속조회)
        반환  : [{"rank", "code", "name", "price", "change_rate", "volume", "market"}, ...]
        """
        body = {
            "mrkt_tp":    market,   # 시장구분 (0=전체)
            "sort_tp":    "1",      # 정렬기준 (1=등락률순)
            "trde_qty_tp":"0",      # 거래량구분 (0=전체)
            "stk_cnd":    "0",      # 종목조건 (0=전체)
            "upjong_cd":  "",       # 업종코드 (전체)
        }
        data = self._post("/api/dostk/rank", body, "ka10027")
        if not data or data.get("return_code") != 0:
            log.debug(f"ka10027 조회 실패: {data.get('return_msg') if data else 'None'}")
            return []

        # 응답 리스트 필드명 후보 (실제 응답 확인 후 자동 매핑)
        row_list = None
        for key in ("stk_errt_stts_qry", "stk_rank_list", "output", "list", "data"):
            candidate = data.get(key)
            if isinstance(candidate, list) and candidate:
                row_list = candidate
                break

        if not row_list:
            # 응답 최상위에 리스트가 직접 있는 경우 대응
            for v in data.values():
                if isinstance(v, list) and len(v) > 0 and isinstance(v[0], dict):
                    row_list = v
                    break

        if not row_list:
            log.debug(f"ka10027 리스트 필드 미발견. 응답 키: {list(data.keys())}")
            return []

        def _safe_float(row, *keys):
            for k in keys:
                try:
                    v = str(row.get(k, "")).replace(",", "").replace("+", "").replace("%", "")
                    f = float(v)
                    if f != 0:
                        return f
                except Exception:
                    continue
            return 0.0

        def _safe_int(row, *keys):
            for k in keys:
                try:
                    v = str(row.get(k, "")).replace(",", "")
                    return abs(int(float(v)))
                except Exception:
                    continue
            return 0

        results = []
        for i, r in enumerate(row_list[:top_n], 1):
            # 등락부호 처리 (flu_smbol: 1=상한, 2=상승, 4=하한, 5=하락)
            flu_smbol = str(r.get("flu_smbol", "2"))
            rate = _safe_float(r, "flu_rt", "chg_rt", "change_rate", "errt_rt")
            if flu_smbol in ("4", "5"):
                rate = -abs(rate)

            # 시장구분 (mrkt_tp: 1=KOSPI, 2=KOSDAQ, 기타=기타)
            mkt_code = str(r.get("mrkt_tp", r.get("mkt_tp", "")))
            mkt_name = {"1": "KOSPI", "2": "KOSDAQ"}.get(mkt_code, "")

            results.append({
                "rank":        i,
                "code":        str(r.get("stk_cd", r.get("code", ""))).zfill(6),
                "name":        r.get("stk_nm", r.get("name", "")),
                "price":       _safe_int(r, "cur_prc", "close_pric", "price"),
                "change_rate": round(rate, 2),
                "volume":      _safe_int(r, "trde_qty", "acml_vol", "volume"),
                "market":      mkt_name,
            })

        log.info(f"ka10027 급상승 Top{len(results)} 수신 완료")
        return results

    # ════════════════════════════════════════════════════════
    # ── 연결 테스트
    # ════════════════════════════════════════════════════════
    def test_connection(self) -> bool:
        """API 연결 및 토큰 발급 테스트"""
        token = self._get_token()
        if token:
            log.info(f"키움 REST API 연결 성공 ({'모의' if self.mock else '실전'})")
            return True
        log.error("키움 REST API 연결 실패 — APP_KEY/SECRET_KEY 확인 필요")
        return False
