"""SSE formatting helpers and multipart/mixed parser for Meta AI."""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator
from typing import Optional

from hubia.core.provider import StreamChunk

# ---------------------------------------------------------------------------
# SSE formatting  (OpenAI-compatible)
# ---------------------------------------------------------------------------


def format_sse_event(data: str) -> str:
    """Wrap *data* in a Server-Sent Event ``data:`` line.

    Returns a string suitable for writing directly to a ``text/event-stream``
    response.
    """
    return f"data: {data}\n\n"


def format_sse_done() -> str:
    """Return the OpenAI ``[DONE]`` sentinel event."""
    return "data: [DONE]\n\n"


# ---------------------------------------------------------------------------
# Meta AI multipart/mixed parser
# ---------------------------------------------------------------------------


def extract_boundary(content_type: str) -> str | None:
    """Extract the boundary string from a ``multipart/mixed`` Content-Type.

    Example::

        extract_boundary(
            "multipart/mixed; boundary=----WebKitFormBoundaryabc123"
        )
        # => "----WebKitFormBoundaryabc123"
    """
    match = re.search(r'boundary="?([^";\s]+)', content_type)
    if match:
        return match.group(1)
    return None


async def parse_multipart_mixed(
    body: bytes,
    boundary: str,
) -> AsyncIterator[StreamChunk]:
    """Parse a ``multipart/mixed`` response body into :class:`StreamChunk`\\ s.

    Each MIME part is expected to contain a JSON payload.  The parser yields
    a chunk for every part that has a ``"delta"`` key with a ``"text"``
    sub-key.  Parts containing ``"done": true`` yield a chunk with a
    ``"stop"`` finish reason and stop iteration.

    Args:
        body: Raw response body bytes.
        boundary: The MIME boundary string.

    Yields:
        :class:`StreamChunk` for each text delta.
    """
    boundary_bytes = boundary.encode("utf-8")
    separator = b"--" + boundary_bytes
    parts = body.split(separator)

    for part in parts:
        part = part.strip()
        if not part or part == b"--":
            continue

        # Split headers from body (headers end at first blank line)
        header_end = part.find(b"\r\n\r\n")
        if header_end == -1:
            header_end = part.find(b"\n\n")

        if header_end == -1:
            continue

        body_part = part[header_end:].strip()
        body_part = body_part.lstrip(b"\r\n").lstrip(b"\n")

        if not body_part:
            continue

        try:
            payload = json.loads(body_part)
        except json.JSONDecodeError:
            continue

        # Detect done marker
        if payload.get("done") is True:
            yield StreamChunk(content="", finish_reason="stop")
            return

        # Extract delta text
        delta = payload.get("delta")
        if isinstance(delta, dict):
            text = delta.get("text")
            if text:
                yield StreamChunk(content=text, finish_reason=None)
        elif isinstance(delta, str):
            yield StreamChunk(content=delta, finish_reason=None)

        # Also handle top-level ``text`` keys when there is no ``delta``
        if "delta" not in payload:
            text = payload.get("text")
            if text:
                yield StreamChunk(content=text, finish_reason=None)


# ---------------------------------------------------------------------------
# Stream conversion helpers
# ---------------------------------------------------------------------------


async def collect_stream(stream: AsyncIterator[StreamChunk]) -> str:
    """Collect all text from an async stream into a single string."""
    parts: list[str] = []
    async for chunk in stream:
        parts.append(chunk.content)
    return "".join(parts)


async def chunk_to_sse(chunk: StreamChunk) -> str:
    """Convert a single :class:`StreamChunk` to an OpenAI SSE ``data:`` line.

    The output follows the OpenAI streaming format::

        data: {"choices":[{"delta":{"content":"Hello"},"index":0}]}
    """
    payload: dict = {
        "choices": [
            {
                "delta": {"content": chunk.content},
                "index": 0,
            }
        ]
    }
    if chunk.finish_reason:
        payload["choices"][0]["finish_reason"] = chunk.finish_reason

    return format_sse_event(json.dumps(payload, separators=(",", ":")))
