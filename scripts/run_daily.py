#!/usr/bin/env python3
"""
Orchestrator: run the full daily report pipeline.
  1. Fetch market data → data/market.json
  2. Fetch news → data/news.json
  3. Generate report → docs/stock-YYYY-MM-DD.html

Usage:
  python run_daily.py
  python run_daily.py --provider groq
  python run_daily.py --provider ollama --ollama-model llama3.1
  python run_daily.py --dry-run   (skip LLM, just fetch data)
"""

import os
import sys
import subprocess
import argparse
from datetime import datetime, timezone, timedelta


def run(cmd: list, label: str) -> int:
    """Run a subprocess and print output."""
    print(f"\n{'='*60}", file=sys.stderr)
    print(f"▶ {label}", file=sys.stderr)
    print(f"  {' '.join(cmd)}", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)

    result = subprocess.run(cmd, capture_output=False)
    if result.returncode != 0:
        print(f"❌ {label} failed with code {result.returncode}", file=sys.stderr)
    return result.returncode


def main():
    parser = argparse.ArgumentParser(description="Run full daily report pipeline")
    parser.add_argument("--provider", default="groq",
                        choices=["groq", "claude", "ollama"])
    parser.add_argument("--model", help="Override model name")
    parser.add_argument("--ollama-model", default="llama3.1")
    parser.add_argument("--dry-run", action="store_true",
                        help="Fetch data only, skip LLM")
    parser.add_argument("--market-only", choices=["hk", "us"],
                        help="Only fetch one market")
    args = parser.parse_args()

    # Paths
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_dir = os.path.dirname(script_dir)
    data_dir = os.path.join(project_dir, "data")
    docs_dir = os.path.join(project_dir, "docs")
    os.makedirs(data_dir, exist_ok=True)
    os.makedirs(docs_dir, exist_ok=True)

    market_file = os.path.join(data_dir, "market.json")
    news_file = os.path.join(data_dir, "news.json")

    tz_hk = timezone(timedelta(hours=8))
    now = datetime.now(tz_hk)
    print(f"🕐 Current time (HKT): {now.strftime('%Y-%m-%d %H:%M')}", file=sys.stderr)

    # Step 1: Fetch market data
    market_cmd = [
        sys.executable,
        os.path.join(script_dir, "fetch_market.py"),
        "--output", market_file,
    ]
    if args.market_only:
        market_cmd += ["--market", args.market_only]

    rc = run(market_cmd, "Step 1: Fetch Market Data")
    if rc != 0:
        print("⚠️ Market fetch had issues, continuing...", file=sys.stderr)

    # Step 2: Fetch news
    news_cmd = [
        sys.executable,
        os.path.join(script_dir, "fetch_news.py"),
        "--json",
        "--output", news_file,
    ]
    rc = run(news_cmd, "Step 2: Fetch News")
    if rc != 0:
        print("⚠️ News fetch had issues, continuing...", file=sys.stderr)

    # Step 3: Generate report
    if args.dry_run:
        print("\n🏁 Dry run complete. Data saved to:", file=sys.stderr)
        print(f"  Market: {market_file}", file=sys.stderr)
        print(f"  News:   {news_file}", file=sys.stderr)
        return

    report_cmd = [
        sys.executable,
        os.path.join(script_dir, "generate_report.py"),
        "--market", market_file,
        "--news", news_file,
        "--output", docs_dir,
        "--provider", args.provider,
    ]
    if args.model:
        report_cmd += ["--model", args.model]
    if args.provider == "ollama":
        report_cmd += ["--ollama-model", args.ollama_model]

    rc = run(report_cmd, "Step 3: Generate Report via LLM")
    if rc != 0:
        print("❌ Report generation failed!", file=sys.stderr)
        sys.exit(1)

    print("\n" + "="*60, file=sys.stderr)
    print("🎉 Pipeline complete!", file=sys.stderr)
    print(f"📄 Report: docs/stock-{now.strftime('%Y-%m-%d')}.html", file=sys.stderr)
    print("="*60, file=sys.stderr)


if __name__ == "__main__":
    main()
