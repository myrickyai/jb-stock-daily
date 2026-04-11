#!/usr/bin/env python3
"""
Fetch HK & US stock market data via yfinance.
Outputs JSON with index + individual stock performance.
"""

import json
import sys
import argparse
from datetime import datetime, timezone, timedelta

try:
    import yfinance as yf
except ImportError:
    print("ERROR: yfinance not installed. Run: pip install yfinance", file=sys.stderr)
    sys.exit(1)


# ── 港股追蹤標的 ──────────────────────────────────────────
HK_INDICES = {
    "^HSI": "恒生指數",
    "^HSTECH.HK": "恒生科技指數",
}

HK_STOCKS = {
    # 科技
    "0700.HK": "騰訊控股",
    "9988.HK": "阿里巴巴",
    "3690.HK": "美團",
    "9999.HK": "網易",
    "9618.HK": "京東集團",
    "1810.HK": "小米集團",
    "0285.HK": "比亞迪電子",
    "9888.HK": "百度集團",
    "0020.HK": "商湯集團",
    # 金融
    "0005.HK": "匯豐控股",
    "1398.HK": "工商銀行",
    "3988.HK": "中國銀行",
    "2318.HK": "中國平安",
    "0388.HK": "香港交易所",
    "1299.HK": "友邦保險",
    # 地產
    "0016.HK": "新鴻基地產",
    "1109.HK": "華潤置地",
    "0688.HK": "中國海外發展",
    # 消費 / 醫藥 / 能源
    "1211.HK": "比亞迪",
    "2015.HK": "理想汽車",
    "9866.HK": "蔚來",
    "9868.HK": "小鵬汽車",
    "0941.HK": "中國移動",
    "0883.HK": "中國海洋石油",
    "0857.HK": "中國石油天然氣",
    "2382.HK": "舜宇光學科技",
    "1024.HK": "快手",
    "6060.HK": "眾安在線",
    "2269.HK": "藥明生物",
    "9901.HK": "新東方",
    "2020.HK": "安踏體育",
    "0027.HK": "銀河娛樂",
    "1928.HK": "金沙中國",
    "0175.HK": "吉利汽車",
    "2333.HK": "長城汽車",
}

# ── 美股追蹤標的 ──────────────────────────────────────────
US_INDICES = {
    "^GSPC": "S&P 500",
    "^IXIC": "納斯達克綜合指數",
    "^DJI": "道瓊斯工業平均指數",
    "^VIX": "VIX 恐慌指數",
}

US_STOCKS = {
    # 科技巨頭 (Mag 7)
    "AAPL": "蘋果",
    "MSFT": "微軟",
    "GOOGL": "Alphabet",
    "AMZN": "亞馬遜",
    "NVDA": "英偉達",
    "META": "Meta",
    "TSLA": "特斯拉",
    # 半導體
    "TSM": "台積電",
    "AMD": "AMD",
    "AVGO": "博通",
    "QCOM": "高通",
    "MU": "美光",
    # 金融
    "JPM": "摩根大通",
    "GS": "高盛",
    "BAC": "美國銀行",
    # 其他重點
    "COIN": "Coinbase",
    "PLTR": "Palantir",
    "CRM": "Salesforce",
    "NFLX": "Netflix",
    "DIS": "迪士尼",
    "BA": "波音",
    "XOM": "埃克森美孚",
    "UNH": "聯合健康",
}

# ── 其他市場指標 ──────────────────────────────────────────
OTHER_INDICATORS = {
    "GC=F": "黃金期貨",
    "CL=F": "WTI 原油",
    "DX-Y.NYB": "美元指數",
    "^TNX": "美國10年期國債收益率",
    "BTC-USD": "比特幣",
    "ETH-USD": "以太坊",
}


def fetch_ticker_data(symbol: str, name: str, period: str = "5d") -> dict:
    """Fetch price data for a single ticker."""
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period=period)

        if hist.empty or len(hist) < 1:
            return {"symbol": symbol, "name": name, "error": "no data"}

        latest = hist.iloc[-1]
        prev = hist.iloc[-2] if len(hist) >= 2 else hist.iloc[-1]

        close = round(float(latest["Close"]), 2)
        prev_close = round(float(prev["Close"]), 2)
        change = round(close - prev_close, 2)
        change_pct = round((change / prev_close) * 100, 2) if prev_close != 0 else 0
        volume = int(latest["Volume"]) if latest["Volume"] > 0 else None
        high = round(float(latest["High"]), 2)
        low = round(float(latest["Low"]), 2)

        return {
            "symbol": symbol,
            "name": name,
            "close": close,
            "prev_close": prev_close,
            "change": change,
            "change_pct": change_pct,
            "high": high,
            "low": low,
            "volume": volume,
            "date": str(hist.index[-1].date()),
        }
    except Exception as e:
        return {"symbol": symbol, "name": name, "error": str(e)}


def fetch_group(tickers: dict, label: str) -> list:
    """Fetch data for a group of tickers."""
    results = []
    print(f"  Fetching {label} ({len(tickers)} tickers)...", file=sys.stderr)
    for symbol, name in tickers.items():
        data = fetch_ticker_data(symbol, name)
        results.append(data)
    return results


def main():
    parser = argparse.ArgumentParser(description="Fetch HK & US stock market data")
    parser.add_argument("--market", choices=["hk", "us", "all"], default="all",
                        help="Which market to fetch")
    parser.add_argument("--compact", action="store_true",
                        help="Only fetch indices + top movers")
    parser.add_argument("--output", help="Output file path (default: stdout)")
    args = parser.parse_args()

    tz_hk = timezone(timedelta(hours=8))
    now_hk = datetime.now(tz_hk)

    result = {
        "generated_at": now_hk.isoformat(),
        "date": now_hk.strftime("%Y-%m-%d"),
    }

    if args.market in ("hk", "all"):
        print("📊 Fetching HK market data...", file=sys.stderr)
        result["hk"] = {
            "indices": fetch_group(HK_INDICES, "HK Indices"),
            "stocks": fetch_group(HK_STOCKS, "HK Stocks"),
        }

    if args.market in ("us", "all"):
        print("📊 Fetching US market data...", file=sys.stderr)
        result["us"] = {
            "indices": fetch_group(US_INDICES, "US Indices"),
            "stocks": fetch_group(US_STOCKS, "US Stocks"),
        }

    print("📊 Fetching other indicators...", file=sys.stderr)
    result["other"] = fetch_group(OTHER_INDICATORS, "Other Indicators")

    # ── 計算今日之最 ──
    for market_key in ["hk", "us"]:
        if market_key not in result:
            continue
        stocks = [s for s in result[market_key]["stocks"] if "error" not in s]
        if stocks:
            top_gainers = sorted(stocks, key=lambda x: x["change_pct"], reverse=True)[:5]
            top_losers = sorted(stocks, key=lambda x: x["change_pct"])[:5]
            top_volume = sorted(stocks, key=lambda x: x["volume"] or 0, reverse=True)[:5]
            result[market_key]["top_gainers"] = top_gainers
            result[market_key]["top_losers"] = top_losers
            result[market_key]["top_volume"] = top_volume

    output_json = json.dumps(result, ensure_ascii=False, indent=2)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output_json)
        print(f"✅ Market data saved to {args.output}", file=sys.stderr)
    else:
        print(output_json)


if __name__ == "__main__":
    main()
