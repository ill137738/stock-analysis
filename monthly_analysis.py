import requests
import json
import time
import os
from datetime import datetime
from stocks_config import STOCKS
try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False

# ===== 설정 =====
BRAVE_API_KEY = os.environ.get("BRAVE_API_KEY", "")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
NEWS_COUNT = 70  # 월간 분석용 뉴스 수


# 야후 파이낸스 티커 매핑 (한국 종목은 종목코드.KS 또는 .KQ)
YAHOO_TICKERS = {
    "CRSP": "CRSP",
    "한화에어로스페이스": "012450.KS",
    "JOBY": "JOBY",
    "클래시스": "214150.KQ",
    "Netflix": "NFLX",
    "CoreWeave": "CRWV",
    "Tempus AI": "TEM",
    "이더리움": "ETH-USD",
    "부동산": None  # 야후 파이낸스 해당 없음
}


def get_yahoo_data(stock_name):
    """야후 파이낸스에서 재무 데이터 가져오기"""
    if not YFINANCE_AVAILABLE:
        return "yfinance 미설치"

    ticker_symbol = YAHOO_TICKERS.get(stock_name)
    if not ticker_symbol:
        return "야후 파이낸스 데이터 없음"

    try:
        ticker = yf.Ticker(ticker_symbol)
        info = ticker.info

        # 주가 히스토리 (1달)
        hist = ticker.history(period="1mo")
        if not hist.empty:
            current_price = hist['Close'].iloc[-1]
            month_start_price = hist['Close'].iloc[0]
            month_return = ((current_price - month_start_price) / month_start_price) * 100
            month_high = hist['High'].max()
            month_low = hist['Low'].min()
        else:
            current_price = month_return = month_high = month_low = None

        # 52주 고저
        week52_high = info.get('fiftyTwoWeekHigh')
        week52_low = info.get('fiftyTwoWeekLow')

        # 밸류에이션
        per = info.get('trailingPE') or info.get('forwardPE')
        psr = info.get('priceToSalesTrailing12Months')
        pbr = info.get('priceToBook')
        market_cap = info.get('marketCap')

        # 실적
        revenue = info.get('totalRevenue')
        revenue_growth = info.get('revenueGrowth')
        operating_margins = info.get('operatingMargins')
        gross_margins = info.get('grossMargins')

        # 포맷
        def fmt(v, pct=False, price=False):
            if v is None:
                return "N/A"
            if pct:
                return f"{v*100:.1f}%"
            if price:
                return f"${v:,.2f}" if ticker_symbol and not ticker_symbol.endswith('.KS') and not ticker_symbol.endswith('.KQ') else f"{v:,.0f}"
            if v > 1e9:
                return f"${v/1e9:.1f}B"
            if v > 1e6:
                return f"${v/1e6:.1f}M"
            return f"{v:.2f}"

        result = f"""
[야후 파이낸스 실시간 데이터]
현재가: {fmt(current_price, price=True)}
월간 수익률: {f'{month_return:.1f}%' if month_return is not None else 'N/A'}
월간 고가: {fmt(month_high, price=True)} / 저가: {fmt(month_low, price=True)}
52주 고가: {fmt(week52_high, price=True)} / 저가: {fmt(week52_low, price=True)}
시가총액: {fmt(market_cap)}
PER: {fmt(per)}
PBR: {fmt(pbr)}
PSR: {fmt(psr)}
매출: {fmt(revenue)}
매출 YoY 성장률: {fmt(revenue_growth, pct=True)}
영업이익률: {fmt(operating_margins, pct=True)}
매출총이익률: {fmt(gross_margins, pct=True)}"""

        # 밸류에이션 효율 지표 계산
        if revenue_growth is not None and operating_margins is not None and psr is not None and psr > 0:
            val_score = (revenue_growth * 100 + operating_margins * 100) / 4 / psr
            result += f"\n밸류에이션 효율 지표: {val_score:.2f} (1.0↑ 양호, 0.5↓ 고평가 신호)"

        return result

    except Exception as e:
        return f"데이터 조회 실패: {e}"


