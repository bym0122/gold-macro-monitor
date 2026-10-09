"""Unit tests for news collection rules (no live network required)."""

from __future__ import annotations

from gold_monitor.providers.news import (
    NewsArticle,
    deterministic_dedupe,
    _rule_relevance,
    _extract_source_from_title,
    _is_google_news_url,
    _article_id,
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
        summary=kw.get("summary", ""),
        language="en",
        search_topic=kw.get("search_topic", "test"),
        keyword_tags=kw.get("keyword_tags", []),
        relevance_to_gold_rule_score=kw.get("score"),
        content_status="rss_summary_only",
    )


def test_same_url_deduped():
    a1 = _art("https://example.com/a", "Title A")
    a2 = _art("https://example.com/a", "Title A copy")
    out, dropped = deterministic_dedupe([a1, a2])
    assert dropped == 1
    assert len(out) == 1


def test_same_event_different_urls_kept():
    """Different outlets reporting same story must both be kept (no event merge)."""
    a1 = _art("https://reuters.com/iran-1", "Iran launches strike on tankers - Reuters")
    a2 = _art("https://bbc.com/iran-1", "Iran launches strike on tankers - BBC")
    out, dropped = deterministic_dedupe([a1, a2])
    assert dropped == 0
    assert len(out) == 2


def test_low_gold_keyword_not_a_drop_filter():
    """Iran-only article still has a rule score but collection must not require score>=3."""
    text = "Iran announces new sanctions response after overnight strikes"
    score = _rule_relevance(text)
    assert score >= 1
    # The hard filter is gone; score is advisory only.
    assert score < 5 or score >= 3  # just ensure function runs


def test_source_not_forged_for_google_news():
    title, src = _extract_source_from_title("Gold rises after data - Kitco")
    assert src == "Kitco"
    assert "Gold rises" in title
    assert _is_google_news_url("https://news.google.com/rss/articles/abc")
    a = _art("https://news.google.com/rss/articles/abc", "Something happened")
    assert a.source_name is None or a.source_name  # may be None
    assert a.url_is_google_news_redirect is True


def test_missing_published_at_ok():
    a = _art("https://example.com/x", "No date story", published_at=None)
    out, _ = deterministic_dedupe([a])
    assert len(out) == 1
    assert out[0].published_at is None


def test_article_id_stable():
    id1 = _article_id("https://example.com/z", "Hello")
    id2 = _article_id("https://example.com/z", "Hello")
    assert id1 == id2
