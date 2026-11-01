#!/usr/bin/env python3
"""
Unit tests for fetch_headlines.py
"""

import json
import os
import tempfile
import unittest
from fetch_headlines import parse_rss_items, save_headlines_json

SAMPLE_RSS_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Sample News</title>
    <link>https://example.com</link>
    <description>Sample RSS Channel</description>
    <item>
      <title>Headline 1 &amp; Breaking News</title>
      <link>https://example.com/news/1</link>
      <pubDate>Wed, 28 Oct 2026 08:00:00 GMT</pubDate>
      <description>Summary of story 1 &lt;b&gt;bold&lt;/b&gt;</description>
      <guid>https://example.com/news/1#id</guid>
    </item>
    <item>
      <title>Headline 2</title>
      <link>https://example.com/news/2</link>
      <pubDate>Wed, 28 Oct 2026 07:30:00 GMT</pubDate>
      <description>Summary of story 2</description>
    </item>
    <item>
      <title>Headline 3</title>
      <link>https://example.com/news/3</link>
      <pubDate>Wed, 28 Oct 2026 07:00:00 GMT</pubDate>
      <description>Summary of story 3</description>
    </item>
    <item>
      <title>Headline 4</title>
      <link>https://example.com/news/4</link>
      <pubDate>Wed, 28 Oct 2026 06:30:00 GMT</pubDate>
      <description>Summary of story 4</description>
    </item>
    <item>
      <title>Headline 5</title>
      <link>https://example.com/news/5</link>
      <pubDate>Wed, 28 Oct 2026 06:00:00 GMT</pubDate>
      <description>Summary of story 5</description>
    </item>
    <item>
      <title>Headline 6 (Should be ignored by limit 5)</title>
      <link>https://example.com/news/6</link>
      <pubDate>Wed, 28 Oct 2026 05:30:00 GMT</pubDate>
      <description>Summary of story 6</description>
    </item>
  </channel>
</rss>
"""


class TestFetchHeadlines(unittest.TestCase):
    def test_parse_rss_items_limit(self):
        headlines = parse_rss_items(SAMPLE_RSS_XML, limit=5)
        self.assertEqual(len(headlines), 5)
        self.assertEqual(headlines[0]["title"], "Headline 1 & Breaking News")
        self.assertEqual(headlines[0]["link"], "https://example.com/news/1")
        self.assertEqual(headlines[0]["published"], "Wed, 28 Oct 2026 08:00:00 GMT")
        self.assertEqual(headlines[0]["guid"], "https://example.com/news/1#id")
        self.assertEqual(headlines[4]["title"], "Headline 5")

    def test_parse_rss_custom_limit(self):
        headlines = parse_rss_items(SAMPLE_RSS_XML, limit=2)
        self.assertEqual(len(headlines), 2)
        self.assertEqual(headlines[0]["title"], "Headline 1 & Breaking News")
        self.assertEqual(headlines[1]["title"], "Headline 2")

    def test_save_headlines_json(self):
        headlines = parse_rss_items(SAMPLE_RSS_XML, limit=3)
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            save_headlines_json(headlines, tmp_path)
            self.assertTrue(os.path.exists(tmp_path))
            with open(tmp_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            self.assertEqual(len(loaded), 3)
            self.assertEqual(loaded[0]["title"], "Headline 1 & Breaking News")
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)


if __name__ == "__main__":
    unittest.main()
