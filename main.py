import os
import json
import time
import html
import re
from datetime import datetime

import feedparser
import requests


LINE_TOKEN = os.getenv("LINE_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")


def clean(text):
    text = html.unescape(text)
    text = re.sub("<.*?>", "", text)
    return text.strip()


def fetch_entries(rss):
    feed = feedparser.parse(rss)
    return feed.entries if feed.entries else []


# ✅ 重複防止
used_links = set()


def choose_entry(entries, category):
    for e in entries:
        link = e.link
        text = e.title + getattr(e, "summary", "")

        if link in used_links:
            continue

        # ローカルフィルタ
        if "keywords" in category:
            if not any(k in text for k in category["keywords"]):
                continue

        used_links.add(link)
        return e

    return None


def call_openai(prompt, title, summary):
    url = "https://api.openai.com/v1/chat/completions"

    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }

    content = prompt + f"\n\nニュース:\n{title}\n{summary}"

    body = {
        "model": OPENAI_MODEL,
        "messages": [{"role": "user", "content": content}],
        "temperature": 0.5
    }

    res = requests.post(url, headers=headers, json=body)
    res.raise_for_status()

    return res.json()["choices"][0]["message"]["content"]


def fallback(summary):
    return f"""🐾何があった？
{summary[:60]}...

🐕かんたの簡単解説
ちょっとむずかしいけど、生活につながる話だよ。

⭐なぜ大事？
社会の流れを知るきっかけになる。

💭考えてみよう
これ、自分の生活とどうつながりそう？"""


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


def process_category(cat, prompt):
    entries = fetch_entries(cat["rss"])
    if not entries:
        return None

    e = choose_entry(entries, cat)
    if not e:
        return None

    title = clean(e.title)
    summary = clean(getattr(e, "summary", title))

    try:
        ai_text = call_openai(prompt, title, summary)
        time.sleep(10)
    except Exception as ex:
        print("AI失敗:", ex)
        ai_text = fallback(summary)

    return f"""【{cat['name']}】
{title}

{ai_text}

▼リンク
{e.link}"""


def main():
    with open("config.json", encoding="utf-8") as f:
        config = json.load(f)

    with open("prompt.txt", encoding="utf-8") as f:
        prompt = f.read()

    # ✅ 日付追加
    now = datetime.now()
    date_str = now.strftime("%-m/%-d(%a)")

    header = f"【{date_str}のニュース（かんた🐕‍🦺）】"
    messages = [header]

    for cat in config["categories"]:
        msg = process_category(cat, prompt)
        if msg:
            messages.append(msg)

    send_line(messages)


if __name__ == "__main__":
    main()
