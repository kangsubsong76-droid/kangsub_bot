"""DART 공시 수집 클라이언트"""
import requests
from datetime import datetime, timedelta
from dataclasses import dataclass
from config.settings import DART_API_KEY
from utils.logger import setup_logger

log = setup_logger("dart_client")

DART_BASE = "https://opendart.fss.or.kr/api"


@dataclass
class DartDisclosure:
    corp_name: str
    corp_code: str
    report_nm: str        # 공시 제목
    rcept_no: str         # 접수번호
    rcept_dt: str         # 접수일자
    flr_nm: str           # 공시 제출인
    rm: str               # 비고 (유/코/코넥 등)
    url: str              # 공시 원문 URL


class DartClient:
    def __init__(self, api_key: str = None):
        self.api_key = api_key or DART_API_KEY
        self.session = requests.Session()

    def get_corp_code(self, stock_code: str) -> str:
        """주식 종목코드 → DART 고유번호 변환 (corpCode.xml 필요)"""
        # NOTE: 최초 1회 corpCode.xml 다운로드 후 매핑 테이블 구축 필요
        # 여기서는 사전 매핑 사용
        return self._corp_code_map.get(stock_code, "")

    def search_disclosures(
        self,
        corp_code: str = None,
        bgn_de: str = None,
        end_de: str = None,
        page_count: int = 20,
    ) -> list[DartDisclosure]:
        """공시 검색"""
        if bgn_de is None:
            bgn_de = (datetime.now() - timedelta(days=7)).strftime("%Y%m%d")
        if end_de is None:
            end_de = datetime.now().strftime("%Y%m%d")

        params = {
            "crtfc_key": self.api_key,
            "bgn_de": bgn_de,
            "end_de": end_de,
            "page_count": page_count,
            "sort": "date",
            "sort_mth": "desc",
        }
        if corp_code:
            params["corp_code"] = corp_code

        try:
            resp = self.session.get(f"{DART_BASE}/list.json", params=params, timeout=10)
            data = resp.json()
            if data.get("status") != "000":
                log.warning(f"DART API 오류: {data.get('message')}")
                return []

            results = []
            for item in data.get("list", []):
                results.append(DartDisclosure(
                    corp_name=item.get("corp_name", ""),
                    corp_code=item.get("corp_code", ""),
                    report_nm=item.get("report_nm", ""),
                    rcept_no=item.get("rcept_no", ""),
                    rcept_dt=item.get("rcept_dt", ""),
                    flr_nm=item.get("flr_nm", ""),
                    rm=item.get("rm", ""),
                    url=f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={item.get('rcept_no', '')}",
                ))
            log.info(f"DART 공시 {len(results)}건 조회 ({bgn_de}~{end_de})")
            return results
        except Exception as e:
            log.error(f"DART 검색 실패: {e}")
            return []

    def get_financial_statements(self, corp_code: str, bsns_year: str, reprt_code: str = "11011"):
        """재무제표 조회 (reprt_code: 11011=사업보고서, 11012=반기, 11013=1분기, 11014=3분기)"""
        params = {
            "crtfc_key": self.api_key,
            "corp_code": corp_code,
            "bsns_year": bsns_year,
            "reprt_code": reprt_code,
            "fs_div": "CFS",  # CFS=연결, OFS=개별
        }
        try:
            resp = self.session.get(f"{DART_BASE}/fnlttSinglAcntAll.json", params=params, timeout=10)
            data = resp.json()
            if data.get("status") != "000":
                return None
            return data.get("list", [])
        except Exception as e:
            log.error(f"재무제표 조회 실패: {e}")
            return None

    def check_negative_disclosures(self, corp_code: str, days: int = 7) -> list[DartDisclosure]:
        """부정적 공시 체크 (횡령, 소송, 감자, 상장폐지 등)"""
        negative_keywords = [
            "횡령", "배임", "소송", "감자", "상장폐지", "관리종목",
            "투자주의", "불성실공시", "조회공시", "풍문", "정정",
            "영업정지", "부도", "회생", "파산",
        ]
        disclosures = self.search_disclosures(
            corp_code=corp_code,
            bgn_de=(datetime.now() - timedelta(days=days)).strftime("%Y%m%d"),
        )
        negatives = []
        for d in disclosures:
            if any(kw in d.report_nm for kw in negative_keywords):
                negatives.append(d)
                log.warning(f"[부정공시] {d.corp_name}: {d.report_nm}")
        return negatives

    # 종목코드 → DART 고유번호 매핑 (유니버스 종목)
    _corp_code_map = {
        "000660": "00126380",  # SK하이닉스
        "042700": "00550756",  # 한미반도체
        "357780": "01187498",  # 솔브레인
        "012450": "00120030",  # 한화에어로스페이스
        "064350": "00164653",  # 현대로템
        "103140": "00111722",  # 풍산
        "267260": "01312539",  # HD현대일렉트릭
        "112610": "00618857",  # 씨에스윈드
        "103590": "00111888",  # 일진전기
        "090430": "00113921",  # 아모레퍼시픽
        "259960": "01216791",  # 크래프톤
        "051900": "00104856",  # LG생활건강
        "105560": "00105017",  # KB금융
        "055550": "00382199",  # 신한지주
        "086790": "00547583",  # 하나금융지주
        "316140": "01126974",  # 우리금융지주
        "005830": "00126186",  # DB손해보험
        "024110": "00131054",  # 기업은행
        "088980": "00549164",  # 맥쿼리인프라
        "000810": "00126217",  # 삼성화재
    }