def search_news_monthly(stock_name, search_query):
    """브레이브 API로 1달치 뉴스 검색"""
    url = "https://api.search.brave.com/res/v1/news/search"
    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "X-Subscription-Token": BRAVE_API_KEY
    }
    has_korean = any(ord(c) > 0x1100 for c in search_query)
    params = {
        "q": search_query,
        "count": NEWS_COUNT,
        "freshness": "pm"  # 1달
    }
    if has_korean:
        params["search_lang"] = "ko"
        params["country"] = "KR"

    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        results = data.get("results", [])
        news_items = []
        for item in results:
            news_items.append({
                "title": item.get("title", ""),
                "description": item.get("description", ""),
                "source": item.get("meta_url", {}).get("hostname", "") or item.get("source", ""),
                "age": item.get("age", ""),
                "url": item.get("url", "")
            })
        return news_items
    except Exception as e:
        print(f"  뉴스 검색 오류 ({stock_name}): {e}")
        return []


MONTHLY_SYSTEM_PROMPT = """당신은 개인 투자자의 합리적인 의사결정을 돕는 전문 투자 어드바이저입니다.
투자 추천이 아닌 정보 제공과 분석 프레임워크 제시가 목적입니다.
모든 최종 결정은 사용자 본인이 내리도록 유도하세요.

핵심 원칙:
- 객관성: 특정 종목/상품을 무조건 추천하거나 비추천하지 않음
- 근거 기반: 주장마다 데이터, 지표, 논리적 근거 제시
- 리스크 명시: 기회 요인과 함께 반드시 리스크 요인 균형 있게 제시
- 확신 표현 지양: "~입니다" 대신 "~로 볼 수 있습니다"

하지 말아야 할 것:
- "지금 당장 사세요 / 파세요" 같은 직접적 매매 지시
- 특정 수익률 보장 또는 암시
- 불확실한 정보를 확실한 것처럼 제시
- 검증되지 않은 기관 평단가를 사실처럼 제시"""


