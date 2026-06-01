import os
import json
import html
import re
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import feedparser
import requests


# =========================
# 基本設定
# =========================
JST = ZoneInfo("Asia/Tokyo")

LINE_TOKEN = os.getenv("LINE_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

if not LINE_TOKEN:
    raise ValueError("LINE_TOKEN が設定されていません。GitHub Secrets を確認してください。")


# =========================
# 設定ファイル読み込み
# =========================
def load_config():
    with open("config.json", "r", encoding="utf-8") as f:
        return json.load(f)


# =========================
# 文字列整形
# =========================
def clean_text(text: str) -> str:
    if not text:
        return ""
    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def shorten_text(text: str, max_len: int) -> str:
    text = clean_text(text)
    if len(text) <= max_len:
        return text
    return text[:max_len].rstrip() + "…"


# =========================
# 曜日・カテゴリ選択
# =========================
def get_today_rule(config: dict):
    today = datetime.now(JST)
    weekday_key = today.strftime("%a")  # Mon, Tue, Wed...
    rules = config.get("weekday_rules", {})
    today_rule = rules.get(weekday_key, {})

    level = today_rule.get("level", config.get("level", "easy"))
    items_per_day = today_rule.get("items_per_day", config.get("items_per_day", 2))
    selected_categories = today_rule.get(
        "categories",
        config.get("default_categories", [])
    )

    return today, weekday_key, level, items_per_day, selected_categories


def build_category_map(config: dict):
    return {c["name"]: c for c in config.get("categories", [])}


# =========================
# RSS取得
# =========================
def fetch_top_entry(rss_url: str):
    feed = feedparser.parse(rss_url)
    if not getattr(feed, "entries", None):
        return None

    entry = feed.entries[0]
    title = clean_text(getattr(entry, "title", ""))
    summary = clean_text(getattr(entry, "summary", "") or getattr(entry, "description", ""))
    link = getattr(entry, "link", "")

    if not title:
        return None

    return {
        "title": title,
        "summary": summary,
        "link": link
    }


# =========================
# AI要約
# =========================
def build_ai_prompt(level: str, category_name: str, title: str, summary: str):
    if level == "hard":
        level_instruction = (
            "高校生上級者向けに、背景も少し入れてください。"
            "ただし長くしすぎず、1項目あたり2文以内にしてください。"
        )
    elif level == "normal":
        level_instruction = (
            "高校1年生向けに、やや丁寧に説明してください。"
            "ただし1項目あたり2文以内にしてください。"
        )
    else:
        level_instruction = (
            "高校1年生がすぐ読めるように、やさしい言葉で説明してください。"
            "難しい用語はできるだけ避け、1項目あたり1〜2文にしてください。"
        )

    system_prompt = f"""
あなたは高校1年生向けの時事ニュース解説編集者です。
LINEで読む前提なので、短く・見やすく・興味を持てる表現にしてください。

条件:
- {level_instruction}
- 1項目は短く、LINEで見やすい長さにする
- タイトルは必要に応じて短く整える
- 「▼何があった？」「▼かんたん解説」「▼なぜ大事？」「▼考えてみよう」を作る
- 「▼考えてみよう」は押しつけず、考えやすい質問にする
- 出力は必ず JSON 形式
- JSONのキーは以下のみ:
  short_title
  what_happened
  easy_explanation
  why_important
  question
"""

    user_prompt = f"""
カテゴリ: {category_name}
レベル: {level}

ニュースタイトル:
{title}

ニュース要約:
{summary}
"""

    return system_prompt, user_prompt


def call_openai_for_news(level: str, category_name: str, title: str, summary: str):
    if not OPENAI_API_KEY:
        return fallback_format(level, category_name, title, summary)

    system_prompt, user_prompt = build_ai_prompt(level, category_name, title, summary)

    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": OPENAI_MODEL,
        "temperature": 0.4,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
    }

    response = requests.post(url, headers=headers, json=payload, timeout=60)
    response.raise_for_status()

    data = response.json()
    content = data["choices"][0]["message"]["content"]
    parsed = json.loads(content)

    return {
        "short_title": shorten_text(parsed.get("short_title", title), 34),
        "what_happened": shorten_text(parsed.get("what_happened", ""), 90),
        "easy_explanation": shorten_text(parsed.get("easy_explanation", ""), 120),
        "why_important": shorten_text(parsed.get("why_important", ""), 90),
        "question": shorten_text(parsed.get("question", ""), 60),
    }


