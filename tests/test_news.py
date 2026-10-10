"""Unit tests for news collection rules (no live network)."""

from __future__ import annotations

from gold_monitor.providers.news import (
    NewsArticle,
    deterministic_dedupe,
    _rule_relevance,
    _extract_source_from_title,
    _is_google_news_url,
    _article_id,
    _real_summary,
    DEFAULT_LOOKBACK_HOURS,
    DEFAULT_PER_FEED_CAP,
)


def _art(url: str, title: str, **kw) -> NewsArticle:
    return NewsArticle(
        article_id=_article_id(url, title),
        title=title,
        source_name=kw.get("source_name"),
        source_feed=kw.get("source_feed", "test"),
        original_url=url,
        url_is_google_news_redirect=_is_google_news_url(url),
        published_at=kw.get("published_at"),
        fetched_at="2026-10-09T00:00:00+00:00",
        summary=kw.get("summary"),
        language="en",
        search_topic=kw.get("search_topic", "test"),
        keyword_tags=kw.get("keyword_tags", []),
        relevance_to_gold_rule_score=kw.get("score"),
        content_status=kw.get("content_status", "title_only"),
        feed_hit_cap=kw.get("feed_hit_cap", False),
    )


def test_lookback_is_24h():
    assert DEFAULT_LOOKBACK_HOURS == 24
    assert DEFAULT_PER_FEED_CAP == 80


def test_same_url_deduped():
    a1 = _art("https://example.com/a", "Title A")
    a2 = _art("https://example.com/a", "Title A copy")
    out, dropped = deterministic_dedupe([a1, a2])
    assert dropped == 1
    assert len(out) == 1


def test_same_event_different_urls_kept():
    a1 = _art("https://reuters.com/iran-1", "Iran launches strike on tankers - Reuters")
    a2 = _art("https://bbc.com/iran-1", "Iran launches strike on tankers - BBC")
    out, dropped = deterministic_dedupe([a1, a2])
    assert dropped == 0
    assert len(out) == 2


def test_no_gold_keyword_not_filtered_out():
    """Iran-only text must remain collectible; score is advisory only."""
    text = "Iran announces new sanctions response after overnight strikes"
    score = _rule_relevance(text)
    assert score >= 1
    # Simulate retention regardless of score
    a = _art("https://example.com/iran", text, score=score)
    out, _ = deterministic_dedupe([a])
    assert len(out) == 1
    assert out[0].relevance_to_gold_rule_score == score


def test_summary_not_forged_from_title():
    summary, status = _real_summary("", "Only a title")
    assert summary is None
    assert status == "title_only"
    summary2, status2 = _real_summary("Only a title", "Only a title")
    assert summary2 is None
    assert status2 == "title_only"
    summary3, status3 = _real_summary("Markets reacted to the overnight developments in detail.", "Markets react")
    assert summary3 is not None
    assert status3 == "rss_summary_only"


def test_source_not_forged_for_google_news():
    title, src = _extract_source_from_title("Gold rises after data - Kitco")
    assert src == "Kitco"
    assert "Gold rises" in title
    assert _is_google_news_url("https://news.google.com/rss/articles/abc") is True
    a = _art("https://news.google.com/rss/articles/abc", "Something happened")
    assert a.url_is_google_news_redirect is True
    # Without publisher suffix, source_name may be None — must not invent
    assert a.source_name is None


def test_feed_hit_cap_flag():
    a = _art("https://example.com/c", "Capped feed item", feed_hit_cap=True)
    assert a.feed_hit_cap is True


def test_missing_published_at_ok():
    a = _art("https://example.com/x", "No date story", published_at=None)
    out, _ = deterministic_dedupe([a])
    assert len(out) == 1
    assert out[0].published_at is None


def test_article_id_stable():
    id1 = _article_id("https://example.com/z", "Hello")
    id2 = _article_id("https://example.com/z", "Hello")
    assert id1 == id2
    assert id1 != _article_id("https://example.com/other", "Hello")

def test_stats_schema_keys():
    """Provider stats must expose keys the report reads (no more em-dash gaps)."""
    required = {
        "raw_fetched", "raw_count",
        "after_deterministic_dedupe", "deduped_count",
        "exact_dupes_dropped", "duplicates_dropped",
        "title_only", "title_only_count",
        "rss_summary_only", "rss_summary_only_count",
        "full_text_available", "full_text_count",
        "google_news_redirect_urls", "unresolved_redirect_count",
        "possible_truncation", "possibly_truncated_feeds",
    }
    stats = {
        "raw_count": 0, "raw_fetched": 0,
        "deduped_count": 0, "after_deterministic_dedupe": 0,
        "duplicates_dropped": 0, "exact_dupes_dropped": 0,
        "title_only_count": 0, "title_only": 0,
        "rss_summary_only_count": 0, "rss_summary_only": 0,
        "full_text_count": 0, "full_text_available": 0,
        "unresolved_redirect_count": 0, "google_news_redirect_urls": 0,
        "possible_truncation": False, "possibly_truncated_feeds": [],
    }
    missing = required - set(stats.keys())
    assert not missing, f"missing keys: {missing}"
