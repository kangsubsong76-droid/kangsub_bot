"""뉴스 크롤링 + NLP 감성분석 + 매매 시그널 생성
개선 v3:
 - 소스: 네이버 금융 + 한국경제 + 연합뉴스(정책) + 정책브리핑
 - 정부/대통령 발언 · 국무회의(화요일 집중) · 대변인 브리핑 수집
 - 정책 뉴스는 시그널 가중치 2배
 - 본문 크롤링 추가 (상위 N건)
 - 섹터 관련성 없는 뉴스 필터링
 - URL 기반 중복 제거
 - 부정어 문맥 처리 추가 ("손실 없이" → 긍정)
"""
import re
import time
import requests
from datetime import datetime
from dataclasses import dataclass, field
from bs4 import BeautifulSoup
from config.settings import NEWS_SOURCES
from config.universe import SECTORS, DIVIDEND_TOP12
from utils.logger import setup_logger

log = setup_logger("news_analyzer")

# ── 섹터-키워드 매핑 ──────────────────────────────────────────────
SECTOR_KEYWORDS = {
    "AI_반도체": [
        "AI", "인공지능", "반도체", "HBM", "엔비디아", "SK하이닉스", "한미반도체",
        "솔브레인", "DB하이텍", "소부장", "메모리", "파운드리", "TSMC", "GPU", "NPU",
    ],
    "K_방산": [
        "방산", "방위산업", "한화에어로", "현대로템", "풍산", "K2전차", "탄약",
        "수출", "UAE", "폴란드", "루마니아", "방위", "무기", "전투기",
    ],
    "원전_SMR": [
        "원전", "SMR", "소형모듈원자로", "한전기술", "두산에너빌리티", "비에이치아이",
        "한전KPS", "원자력", "핵발전", "체코", "원전수출",
    ],
    "전력_인프라": [
        "전력", "변압기", "송전", "배전", "전선", "HD현대일렉", "LS ELECTRIC",
        "제룡전기", "일진전기", "인프라", "데이터센터", "전력망",
    ],
    "피지컬AI_로봇": [
        "로봇", "협동로봇", "휴머노이드", "두산로보틱스", "레인보우로보틱스",
        "에스피지", "스마트팩토리", "피지컬AI", "자동화",
    ],
    "바이오헬스": [
        "바이오", "제약", "삼성바이오", "셀트리온", "종근당", "유한양행",
        "임상", "FDA", "신약", "헬스케어", "의료",
    ],
    "밸류업_금융": [
        "밸류업", "배당", "금융", "은행", "KB금융", "신한지주", "하나금융",
        "우리금융", "주주환원", "PBR", "코리아디스카운트", "기업은행",
    ],
    "외교_한중": [
        "한중", "한한령", "중국", "아모레퍼시픽", "LG생활건강", "크래프톤",
        "방중", "면세", "K뷰티", "문화콘텐츠", "한국콜마",
    ],
    "건설_SOC": [
        "건설", "현대건설", "DL이앤씨", "대우건설", "계룡건설", "SOC",
        "공공주택", "재건축", "리모델링", "인프라투자",
    ],
    "2차전지": [
        "2차전지", "배터리", "LG에너지솔루션", "포스코퓨처엠", "SK이노베이션",
        "LG화학", "전기차", "ESS", "양극재", "음극재",
    ],
}

