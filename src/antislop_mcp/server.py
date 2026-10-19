"""Stdio MCP adapter for a locally served Antislop model."""

from __future__ import annotations

from typing import Any, Literal

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from .service import ensure_app, request


class RewriteRequest(BaseModel):
    text: str = Field(min_length=1, max_length=100_000)
    mode: Literal["polish", "humanize", "continue"] = "humanize"
    context: str | None = Field(default=None, max_length=10_000)
    preserve: list[str] = Field(default_factory=list, max_length=50)
    max_tokens: int = Field(default=1200, ge=16, le=8192)
    temperature: float = Field(default=0.8, ge=0, le=2)


mcp = FastMCP(
    "antislop",
    instructions=(
        "Use antislop_rewrite for text intended for other people: drafts, posts, documents, product copy, "
        "and messages. Preserve meaning and review every rewrite. Do not use it for ordinary assistant replies, "
        "code, or factual verification. The tool runs against a local OpenAI-compatible Antislop endpoint."
    ),
)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False))
async def antislop_status() -> dict[str, Any]:
    """Check whether the locally served Antislop model is reachable."""
    return await ensure_app()


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False))
async def antislop_rewrite(request: RewriteRequest) -> dict[str, Any]:
    """Edit prose to sound more natural and less AI-generated while preserving its meaning.

    Use mode=polish for a light edit, humanize for a stronger rewrite, and continue when text ends mid-thought.
    Include exact words, names, numbers, URLs, or product terms that must remain unchanged in preserve.
    """
    instruction = {
        "polish": "Lightly polish this draft. Keep its structure and voice; change only what improves naturalness.",
        "humanize": "Rewrite this draft in a natural, specific human voice. Keep the author's intent and facts.",
        "continue": "Continue this text naturally from its ending. Match its voice and do not repeat the ending.",
    }[request.mode]
    if request.context:
        instruction += f"\nContext (do not include it in the output): {request.context}"
    if request.preserve:
        instruction += "\nPreserve these exact terms: " + ", ".join(request.preserve)
    status = await ensure_app()
    if status.get("status") == "unavailable":
        return {"status": "unavailable", "text": request.text, "message": status.get("message")}
    try:
        result = await request_service(
            {
                "action": "rewrite",
                "request": {
                    "text": request.text,
                    "instruction": instruction,
                    "max_tokens": request.max_tokens,
                    "temperature": request.temperature,
                },
            },
            timeout=120,
        )
    except (OSError, ValueError, TimeoutError) as exc:
        return {"status": "unavailable", "text": request.text, "message": str(exc)}
    if result.get("status") != "ok":
        return {"status": "unavailable", "text": request.text, "message": result.get("message")}
    output = result["text"]

    missing = [term for term in request.preserve if term not in output]
    if missing:
        return {
            "status": "rejected",
            "text": request.text,
            "message": "The rewrite dropped protected terms: " + ", ".join(missing),
        }
    return {"status": "ok", "text": output, "mode": request.mode, "model": result.get("model")}


async def request_service(body: dict[str, Any], timeout: float) -> dict[str, Any]:
    """Named wrapper keeps the MCP tool's request model separate from the socket request."""
    return await request(body, timeout=timeout)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
