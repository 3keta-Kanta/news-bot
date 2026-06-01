import os
import json
import time
import html
import re
from typing import List, Optional

import feedparser
import requests


LINE_TOKEN = os.getenv("LINE_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")


def load_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def clean_text(text: str) -> str:
    if not text:
        return ""
    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()


def fetch_entries(rss_url: str):
    feed = feedparser.parse(rss_url)
    return getattr(feed, "entries", [])


def choose_entry(entries):
    if not entries:
        return None
    return entries[0]


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
    return f"""▼何があった？
{summary[:60]}...

▼かんた解説
ちょっとむずかしそうでも大事なニュースだワン。

▼なぜ大事？
生活や将来に関係するかもしれないワン。

▼考えてみよう
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


def process_category(category, prompt):
    entries = fetch_entries(category["rss"])

    if not entries:
        return None

    e = choose_entry(entries)

    title = clean_text(e.title)
    summary = clean_text(getattr(e, "summary", e.title))

    try:
        ai_text = call_openai(prompt, title, summary)
        time.sleep(10)
    except Exception as ex:
        print("AI失敗:", ex)
        ai_text = fallback(summary)

    return f"""【{category['name']}】
{title}

{ai_text}

▼リンク
{e.link}"""


def main():
    config = load_json("config.json")
    prompt = load_text("prompt.txt")

    messages = ["【今日のニュース（かんた🐕）】"]

    for cat in config["categories"]:
        msg = process_category(cat, prompt)
        if msg:
            messages.append(msg)

    send_line(messages)


if __name__ == "__main__":
    main()
