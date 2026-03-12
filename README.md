# 📈 KangSub Bot — 자동 주식매매 시스템

> 이재명 정부 정책 연계 · 7섹터 + 고배당 포트폴리오 · 키움증권 Open API 자동매매

---

## 🗂 프로젝트 구조

```
kangsub_bot/
├── config/          설정, 종목 유니버스, 배분 전략
├── core/            포트폴리오, 리스크, 주문 실행 엔진
├── api/             키움 Open API 래퍼
├── signal/          기술적 분석, 시장 판단, 뉴스 NLP
├── data/            시장 데이터 수집/저장
├── notification/    텔레그램 봇, Notion 로거
├── dashboard/       Streamlit 실시간 대시보드
├── scheduler/       일일 운영 스케줄
├── scripts/         EC2 설정, GitHub 동기화
└── main.py          메인 실행
```

---

## 🚀 빠른 시작

### 1. 환경 설정
```powershell
git clone https://github.com/kangsubsong76-droid/kangsub_bot.git
cd kangsub_bot
pip install -r requirements.txt
cp config/.env.example config/.env
# .env 파일에 API 키 입력
```

### 2. Notion DB 자동 생성
```powershell
python scripts/setup_notion_db.py
# 출력된 DB ID를 .env에 입력
```

### 3. 페이퍼 트레이딩 테스트
```powershell
python main.py --paper
```

### 4. 대시보드 실행
```powershell
streamlit run dashboard/app.py --server.port 8501
```

### 5. 실전 매매 (키움 API 연결 후)
```powershell
python main.py
```

---

## 📋 투자 전략 요약

| 항목 | 내용 |
|------|------|
| 투자금 | 1억원 |
| 배분 | 일반 60% (Max 10종목) / 배당 40% (Max 6종목) |
| 분할매수 | 3회 분할 (1차 40%, 2차 30%, 3차 30%) |
| 손절 | 지수대비 -10%p 즉시 / 추적손절 (수익구간별) |
| 리밸런싱 | 분기 1회 (1/4/7/10월) |
| 최대손실 | 전체 -20% 시 전량매도 |

---

## 📅 구현 로드맵

- **Phase 1** (3/11~18): 기반 모듈 구현 ← 현재
- **Phase 2** (3/19~25): 키움 API 연동 + EC2 세팅
- **Phase 3** (3/26~4/1): 통합 테스트 + 모의투자
- **Phase 4** (4/2~): 실전 매매 시작

---

## ⚠️ 주의사항

- `config/.env` 파일은 절대 GitHub에 올리지 마세요 (gitignore 처리됨)
- 키움 Open API는 Windows 환경에서만 동작합니다
- 실전 매매 전 반드시 1주일 이상 페이퍼 트레이딩으로 검증하세요