# ── 정책 뉴스 전용 섹터 키워드 (일반 뉴스보다 광범위한 정책 표현) ──
# 대통령 발언, 국무회의, 브리핑에서 자주 쓰는 표현 포함
POLICY_SECTOR_KEYWORDS = {
    "AI_반도체": [
        "AI 국가전략", "반도체 지원", "AI 예산", "AI 산업 육성", "반도체 클러스터",
        "반도체 패키지", "AI 컴퓨팅", "GPU 센터", "국가 AI", "디지털 전환",
    ],
    "K_방산": [
        "방산 수출", "국방 예산", "방위산업 육성", "방산 지원", "군비",
        "방산 협력", "국방력 강화", "무기 수출", "방위 산업", "방산 투자",
    ],
    "원전_SMR": [
        "원전 확대", "원자력 정책", "SMR 개발", "원전 수출 지원", "에너지 전환",
        "탈탄소", "청정 에너지", "원자력 협력", "무탄소 전원", "전력 공급",
    ],
    "전력_인프라": [
        "전력망 투자", "송배전 현대화", "전력 인프라", "데이터센터 전력",
        "전기요금", "전력 공급 확대", "에너지 인프라",
    ],
    "피지컬AI_로봇": [
        "로봇 산업 육성", "스마트 제조", "제조 혁신", "자동화 지원",
        "로봇 R&D", "첨단 제조", "인공지능 로봇",
    ],
    "바이오헬스": [
        "바이오 육성", "제약 산업", "의약품 지원", "헬스케어 투자",
        "신약 개발 지원", "바이오 클러스터", "의료 혁신",
    ],
    "밸류업_금융": [
        "밸류업 프로그램", "주주환원 정책", "코리아 디스카운트", "자본시장 개혁",
        "금융 규제", "PBR 개선", "배당 확대 정책", "금융투자소득세",
    ],
    "외교_한중": [
        "한중 관계", "한중 정상", "대중 외교", "한한령 해제", "중국 방문",
        "한중 협력", "중국 시장", "K콘텐츠 지원",
    ],
    "건설_SOC": [
        "공공주택 공급", "SOC 투자", "인프라 예산", "건설 경기 부양",
        "주택 공급 확대", "재건축 규제", "도시 재생", "교통 인프라",
    ],
    "2차전지": [
        "배터리 산업", "전기차 지원", "이차전지 육성", "배터리 투자",
        "친환경 모빌리티", "전기차 보조금", "배터리 R&D",
    ],
}

# ── 정책 긍정/부정 키워드 (시장 기사와 다른 표현 추가) ──
POLICY_POSITIVE = [
    "지원", "육성", "투자", "확대", "추진", "강화", "개혁", "협력",
    "선정", "승인", "통과", "합의", "체결", "증액", "신설",
]
POLICY_NEGATIVE = [
    "규제", "제한", "축소", "철회", "반대", "갈등", "마찰", "제재",
    "감액", "폐지", "불허", "금지", "논란", "충돌",
]

# ── 실적발표 관련 키워드 ────────────────────────────────────────────
EARNINGS_KEYWORDS = [
    "영업이익", "순이익", "매출", "실적", "어닝", "분기", "잠정실적",
    "컨센서스", "영업손실", "어닝쇼크", "어닝서프라이즈", "전년比",
    "전분기比", "가이던스", "실적발표", "잠정", "IR", "NDR",
]

# ── 감성 키워드 ───────────────────────────────────────────────────
POSITIVE_WORDS = [
    "상승", "급등", "호재", "수출", "계약", "수주", "흑자", "사상최대",
    "목표가상향", "매수", "실적개선", "성장", "기대", "호황", "확대",
    "승인", "체결", "선정", "신고가", "돌파", "강세", "턴어라운드",
    "어닝서프라이즈", "수익", "흑자전환", "회복", "개선",
]
NEGATIVE_WORDS = [
    "하락", "급락", "악재", "손실", "적자", "취소", "철회", "제재",
    "리스크", "우려", "경고", "위기", "감소", "하향", "소송", "규제",
    "불확실", "부진", "둔화", "침체", "충격", "경고", "타격", "약세",
    "실망", "적자전환", "주의", "경계",
]
# 이 패턴 뒤에 긍정/부정 키워드가 오면 반전
NEGATION_PATTERNS = ["없이", "않", "아니", "불식", "극복", "해소", "탈피"]


@dataclass
class NewsItem:
    title: str
    url: str
    source: str
    published: str
    content: str = ""
    sectors: list = field(default_factory=list)
    sentiment: float = 0.0        # -1.0 ~ +1.0
    summary: str = ""
    is_policy: bool = False       # 정부/대통령 발언 여부 → 가중치 2배
    is_earnings: bool = False     # 실적발표 여부 → 가중치 1.5배
    weight: float = 1.0           # 최종 가중치


