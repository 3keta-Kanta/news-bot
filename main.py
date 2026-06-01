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

if not LINE_TOKEN:
    raise ValueError("LINE_TOKEN が設定されていません。")

if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY が設定されていません。")


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
    text = re.sub(r"\s+", " ", text).strip()
    return text


def fetch_entries(rss_url: str):
    feed = feedparser.parse(rss_url)
    return getattr(feed, "entries", [])


def get_entry_text(entry) -> str:
    title = clean_text(getattr(entry, "title", ""))
    summary = clean_text(getattr(entry, "summary", "") or getattr(entry, "description", "") or title)
    return f"{title} {summary}"


def score_entry(entry, category: dict) -> int:
    """
    地方ニュースや興味を引きそうな話題を拾うための簡易スコアリング。
    """
    text = get_entry_text(entry)
    score = 0

    must_keywords = category.get("must_keywords", [])
    if must_keywords:
        if not any(k in text for k in must_keywords):
            return -9999
        score += 10

    boost_keywords = category.get("boost_keywords", [])
    for k in boost_keywords:
        if k in text:
            score += 3

    strong_boost_keywords = category.get("strong_boost_keywords", [])
    for k in strong_boost_keywords:
        if k in text:
            score += 6

    avoid_keywords = category.get("avoid_keywords", [])
    for k in avoid_keywords:
        if k in text:
            score -= 4

    # タイトルが短すぎる/長すぎるものを少しだけ調整
    title = clean_text(getattr(entry, "title", ""))
    title_len = len(title)
    if 15 <= title_len <= 55:
        score += 2

    return score


def choose_best_entry(entries, category: dict):
    if not entries:
        return None

    scored = []
    for e in entries[:20]:
        s = score_entry(e, category)
        scored.append((s, e))

    scored.sort(key=lambda x: x[0], reverse=True)

    if not scored or scored[0][0] <= -9999:
        return None

    return scored[0][1]


def build_prompt(prompt_template: str, category_name: str) -> str:
    return prompt_template.replace("{category_name}", category_name)


def call_openai(prompt_text: str, title: str, summary: str, retries: int = 3) -> str:
    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }

    user_content = f"{prompt_text}\n\nニュースタイトル:\n{title}\n\nニュース本文/要約:\n{summary}"

    body = {
        "model": OPENAI_MODEL,
        "messages": [
            {"role": "user", "content": user_content}
        ],
        "temperature": 0.5
    }

    wait_seconds = 5
    last_error = None

    for attempt in range(retries):
        try:
            res = requests.post(url, headers=headers, json=body, timeout=60)
            res.raise_for_status()
            return res.json()["choices"][0]["message"]["content"]
        except requests.HTTPError as e:
            last_error = e
            status = e.response.status_code if e.response is not None else None

            # 429 の場合だけ待機して再試行
            if status == 429 and attempt < retries - 1:
                print(f"[WARN] OpenAI 429。{wait_seconds}秒待機して再試行します。")
                time.sleep(wait_seconds)
                wait_seconds *= 2
                continue
            raise

    raise last_error


def fallback_format(summary: str) -> str:
    summary = clean_text(summary)
    short_summary = summary[:70] + ("…" if len(summary) > 70 else "")

    return f"""▼何があった？
{short_summary}

▼かんた解説
ちょっとむずかしそうでも、生活や将来につながる話かもしれないワン。

▼なぜ大事？
社会の動きを知ると、自分の考えを持ちやすくなるワン。

▼考えてみよう
これ、自分の生活や将来とどうつながりそう？"""


def build_message(category_name: str, title: str, ai_text: str, link: str) -> str:
    return f"""【{category_name}】
{title}

{ai_text}

▼リンク
{link}"""


def chunk_list(items: List[str], chunk_size: int) -> List[List[str]]:
    return [items[i:i + chunk_size] for i in range(0, len(items), chunk_size)]