def analyze_stock_monthly(stock_name, search_query, news_items):
    """단일 종목 월간 심층 분석"""

    # 뉴스 텍스트 구성 + 인덱스 맵 (번호 → {source, age, url})
    news_text = ""
    news_index_map = {}  # 번호 → 뉴스 정보
    source_url_map = {}  # 출처명 → URL 매핑
    for i, item in enumerate(news_items, 1):
        source = item['source']
        age = item.get('age', '')
        url = item.get('url', '')
        news_index_map[i] = {'source': source, 'age': age, 'url': url}
        source_info = f" ({source}" + (f", {age}" if age else "") + ")"
        news_text += f"[{i}] {item['title']}{source_info}\n"
        if item['description']:
            news_text += f"   {item['description']}\n"
        if url and source:
            source_url_map[source.lower()] = url
    news_text = news_text or "최근 1달 내 관련 뉴스 없음"

    today = datetime.now().strftime("%Y년 %m월 %d일")
    yahoo_data = get_yahoo_data(stock_name)

    user_prompt = f"""오늘은 {today}입니다. 다음 종목에 대해 월간 심층 분석을 수행하세요: {stock_name}

⚠️ 중요 지시사항:
- 아래 제공된 야후 파이낸스 실시간 데이터와 최근 1달 뉴스를 반드시 분석의 핵심 근거로 사용하세요
- 학습 데이터(2024년 이전)에 의존하지 말고, 제공된 데이터 기반으로 작성하세요
- 뉴스와 데이터에 없는 정보는 "최신 데이터 미확인"으로 명시하세요
- 주장이나 분석 근거로 뉴스를 사용할 때는 절대 뉴스 번호(8, 10, 14 같은 숫자)로 표기하지 마세요
- 반드시 바로 옆에 (출처명, 시간, URL) 형식으로 실제 링크를 포함하세요
- 출처 표기 형식: (언론사명, 시간, URL) — 기사 제목은 절대 쓰지 마세요
- 예시: "전환사채 발행으로 주가 하락 (Motley Fool, 2 days ago, https://...)"
- URL이 없는 뉴스는 (언론사명, 시간) 형식으로만 표기하세요
- 언론사명은 짧게: "The Motley Fool" → "Motley Fool", "한국경제신문" → "한국경제"

{yahoo_data}

[최근 1달 뉴스 — 이것이 분석의 주요 근거입니다]
{news_text}

위 뉴스를 반드시 참고하여 아래 섹션을 모두 포함하여 상세하게 분석하세요.

---

🧬 1. 본질 가치 분석
[욕망 분석]
- 이 자산/기업의 존재 이유는 무엇인가?
- 어떤 인간의 욕망/필요를 해결하는가?
- 그 욕망은 일시적 트렌드인가, 구조적·영속적인가?
- 10년 후에도 이 욕망은 존재할 것인가?
- 이 자산이 그 욕망을 채우는 데 대체 불가능한가?

[시대 흐름 정합성]
- 어떤 메가트렌드와 연결되는가?
- 5~10년 후 이 자산의 역할이 커질 것인가, 작아질 것인가?
- 정합성 등급: ✅ 강한 순풍 / 🔶 혼재 / ❌ 역풍

---

🎯 2. 시장 포지셔닝
- 시장에서 이 자산/기업을 한 문장으로 정의
- 포지셔닝이 시간이 갈수록 강화되는가, 희석되는가?
- 경쟁사 포지셔닝 침범 위험도: 🟢 낮음 / 🟡 중간 / 🔴 높음
- 매스 어돕션 현황 및 채택 가속도: 🚀 가속 중 / ➡️ 유지 / 🐢 둔화

---

⚔️ 3. 경쟁 우위 & 경제적 해자
- 주요 경쟁자와 핵심 차별점
- 경제적 해자 유형 및 강도: ⭐⭐⭐ 강함 / ⭐⭐ 보통 / ⭐ 약함

---

🚀 4. 가격 상승 모멘텀 (Catalysts)
- 단기(3~6개월) 촉매 및 실현 가능성
- 중기(6개월~2년) 촉매 및 실현 가능성
- 가장 강력한 단일 촉매

---

📈 5. Bull / Bear Case & 핵심 지표

[재무 지표 — 뉴스에 언급된 최신 수치 사용, 없으면 "최신 데이터 미확인" 명시]
- 최근 분기/연간 매출 및 YoY 상승률(%)
- 영업이익 및 영업이익률(%)
- PER (주가수익비율)
- PSR (주가매출비율)
- 밸류에이션 효율 지표: (매출 YoY 상승률 + 영업이익률) / 4 / PSR
  → 이 값이 높을수록 성장 대비 저평가 의미. 1.0 이상이면 양호, 0.5 미만이면 고평가 신호
- 코인의 경우: 시총, 거래량, 도미넌스

🐂 Bull Case: 성장 동력 2~3가지
🐻 Bear Case: 주요 리스크 2~3가지
[좋은 적자 vs 나쁜 적자] 해당 시 구분하여 분석

---

🧭 6. 투자 판단 관점
- 어떤 투자자에게 적합한가 (성향/기간/목적)
- 포트폴리오 10종목 기준 추천 비중 (10% = 1종목 비중):
  공격적 투자자: X% (X/10종목)
  중립적 투자자: X% (X/10종목)
  보수적 투자자: X% (X/10종목)
  ※ 포트폴리오 10종목 기준

비중 산정 기준 (과감하게 부여할 것):
- 장기적으로 신뢰할 수 있고 포트폴리오의 주축이 될 수 있는 종목은 공격적 투자자 기준 20~30%도 가능
- 메가트렌드 정합성 강하고 해자 뚜렷한 종목: 공격적 20%+, 중립적 15%+
- 성장 모멘텀 강하고 리스크 감내 가능한 종목: 공격적 15~20%, 중립적 10~15%
- 불확실성 높은 초기 성장주: 공격적 10~15%, 중립적 5~10%
- 리스크 높고 투기적 성격: 공격적 5~10%, 중립적 0~5%
- 보수적 투자자는 위 기준의 절반 이하로 설정
- 절대 모든 종목을 10%로 균등하게 배분하지 말 것. 종목의 질과 확신도에 따라 차별화할 것

---

💰 7. 적정 매수 구간
- 역사적 밸류에이션 대비 현재 위치
- 분할 매수 1차·2차·3차 구간
- 매수 매력도: 🟢 저평가 / 🟡 적정 / 🔴 고평가

---

🚪 8. Thesis 붕괴 Exit 조건
- 본질 가치를 훼손하는 사건이 발생했는가? (예: 핵심 경영진 교체, 주력 제품 리콜, 규제 제재, 회계 부정)
- 시대 흐름이 반전됐는가? (예: 방산주 → 전쟁 종전, 이더리움 → 치명적 보안 취약점 발견)
- 더 나은 대안이 나타났는가?
- 위 조건 중 현재 해당되는 것이 있다면 명시하세요

---

📊 9. 급등/급락 원인 분석 (최근 ±20% 이상 있었다면)
- 원인 유형 분류 (펀더멘털 변화 / 수급 이벤트 / 매크로 충격 / 루머 / 내부자 이슈)
- Thesis 유지/훼손 여부
- 결론: "이번 [급등/급락]은 [원인 유형]으로 판단됩니다. Thesis는 [유지/훼손]되었으며, 현재는 [매수 기회 / 관망 / 경고 신호]로 볼 수 있습니다."

---

🏦 10. 스마트머니 추적 (뉴스에 언급된 경우만 작성, 없으면 이 섹션 생략)
- 검증된 펀드(ARK, Baillie Gifford, Tiger Global 등) 매수/매도 동향
- 하락 구간에서도 매수 지속했는가?
- 판단: 📥 강한 확신 신호 / 📤 경고 신호 / ⚪ 정보 없음

---

📉 11. 공매도 현황 (뉴스에 언급된 경우만 작성, 없으면 이 섹션 생략)
- 공매도 비율 및 추이
- 판단: 🟢 숏스퀴즈 가능성 / 🟡 모니터링 / 🔴 경고 신호

---

🕵️ 12. 내부자 거래 (뉴스에 언급된 경우만 작성, 없으면 이 섹션 생략)
- 최근 내부자 매수/매도 동향
- 판단: 📥 강세 신호 / 📤 경고 신호 / ⚪ 정보 없음

---

출력 시 가독성을 위해 아래 기호를 최대한 활용하세요:
- 등급/판단: ✅ 양호 / ⚠️ 주의 / ❌ 위험 / 🟢 긍정 / 🟡 중립 / 🔴 부정
- 방향: ↑ 상승 / ↓ 하락 / → 유지 / ▲ 증가 / ▼ 감소
- 강도: ⭐⭐⭐ 강 / ⭐⭐ 중 / ⭐ 약
- 신호: 📥 매수 / 📤 매도 / 🚀 가속 / 🐢 둔화
- 구분선 대신 빈 줄로 섹션 구분
- 불필요한 긴 문장보다 핵심만 간결하게

마지막에 반드시 추가:
💡 이 내용은 투자 참고 정보이며, 전문 금융 조언이 아닙니다. 투자 결정 전 본인의 재무 상황과 리스크 허용 범위를 충분히 고려하시고, 필요 시 공인 금융 전문가와 상담하시기 바랍니다."""

    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://monthly-analysis.local",
        "X-Title": "Monthly Stock Deep Analysis"
    }
    payload = {
        "model": "deepseek/deepseek-v3.2",
        "messages": [
            {"role": "system", "content": MONTHLY_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt}
        ],
        "max_tokens": 16000,
        "temperature": 0.3
    }

    try:
        print(f"  {stock_name} DeepSeek 분석 중...")
        response = requests.post(url, headers=headers, json=payload, timeout=180)
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"], news_index_map, source_url_map
    except Exception as e:
        print(f"  {stock_name} 분석 오류: {e}")
        return None, {}, {}