class NewsAnalyzer:
    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    }
    CONTENT_FETCH_LIMIT = 10  # 본문을 실제로 가져올 기사 수

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)

    # ── 1. 크롤링 ─────────────────────────────────────────────────

    def fetch_naver_market_news(self, limit: int = 30) -> list[NewsItem]:
        """네이버 금융 시장 전체 뉴스 — 주식 관련성 가장 높음"""
        items = []
        # 네이버 금융 홈 헤드라인
        urls_to_try = [
            "https://finance.naver.com/news/mainnews.naver",
            "https://finance.naver.com/news/news_list.naver?mode=LSS2D&section_id=101&section_id2=258",
        ]
        for url in urls_to_try:
            try:
                resp = self.session.get(url, timeout=10)
                soup = BeautifulSoup(resp.text, "html.parser")
                # 메인뉴스 리스트
                for a in soup.select("ul.newsList li dt a, .articleSubject a, dl dt a"):
                    title = a.get_text(strip=True)
                    href = a.get("href", "")
                    if not title or len(title) < 8:
                        continue
                    full_url = href if href.startswith("http") else f"https://finance.naver.com{href}"
                    items.append(NewsItem(
                        title=title, url=full_url,
                        source="네이버금융",
                        published=datetime.now().strftime("%Y-%m-%d"),
                    ))
                if items:
                    break
            except Exception as e:
                log.debug(f"네이버 시장뉴스 ({url}) 실패: {e}")
        return items[:limit]

    def fetch_naver_stock_news(self, code: str, name: str = "", limit: int = 5) -> list[NewsItem]:
        """네이버 금융 종목별 뉴스"""
        items = []
        try:
            url = f"https://finance.naver.com/item/news_news.naver?code={code}"
            resp = self.session.get(url, timeout=10)
            soup = BeautifulSoup(resp.text, "html.parser")
            for row in soup.select("table.type5 tr")[:limit]:
                a = row.select_one("td.title a")
                date_td = row.select_one("td.date")
                if a:
                    title = a.get_text(strip=True)
                    href = a.get("href", "")
                    full_url = f"https://finance.naver.com{href}" if href.startswith("/") else href
                    items.append(NewsItem(
                        title=title, url=full_url,
                        source=f"네이버금융({name or code})",
                        published=date_td.get_text(strip=True) if date_td else "",
                    ))
        except Exception as e:
            log.debug(f"네이버 종목뉴스 실패 ({code}): {e}")
        return items

    def fetch_naver_article_content(self, url: str) -> str:
        """네이버 뉴스 본문 크롤링"""
        try:
            # 네이버 금융 기사는 read.naver.com 으로 리다이렉트됨
            resp = self.session.get(url, timeout=8, allow_redirects=True)
            soup = BeautifulSoup(resp.text, "html.parser")
            # 본문 선택자 우선순위
            for selector in [
                "#newsct_article", "#articeBody", "#articleBody",
                ".newsct_article", "article", "#content",
            ]:
                el = soup.select_one(selector)
                if el:
                    text = el.get_text(separator=" ", strip=True)
                    return text[:1000]  # 최대 1000자
        except Exception as e:
            log.debug(f"본문 크롤링 실패 ({url}): {e}")
        return ""

    def fetch_yonhap_policy_news(self, limit: int = 15) -> list[NewsItem]:
        """
        연합뉴스 — 대통령 발언 · 국무회의 · 정부 브리핑 수집
        화요일(국무회의 당일)은 limit 2배
        """
        is_tuesday = datetime.now().weekday() == 1
        if is_tuesday:
            limit = limit * 2
            log.info("화요일 국무회의 — 정책 뉴스 수집량 2배 적용")

        items = []
        # 검색 쿼리: 정책 핵심 키워드
        queries = [
            "국무회의",
            "이재명 대통령 발언",
            "정부 대변인 브리핑",
            "대수보 대통령",          # 대통령비서실 수석·보좌관 회의
        ]
        seen = set()
        for query in queries:
            try:
                # 연합뉴스 검색 (최신순)
                url = (
                    f"https://www.yna.co.kr/search/index"
                    f"?query={requests.utils.quote(query)}&sort=latest"
                )
                resp = self.session.get(url, timeout=10)
                soup = BeautifulSoup(resp.text, "html.parser")
                for a in soup.select(".sch-news-title a, .news-title a, li.item h3 a")[:limit]:
                    title = a.get_text(strip=True)
                    href = a.get("href", "")
                    if not title or len(title) < 8:
                        continue
                    full_url = href if href.startswith("http") else f"https://www.yna.co.kr{href}"
                    if full_url in seen:
                        continue
                    seen.add(full_url)
                    items.append(NewsItem(
                        title=title, url=full_url,
                        source=f"연합뉴스(정책)",
                        published=datetime.now().strftime("%Y-%m-%d"),
                        is_policy=True,
                        weight=2.0,
                    ))
                time.sleep(0.3)
            except Exception as e:
                log.debug(f"연합뉴스 정책검색 실패 ({query}): {e}")

        log.info(f"정책 뉴스 수집: {len(items)}건 (화요일={is_tuesday})")
        return items[:limit * len(queries)]

    def fetch_korea_kr_briefing(self, limit: int = 10) -> list[NewsItem]:
        """
        정책브리핑(korea.kr) — 공식 정부 보도자료 · 브리핑
        """
        items = []
        urls_to_try = [
            "https://www.korea.kr/briefing/pressReleaseView.do",   # 보도자료
            "https://www.korea.kr/news/policyBriefingView.do",     # 정책브리핑
        ]
        for url in urls_to_try:
            try:
                resp = self.session.get(url, timeout=10)
                soup = BeautifulSoup(resp.text, "html.parser")
                for a in soup.select(".list_area li a, .news_list li a, dl dt a")[:limit]:
                    title = a.get_text(strip=True)
                    href = a.get("href", "")
                    if not title or len(title) < 8:
                        continue
                    full_url = href if href.startswith("http") else f"https://www.korea.kr{href}"
                    items.append(NewsItem(
                        title=title, url=full_url,
                        source="정책브리핑",
                        published=datetime.now().strftime("%Y-%m-%d"),
                        is_policy=True,
                        weight=2.0,
                    ))
            except Exception as e:
                log.debug(f"정책브리핑 크롤링 실패 ({url}): {e}")
        return items[:limit]

    def fetch_earnings_news(self, limit: int = 20) -> list[NewsItem]:
        """
        주요 기업 실적발표 뉴스 — 네이버 금융 실적 섹션 + 연합뉴스 검색
        유니버스 종목 + 시가총액 상위 실적 모두 수집
        """
        items = []
        # 1) 네이버 금융 실적 뉴스 검색
        try:
            url = (
                "https://finance.naver.com/news/news_list.naver"
                "?mode=LSS2D&section_id=101&section_id2=258"
            )
            resp = self.session.get(url, timeout=10)
            soup = BeautifulSoup(resp.text, "html.parser")
            for a in soup.select("dl dt a, .articleSubject a")[:limit]:
                title = a.get_text(strip=True)
                href = a.get("href", "")
                # 실적 관련 키워드가 제목에 있는 것만
                if not any(kw in title for kw in EARNINGS_KEYWORDS):
                    continue
                full_url = href if href.startswith("http") else f"https://finance.naver.com{href}"
                items.append(NewsItem(
                    title=title, url=full_url,
                    source="네이버금융(실적)",
                    published=datetime.now().strftime("%Y-%m-%d"),
                    is_earnings=True,
                    weight=1.5,
                ))
        except Exception as e:
            log.debug(f"네이버 실적뉴스 실패: {e}")

        # 2) 연합뉴스 실적발표 검색
        for query in ["분기 실적", "잠정실적", "영업이익 발표"]:
            try:
                url = (
                    f"https://www.yna.co.kr/search/index"
                    f"?query={requests.utils.quote(query)}&sort=latest"
                )
                resp = self.session.get(url, timeout=10)
                soup = BeautifulSoup(resp.text, "html.parser")
                for a in soup.select(".sch-news-title a, .news-title a")[:5]:
                    title = a.get_text(strip=True)
                    href = a.get("href", "")
                    if not title or len(title) < 8:
                        continue
                    full_url = href if href.startswith("http") else f"https://www.yna.co.kr{href}"
                    items.append(NewsItem(
                        title=title, url=full_url,
                        source="연합뉴스(실적)",
                        published=datetime.now().strftime("%Y-%m-%d"),
                        is_earnings=True,
                        weight=1.5,
                    ))
                time.sleep(0.2)
            except Exception as e:
                log.debug(f"연합뉴스 실적검색 실패 ({query}): {e}")

        log.info(f"실적발표 뉴스 수집: {len(items)}건")
        return items

    def fetch_hankook_economy(self, limit: int = 15) -> list[NewsItem]:
        """한국경제 증권 뉴스 — 주식 전문 미디어"""
        items = []
        try:
            url = "https://www.hankyung.com/economy"
            resp = self.session.get(url, timeout=10)
            soup = BeautifulSoup(resp.text, "html.parser")
            for a in soup.select("h3.news-tit a, .article-list li a")[:limit]:
                title = a.get_text(strip=True)
                href = a.get("href", "")
                if not title or len(title) < 8:
                    continue
                full_url = href if href.startswith("http") else f"https://www.hankyung.com{href}"
                items.append(NewsItem(
                    title=title, url=full_url,
                    source="한국경제",
                    published=datetime.now().strftime("%Y-%m-%d"),
                ))
        except Exception as e:
            log.debug(f"한국경제 크롤링 실패: {e}")
        return items

    def collect_all_news(self, stock_codes: list[str] = None) -> list[NewsItem]:
        """전체 뉴스 수집 — 유니버스 전 종목 + 정책/실적 포함"""
        all_news: list[NewsItem] = []
        seen_urls: set[str] = set()

        # 1) 네이버 금융 시장 전체 뉴스 (주식 관련성 최고)
        all_news.extend(self.fetch_naver_market_news(limit=30))

        # 2) 한국경제 경제 뉴스
        all_news.extend(self.fetch_hankook_economy(limit=15))

        # 3) 정부 정책 뉴스 — 대통령 발언, 국무회의(화요일 집중), 대변인 브리핑
        all_news.extend(self.fetch_yonhap_policy_news(limit=15))
        all_news.extend(self.fetch_korea_kr_briefing(limit=10))

        # 4) 주요 기업 실적발표 뉴스
        all_news.extend(self.fetch_earnings_news(limit=20))

        # 5) 유니버스 종목별 직접 뉴스 (섹터당 주도주 2개씩)
        target_codes = list(stock_codes) if stock_codes else []
        if not target_codes:
            for sector in SECTORS.values():
                leaders = [c for c, info in sector["stocks"].items() if info.get("type") == "주도주"]
                target_codes.extend(leaders[:2])

        from config.universe import get_stock_name
        for code in target_codes[:15]:  # 최대 15종목
            name = get_stock_name(code)
            all_news.extend(self.fetch_naver_stock_news(code, name, limit=3))
            time.sleep(0.2)

        # 6) URL 기반 중복 제거
        deduped = []
        for item in all_news:
            key = item.url.split("?")[0].rstrip("/")
            if key not in seen_urls and item.title:
                seen_urls.add(key)
                deduped.append(item)

        policy_cnt = sum(1 for n in deduped if n.is_policy)
        earnings_cnt = sum(1 for n in deduped if n.is_earnings)
        log.info(
            f"뉴스 수집 완료: 총 {len(all_news)}건 → 중복제거 {len(deduped)}건 "
            f"(정책 {policy_cnt}건 / 실적 {earnings_cnt}건)"
        )
        return deduped

    # ── 2. 본문 보강 ──────────────────────────────────────────────

    def enrich_content(self, items: list[NewsItem], limit: int = None) -> list[NewsItem]:
        """상위 N건의 본문을 실제로 크롤링"""
        limit = limit or self.CONTENT_FETCH_LIMIT
        for i, item in enumerate(items[:limit]):
            if not item.content and "naver" in item.url.lower():
                item.content = self.fetch_naver_article_content(item.url)
                time.sleep(0.15)
        return items

    # ── 3. 감성분석 ───────────────────────────────────────────────

    def analyze_sentiment(self, text: str) -> float:
        """
        키워드 기반 감성점수 (-1.0 ~ +1.0)
        부정어 문맥 처리: "손실 없이" → 긍정, "성장 우려" → 부정
        """
        score = 0.0
        words = list(text)
        text_len = len(text)

        def has_negation_before(pos: int, window: int = 8) -> bool:
            """키워드 앞 window글자 내에 부정어 패턴이 있는지"""
            snippet = text[max(0, pos - window): pos]
            return any(neg in snippet for neg in NEGATION_PATTERNS)

        for word in POSITIVE_WORDS:
            idx = 0
            while True:
                pos = text.find(word, idx)
                if pos == -1:
                    break
                if has_negation_before(pos):
                    score -= 0.5  # 부정어+긍정 → 약한 부정
                else:
                    score += 1.0
                idx = pos + 1

        for word in NEGATIVE_WORDS:
            idx = 0
            while True:
                pos = text.find(word, idx)
                if pos == -1:
                    break
                if has_negation_before(pos):
                    score += 0.5  # 부정어+부정 → 약한 긍정 (불식, 우려 없어)
                else:
                    score -= 1.0
                idx = pos + 1

        if score == 0:
            return 0.0
        # -5~+5 범위를 -1~+1 로 클램핑 정규화
        return round(max(-1.0, min(1.0, score / 5.0)), 3)

    def detect_sectors(self, text: str, is_policy: bool = False) -> list[str]:
        """
        뉴스에서 관련 섹터 감지
        정책 뉴스는 POLICY_SECTOR_KEYWORDS도 추가 적용
        """
        found = set()
        for sector, keywords in SECTOR_KEYWORDS.items():
            if any(kw in text for kw in keywords):
                found.add(sector)
        if is_policy:
            for sector, keywords in POLICY_SECTOR_KEYWORDS.items():
                if any(kw in text for kw in keywords):
                    found.add(sector)
        return list(found)

    def _has_earnings_keyword(self, text: str) -> bool:
        return any(kw in text for kw in EARNINGS_KEYWORDS)

    def summarize(self, title: str, content: str = "") -> str:
        """간단 요약 (제목 + 핵심 문장 최대 2개)"""
        if not content:
            return title
        # 문장 분리 후 20자 이상인 문장만
        sentences = re.split(r"[.。!?\n]", content)
        key = [s.strip() for s in sentences if len(s.strip()) > 20][:2]
        return title + (" | " + " ".join(key) if key else "")

    def process_news(self, items: list[NewsItem], filter_irrelevant: bool = True) -> list[NewsItem]:
        """
        수집된 뉴스 분석 처리
        - filter_irrelevant=True: 섹터 키워드 없는 기사 제외
          (단, 실적발표 키워드가 있으면 섹터 미매칭이어도 보존)
        - 가중치 최종 확정: is_policy=2.0 / is_earnings=1.5 / 일반=1.0
        """
        results = []
        for item in items:
            combined = item.title + " " + item.content
            item.sectors = self.detect_sectors(combined, is_policy=item.is_policy)
            item.sentiment = self.analyze_sentiment(combined)
            item.summary = self.summarize(item.title, item.content)

            # 실적 키워드 자동 감지 (소스 외에도 제목에서 판별)
            if not item.is_earnings and self._has_earnings_keyword(item.title):
                item.is_earnings = True
                item.weight = max(item.weight, 1.5)

            # 가중치 최종 확정
            if item.is_policy:
                item.weight = 2.0
            elif item.is_earnings:
                item.weight = 1.5

            # 관련성 필터
            if filter_irrelevant and not item.sectors:
                # 실적발표는 섹터 미매칭이어도 보존 (유니버스 종목 실적일 수 있음)
                if not item.is_earnings:
                    log.debug(f"관련성 없음, 제외: {item.title[:40]}")
                    continue
            results.append(item)

        policy_cnt = sum(1 for n in results if n.is_policy)
        earnings_cnt = sum(1 for n in results if n.is_earnings)
        log.info(
            f"뉴스 분석 완료: {len(items)}건 → 관련뉴스 {len(results)}건 "
            f"(정책 {policy_cnt}건 / 실적 {earnings_cnt}건)"
        )
        return results

    # ── 4. 종목별 뉴스 시그널 점수 ───────────────────────────────

    def get_stock_news_score(
        self, code: str, news_list: list[NewsItem]
    ) -> tuple[float, list[str]]:
        """
        특정 종목 관련 뉴스의 감성점수 집계
        반환: (0~100 점수, 이유 리스트)
        매칭 우선순위: 종목명 > 종목코드 > 섹터
        """
        from config.universe import get_stock_name
        name = get_stock_name(code)

        stock_sector = None
        for sec_key, sec in SECTORS.items():
            if code in sec["stocks"]:
                stock_sector = sec_key
                break

        direct_hits = []   # 종목명/코드 직접 언급
        sector_hits = []   # 섹터 관련 뉴스

        for item in news_list:
            combined = item.title + " " + item.content
            if name in combined or code in combined:
                direct_hits.append(item)
            elif stock_sector and stock_sector in item.sectors:
                sector_hits.append(item)

        # 직접 언급 뉴스 기본 2배, 정책/실적은 item.weight 추가 반영
        if not direct_hits and not sector_hits:
            return 50.0, []

        def _w(item: NewsItem, base: float) -> float:
            return item.sentiment * base * item.weight

        weighted_sum = sum(_w(n, 2.0) for n in direct_hits) + \
                       sum(_w(n, 1.0) for n in sector_hits)
        weighted_count = (sum(2.0 * n.weight for n in direct_hits) +
                          sum(1.0 * n.weight for n in sector_hits))
        avg_sentiment = weighted_sum / weighted_count if weighted_count else 0

        score = 50.0 + avg_sentiment * 40
        score = round(min(100.0, max(0.0, score)), 1)

        reasons = []
        # 정책 뉴스 — 가장 중요하므로 맨 앞에
        pol_pos = [n for n in direct_hits + sector_hits if n.is_policy and n.sentiment > 0.05]
        pol_neg = [n for n in direct_hits + sector_hits if n.is_policy and n.sentiment < -0.05]
        earn = [n for n in direct_hits if n.is_earnings]

        if pol_pos:
            reasons.append(f"[정책호재] {pol_pos[0].title[:45]}")
        if pol_neg:
            reasons.append(f"[정책악재] {pol_neg[0].title[:45]}")
        if earn:
            tag = "실적서프라이즈" if earn[0].sentiment > 0.1 else "실적쇼크" if earn[0].sentiment < -0.1 else "실적발표"
            reasons.append(f"[{tag}] {earn[0].title[:45]}")

        pos_direct = [n for n in direct_hits if n.sentiment > 0.1 and not n.is_policy]
        neg_direct = [n for n in direct_hits if n.sentiment < -0.1 and not n.is_policy]
        pos_sector = [n for n in sector_hits if n.sentiment > 0.1 and not n.is_policy]
        neg_sector = [n for n in sector_hits if n.sentiment < -0.1 and not n.is_policy]

        if pos_direct:
            reasons.append(f"[종목직접] 긍정 {len(pos_direct)}건: {pos_direct[0].title[:40]}")
        if neg_direct:
            reasons.append(f"[종목직접] 부정 {len(neg_direct)}건: {neg_direct[0].title[:40]}")
        if pos_sector:
            reasons.append(f"[섹터호재] {len(pos_sector)}건: {pos_sector[0].title[:40]}")
        if neg_sector:
            reasons.append(f"[섹터악재] {len(neg_sector)}건: {neg_sector[0].title[:40]}")

        return score, reasons

    # ── 5. 전체 파이프라인 (main.py에서 호출) ───────────────────

    def run_pipeline(self, stock_codes: list[str] = None) -> list[NewsItem]:
        """
        뉴스 수집 → 본문 보강 → 분석 → 필터링 전체 파이프라인
        """
        raw = self.collect_all_news(stock_codes)
        enriched = self.enrich_content(raw, limit=self.CONTENT_FETCH_LIMIT)
        processed = self.process_news(enriched, filter_irrelevant=True)
        return processed
