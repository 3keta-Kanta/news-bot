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


# =========================
# 共通処理
# =========================
def clean(text):
    text = html.unescape(text)
    text = re.sub("<.*?>", "", text)
    return text.strip()


def fetch_entries(rss):
    feed = feedparser.parse(rss)
    return feed.entries if feed.entries else []


# =========================
# 重複防止
# =========================
used_links = set()


# =========================
# 記事選定ロジック（改善版）
# =========================
def choose_entry(entries, category):
    local_candidates = []
    regional_candidates = []
    prefer_candidates = []
    other_candidates = []

    for e in entries:
        link = e.link
        if link in used_links:
            continue

        text = (e.title + " " + getattr(e, "summary", "")).lower()

        # 除外
        if any(k.lower() in text for k in category.get("avoid_keywords", [])):
            continue

        # 地域優先
        if any(k.lower() in text for k in category.get("must_keywords", [])):
            local_candidates.append(e)

        elif any(k.lower() in text for k in category.get("regional_keywords", [])):
            regional_candidates.append(e)

        # 国際偏り制御
        elif any(k.lower() in text for k in category.get("prefer_keywords", [])):
            prefer_candidates.append(e)

        else:
            other_candidates.append(e)

    selected = None

    if local_candidates:
        selected = local_candidates[0]
    elif regional_candidates:
        selected = regional_candidates[0]
    elif prefer_candidates:
        selected = prefer_candidates[0]
    elif other_candidates:
        selected = other_candidates[0]

    if selected:
        used_links.add(selected.link)

    return selected


# =========================
# AI呼び出し
# =========================
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


# =========================
# フォールバック
# =========================
def fallback(summary):
    return f"""🐾何があった？
{summary[:60]}...

🐕かんた解説
ちょっとむずかしいけど生活につながる話かも。

⭐なぜ大事？
社会の流れを知るきっかけになる。

💭考えてみよう
これ、自分の生活や将来とどうつながると思う？"""


# =========================
# LINE送信
# =========================
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


# =========================
# カテゴリ処理
# =========================
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
        time.sleep(8)
    except Exception as ex:
        print("AI失敗:", ex)
        ai_text = fallback(summary)

    return f"""【{cat['name']}】
{title}

{ai_text}

▼リンク
{e.link}"""


# =========================
# メイン
# =========================
def main():
    with open("config.json", encoding="utf-8") as f:
        config = json.load(f)

    with open("prompt.txt", encoding="utf-8") as f:
        prompt = f.read()

    now = datetime.now()
    date_str = now.strftime("%-m/%-d(%a)")

    messages = [f"【{date_str} 更新ニュース（かんた🐕‍🦺）】"]

    for cat in config["categories"]:
        msg = process_category(cat, prompt)
        if msg:
            messages.append(msg)

    send_line(messages)


if __name__ == "__main__":
    main()
