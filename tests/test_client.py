from antislop_mcp.client import strip_thinking


def test_strip_thinking_removes_orphaned_and_balanced_blocks():
    assert strip_thinking("<think>private</think>answer") == "answer"
    assert strip_thinking("private reasoning</think>answer") == "answer"