def clean_markdown(text):
    """마크다운 기호 제거"""
    import re
    text = re.sub(r'###\s*', '', text)
    text = re.sub(r'##\s*', '', text)
    text = re.sub(r'#\s*', '', text)
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'\*(.+?)\*', r'\1', text)
    text = re.sub(r'__(.+?)__', r'\1', text)
    text = re.sub(r'_(.+?)_', r'\1', text)
    return text


def convert_urls_to_html(text, source_url_map=None, news_index_map=None):
    """[번호] 형식 참조를 HTML 링크로 변환"""
    import re

    if news_index_map:
        def replace_index(m):
            num = int(m.group(1))
            info = news_index_map.get(num)
            if info and info.get('url'):
                source = info['source']
                age = info.get('age', '')
                label = source + (f", {age}" if age else "")
                return f'<a href="{info["url"]}">{label}</a>'
            elif info:
                source = info['source']
                age = info.get('age', '')
                return f'({source}{", " + age if age else ""})'
            return m.group(0)
        text = re.sub(r'\[(\d+)\]', replace_index, text)

    # (출처명, 시간) 패턴도 source_url_map으로 링크 변환
    if source_url_map:
        def replace_text_citation(m):
            inner = m.group(1)
            for source_key, url in source_url_map.items():
                if source_key in inner.lower():
                    return f'(<a href="{url}">{inner.strip()}</a>)'
            return m.group(0)
        text = re.sub(r'\(([^)]{3,80})\)', replace_text_citation, text)

    # 혹시 남은 단독 URL 제거
    text = re.sub(r'(?<!["(])https?://[^\s)<]+', '', text)
    # 빈 괄호 제거
    text = re.sub(r'\(\s*,?\s*\)', '', text)
    return text


