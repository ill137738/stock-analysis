import requests
import json
import time
import os
from datetime import datetime
from stocks_config import STOCKS

# ===== 설정 =====
BRAVE_API_KEY = os.environ.get("BRAVE_API_KEY", "")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
NEWS_COUNT = 20  # 월간 분석용 뉴스 수 (더 많이)


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

    # 뉴스 텍스트 구성
    news_text = ""
    for i, item in enumerate(news_items, 1):
        source_info = f" ({item['source']}" + (f", {item['age']}" if item['age'] else "") + ")"
        news_text += f"{i}. {item['title']}{source_info}\n"
        if item.get('url'):
            news_text += f"   URL: {item['url']}\n"
        if item['description']:
            news_text += f"   {item['description']}\n"
    news_text = news_text or "최근 1달 내 관련 뉴스 없음"

    user_prompt = f"""다음 종목에 대해 월간 심층 분석을 수행하세요: {stock_name}

[최근 1달 뉴스]
{news_text}

위 뉴스를 반드시 참고하여 아래 12개 섹션을 모두 포함하여 상세하게 분석하세요.

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

🏦 4. 스마트머니 추적
- 검증된 펀드(ARK, Baillie Gifford, Tiger Global 등) 보유 현황
- 최근 분기 매수/매도/유지 여부
- 하락 구간에서도 매수 지속했는가?
- 데이터 출처 및 기준일 명시

---

🚀 5. 가격 상승 모멘텀 (Catalysts)
- 단기(3~6개월) 촉매 및 실현 가능성
- 중기(6개월~2년) 촉매 및 실현 가능성
- 가장 강력한 단일 촉매

---

📈 6. Bull / Bear Case & 핵심 지표

[재무 지표 — 반드시 포함]
- 최근 분기/연간 매출 및 YoY 상승률(%)
- 영업이익 및 영업이익률(%)
- PER (주가수익비율)
- PSR (주가매출비율)
- 밸류에이션 효율 지표: (매출 YoY 상승률 + 영업이익률) / 4 / PSR
  → 이 값이 높을수록 성장 대비 저평가 의미. 1.0 이상이면 양호, 0.5 미만이면 고평가 신호
- 코인의 경우: 시총, 거래량, 도미넌스

[Bull Case] 성장 동력 2~3가지
[Bear Case] 주요 리스크 2~3가지
[좋은 적자 vs 나쁜 적자] 해당 시 구분하여 분석

---

🧭 7. 투자 판단 관점
- 어떤 투자자에게 적합한가 (성향/기간/목적)
- 성향별 포트폴리오 추천 비중표 (공격적 / 중립적 / 보수적)

---

📉 8. 공매도 현황 (Short Interest)
- 현재 공매도 비율 및 추이
- 판단: 🟢 숏스퀴즈 가능성 / 🟡 모니터링 / 🔴 경고 신호

---

🕵️ 9. 내부자 거래 추적
- 최근 6개월 내부자 매수/매도 현황
- 판단: 📥 강세 신호 / 📤 경고 신호 / ⚪ 중립

---

💰 10. 적정 매수 구간
- 역사적 밸류에이션 대비 현재 위치
- 분할 매수 1차·2차·3차 구간
- 매수 매력도: 🟢 저평가 / 🟡 적정 / 🔴 고평가

---

🚪 11. Exit 전략 프레임
- 목표가 기반 Exit (1차/2차/최종)
- Thesis 붕괴 Exit 조건
- 손절 기준

---

📊 12. 급등/급락 원인 분석 (최근 ±20% 이상 있었다면)
- 원인 유형 분류
- Thesis 유지/훼손 여부
- 결론: "이번 [급등/급락]은 [원인 유형]으로 판단됩니다. Thesis는 [유지/훼손]되었으며, 현재는 [매수 기회 / 관망 / 경고 신호]로 볼 수 있습니다."

---

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
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"  {stock_name} 분석 오류: {e}")
        return None


def send_telegram(message):
    """텔레그램 메시지 전송 (긴 메시지 자동 분할)"""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    # 텔레그램 최대 4096자 제한 → 분할 전송
    max_len = 4000
    chunks = []
    while len(message) > max_len:
        split_pos = message.rfind('\n', 0, max_len)
        if split_pos == -1:
            split_pos = max_len
        chunks.append(message[:split_pos])
        message = message[split_pos:].lstrip()
    chunks.append(message)

    success = True
    for chunk in chunks:
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": chunk,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True
        }
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
        analysis = analyze_stock_monthly(stock_name, search_query)

        if analysis:
            # 종목 헤더 추가
            full_message = f"🎯 *[{stock_name}] 월간 심층 분석*\n\n{analysis}"
            success = send_telegram(full_message)
            print(f"  - {stock_name}: {'✅ 전송 완료' if success else '❌ 전송 실패'}")
        else:
            print(f"  - {stock_name}: ❌ 분석 실패")

        # API 과부하 방지
        time.sleep(10)

    print("\n=== 월간 분석 완료 ===")


if __name__ == "__main__":
    main()
