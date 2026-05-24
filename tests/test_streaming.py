"""Streaming tests — SSE formatting, multipart/mixed parser, stream helpers."""

from __future__ import annotations

import json

import pytest

from hubia.core.provider import StreamChunk
from hubia.core.streaming import (
    chunk_to_sse,
    collect_stream,
    extract_boundary,
    format_sse_done,
    format_sse_event,
    parse_multipart_mixed,
)


# ===========================================================================
# SSE formatting
# ===========================================================================


class TestSSEFormatting:
    """Server-Sent Events format helpers."""

    def test_format_sse_event(self):
        """format_sse_event wraps data in ``data: ...\\n\\n``."""
        result = format_sse_event("hello")
        assert result == "data: hello\n\n"

    def test_format_sse_event_json(self):
        """JSON data is preserved as-is in the SSE line."""
        payload = json.dumps({"key": "value"})
        result = format_sse_event(payload)
        assert result == f"data: {payload}\n\n"

    def test_format_sse_done(self):
        """format_sse_done returns the OpenAI [DONE] sentinel."""
        result = format_sse_done()
        assert result == "data: [DONE]\n\n"


# ===========================================================================
# Boundary extraction
# ===========================================================================


class TestBoundaryExtraction:
    """Extract boundary string from Content-Type."""

    def test_extract_boundary_standard(self):
        """Standard multipart/mixed Content-Type."""
        ct = 'multipart/mixed; boundary=----WebKitFormBoundaryabc'
        assert extract_boundary(ct) == "----WebKitFormBoundaryabc"

    def test_extract_boundary_quoted(self):
        """Boundary may be quoted."""
        ct = 'multipart/mixed; boundary="----Boundary123"'
        assert extract_boundary(ct) == "----Boundary123"

    def test_extract_boundary_none(self):
        """No boundary → returns None."""
        ct = "application/json"
        assert extract_boundary(ct) is None


# ===========================================================================
# Multipart/mixed parser
# ===========================================================================


class TestMultipartParser:
    """Parse Meta AI multipart/mixed responses."""

    async def test_valid_delta_chunks(self):
        """Delta chunks yield StreamChunks with correct content."""
        boundary = "----TestBoundary"
        body = (
            f"--{boundary}\r\n"
            "Content-Type: application/json\r\n\r\n"
            '{"delta": {"text": "Hello "}}\r\n'
            f"--{boundary}\r\n"
            "Content-Type: application/json\r\n\r\n"
            '{"delta": {"text": "world"}}\r\n'
            f"--{boundary}\r\n"
            "Content-Type: application/json\r\n\r\n"
            '{"done": true}\r\n'
            f"--{boundary}--\r\n"
        ).encode()

        chunks: list[StreamChunk] = []
        async for chunk in parse_multipart_mixed(body, boundary):
            chunks.append(chunk)

        assert len(chunks) == 3
        assert chunks[0].content == "Hello "
        assert chunks[0].finish_reason is None
        assert chunks[1].content == "world"
        assert chunks[1].finish_reason is None
        assert chunks[2].content == ""
        assert chunks[2].finish_reason == "stop"

    async def test_empty_body(self):
        """Empty body yields no chunks."""
        chunks = [c async for c in parse_multipart_mixed(b"", "boundary")]
        assert len(chunks) == 0

    async def test_malformed_json(self):
        """Parts with malformed JSON are skipped."""
        boundary = "BOUND"
        body = (
            f"--{boundary}\r\n"
            "Content-Type: application/json\r\n\r\n"
            "not-json\r\n"
            f"--{boundary}--\r\n"
        ).encode()

        chunks = [c async for c in parse_multipart_mixed(body, boundary)]
        assert len(chunks) == 0

    async def test_delta_as_string(self):
        """Delta may be a plain string rather than a dict."""
        boundary = "B"
        body = (
            f"--{boundary}\r\n"
            "Content-Type: application/json\r\n\r\n"
            '{"delta": "plain text"}\r\n'
            f"--{boundary}--\r\n"
        ).encode()

        chunks = [c async for c in parse_multipart_mixed(body, boundary)]
        assert len(chunks) == 1
        assert chunks[0].content == "plain text"

    async def test_top_level_text(self):
        """Top-level ``text`` key is used when no ``delta`` key exists."""
        boundary = "B"
        body = (
            f"--{boundary}\r\n"
            "Content-Type: application/json\r\n\r\n"
            '{"text": "top-level"}\r\n'
            f"--{boundary}--\r\n"
        ).encode()

        chunks = [c async for c in parse_multipart_mixed(body, boundary)]
        assert len(chunks) == 1
        assert chunks[0].content == "top-level"


# ===========================================================================
# Stream conversion helpers
# ===========================================================================


class TestStreamConversion:
    """Async stream → text and SSE conversion."""

    async def test_collect_stream(self):
        """collect_stream concatenates all chunk content."""
        async def gen():
            yield StreamChunk(content="a", finish_reason=None)
            yield StreamChunk(content="b", finish_reason=None)
            yield StreamChunk(content="c", finish_reason="stop")

        text = await collect_stream(gen())
        assert text == "abc"

    async def test_collect_stream_empty(self):
        """Empty stream produces empty string."""
        async def gen():
            return
            yield  # pragma: no cover

        text = await collect_stream(gen())
        assert text == ""

    async def test_chunk_to_sse(self):
        """chunk_to_sse produces OpenAI-formatted SSE line."""
        chunk = StreamChunk(content="Hello", finish_reason=None)
        sse = await chunk_to_sse(chunk)
        assert sse.startswith("data: ")
        payload = json.loads(sse[6:].strip())
        assert payload["choices"][0]["delta"]["content"] == "Hello"

    async def test_chunk_to_sse_with_finish(self):
        """SSE includes finish_reason when present."""
        chunk = StreamChunk(content="", finish_reason="stop")
        sse = await chunk_to_sse(chunk)
        payload = json.loads(sse[6:].strip())
        assert payload["choices"][0]["finish_reason"] == "stop"