def send_telegram(message, use_html=False, source_url_map=None, news_index_map=None):
    """텔레그램 메시지 전송 (챕터 단위로 분할)"""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    # 마크다운 기호 제거
    if not use_html:
        message = clean_markdown(message)
    else:
        # HTML 모드에서도 ### ** 등 제거
        import re
        message = re.sub(r'###\s*', '', message)
        message = re.sub(r'##\s*', '', message)
        message = re.sub(r'#\s*', '', message)
        message = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', message)
        message = re.sub(r'\*(.+?)\*', r'\1', message)
        message = convert_urls_to_html(message, source_url_map, news_index_map)

    # 챕터 단위로 먼저 분리
    import re
    max_len = 4000
    chapter_pattern = re.compile(r'^[🧬🎯⚔️🚀📈🧭💰🚪📊📎🏦📉🕵️]', re.MULTILINE)

    # 챕터 경계 찾기
    lines = message.split('\n')
    chapters = []
    current_chapter = []
    for line in lines:
        if chapter_pattern.match(line) and current_chapter:
            chapters.append('\n'.join(current_chapter))
            current_chapter = [line]
        else:
            current_chapter.append(line)
    if current_chapter:
        chapters.append('\n'.join(current_chapter))

    # 챕터를 4000자 이내로 묶기 (챕터는 절대 중간에 자르지 않음)
    chunks = []
    current = ""
    for chapter in chapters:
        if len(chapter) > max_len:
            # 챕터 자체가 너무 길면 어쩔 수 없이 줄 단위로 분할
            if current:
                chunks.append(current.strip())
                current = ""
            sub_lines = chapter.split('\n')
            sub_current = ""
            for sub_line in sub_lines:
                if len(sub_current) + len(sub_line) + 1 > max_len:
                    chunks.append(sub_current.strip())
                    sub_current = sub_line + '\n'
                else:
                    sub_current += sub_line + '\n'
            if sub_current.strip():
                chunks.append(sub_current.strip())
        elif len(current) + len(chapter) + 1 > max_len:
            chunks.append(current.strip())
            current = chapter + '\n'
        else:
            current += chapter + '\n'

    if current.strip():
        chunks.append(current.strip())

    success = True
    for chunk in chunks:
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": chunk,
            "disable_web_page_preview": True
        }
        if use_html:
            payload["parse_mode"] = "HTML"
        try:
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            time.sleep(1)
        except Exception as e:
            print(f"  텔레그램 전송 실패: {e}")
            success = False
    return success


def main():
    today = datetime.now().strftime("%Y-%m-%d")
    print(f"=== 월간 심층 분석 시작 ({today}) ===")
    print(f"분석 대상: {len(STOCKS)}개 종목\n")

    # 헤더 메시지 전송
    header = f"📊 *월간 심층 분석 리포트*\n{today}\n분석 종목: {', '.join(STOCKS.keys())}"
    send_telegram(header)
    time.sleep(2)

    for stock_name, search_query in STOCKS.items():
        # 부동산 같은 비종목 항목은 월간 분석 제외
        if stock_name in ["부동산"]:
            print(f"  - {stock_name}: 종목 아님, 건너뜀")
            continue

        print(f"\n[{stock_name}] 분석 시작...")
        news_items = search_news_monthly(stock_name, search_query)
        print(f"  뉴스 {len(news_items)}건 검색됨")
        analysis, news_index_map, source_url_map = analyze_stock_monthly(stock_name, search_query, news_items)

        if analysis:
            full_message = f"🎯 <b>[{stock_name}] 월간 심층 분석</b>\n\n{analysis}"
            success = send_telegram(full_message, use_html=True, source_url_map=source_url_map, news_index_map=news_index_map)
            print(f"  - {stock_name}: {'✅ 전송 완료' if success else '❌ 전송 실패'}")
        else:
            print(f"  - {stock_name}: ❌ 분석 실패")

        # API 과부하 방지
        time.sleep(10)

    print("\n=== 월간 분석 완료 ===")


if __name__ == "__main__":
    main()
