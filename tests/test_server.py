import asyncio

from antislop_mcp.server import MAX_REWRITE_WORDS, RewriteRequest, antislop_rewrite, count_words


def test_count_words_uses_whitespace_boundaries():
    assert count_words("one two\nthree") == 3


def test_oversized_rewrite_fails_fast_with_chunking_guidance():
    request = RewriteRequest(text="word " * (MAX_REWRITE_WORDS + 1))
    result = asyncio.run(antislop_rewrite(request))

    assert result["status"] == "needs_chunking"
    assert result["word_count"] == MAX_REWRITE_WORDS + 1
    assert result["max_words_per_call"] == MAX_REWRITE_WORDS
    assert "heading or paragraph boundaries" in result["message"]
