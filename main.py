import os
import json
import time
import html
import re
from datetime import datetime
from zoneinfo import ZoneInfo

import feedparser
import requests

JST = ZoneInfo("Asia/Tokyo")

LINE_TOKEN = os.getenv("LINE_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

def clean_text(text: str) -> str:
    if not text:
        return ""
    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()

def shorten(text, max_len):
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."

def fetch_news(rss):
    feed = feedparser.parse(rss)
    if not feed.entries:
        return None
    e = feed.entries[0]
    return {
        "title": clean_text(e.title),
        "summary": clean_text(e.summary),
        "link": e.link
    }

def call_openai(title, summary):
    url = "https://api.openai.com/v1/chat/completions"

    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }

    prompt = f"""
高校1年生向けにわかりやすく説明してください。

・短く
・やさしく
・各項目1〜2文

▼何があった？
▼かんたん解説
▼なぜ大事？
▼考えてみよう

ニュース:
{title}
{summary}
"""

    body = {
        "model": OPENAI_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.5
    }

    res = requests.post(url, headers=headers, json=body)
    res.raise_for_status()

    text = res.json()["choices"][0]["message"]["content"]
    return text

def fallback(title, summary):
    return f"""
▼何があった？
{shorten(summary, 60)}

▼かんたん解説
生活に関係するニュースです。

▼なぜ大事？
社会の流れに影響します。

▼考えてみよう
あなたはどう思う？
"""

def send_line(messages):
    url = "https://api.line.me/v2/bot/message/broadcast"

    headers = {
        "Authorization": f"Bearer {LINE_TOKEN}",
        "Content-Type": "application/json"
    }

    payload = {
        "messages": [{"type": "text", "text": m[:5000]} for m in messages]
    }

    res = requests.post(url, headers=headers, json=payload)
    print("Status:", res.status_code)
    print("Response:", res.text)

def main():
    with open("config.json", encoding="utf-8") as f:
        config = json.load(f)

    today = datetime.now(JST)

    category = config["categories"][0]  # ★まず1件だけに固定

    news = fetch_news(category["rss"])

    if not news:
        send_line(["ニュース取得失敗"])
        return

    try:
        ai_text = call_openai(news["title"], news["summary"])
        time.sleep(5)  # ★ここ重要（絶対入れる）
    except Exception as e:
        print("AI失敗:", e)
        ai_text = fallback(news["title"], news["summary"])

    msg = f"""【{category['name']}】
{news['title']}

{ai_text}

▼リンク
{news['link']}"""

    header = f"""【今日のニュース】
{today.strftime('%Y/%m/%d')}
"""

    send_line([header, msg])

if __name__ == "__main__":
    main()
