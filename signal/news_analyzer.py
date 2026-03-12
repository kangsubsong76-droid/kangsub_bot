"""뉴스 크롤링 + NLP 감성분석 + 매매 시그널 생성"""
import re
import time
import requests
from datetime import datetime, timedelta
from dataclasses import dataclass
from bs4 import BeautifulSoup
from config.settings import NEWS_SOURCES
from config.universe import SECTORS, DIVIDEND_TOP12
from utils.logger import setup_logger

log = setup_logger("news_analyzer")

# 섹터-키워드 매핑
SECTOR_KEYWORDS = {
    "AI_반도체": ["AI", "인공지능", "반도체", "HBM", "엔비디아", "SK하이닉스", "한미반도체", "솔브레인", "소부장", "메모리"],
    "K_방산": ["방산", "방위산업", "한화에어로", "현대로템", "풍산", "K2전차", "탄약", "수출", "UAE", "폴란드", "루마니아"],
    "재생에너지": ["재생에너지", "풍력", "태양광", "전력망", "변압기", "HD현대일렉", "씨에스윈드", "일진전기", "데이터센터", "탄소중립"],
    "피지컬AI_로봇": ["로봇", "협동로봇", "휴머노이드", "두산로보틱스", "레인보우로보틱스", "에스비비테크", "스마트팩토리", "피지컬AI"],
    "외교_한중": ["한중", "한한령", "중국", "아모레퍼시픽", "LG생활건강", "크래프톤", "방중", "면세", "K뷰티", "문화콘텐츠"],
    "밸류업_금융": ["밸류업", "배당", "금융", "은행", "KB금융", "신한지주", "하나금융", "우리금융", "주주환원", "PBR", "코리아디스카운트"],
    "중소_벤처": ["중소기업", "벤처", "소부장", "R&D", "기술탈취", "스타트업", "코스닥"],
    "이재명": ["이재명", "정부정책", "경제정책", "예산", "정책", "국정", "밸류업"],
}

# 긍정/부정 키워드
POSITIVE_WORDS = [
    "상승", "급등", "호재", "수출", "계약", "수주", "흑자", "사상최대", "목표가상향",
    "매수", "실적개선", "성장", "기대", "호황", "확대", "승인", "체결", "선정",
]
NEGATIVE_WORDS = [
    "하락", "급락", "악재", "손실", "적자", "취소", "철회", "제재", "리스크",
    "우려", "경고", "부정", "위기", "감소", "하향", "소송", "규제", "불확실",
]


@dataclass
class NewsItem:
    title: str
    url: str
    source: str
    published: str
    content: str = ""
    sectors: list = None
    sentiment: float = 0.0   # -1.0 ~ +1.0
    summary: str = ""

    def __post_init__(self):
        if self.sectors is None:
            self.sectors = []


