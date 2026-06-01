import feedparser
import requests
import os

LINE_TOKEN = os.getenv("LINE_TOKEN")

LEVEL = "easy"

CATEGORIES = [
    {"name": "国内", "rss": "https://www3.nhk.or.jp/rss/news/cat0.xml"},
    {"name": "海外", "rss": "http://feeds.bbci.co.uk/news/world/rss.xml"}
]

def make_explanation(text):
    if LEVEL == "easy":
        return f"かんたんに言うと、{text[:120]}...。つまり、生活に関係するニュースです。"
    else:
        return text[:150]

def send_line(msg):
    url = "https://api.line.me/v2/bot/message/broadcast"

    headers = {
        "Authorization": f"Bearer {LINE_TOKEN}",
        "Content-Type": "application/json"
    }

    data = {
        "messages": [
            {
                "type": "text",
                "text": msg[:5000]
            }
        ]
    }

    response = requests.post(url, headers=headers, json=data)

    print("Status:", response.status_code)
    print("Response:", response.text)

def main():
    result = []

    for cat in CATEGORIES:
        feed = feedparser.parse(cat["rss"])

        if not feed.entries:
            continue

        entry = feed.entries[0]
        explanation = make_explanation(entry.summary)

        msg = f"""【{cat['name']}】
{entry.title}

▼解説
{explanation}

▼リンク
{entry.link}
"""
        result.append(msg)

    final_msg = "\n\n".join(result)
    send_line(final_msg)

if __name__ == "__main__":
    main()
