from antislop_mcp.client import AntislopClient, strip_thinking


def test_strip_thinking_removes_orphaned_and_balanced_blocks():
    assert strip_thinking("<think>private</think>answer") == "answer"
    assert strip_thinking("private reasoning</think>answer") == "answer"


def test_default_timeout_allows_long_local_generations(monkeypatch):
    monkeypatch.delenv("ANTISLOP_TIMEOUT", raising=False)
    assert AntislopClient().timeout == 240


def test_timeout_can_be_overridden(monkeypatch):
    monkeypatch.setenv("ANTISLOP_TIMEOUT", "420")
    assert AntislopClient().timeout == 420

