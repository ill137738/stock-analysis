from stocks_config import STOCKS
import requests
import json
import time
from datetime import datetime

# ===== 설정 (여기만 수정하세요) =====
import os
BRAVE_API_KEY = os.environ.get("BRAVE_API_KEY", "")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")


NEWS_COUNT = 15  # 종목당 뉴스 검색 수
# =====================================


def search_news(stock_name, search_query):
    """브레이브 API로 뉴스 검색"""
    url = "https://api.search.brave.com/res/v1/news/search"
    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "X-Subscription-Token": BRAVE_API_KEY
    }
    # 한글 포함 쿼리는 한국어 검색
    has_korean = any(ord(c) > 0x1100 for c in search_query)
    params = {
        "q": search_query,
        "count": NEWS_COUNT,
        "freshness": "pd"
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
            title = item.get("title", "")
            description = item.get("description", "")
            source = item.get("meta_url", {}).get("hostname", "") or item.get("source", "")
            age = item.get("age", "")

            # 24시간 넘은 뉴스 제외 (days ago, weeks ago, months ago)
            age_lower = age.lower()
            if any(w in age_lower for w in ["day", "week", "month", "year", "일 전", "주 전", "달 전"]):
                continue

            url_link = item.get("url", "")
            news_items.append({
                "title": title,
                "description": description,
                "source": source,
                "age": age,
                "url": url_link
            })

        return news_items if news_items else []
    except Exception as e:
        print(f"  뉴스 검색 오류 ({stock_name}): {e}")
        return []


def analyze_all_stocks(news_data):
    """DeepSeek API로 전체 종목 한 번에 분석 (1회 호출)"""

    news_prompt = ""
    for stock, items in news_data.items():
        news_prompt += f"### {stock}\n"
        for i, item in enumerate(items, 1):
            source_info = f" ({item['source']}" + (f", {item['age']}" if item['age'] else "") + ")"
            news_prompt += f"{i}. {item['title']}{source_info}\n"
            if item.get('url'):
                news_prompt += f"   URL: {item['url']}\n"
            if item['description']:
                news_prompt += f"   {item['description']}\n"
        news_prompt += "\n"

    system_prompt = """당신은 투자 뉴스 분석 전문가입니다.
각 종목의 뉴스를 분석하여 투자자에게 유용한 상세 인사이트를 제공하세요.
반드시 아래 JSON 형식으로만 출력하세요. 다른 텍스트나 마크다운은 절대 출력하지 마세요.
존댓말로 작성하세요."""

    user_prompt = f"""아래 종목들의 뉴스를 분석하고 반드시 순수 JSON 형식으로만 응답하세요.

{news_prompt}

중요: 뉴스 목록에 해당 종목과 직접 관련된 내용이 없으면 "skip": true만 반환하세요.

출력 형식 (이 형식 그대로, JSON만 출력):
{{
  "종목명": {{
    "skip": false,
    "핵심뉴스": [
      {{"내용": "뉴스 요약", "출처": "출처명", "시간": "시간정보", "url": "기사URL"}},
      {{"내용": "뉴스 요약", "출처": "출처명", "시간": "시간정보", "url": "기사URL"}}
    ],
    "투자인사이트": "2~3줄 종합 인사이트",
    "긍정": ["긍정적 요인1", "긍정적 요인2", "긍정적 요인3"],
    "부정": ["부정적 요인1", "부정적 요인2", "부정적 요인3"]
  }}
}}

관련 뉴스 없을 때:
{{
  "종목명": {{"skip": true}}
}}"""

    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://morning-analysis.local",
        "X-Title": "Morning Stock Analysis"
    }
    payload = {
        "model": "deepseek/deepseek-v4-flash",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "max_tokens": 16000,
        "temperature": 0.3
    }

    try:
        print("  DeepSeek API 호출 중...")
        response = requests.post(url, headers=headers, json=payload, timeout=120)
        response.raise_for_status()
        data = response.json()
        content = data["choices"][0]["message"]["content"]

        content = content.strip()
        if "```" in content:
            parts = content.split("```")
            for part in parts:
                if part.startswith("json"):
                    content = part[4:].strip()
                    break
                elif "{" in part:
                    content = part.strip()
                    break

        return json.loads(content)
    except json.JSONDecodeError as e:
        print(f"  JSON 파싱 오류: {e}")
        print(f"  응답 내용: {content[:200]}")
        return None
    except Exception as e:
        print(f"  DeepSeek API 오류: {e}")
        return None


def send_telegram(message):
    """텔레그램 메시지 전송"""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        return True
    except Exception as e:
        print(f"  텔레그램 전송 실패: {e}")
        return False


def format_message(stock_name, analysis):
    """텔레그램 메시지 포맷"""
    today = datetime.now().strftime("%m/%d")

    news_lines = ""
    for item in analysis.get("핵심뉴스", []):
        source = item.get("출처", "")
        time_info = item.get("시간", "")
        url_link = item.get("url", "")
        if url_link:
            source_str = f' (<a href="{url_link}">{source}</a>' + (f", {time_info}" if time_info else "") + ")" if source else f' (<a href="{url_link}">링크</a>)'
        else:
            source_str = f" ({source}" + (f", {time_info}" if time_info else "") + ")" if source else ""
        news_lines += f"• {item.get('내용', '')}{source_str}\n"

    positive_lines = ""
    for p in analysis.get("긍정", []):
        positive_lines += f"• {p}\n"

    negative_lines = ""
    for n in analysis.get("부정", []):
        negative_lines += f"• {n}\n"

    message = f"""🎯 <b>[{stock_name}]</b> ({today})

📰 <b>핵심 뉴스</b>
{news_lines.strip()}

✨ <b>투자 인사이트</b>
{analysis.get('투자인사이트', '정보 없음')}

✅ <b>긍정적 요인</b>
{positive_lines.strip()}

⚠️ <b>부정적 요인</b>
{negative_lines.strip()}"""

    return message.strip()


def main():
    print(f"=== 아침 투자 뉴스 분석 시작 ({datetime.now().strftime('%Y-%m-%d %H:%M')}) ===")

    print("\n📰 뉴스 검색 중...")
    news_data = {}
    for stock, query in STOCKS.items():
        print(f"  - {stock} 검색 중...")
        news_data[stock] = search_news(stock, query)

    # 뉴스 없는 종목 제외
    news_data = {k: v for k, v in news_data.items() if v}
    if not news_data:
        print("오늘 분석할 뉴스가 없습니다.")
        return

    print(f"\n🤖 DeepSeek 분석 중... ({len(news_data)}개 종목, 1회 호출)")
    analysis_result = analyze_all_stocks(news_data)

    if not analysis_result:
        print("❌ 분석 실패 - 종료")
        return

    print("\n📨 텔레그램 전송 중...")
    for stock in STOCKS:
        if not news_data.get(stock):
            print(f"  - {stock}: ⏭️ 오늘 뉴스 없음 (건너뜀)")
            continue
        if stock in analysis_result:
            result = analysis_result[stock]
            if result.get("skip"):
                print(f"  - {stock}: ⏭️ 관련 뉴스 없음 (건너뜀)")
                continue
            message = format_message(stock, result)
            success = send_telegram(message)
            print(f"  - {stock}: {'✅ 전송 완료' if success else '❌ 실패'}")
            time.sleep(3)
        else:
            print(f"  - {stock}: ⚠️ 분석 결과 없음")

    print("\n=== 완료 ===")


if __name__ == "__main__":
    main()