class NewsAnalyzer:
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0"
    }

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)

    # ── 1. 크롤링 ──

    def fetch_hani(self, limit: int = 10) -> list[NewsItem]:
        """한겨레 경제 뉴스"""
        items = []
        try:
            url = "https://www.hani.co.kr/arti/economy"
            resp = self.session.get(url, timeout=10)
            soup = BeautifulSoup(resp.text, "html.parser")
            for a in soup.select("a[href*='/arti/economy']")[:limit]:
                title = a.get_text(strip=True)
                href = a.get("href", "")
                if title and len(title) > 10:
                    full_url = href if href.startswith("http") else f"https://www.hani.co.kr{href}"
                    items.append(NewsItem(
                        title=title, url=full_url, source="한겨레",
                        published=datetime.now().strftime("%Y-%m-%d"),
                    ))
        except Exception as e:
            log.warning(f"한겨레 크롤링 실패: {e}")
        return items

    def fetch_khan(self, limit: int = 10) -> list[NewsItem]:
        """경향신문 경제 뉴스"""
        items = []
        try:
            url = "https://www.khan.co.kr/economy"
            resp = self.session.get(url, timeout=10)
            soup = BeautifulSoup(resp.text, "html.parser")
            for a in soup.select("a[href*='/economy/']")[:limit]:
                title = a.get_text(strip=True)
                href = a.get("href", "")
                if title and len(title) > 10:
                    full_url = href if href.startswith("http") else f"https://www.khan.co.kr{href}"
                    items.append(NewsItem(
                        title=title, url=full_url, source="경향신문",
                        published=datetime.now().strftime("%Y-%m-%d"),
                    ))
        except Exception as e:
            log.warning(f"경향 크롤링 실패: {e}")
        return items

    def fetch_humblefactory(self, limit: int = 5) -> list[NewsItem]:
        """김어준 뉴스공장"""
        items = []
        try:
            url = "https://humblefactory.co.kr/"
            resp = self.session.get(url, timeout=10)
            soup = BeautifulSoup(resp.text, "html.parser")
            for a in soup.select("a[href*='humblefactory']")[:limit]:
                title = a.get_text(strip=True)
                if title and len(title) > 5:
                    items.append(NewsItem(
                        title=title, url=a.get("href", url),
                        source="김어준뉴스공장",
                        published=datetime.now().strftime("%Y-%m-%d"),
                    ))
        except Exception as e:
            log.warning(f"뉴스공장 크롤링 실패: {e}")
        return items

    def fetch_naver_finance_news(self, code: str, limit: int = 5) -> list[NewsItem]:
        """네이버 금융 종목 뉴스"""
        items = []
        try:
            url = f"https://finance.naver.com/item/news_news.naver?code={code}"
            resp = self.session.get(url, timeout=10)
            soup = BeautifulSoup(resp.text, "html.parser")
            for row in soup.select("table.type5 tr")[:limit]:
                a = row.select_one("td.title a")
                date_td = row.select_one("td.date")
                if a:
                    items.append(NewsItem(
                        title=a.get_text(strip=True),
                        url=f"https://finance.naver.com{a.get('href', '')}",
                        source="네이버금융",
                        published=date_td.get_text(strip=True) if date_td else "",
                    ))
        except Exception as e:
            log.warning(f"네이버 뉴스 크롤링 실패 ({code}): {e}")
        return items

    def collect_all_news(self, stock_codes: list[str] = None) -> list[NewsItem]:
        """전체 뉴스 수집"""
        all_news = []
        all_news.extend(self.fetch_hani())
        all_news.extend(self.fetch_khan())
        all_news.extend(self.fetch_humblefactory())
        if stock_codes:
            for code in stock_codes[:5]:  # 너무 많은 요청 방지
                all_news.extend(self.fetch_naver_finance_news(code))
                time.sleep(0.3)
        log.info(f"뉴스 수집 완료: {len(all_news)}건")
        return all_news

    # ── 2. 감성분석 ──

    def analyze_sentiment(self, text: str) -> float:
        """키워드 기반 감성점수 (-1.0 ~ +1.0)"""
        pos = sum(1 for w in POSITIVE_WORDS if w in text)
        neg = sum(1 for w in NEGATIVE_WORDS if w in text)
        total = pos + neg
        if total == 0:
            return 0.0
        return round((pos - neg) / total, 3)

    def detect_sectors(self, text: str) -> list[str]:
        """뉴스에서 관련 섹터 감지"""
        found = []
        for sector, keywords in SECTOR_KEYWORDS.items():
            if any(kw in text for kw in keywords):
                found.append(sector)
        return found

    def summarize(self, title: str, content: str = "") -> str:
        """간단 요약 (제목 + 핵심 문장)"""
        if not content:
            return title
        sentences = re.split(r"[.。!?]", content)
        key = [s.strip() for s in sentences if len(s.strip()) > 20][:2]
        return title + (" | " + " ".join(key) if key else "")

    def process_news(self, items: list[NewsItem]) -> list[NewsItem]:
        """수집된 뉴스 분석 처리"""
        for item in items:
            combined = item.title + " " + item.content
            item.sentiment = self.analyze_sentiment(combined)
            item.sectors = self.detect_sectors(combined)
            item.summary = self.summarize(item.title, item.content)
        return items

    # ── 3. 종목별 뉴스 시그널 점수 계산 ──

    def get_stock_news_score(
        self, code: str, news_list: list[NewsItem]
    ) -> tuple[float, list[str]]:
        """
        특정 종목 관련 뉴스의 감성점수 집계
        반환: (0~100 점수, 이유 리스트)
        """
        # 종목명 가져오기
        from config.universe import get_stock_name
        name = get_stock_name(code)

        # 해당 종목 섹터 찾기
        stock_sector = None
        for sec_key, sec in SECTORS.items():
            if code in sec["stocks"]:
                stock_sector = sec_key
                break

        relevant = []
        for item in news_list:
            if name in item.title or code in item.title:
                relevant.append(item)
            elif stock_sector and stock_sector in item.sectors:
                relevant.append(item)

        if not relevant:
            return 50.0, []  # 중립

        avg_sentiment = sum(n.sentiment for n in relevant) / len(relevant)
        # -1~+1 → 0~100 변환
        score = 50.0 + avg_sentiment * 40

        reasons = []
        pos_news = [n for n in relevant if n.sentiment > 0.2]
        neg_news = [n for n in relevant if n.sentiment < -0.2]
        if pos_news:
            reasons.append(f"긍정 뉴스 {len(pos_news)}건: {pos_news[0].title[:30]}")
        if neg_news:
            reasons.append(f"부정 뉴스 {len(neg_news)}건: {neg_news[0].title[:30]}")

        return round(min(100, max(0, score)), 1), reasons
