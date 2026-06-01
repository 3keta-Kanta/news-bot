import os
import json
import time
import feedparser
import requests

LINE_TOKEN = os.getenv("LINE_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")


def load_config():
    with open("config.json", encoding="utf-8") as f:
        return json.load(f)


def load_prompt():
    with open("prompt.txt", encoding="utf-8") as f:
        return f.read()


def fetch_news(rss):
    feed = feedparser.parse(rss)
    if not feed.entries:
        return None

    e = feed.entries[0]
    return {
        "title": e.title,
        "summary": e.summary,
        "link": e.link
    }


def call_openai(prompt, title, summary):
    url = "https://api.openai.com/v1/chat/completions"

    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }

    full_prompt = prompt + f"\n\nニュース:\n{title}\n{summary}"

    body = {
        "model": OPENAI_MODEL,
        "messages": [{"role": "user", "content": full_prompt}],
        "temperature": 0.5
    }

    res = requests.post(url, headers=headers, json=body)
    res.raise_for_status()

    return res.json()["choices"][0]["message"]["content"]


def fallback(summary):
    return f"""▼何があった？
{summary[:60]}...

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
    config = load_config()
    prompt = load_prompt()

    category_list = config["categories"]

    messages = []

    for cat in category_list[:config["items_per_day"]]:
        news = fetch_news(cat["rss"])

        if not news:
            continue

        try:
            ai_text = call_openai(prompt, news["title"], news["summary"])
            time.sleep(10)
        except Exception as e:
            print("AI失敗:", e)
            ai_text = fallback(news["summary"])

        msg = f"""【{cat['name']}】
{news['title']}

{ai_text}

▼リンク
{news['link']}"""

        messages.append(msg)

    header = "【今日のニュース】"
    send_line([header] + messages)


if __name__ == "__main__":
    main()