def fallback_format(level: str, category_name: str, title: str, summary: str):
    # AIキー未設定時の簡易フォールバック
    short_title = shorten_text(title, 34)
    compact = shorten_text(summary, 85)

    if level == "hard":
        easy_explanation = "背景まで考えると、社会や経済の流れを見る手がかりになるニュースです。"
        why_important = "一つの出来事が、企業・政府・海外との関係に広がることがあります。"
        question = "この話題は将来の進路や仕事にどうつながると思う？"
    elif level == "normal":
        easy_explanation = "ニュースの表面だけでなく、その後に何が起きそうか考えると理解しやすいです。"
        why_important = "社会の動きは、生活やお金、将来の選択にもつながります。"
        question = "このニュースが続くと、日本や身近な生活にどんな影響がありそう？"
    else:
        easy_explanation = "むずかしく見えても、身近な生活や将来とつながるニュースとして読むとわかりやすいです。"
        why_important = "世の中の変化を知ると、学校で学ぶことの意味も見えやすくなります。"
        question = "自分の生活と結びつけると、どんなことが思い浮かぶ？"

    return {
        "short_title": short_title,
        "what_happened": compact,
        "easy_explanation": easy_explanation,
        "why_important": why_important,
        "question": question
    }


# =========================
# LINE送信用メッセージ整形
# =========================
def build_line_header(today: datetime, level: str, selected_categories: list, items_count: int):
    jp_weekdays = {
        "Mon": "月", "Tue": "火", "Wed": "水", "Thu": "木",
        "Fri": "金", "Sat": "土", "Sun": "日"
    }
    weekday_en = today.strftime("%a")
    weekday_jp = jp_weekdays.get(weekday_en, weekday_en)

    category_text = "・".join(selected_categories)
    return (
        f"【今日のニュース】\n"
        f"{today.strftime('%Y/%m/%d')}（{weekday_jp}）\n"
        f"レベル: {level}\n"
        f"カテゴリ: {category_text}\n"
        f"件数: {items_count}件"
    )


def build_line_news_message(category_name: str, article: dict, formatted: dict):
    return (
        f"【{category_name}】\n"
        f"{formatted['short_title']}\n\n"
        f"▼何があった？\n"
        f"{formatted['what_happened']}\n\n"
        f"▼かんたん解説\n"
        f"{formatted['easy_explanation']}\n\n"
        f"▼なぜ大事？\n"
        f"{formatted['why_important']}\n\n"
        f"▼考えてみよう\n"
        f"{formatted['question']}\n\n"
        f"▼リンク\n"
        f"{article['link']}"
    )


# =========================
# LINE送信
# =========================
def send_line_messages(message_texts: list[str]):
    # LINE Messaging API の messages は最大5件/回
    messages = []
    for text in message_texts[:5]:
        messages.append({
            "type": "text",
            "text": text[:5000]
        })

    url = "https://api.line.me/v2/bot/message/broadcast"
    headers = {
        "Authorization": f"Bearer {LINE_TOKEN}",
        "Content-Type": "application/json"
    }
    data = {
        "messages": messages
    }

    response = requests.post(url, headers=headers, json=data, timeout=60)
    print("Status:", response.status_code)
    print("Response:", response.text)
    response.raise_for_status()


# =========================
# メイン
# =========================
def main():
    config = load_config()
    category_map = build_category_map(config)

    today, weekday_key, level, items_per_day, selected_categories = get_today_rule(config)

    messages = []
    news_messages = []

    for category_name in selected_categories[:items_per_day]:
        category_info = category_map.get(category_name)
        if not category_info:
            print(f"[WARN] config.json にカテゴリ '{category_name}' が見つかりません。")
            continue

        article = fetch_top_entry(category_info["rss"])
        if not article:
            print(f"[WARN] RSS取得失敗: {category_name}")
            continue

        try:
            formatted = call_openai_for_news(
                level=level,
                category_name=category_name,
                title=article["title"],
                summary=article["summary"]
            )
            time.sleep(2)
        except Exception as e:
            print(f"[WARN] AI整形に失敗したためフォールバックします: {e}")
            formatted = fallback_format(
                level=level,
                category_name=category_name,
                title=article["title"],
                summary=article["summary"]
            )

        msg = build_line_news_message(category_name, article, formatted)
        news_messages.append(msg)

    if not news_messages:
        messages.append("【今日のニュース】\nニュースを取得できませんでした。RSS設定を確認してください。")
    else:
        header = build_line_header(today, level, selected_categories, len(news_messages))
        messages.append(header)
        messages.extend(news_messages)

    send_line_messages(messages)


if __name__ == "__main__":
    main()
