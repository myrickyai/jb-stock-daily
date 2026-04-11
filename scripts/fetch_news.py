#!/usr/bin/env python3
"""
Fetch financial news from RSS feeds + scrape AAStocks HK news.
Sources: AAStocks, WSJ Markets, MarketWatch, CNBC, ForexLive, Reuters
"""

import json
import re
import sys
import argparse
from datetime import datetime, timezone, timedelta
from urllib.request import urlopen, Request
from urllib.error import URLError
from html import unescape

try:
    import feedparser
except ImportError:
    feedparser = None

# ── RSS 來源 ──────────────────────────────────────────────
RSS_FEEDS = [
    {
        "name": "WSJ Markets",
        "url": "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",
        "category": "us",
    },
    {
        "name": "MarketWatch",
        "url": "https://feeds.marketwatch.com/marketwatch/topstories/",
        "category": "us",
    },
    {
        "name": "CNBC",
        "url": "https://www.cnbc.com/id/100003114/device/rss/rss.html",
        "category": "us",
    },
    {
        "name": "ForexLive",
        "url": "https://www.forexlive.com/feed",
        "category": "macro",
    },
    {
        "name": "Reuters Business",
        "url": "https://www.reutersagency.com/feed/?best-topics=business-finance&post_type=best",
        "category": "global",
    },
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


# ── AAStocks 港股新聞抓取 ─────────────────────────────────
def fetch_aastocks_news(max_items: int = 30) -> list:
    """
    Scrape latest HK stock news from AAStocks.
    URL: https://www.aastocks.com/tc/stocks/news/aafn
    """
    articles = []
    url = "https://www.aastocks.com/tc/stocks/news/aafn"

    try:
        req = Request(url, headers={
            **HEADERS,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
        })
        with urlopen(req, timeout=20) as resp:
            html = resp.read().decode("utf-8", errors="replace")

        # AAStocks 新聞列表格式：提取新聞標題和連結
        # 匹配 /tc/stocks/news/aafn-con/... 頁面連結
        pattern = r'<a[^>]*href="(/tc/stocks/news/aafn-con/[^"]*)"[^>]*>\s*(.*?)\s*</a>'
        matches = re.findall(pattern, html, re.DOTALL)

        # 也嘗試匹配 data-newsid 格式
        pattern2 = r'class="[^"]*news[^"]*"[^>]*>.*?<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>'
        matches2 = re.findall(pattern2, html, re.DOTALL)

        all_matches = matches + matches2

        # 備用：匹配含有新聞內容的 div
        if not all_matches:
            pattern3 = r'<div[^>]*class="[^"]*newshead[^"]*"[^>]*>.*?<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>'
            all_matches = re.findall(pattern3, html, re.DOTALL)

        # 更寬泛的備用匹配
        if not all_matches:
            pattern4 = r'href="([^"]*aafn[^"]*)"[^>]*>\s*([^<]{10,})\s*<'
            all_matches = re.findall(pattern4, html)

        seen_titles = set()
        for link, title in all_matches[:max_items]:
            title = re.sub(r'<[^>]+>', '', title).strip()
            title = unescape(title)

            if not title or len(title) < 5 or title in seen_titles:
                continue
            seen_titles.add(title)

            full_link = f"https://www.aastocks.com{link}" if link.startswith("/") else link

            articles.append({
                "source": "AAStocks",
                "title": title,
                "link": full_link,
                "pubDate": datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d"),
                "content": "",
                "category": "hk",
            })

    except Exception as e:
        print(f"[WARNING] Failed to fetch AAStocks: {e}", file=sys.stderr)

    return articles


# ── RSS 抓取 ─────────────────────────────────────────────
def strip_html(text: str) -> str:
    """Remove HTML tags from text."""
    if not text:
        return ""
    clean = re.sub(r'<[^>]+>', '', text)
    clean = unescape(clean)
    return clean.strip()[:500]


def fetch_rss_feed(source: dict) -> list:
    """Fetch articles from a single RSS feed."""
    articles = []

    if feedparser:
        return fetch_rss_feedparser(source)

    # Fallback: manual XML parsing
    try:
        import xml.etree.ElementTree as ET
        req = Request(source["url"], headers=HEADERS)
        with urlopen(req, timeout=15) as resp:
            content = resp.read()

        root = ET.fromstring(content)
        items = root.findall(".//item")

        for item in items:
            def get(tag, fallback=""):
                el = item.find(tag)
                return (el.text or "").strip() if el is not None else fallback

            title = get("title")
            link = get("link")
            pub_date = get("pubDate")
            description = strip_html(get("description"))

            articles.append({
                "source": source["name"],
                "title": title,
                "link": link,
                "pubDate": pub_date,
                "content": description,
                "category": source.get("category", "global"),
            })

    except Exception as e:
        print(f"[WARNING] Failed to fetch {source['name']}: {e}", file=sys.stderr)

    return articles


def fetch_rss_feedparser(source: dict) -> list:
    """Fetch articles using feedparser library."""
    articles = []
    try:
        feed = feedparser.parse(source["url"])
        for entry in feed.entries:
            title = entry.get("title", "")
            link = entry.get("link", "")
            pub_date = entry.get("published", entry.get("updated", ""))
            summary = strip_html(entry.get("summary", entry.get("description", "")))

            articles.append({
                "source": source["name"],
                "title": title,
                "link": link,
                "pubDate": pub_date,
                "content": summary,
                "category": source.get("category", "global"),
            })
    except Exception as e:
        print(f"[WARNING] Failed to fetch {source['name']}: {e}", file=sys.stderr)

    return articles


# ── 日期過濾 ─────────────────────────────────────────────
def parse_date(date_str: str):
    """Parse various date formats."""
    if not date_str:
        return None
    formats = [
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S GMT",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(date_str.strip(), fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    return None


def filter_by_date(articles: list, target_date: str) -> list:
    """Filter articles by target date (HKT)."""
    tz_hk = timezone(timedelta(hours=8))
    try:
        target = datetime.strptime(target_date, "%Y-%m-%d").date()
    except ValueError:
        return articles

    filtered = []
    for a in articles:
        dt = parse_date(a.get("pubDate", ""))
        if dt:
            local_dt = dt.astimezone(tz_hk)
            if local_dt.date() == target:
                filtered.append(a)
        elif a.get("pubDate", "").startswith(target_date):
            # AAStocks 格式: "2026-04-10"
            filtered.append(a)

    return filtered


# ── 主程式 ───────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Fetch HK & US financial news")
    parser.add_argument("--date", help="Target date YYYY-MM-DD")
    parser.add_argument("--relative", choices=["yesterday", "today"],
                        help="Relative date")
    parser.add_argument("--source", choices=["all", "hk", "us", "macro"],
                        default="all", help="Filter by source category")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--output", help="Output file path")
    parser.add_argument("--no-aastocks", action="store_true",
                        help="Skip AAStocks scraping")
    args = parser.parse_args()

    tz_hk = timezone(timedelta(hours=8))
    now_hk = datetime.now(tz_hk)

    # Determine target date
    if args.date:
        target_date = args.date
    elif args.relative == "yesterday":
        target_date = (now_hk - timedelta(days=1)).strftime("%Y-%m-%d")
    else:
        target_date = now_hk.strftime("%Y-%m-%d")

    all_articles = []

    # Fetch RSS feeds
    for source in RSS_FEEDS:
        if args.source != "all" and source["category"] != args.source:
            continue
        print(f"  Fetching {source['name']}...", file=sys.stderr)
        articles = fetch_rss_feed(source)
        all_articles.extend(articles)

    # Fetch AAStocks
    if not args.no_aastocks and args.source in ("all", "hk"):
        print("  Fetching AAStocks 港股新聞...", file=sys.stderr)
        aastocks = fetch_aastocks_news()
        all_articles.extend(aastocks)
        print(f"  AAStocks: {len(aastocks)} articles found", file=sys.stderr)

    # Filter by date (optional, RSS 可能沒有精確日期)
    # filtered = filter_by_date(all_articles, target_date)
    # 由於部分 RSS 日期格式不一，先保留全部，讓 AI 篩選
    filtered = all_articles

    # Deduplicate by title similarity
    seen = set()
    deduped = []
    for a in filtered:
        key = a["title"][:30].lower()
        if key not in seen:
            seen.add(key)
            deduped.append(a)

    print(f"\n✅ Total: {len(deduped)} unique articles", file=sys.stderr)

    result = {
        "date": target_date,
        "count": len(deduped),
        "articles": deduped,
    }

    output_json = json.dumps(result, ensure_ascii=False, indent=2)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output_json)
        print(f"✅ News saved to {args.output}", file=sys.stderr)
    elif args.json:
        print(output_json)
    else:
        # Plain text output for AI consumption
        if not deduped:
            print(f"NO_CONTENT:{target_date}")
        else:
            print(f"DATE:{target_date}")
            print(f"COUNT:{len(deduped)}")
            print("---")
            for a in deduped:
                print(f"【來源】{a['source']}  【分類】{a['category']}")
                print(f"【標題】{a['title']}")
                print(f"【日期】{a['pubDate']}")
                print(f"【連結】{a['link']}")
                if a['content']:
                    print(f"【摘要】{a['content']}")
                print("\n---\n")


if __name__ == "__main__":
    main()
