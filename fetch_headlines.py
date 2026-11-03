#!/usr/bin/env python3
"""
Fetch today's top financial and market news headlines via RSS, format them as JSON,
and save them to a file for market sentiment analysis.
"""

import argparse
import html
import json
import os
import sys
import urllib.request
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional

INDIAN_MARKET_FEEDS = [
    "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
    "https://www.moneycontrol.com/rss/marketreports.xml",
    "https://www.livemint.com/rss/markets",
]
DEFAULT_FEED_URL = INDIAN_MARKET_FEEDS[0]
DEFAULT_OUTPUT_FILE = "headlines.json"
DEFAULT_LIMIT = 5


def fetch_rss(url: str, timeout: int = 30) -> bytes:
    """Fetch raw XML data from an RSS feed URL, falling back to alternatives if needed."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) NewsFetcher/1.0"
    }

    candidates = [url] + [u for u in INDIAN_MARKET_FEEDS if u != url]
    last_err = None

    for candidate_url in candidates:
        try:
            request = urllib.request.Request(candidate_url, headers=headers)
            with urllib.request.urlopen(request, timeout=timeout) as response:
                if response.status == 200:
                    return response.read()
        except Exception as exc:
            last_err = exc
            continue

    raise RuntimeError(f"HTTP request failed across all candidate feeds: {last_err}")


def parse_rss_items(xml_content: bytes, limit: int = 5) -> List[Dict[str, Any]]:
    """Parse XML feed content and return a list of top headline items."""
    root = ET.fromstring(xml_content)
    
    # Standard RSS 2.0 items are under channel/item, or .//item
    items = root.findall(".//item")
    headlines: List[Dict[str, Any]] = []

    for item in items[:limit]:
        title = item.findtext("title", "").strip()
        link = item.findtext("link", "").strip()
        pub_date = item.findtext("pubDate", "").strip()
        description = item.findtext("description", "").strip()
        guid = item.findtext("guid", "").strip()

        # Clean HTML entities from title and description
        clean_title = html.unescape(title)
        clean_description = html.unescape(description)

        headline_entry: Dict[str, Any] = {
            "title": clean_title,
            "link": link,
            "published": pub_date,
            "description": clean_description,
        }
        if guid:
            headline_entry["guid"] = guid

        headlines.append(headline_entry)

    return headlines


def save_headlines_json(headlines: List[Dict[str, Any]], output_path: str) -> None:
    """Save headlines list to a JSON file."""
    output_dir = os.path.dirname(os.path.abspath(output_path))
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(headlines, f, indent=2, ensure_ascii=False)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch top news headlines via RSS and output as JSON."
    )
    parser.add_argument(
        "--url",
        default=DEFAULT_FEED_URL,
        help=f"RSS feed URL to fetch (default: {DEFAULT_FEED_URL})",
    )
    parser.add_argument(
        "--output",
        "-o",
        default=DEFAULT_OUTPUT_FILE,
        help=f"Path to output JSON file (default: {DEFAULT_OUTPUT_FILE})",
    )
    parser.add_argument(
        "--limit",
        "-n",
        type=int,
        default=DEFAULT_LIMIT,
        help=f"Number of headlines to fetch (default: {DEFAULT_LIMIT})",
    )
    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Suppress console output of parsed headlines",
    )

    args = parser.parse_args()

    try:
        print(f"Fetching headlines from: {args.url} ...", file=sys.stderr)
        xml_data = fetch_rss(args.url)
        headlines = parse_rss_items(xml_data, limit=args.limit)

        save_headlines_json(headlines, args.output)
        print(f"Successfully saved {len(headlines)} headlines to {args.output}\n", file=sys.stderr)

        if not args.quiet:
            json_output = json.dumps(headlines, indent=2, ensure_ascii=False)
            print(json_output)

        return 0

    except Exception as exc:
        print(f"Error fetching/parsing headlines: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
