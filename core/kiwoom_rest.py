"""
키움증권 REST API 클라이언트
api.kiwoom.com — 잔고조회 / 주문 / 실시간 시세

계좌: 6594-7112
모의투자: KIWOOM_MOCK=true  → https://mockapi.kiwoom.com
실전매매: KIWOOM_MOCK=false → https://api.kiwoom.com

※ 엔드포인트 확인 방법:
   openapi.kiwoom.com 로그인 → API 문서 → 각 TR별 URL 확인
   현재 구현은 공개된 래퍼 라이브러리 기반 추정값 — 실제 문서와 대조 필요
"""
import time
import requests
from datetime import datetime, timedelta
from utils.logger import setup_logger
from config.settings import (
    KIWOOM_APP_KEY, KIWOOM_SECRET_KEY,
    KIWOOM_ACCOUNT, KIWOOM_MOCK, LOG_DIR,
)

log = setup_logger("kiwoom_rest", LOG_DIR)

# ── API 엔드포인트 (포트 443 표준 HTTPS) ─────────────────────
BASE_REAL = "https://api.kiwoom.com"           # 실전
BASE_MOCK = "https://mockapi.kiwoom.com"       # 모의투자

HEADERS_BASE = {
    "Content-Type": "application/json; charset=utf-8",
    "Accept": "application/json",
}


