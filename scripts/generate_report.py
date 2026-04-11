#!/usr/bin/env python3
"""
Main report generator.
1. Load market data JSON + news JSON
2. Send to LLM (Groq / Claude / Ollama) for analysis
3. Generate styled HTML report
4. Update index.html

Usage:
  python generate_report.py --market data/market.json --news data/news.json --output docs/
  python generate_report.py --provider groq   (default)
  python generate_report.py --provider claude
  python generate_report.py --provider ollama --ollama-model llama3.1
"""

import json
import os
import sys
import argparse
from datetime import datetime, timezone, timedelta
from string import Template

# ── LLM Provider Abstraction ─────────────────────────────

def call_groq(prompt: str, model: str = "llama-3.3-70b-versatile") -> str:
    """Call Groq API (OpenAI-compatible)."""
    from openai import OpenAI

    client = OpenAI(
        base_url="https://api.groq.com/openai/v1",
        api_key=os.environ.get("GROQ_API_KEY", ""),
    )

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "你是一位專業的港美股分析師，擅長從大量財經數據中提煉關鍵資訊，用繁體中文撰寫專業但易懂的市場日報。"},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
        max_tokens=4096,
    )
    return response.choices[0].message.content


def call_claude(prompt: str, model: str = "claude-sonnet-4-20250514") -> str:
    """Call Claude API."""
    import anthropic

    client = anthropic.Anthropic()
    message = client.messages.create(
        model=model,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


def call_ollama(prompt: str, model: str = "llama3.1") -> str:
    """Call Ollama local API."""
    import urllib.request

    data = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
    }).encode("utf-8")

    req = urllib.request.Request(
        "http://localhost:11434/api/generate",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        result = json.loads(resp.read())
    return result.get("response", "")


PROVIDERS = {
    "groq": call_groq,
    "claude": call_claude,
    "ollama": call_ollama,
}


# ── Prompt Construction ──────────────────────────────────

def build_prompt(market_data: dict, news_data: dict) -> str:
    """Build the analysis prompt for the LLM."""

    # Format market data summary
    market_summary = ""

    if "hk" in market_data:
        market_summary += "\n=== 港股行情 ===\n"
        for idx in market_data["hk"].get("indices", []):
            if "error" not in idx:
                arrow = "🔴" if idx["change_pct"] < 0 else "🟢"
                market_summary += f"{arrow} {idx['name']}({idx['symbol']}): {idx['close']} ({idx['change_pct']:+.2f}%)\n"
        market_summary += "\n港股個股:\n"
        for s in market_data["hk"].get("stocks", []):
            if "error" not in s:
                market_summary += f"  {s['name']}({s['symbol']}): {s['close']} ({s['change_pct']:+.2f}%)\n"

        if "top_gainers" in market_data["hk"]:
            market_summary += "\n港股升幅榜:\n"
            for s in market_data["hk"]["top_gainers"]:
                market_summary += f"  🟢 {s['name']}: {s['change_pct']:+.2f}%\n"
            market_summary += "\n港股跌幅榜:\n"
            for s in market_data["hk"]["top_losers"]:
                market_summary += f"  🔴 {s['name']}: {s['change_pct']:+.2f}%\n"

    if "us" in market_data:
        market_summary += "\n=== 美股行情 ===\n"
        for idx in market_data["us"].get("indices", []):
            if "error" not in idx:
                arrow = "🔴" if idx["change_pct"] < 0 else "🟢"
                market_summary += f"{arrow} {idx['name']}({idx['symbol']}): {idx['close']} ({idx['change_pct']:+.2f}%)\n"
        market_summary += "\n美股個股:\n"
        for s in market_data["us"].get("stocks", []):
            if "error" not in s:
                market_summary += f"  {s['name']}({s['symbol']}): {s['close']} ({s['change_pct']:+.2f}%)\n"

        if "top_gainers" in market_data["us"]:
            market_summary += "\n美股升幅榜:\n"
            for s in market_data["us"]["top_gainers"]:
                market_summary += f"  🟢 {s['name']}: {s['change_pct']:+.2f}%\n"
            market_summary += "\n美股跌幅榜:\n"
            for s in market_data["us"]["top_losers"]:
                market_summary += f"  🔴 {s['name']}: {s['change_pct']:+.2f}%\n"

    if "other" in market_data:
        market_summary += "\n=== 其他指標 ===\n"
        for s in market_data["other"]:
            if "error" not in s:
                market_summary += f"  {s['name']}: {s['close']} ({s['change_pct']:+.2f}%)\n"

    # Format news
    news_text = ""
    for a in news_data.get("articles", [])[:50]:  # Limit to 50 articles
        news_text += f"【{a['source']}】{a['title']}\n"
        if a.get("content"):
            news_text += f"  {a['content'][:200]}\n"
        news_text += "\n"

    date_str = market_data.get("date", news_data.get("date", ""))

    prompt = f"""你是港美股首席分析師。根據以下 {date_str} 的市場數據和財經新聞，生成一份結構化的繁體中文日報分析。

【市場數據】
{market_summary}

【財經新聞】
{news_text}

請嚴格以下面的 JSON 格式回覆，不要加任何 markdown 標記或說明文字：

{{
  "date": "{date_str}",
  "core_summary": "2-3句精煉總結今日港美股走勢及關鍵驅動因素",
  "hk_market": {{
    "overview": "港股今日整體表現描述（2-3句）",
    "key_movers": [
      {{"name": "股票名", "symbol": "代碼", "change": "+X.XX%", "reason": "原因"}}
    ],
    "sector_analysis": "板塊輪動分析（科技、金融、地產、消費等）"
  }},
  "us_market": {{
    "overview": "美股昨晚表現描述（2-3句）",
    "key_movers": [
      {{"name": "股票名", "symbol": "代碼", "change": "+X.XX%", "reason": "原因"}}
    ],
    "sector_analysis": "板塊分析"
  }},
  "key_news": [
    {{
      "tag": "分類標籤（從以下選：地緣政治/監管政策/總經數據/央行動態/企業財報/併購消息/IPO/行業趨勢）",
      "emoji": "對應emoji",
      "title": "新聞標題（15字內）",
      "summary": "2-3句描述事件及對港美股的影響",
      "impact": "利好/利淡/中性"
    }}
  ],
  "macro_indicators": {{
    "summary": "重要總經數據摘要",
    "upcoming": "近期需關注的經濟事件/數據公佈"
  }},
  "risk_alerts": [
    "風險提示1",
    "風險提示2"
  ],
  "keywords": ["關鍵詞1", "關鍵詞2", "關鍵詞3", "關鍵詞4", "關鍵詞5"]
}}

要求：
1. key_news 選 4-6 條最重要的新聞，每條都要點出對港美股的實際影響
2. key_movers 港股和美股各選 3-5 隻最值得關注的個股
3. 所有內容用繁體中文
4. 保持專業但易懂的語調
5. 只回覆 JSON，不要任何額外文字"""

    return prompt


# ── HTML Generation ──────────────────────────────────────

def generate_html(analysis: dict, market_data: dict) -> str:
    """Generate the full HTML report page."""

    date_str = analysis.get("date", "")
    date_display = date_str  # e.g. "2026-04-10"

    # Parse date for Chinese display
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        weekdays = ["一", "二", "三", "四", "五", "六", "日"]
        date_display_cn = f"{dt.year}年{dt.month}月{dt.day}日 星期{weekdays[dt.weekday()]}"
    except Exception:
        date_display_cn = date_str

    # ── Build market table rows ──
    def make_table_rows(stocks: list, max_rows: int = 20) -> str:
        rows = ""
        for s in stocks[:max_rows]:
            if "error" in s:
                continue
            pct = s["change_pct"]
            if pct > 0:
                css_class = "price-up"
                arrow = "▲"
            elif pct < 0:
                css_class = "price-down"
                arrow = "▼"
            else:
                css_class = "price-neutral"
                arrow = "─"
            vol_str = ""
            if s.get("volume"):
                if s["volume"] >= 1_000_000_000:
                    vol_str = f"{s['volume']/1_000_000_000:.1f}B"
                elif s["volume"] >= 1_000_000:
                    vol_str = f"{s['volume']/1_000_000:.1f}M"
                else:
                    vol_str = f"{s['volume']/1_000:.0f}K"
            rows += f"""<tr>
              <td>{s['name']}<span class="symbol">{s['symbol']}</span></td>
              <td class="{css_class}">{s['close']}</td>
              <td class="{css_class}">{arrow} {pct:+.2f}%</td>
              <td>{vol_str}</td>
            </tr>\n"""
        return rows

    # ── Build news cards ──
    def make_news_cards(news_list: list) -> str:
        cards = ""
        impact_colors = {
            "利好": "#10B981",
            "利淡": "#EF4444",
            "中性": "#64748B",
        }
        for i, news in enumerate(news_list):
            impact = news.get("impact", "中性")
            color = impact_colors.get(impact, "#64748B")
            delay = f"{0.1 + i * 0.06:.2f}s"
            cards += f"""<div class="news-card" style="animation-delay:{delay}">
              <div class="card-header">
                <span class="news-emoji">{news.get('emoji', '📰')}</span>
                <span class="news-tag">{news.get('tag', '')}</span>
                <span class="impact-badge" style="background:{color}20;color:{color}">{impact}</span>
              </div>
              <h3>{news.get('title', '')}</h3>
              <p>{news.get('summary', '')}</p>
            </div>\n"""
        return cards

    # ── Build keyword tags ──
    def make_keywords(keywords: list) -> str:
        return "\n".join(f'<span class="keyword">{k}</span>' for k in keywords)

    # ── Build risk alerts ──
    def make_alerts(alerts: list) -> str:
        items = ""
        for a in alerts:
            items += f"<li>{a}</li>\n"
        return items

    # ── HK market data ──
    hk_indices_rows = ""
    hk_stocks_rows = ""
    if "hk" in market_data:
        hk_indices_rows = make_table_rows(market_data["hk"].get("indices", []))
        hk_stocks_rows = make_table_rows(market_data["hk"].get("stocks", []))

    # ── US market data ──
    us_indices_rows = ""
    us_stocks_rows = ""
    if "us" in market_data:
        us_indices_rows = make_table_rows(market_data["us"].get("indices", []))
        us_stocks_rows = make_table_rows(market_data["us"].get("stocks", []))

    # ── Other indicators ──
    other_rows = make_table_rows(market_data.get("other", []))

    # ── HK analysis ──
    hk_analysis = analysis.get("hk_market", {})
    us_analysis = analysis.get("us_market", {})
    macro = analysis.get("macro_indicators", {})

    # ── Key movers cards ──
    def make_movers(movers: list) -> str:
        html = ""
        for m in movers:
            change = m.get("change", "")
            is_up = "+" in str(change) and "-" not in str(change)
            css = "price-up" if is_up else "price-down"
            html += f"""<div class="mover-chip">
              <span class="mover-name">{m.get('name','')}</span>
              <span class="{css}">{change}</span>
              <span class="mover-reason">{m.get('reason','')}</span>
            </div>\n"""
        return html

    # Count sections
    section_count = 0
    for section in ["core_summary", "hk_market", "us_market", "key_news", "macro_indicators", "risk_alerts", "keywords"]:
        if analysis.get(section):
            section_count += 1

    html = f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>港美股日報 · {date_display_cn}</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#000;color:#E3F2FD;font-family:-apple-system,"PingFang TC","Noto Sans TC","Helvetica Neue",Arial,sans-serif;line-height:1.7;-webkit-font-smoothing:antialiased}}
body::before{{content:'';position:fixed;top:-40%;left:-20%;width:80%;height:80%;background:radial-gradient(circle,rgba(59,130,246,0.08) 0%,transparent 70%);pointer-events:none;z-index:0}}
body::after{{content:'';position:fixed;bottom:-30%;right:-20%;width:70%;height:70%;background:radial-gradient(circle,rgba(245,158,11,0.05) 0%,transparent 70%);pointer-events:none;z-index:0}}
.container{{max-width:900px;margin:0 auto;padding:60px 32px;position:relative;z-index:1}}

/* Header */
header{{display:flex;align-items:center;gap:16px;margin-bottom:36px;animation:fadeDown 0.6s ease both}}
.logo-icon{{width:52px;height:52px;border-radius:14px;background:linear-gradient(135deg,#3B82F6,#F59E0B);display:flex;align-items:center;justify-content:center;font-size:28px;flex-shrink:0}}
.header-text h1{{font-size:22px;font-weight:700;letter-spacing:0.5px}}
.header-meta{{display:flex;gap:8px;margin-top:6px;flex-wrap:wrap}}
.badge{{display:inline-flex;align-items:center;gap:4px;padding:3px 10px;border-radius:20px;font-size:11.5px;font-weight:500}}
.badge-date{{background:rgba(245,158,11,0.15);color:#F59E0B;border:1px solid rgba(245,158,11,0.25)}}
.badge-count{{background:rgba(100,116,139,0.15);color:#94A3B8;border:1px solid rgba(100,116,139,0.2)}}
.badge-hk{{background:rgba(239,68,68,0.12);color:#FCA5A5;border:1px solid rgba(239,68,68,0.2)}}
.badge-us{{background:rgba(59,130,246,0.12);color:#93C5FD;border:1px solid rgba(59,130,246,0.2)}}

/* Summary Card */
.summary-card{{background:linear-gradient(135deg,rgba(245,158,11,0.08),rgba(245,158,11,0.02));border:1px solid rgba(245,158,11,0.2);border-radius:16px;padding:24px 28px;margin-bottom:28px;animation:fadeUp 0.5s ease both}}
.summary-card h2{{font-size:15px;font-weight:600;color:#F59E0B;margin-bottom:12px;display:flex;align-items:center;gap:8px}}
.summary-card p{{font-size:14px;line-height:1.8;color:#CBD5E1}}

/* Sections */
.section{{margin-bottom:24px;animation:fadeUp 0.5s ease both}}
.section-title{{display:flex;align-items:center;gap:10px;font-size:16px;font-weight:600;margin-bottom:14px;color:#E3F2FD}}
.section-icon{{width:30px;height:30px;border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:16px;flex-shrink:0}}

/* Tables */
.data-table{{width:100%;border-collapse:collapse;font-size:13px;margin-bottom:12px}}
.data-table th{{text-align:left;padding:8px 10px;color:#64748B;font-weight:500;border-bottom:1px solid rgba(255,255,255,0.06);font-size:11.5px;text-transform:uppercase;letter-spacing:0.5px}}
.data-table td{{padding:7px 10px;border-bottom:1px solid rgba(255,255,255,0.04)}}
.data-table tr:hover{{background:rgba(255,255,255,0.02)}}
.symbol{{color:#64748B;font-size:11px;margin-left:6px}}
.price-up{{color:#10B981;font-weight:600}}
.price-down{{color:#EF4444;font-weight:600}}
.price-neutral{{color:#94A3B8}}

/* Cards */
.card{{background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.07);border-radius:16px;padding:20px 24px;margin-bottom:12px;transition:all 0.2s ease}}
.card:hover{{background:rgba(255,255,255,0.05);border-color:rgba(255,255,255,0.12);transform:translateY(-1px)}}
.card h3{{font-size:14.5px;font-weight:600;margin-bottom:8px}}
.card p{{font-size:13.5px;color:#94A3B8;line-height:1.75}}

/* News Cards */
.news-card{{background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.07);border-radius:14px;padding:18px 22px;margin-bottom:10px;transition:all 0.2s ease;animation:fadeUp 0.5s ease both}}
.news-card:hover{{background:rgba(255,255,255,0.05);border-color:rgba(245,158,11,0.2);transform:translateY(-2px)}}
.card-header{{display:flex;align-items:center;gap:8px;margin-bottom:8px}}
.news-emoji{{font-size:18px}}
.news-tag{{font-size:11.5px;color:#94A3B8;font-weight:500;background:rgba(100,116,139,0.15);padding:2px 8px;border-radius:10px}}
.impact-badge{{font-size:10.5px;font-weight:600;padding:2px 8px;border-radius:10px}}
.news-card h3{{font-size:14px;font-weight:600;margin-bottom:6px}}
.news-card p{{font-size:13px;color:#94A3B8;line-height:1.7}}

/* Movers */
.movers-grid{{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:12px}}
.mover-chip{{background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.08);border-radius:10px;padding:8px 14px;font-size:12.5px;display:flex;align-items:center;gap:8px}}
.mover-name{{font-weight:600;color:#E3F2FD}}
.mover-reason{{color:#64748B;font-size:11.5px}}

/* Keywords */
.keywords{{display:flex;flex-wrap:wrap;gap:8px;margin-top:8px}}
.keyword{{background:rgba(139,92,246,0.1);color:#A78BFA;border:1px solid rgba(139,92,246,0.2);padding:4px 14px;border-radius:20px;font-size:12.5px;font-weight:500;transition:all 0.2s}}
.keyword:hover{{background:rgba(139,92,246,0.2);transform:scale(1.03)}}

/* Alerts */
.alert-card{{background:rgba(239,68,68,0.06);border:1px solid rgba(239,68,68,0.15);border-left:3px solid #EF4444;border-radius:12px;padding:16px 20px;margin-bottom:10px}}
.alert-card ul{{list-style:none;padding:0}}
.alert-card li{{font-size:13px;color:#FCA5A5;padding:4px 0;line-height:1.6}}
.alert-card li::before{{content:"⚠️ ";margin-right:4px}}

/* Analysis text */
.analysis-text{{font-size:13.5px;color:#94A3B8;line-height:1.8;margin-bottom:12px}}

/* Footer */
.footer{{text-align:center;padding:40px 0 20px;color:#475569;font-size:11.5px;border-top:1px solid rgba(255,255,255,0.05);margin-top:40px}}

/* Table container for scroll on mobile */
.table-wrap{{overflow-x:auto;-webkit-overflow-scrolling:touch}}

/* Animations */
@keyframes fadeDown{{from{{opacity:0;transform:translateY(-16px)}}to{{opacity:1;transform:translateY(0)}}}}
@keyframes fadeUp{{from{{opacity:0;transform:translateY(16px)}}to{{opacity:1;transform:translateY(0)}}}}

/* Responsive */
@media(max-width:640px){{
  .container{{padding:32px 16px}}
  .header-text h1{{font-size:18px}}
  .data-table{{font-size:12px}}
  .movers-grid{{flex-direction:column}}
}}
</style>
</head>
<body>
<div class="container">

  <!-- Header -->
  <header>
    <div class="logo-icon">📊</div>
    <div class="header-text">
      <h1>港美股日報</h1>
      <div class="header-meta">
        <span class="badge badge-date">{date_display_cn}</span>
        <span class="badge badge-count">{section_count}個板塊</span>
        <span class="badge badge-hk">🇭🇰 港股</span>
        <span class="badge badge-us">🇺🇸 美股</span>
      </div>
    </div>
  </header>

  <!-- Core Summary -->
  <div class="summary-card">
    <h2>📋 核心摘要</h2>
    <p>{analysis.get('core_summary', '')}</p>
  </div>

  <!-- HK Market -->
  <div class="section" style="animation-delay:0.10s">
    <div class="section-title">
      <div class="section-icon" style="background:rgba(239,68,68,0.12)">🇭🇰</div>
      港股行情
    </div>
    <div class="card">
      <p class="analysis-text">{hk_analysis.get('overview', '')}</p>
      <div class="movers-grid">
        {make_movers(hk_analysis.get('key_movers', []))}
      </div>
      <p class="analysis-text">{hk_analysis.get('sector_analysis', '')}</p>
      <div class="table-wrap">
        <table class="data-table">
          <thead><tr><th>指數</th><th>收盤</th><th>漲跌</th><th>成交量</th></tr></thead>
          <tbody>{hk_indices_rows}</tbody>
        </table>
      </div>
      <details>
        <summary style="color:#64748B;font-size:12px;cursor:pointer;margin:8px 0">展開全部港股 ▾</summary>
        <div class="table-wrap">
          <table class="data-table">
            <thead><tr><th>股票</th><th>收盤</th><th>漲跌</th><th>成交量</th></tr></thead>
            <tbody>{hk_stocks_rows}</tbody>
          </table>
        </div>
      </details>
    </div>
  </div>

  <!-- US Market -->
  <div class="section" style="animation-delay:0.16s">
    <div class="section-title">
      <div class="section-icon" style="background:rgba(59,130,246,0.12)">🇺🇸</div>
      美股行情
    </div>
    <div class="card">
      <p class="analysis-text">{us_analysis.get('overview', '')}</p>
      <div class="movers-grid">
        {make_movers(us_analysis.get('key_movers', []))}
      </div>
      <p class="analysis-text">{us_analysis.get('sector_analysis', '')}</p>
      <div class="table-wrap">
        <table class="data-table">
          <thead><tr><th>指數</th><th>收盤</th><th>漲跌</th><th>成交量</th></tr></thead>
          <tbody>{us_indices_rows}</tbody>
        </table>
      </div>
      <details>
        <summary style="color:#64748B;font-size:12px;cursor:pointer;margin:8px 0">展開全部美股 ▾</summary>
        <div class="table-wrap">
          <table class="data-table">
            <thead><tr><th>股票</th><th>收盤</th><th>漲跌</th><th>成交量</th></tr></thead>
            <tbody>{us_stocks_rows}</tbody>
          </table>
        </div>
      </details>
    </div>
  </div>

  <!-- Other Indicators -->
  <div class="section" style="animation-delay:0.22s">
    <div class="section-title">
      <div class="section-icon" style="background:rgba(245,158,11,0.12)">🌐</div>
      市場指標
    </div>
    <div class="card">
      <div class="table-wrap">
        <table class="data-table">
          <thead><tr><th>指標</th><th>價格</th><th>漲跌</th><th>成交量</th></tr></thead>
          <tbody>{other_rows}</tbody>
        </table>
      </div>
    </div>
  </div>

  <!-- Key News -->
  <div class="section" style="animation-delay:0.28s">
    <div class="section-title">
      <div class="section-icon" style="background:rgba(139,92,246,0.12)">📰</div>
      重點新聞
    </div>
    {make_news_cards(analysis.get('key_news', []))}
  </div>

  <!-- Macro -->
  <div class="section" style="animation-delay:0.34s">
    <div class="section-title">
      <div class="section-icon" style="background:rgba(16,185,129,0.12)">📊</div>
      總經數據
    </div>
    <div class="card">
      <p class="analysis-text">{macro.get('summary', '')}</p>
      <p class="analysis-text" style="color:#F59E0B">📅 {macro.get('upcoming', '')}</p>
    </div>
  </div>

  <!-- Risk Alerts -->
  <div class="section" style="animation-delay:0.40s">
    <div class="section-title">
      <div class="section-icon" style="background:rgba(239,68,68,0.12)">🚨</div>
      風險提示
    </div>
    <div class="alert-card">
      <ul>
        {make_alerts(analysis.get('risk_alerts', []))}
      </ul>
    </div>
  </div>

  <!-- Keywords -->
  <div class="section" style="animation-delay:0.46s">
    <div class="section-title">
      <div class="section-icon" style="background:rgba(139,92,246,0.12)">#️⃣</div>
      熱門關鍵字
    </div>
    <div class="keywords">
      {make_keywords(analysis.get('keywords', []))}
    </div>
  </div>

  <!-- Footer -->
  <div class="footer">
    <p>港美股日報 · 自動生成於 {datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")} HKT</p>
    <p style="margin-top:4px">數據來源：Yahoo Finance · AAStocks · WSJ · CNBC · MarketWatch · ForexLive</p>
    <p style="margin-top:4px;color:#475569">⚠️ 本日報僅供參考，不構成任何投資建議</p>
  </div>

</div>
</body>
</html>"""

    return html


# ── Index Page Generator ─────────────────────────────────

def update_index(docs_dir: str, date_str: str):
    """Update or create index.html with links to all reports."""
    import glob

    # Find all report files
    pattern = os.path.join(docs_dir, "stock-*.html")
    files = sorted(glob.glob(pattern), reverse=True)

    links = ""
    for f in files:
        fname = os.path.basename(f)
        # Extract date from filename: stock-2026-04-10.html
        d = fname.replace("stock-", "").replace(".html", "")
        try:
            dt = datetime.strptime(d, "%Y-%m-%d")
            weekdays = ["一", "二", "三", "四", "五", "六", "日"]
            display = f"{dt.year}年{dt.month}月{dt.day}日 星期{weekdays[dt.weekday()]}"
        except Exception:
            display = d
        is_today = " (最新)" if d == date_str else ""
        links += f'<a href="{fname}" class="report-link"><span class="report-date">{display}{is_today}</span></a>\n'

    index_html = f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>港美股日報</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#000;color:#E3F2FD;font-family:-apple-system,"PingFang TC","Noto Sans TC",sans-serif;line-height:1.7}}
.container{{max-width:600px;margin:0 auto;padding:60px 24px}}
h1{{font-size:24px;margin-bottom:8px}}
.subtitle{{color:#64748B;font-size:14px;margin-bottom:32px}}
.report-link{{display:block;padding:14px 18px;margin-bottom:8px;background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.07);border-radius:12px;text-decoration:none;color:#E3F2FD;transition:all 0.2s}}
.report-link:hover{{background:rgba(59,130,246,0.08);border-color:rgba(59,130,246,0.2);transform:translateX(4px)}}
.report-date{{font-size:14px;font-weight:500}}
</style>
</head>
<body>
<div class="container">
<h1>📊 港美股日報</h1>
<p class="subtitle">每日自動生成 · 港股 + 美股 + 總經分析</p>
{links}
</div>
</body>
</html>"""

    with open(os.path.join(docs_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(index_html)
    print(f"✅ index.html updated", file=sys.stderr)


# ── Main ─────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Generate stock daily report")
    parser.add_argument("--market", required=True, help="Market data JSON file")
    parser.add_argument("--news", required=True, help="News data JSON file")
    parser.add_argument("--output", default="docs", help="Output directory")
    parser.add_argument("--provider", choices=["groq", "claude", "ollama"],
                        default="groq", help="LLM provider")
    parser.add_argument("--model", help="Override model name")
    parser.add_argument("--ollama-model", default="llama3.1",
                        help="Ollama model name")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print prompt without calling LLM")
    args = parser.parse_args()

    # Load data
    with open(args.market, "r", encoding="utf-8") as f:
        market_data = json.load(f)
    with open(args.news, "r", encoding="utf-8") as f:
        news_data = json.load(f)

    date_str = market_data.get("date", news_data.get("date", "unknown"))
    print(f"📊 Generating report for {date_str}...", file=sys.stderr)

    # Build prompt
    prompt = build_prompt(market_data, news_data)

    if args.dry_run:
        print("=== PROMPT ===")
        print(prompt)
        print(f"\n=== Prompt length: {len(prompt)} chars ===")
        return

    # Call LLM
    print(f"🤖 Calling {args.provider}...", file=sys.stderr)
    provider_fn = PROVIDERS[args.provider]

    if args.model:
        result_text = provider_fn(prompt, model=args.model)
    elif args.provider == "ollama":
        result_text = provider_fn(prompt, model=args.ollama_model)
    else:
        result_text = provider_fn(prompt)

    # Parse JSON from LLM response
    # Strip markdown code fences if present
    clean = result_text.strip()
    if clean.startswith("```"):
        clean = clean.split("\n", 1)[1] if "\n" in clean else clean[3:]
    if clean.endswith("```"):
        clean = clean[:-3]
    clean = clean.strip()
    if clean.startswith("json"):
        clean = clean[4:].strip()

    try:
        analysis = json.loads(clean)
    except json.JSONDecodeError as e:
        print(f"❌ Failed to parse LLM response as JSON: {e}", file=sys.stderr)
        print(f"Raw response:\n{result_text[:500]}", file=sys.stderr)
        # Try to extract JSON from response
        import re
        json_match = re.search(r'\{[\s\S]*\}', result_text)
        if json_match:
            try:
                analysis = json.loads(json_match.group())
                print("✅ Recovered JSON from response", file=sys.stderr)
            except json.JSONDecodeError:
                print("❌ Could not recover JSON. Exiting.", file=sys.stderr)
                sys.exit(1)
        else:
            sys.exit(1)

    # Generate HTML
    html = generate_html(analysis, market_data)

    # Write output
    os.makedirs(args.output, exist_ok=True)
    output_file = os.path.join(args.output, f"stock-{date_str}.html")
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"✅ Report saved: {output_file}", file=sys.stderr)

    # Save analysis JSON for reference
    analysis_file = os.path.join(args.output, f"stock-{date_str}.json")
    with open(analysis_file, "w", encoding="utf-8") as f:
        json.dump(analysis, f, ensure_ascii=False, indent=2)

    # Update index
    update_index(args.output, date_str)

    print(f"\n🎉 Done! Open {output_file} to view the report.", file=sys.stderr)


if __name__ == "__main__":
    main()