class KiwoomRestAPI:
    """키움 REST API 래퍼"""

    def __init__(self):
        self.app_key    = KIWOOM_APP_KEY
        self.secret_key = KIWOOM_SECRET_KEY
        self.account    = KIWOOM_ACCOUNT.replace("-", "")  # "65947112"
        self.mock       = KIWOOM_MOCK
        self.base_url   = BASE_MOCK if KIWOOM_MOCK else BASE_REAL
        # TR_ID 접두사: 모의=V, 실전=T (일부 TR에 적용)
        self.tr_prefix  = "V" if KIWOOM_MOCK else "T"

        self._access_token = None
        self._token_expire = datetime.min

        mode = "모의투자" if self.mock else "실전매매"
        log.info(f"KiwoomRestAPI 초기화 ({mode}) 계좌: {self.account}")
        log.info(f"API 서버: {self.base_url}")

        if not self.app_key or not self.secret_key:
            log.warning("KIWOOM_APP_KEY / KIWOOM_SECRET_KEY 미설정 — .env 확인 필요")

    # ── 토큰 발급 ──────────────────────────────────────────
    def _get_token(self) -> str | None:
        """OAuth2 Access Token 발급 (만료 전 자동 갱신)"""
        if self._access_token and datetime.now() < self._token_expire:
            return self._access_token

        url = f"{self.base_url}/oauth2/token"
        body = {
            "grant_type": "client_credentials",
            "appkey": self.app_key,
            "secretkey": self.secret_key,
        }
        try:
            resp = requests.post(url, json=body, headers=HEADERS_BASE, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            self._access_token = data.get("token") or data.get("access_token")
            expires_in = int(data.get("expires_in", 86400))
            self._token_expire = datetime.now() + timedelta(seconds=expires_in - 60)
            log.info(f"키움 토큰 발급 완료 (만료: {self._token_expire.strftime('%H:%M')})")
            return self._access_token
        except Exception as e:
            log.error(f"키움 토큰 발급 실패: {e}")
            return None

    def _headers(self, tr_id: str = "", tr_cont: str = "") -> dict:
        token = self._get_token()
        h = {
            **HEADERS_BASE,
            "authorization": f"Bearer {token}",
            "appkey": self.app_key,
            "secretkey": self.secret_key,
        }
        if tr_id:   h["tr_id"] = tr_id
        if tr_cont: h["tr_cont"] = tr_cont
        return h

    def _get(self, path: str, params: dict, tr_id: str) -> dict | None:
        url = f"{self.base_url}{path}"
        try:
            resp = requests.get(url, params=params, headers=self._headers(tr_id), timeout=15)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            log.error(f"GET {path} 실패: {e}")
            return None

    def _post(self, path: str, body: dict, tr_id: str) -> dict | None:
        url = f"{self.base_url}{path}"
        try:
            resp = requests.post(url, json=body, headers=self._headers(tr_id), timeout=15)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            log.error(f"POST {path} 실패: {e}")
            return None

    # ── 잔고 조회 ──────────────────────────────────────────
    def get_balance(self) -> dict:
        """
        주식잔고조회
        반환: {cash, holdings: [{code, name, qty, avg_price, current_price, pnl_pct}], total_value}
        """
        # 모의: VTTHSTOCK / 실전: TTTC8434R (잔고조회)
        tr_id = "VTTHSTOCK" if self.mock else "TTTC8434R"
        params = {
            "CANO": self.account[:8],
            "ACNT_PRDT_CD": "01",
            "AFHR_FLPR_YN": "N",
            "OFL_YN": "N",
            "INQR_DVSN": "01",
            "UNPR_DVSN": "01",
            "FUND_STTL_ICLD_YN": "N",
            "FNCG_AMT_AUTO_RDPT_YN": "N",
            "PRCS_DVSN": "00",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": "",
        }
        data = self._get("/uapi/domestic-stock/v1/trading/inquire-balance", params, tr_id)
        if not data:
            return self._empty_balance()

        try:
            output1 = data.get("output1", [])  # 보유 종목
            output2 = data.get("output2", [{}])[0]  # 계좌 요약

            holdings = []
            for item in output1:
                qty = int(item.get("hldg_qty", 0))
                if qty == 0:
                    continue
                avg   = float(item.get("pchs_avg_pric", 0))
                cur   = float(item.get("prpr", 0))
                pnl   = ((cur - avg) / avg * 100) if avg > 0 else 0
                holdings.append({
                    "code":          item.get("pdno", ""),
                    "name":          item.get("prdt_name", ""),
                    "qty":           qty,
                    "avg_price":     avg,
                    "current_price": cur,
                    "pnl_pct":       round(pnl, 2),
                    "eval_amount":   round(cur * qty),
                })

            cash        = float(output2.get("dnca_tot_amt", 0))
            total_eval  = float(output2.get("tot_evlu_amt", 0))
            total_pnl   = float(output2.get("evlu_pfls_smtl_amt", 0))

            return {
                "cash":        cash,
                "total_value": total_eval,
                "total_pnl":   total_pnl,
                "total_pnl_pct": round(total_pnl / (total_eval - total_pnl) * 100, 2) if total_eval > total_pnl else 0,
                "num_holdings": len(holdings),
                "holdings":    holdings,
                "updated_at":  datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        except Exception as e:
            log.error(f"잔고 파싱 오류: {e}")
            return self._empty_balance()

    def _empty_balance(self) -> dict:
        return {
            "cash": 0, "total_value": 0, "total_pnl": 0,
            "total_pnl_pct": 0, "num_holdings": 0, "holdings": [],
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "error": "API 조회 실패",
        }

    # ── 현재가 조회 ──────────────────────────────────────────
    def get_current_price(self, code: str) -> dict | None:
        """
        주식 현재가 조회
        반환: {code, name, price, change_pct, volume, high, low}
        """
        tr_id = "FHKST01010100"
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": code.zfill(6),
        }
        data = self._get("/uapi/domestic-stock/v1/quotations/inquire-price", params, tr_id)
        if not data:
            return None
        try:
            o = data.get("output", {})
            return {
                "code":       code,
                "name":       o.get("hts_kor_isnm", ""),
                "price":      int(o.get("stck_prpr", 0)),
                "change_pct": float(o.get("prdy_ctrt", 0)),
                "volume":     int(o.get("acml_vol", 0)),
                "high":       int(o.get("stck_hgpr", 0)),
                "low":        int(o.get("stck_lwpr", 0)),
                "open":       int(o.get("stck_oprc", 0)),
            }
        except Exception as e:
            log.error(f"현재가 파싱 오류 ({code}): {e}")
            return None

    # ── 주문 ──────────────────────────────────────────────
    def buy_market(self, code: str, qty: int) -> dict | None:
        """시장가 매수"""
        # 모의: VTTC0802U / 실전: TTTC0802U
        tr_id = f"{TR_PREFIX}TTC0802U"
        body = {
            "CANO":          self.account[:8],
            "ACNT_PRDT_CD":  "01",
            "PDNO":          code.zfill(6),
            "ORD_DVSN":      "01",   # 시장가
            "ORD_QTY":       str(qty),
            "ORD_UNPR":      "0",    # 시장가이므로 0
        }
        result = self._post("/uapi/domestic-stock/v1/trading/order-cash", body, tr_id)
        if result:
            log.info(f"매수 주문 완료: {code} {qty}주 (시장가) — {result.get('msg1', '')}")
        return result

    def sell_market(self, code: str, qty: int) -> dict | None:
        """시장가 매도"""
        # 모의: VTTC0801U / 실전: TTTC0801U
        tr_id = f"{TR_PREFIX}TTC0801U"
        body = {
            "CANO":          self.account[:8],
            "ACNT_PRDT_CD":  "01",
            "PDNO":          code.zfill(6),
            "ORD_DVSN":      "01",   # 시장가
            "ORD_QTY":       str(qty),
            "ORD_UNPR":      "0",
        }
        result = self._post("/uapi/domestic-stock/v1/trading/order-cash", body, tr_id)
        if result:
            log.info(f"매도 주문 완료: {code} {qty}주 (시장가) — {result.get('msg1', '')}")
        return result

    def buy_limit(self, code: str, qty: int, price: int) -> dict | None:
        """지정가 매수"""
        tr_id = f"{TR_PREFIX}TTC0802U"
        body = {
            "CANO":          self.account[:8],
            "ACNT_PRDT_CD":  "01",
            "PDNO":          code.zfill(6),
            "ORD_DVSN":      "00",   # 지정가
            "ORD_QTY":       str(qty),
            "ORD_UNPR":      str(price),
        }
        result = self._post("/uapi/domestic-stock/v1/trading/order-cash", body, tr_id)
        if result:
            log.info(f"지정가 매수 주문: {code} {qty}주 @{price:,}원 — {result.get('msg1', '')}")
        return result

    # ── 미체결 주문 조회 ──────────────────────────────────────
    def get_pending_orders(self) -> list:
        """미체결 주문 조회"""
        tr_id = "VTTT3016R" if self.mock else "TTTC8036R"
        params = {
            "CANO":         self.account[:8],
            "ACNT_PRDT_CD": "01",
            "INQR_DVSN_1":  "",
            "INQR_DVSN_2":  "0",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": "",
        }
        data = self._get("/uapi/domestic-stock/v1/trading/inquire-psbl-rvsecncl", params, tr_id)
        if not data:
            return []
        return data.get("output", [])

    # ── 주문 취소 ──────────────────────────────────────────
    def cancel_order(self, order_no: str, code: str, qty: int) -> dict | None:
        """주문 취소"""
        tr_id = f"{TR_PREFIX}TTC0803U"
        body = {
            "CANO":          self.account[:8],
            "ACNT_PRDT_CD":  "01",
            "KRX_FWDG_ORD_ORGNO": "",
            "ORGN_ODNO":     order_no,
            "ORD_DVSN":      "00",
            "RVSE_CNCL_DVSN_CD": "02",  # 취소
            "ORD_QTY":       str(qty),
            "ORD_UNPR":      "0",
            "QTY_ALL_ORD_YN": "Y",
            "PDNO":          code.zfill(6),
        }
        return self._post("/uapi/domestic-stock/v1/trading/order-rvsecncl", body, tr_id)

    # ── 연결 테스트 ──────────────────────────────────────────
    def test_connection(self) -> bool:
        """API 연결 및 토큰 테스트"""
        token = self._get_token()
        if token:
            log.info("키움 REST API 연결 테스트 성공")
            return True
        log.error("키움 REST API 연결 테스트 실패")
        return False
