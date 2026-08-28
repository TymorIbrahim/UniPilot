"""Unit tests for transcript parser HTTP client."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.clients.transcript_parser_client import TranscriptParserClientError, parse_transcript_pdf
from app.config import Settings


@pytest.mark.asyncio
async def test_parse_transcript_pdf_returns_parse_result():
    response = httpx.Response(
        200,
        json={
            "success": True,
            "data": {"parseResult": {"courses": [], "warnings": [], "parseMetadata": {}}},
            "error": None,
        },
        request=httpx.Request("POST", "http://transcript-parser/parse"),
    )

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("app.clients.transcript_parser_client.httpx.AsyncClient", return_value=mock_client):
        result = await parse_transcript_pdf(b"%PDF-sample", filename="transcript.pdf")

    assert result == {"courses": [], "warnings": [], "parseMetadata": {}}


@pytest.mark.asyncio
async def test_parse_transcript_pdf_raises_on_parser_error():
    response = httpx.Response(
        400,
        json={"success": False, "data": None, "error": "Uploaded file must be a PDF"},
        request=httpx.Request("POST", "http://transcript-parser/parse"),
    )

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("app.clients.transcript_parser_client.httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(TranscriptParserClientError) as exc_info:
            await parse_transcript_pdf(b"bad", filename="transcript.pdf")

    assert exc_info.value.status_code == 400
    assert "PDF" in exc_info.value.detail


@pytest.mark.asyncio
async def test_parse_transcript_pdf_sends_internal_service_token_when_configured():
    response = httpx.Response(
        200,
        json={
            "success": True,
            "data": {"parseResult": {"courses": [], "warnings": [], "parseMetadata": {}}},
            "error": None,
        },
        request=httpx.Request("POST", "http://transcript-parser/parse"),
    )

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    settings = Settings(
        environment="development",
        jwt_secret="test-secret-value-long-enough",
        internal_service_token="internal-token-value",
    )

    with patch("app.clients.transcript_parser_client.httpx.AsyncClient", return_value=mock_client):
        await parse_transcript_pdf(
            b"%PDF-sample", filename="transcript.pdf", settings=settings
        )

    _, kwargs = mock_client.post.call_args
    assert kwargs["headers"]["X-Internal-Service-Token"] == "internal-token-value"


@pytest.mark.asyncio
async def test_parse_transcript_pdf_uses_default_detail_when_error_field_missing():
    response = httpx.Response(
        400,
        json={"success": False, "data": None},
        request=httpx.Request("POST", "http://transcript-parser/parse"),
    )

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("app.clients.transcript_parser_client.httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(TranscriptParserClientError) as exc_info:
            await parse_transcript_pdf(b"bad", filename="transcript.pdf")

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Transcript parser request failed"


@pytest.mark.asyncio
async def test_parse_transcript_pdf_raises_when_parse_result_missing():
    response = httpx.Response(
        200,
        json={"success": True, "data": {}, "error": None},
        request=httpx.Request("POST", "http://transcript-parser/parse"),
    )

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("app.clients.transcript_parser_client.httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(TranscriptParserClientError) as exc_info:
            await parse_transcript_pdf(b"%PDF-sample", filename="transcript.pdf")

    assert exc_info.value.status_code == 502
    assert "parseResult" in exc_info.value.detail


@pytest.mark.asyncio
async def test_parse_transcript_pdf_raises_on_invalid_success_payload():
    response = httpx.Response(
        200,
        json={"success": False, "data": None, "error": "failed"},
        request=httpx.Request("POST", "http://transcript-parser/parse"),
    )

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("app.clients.transcript_parser_client.httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(TranscriptParserClientError) as exc_info:
            await parse_transcript_pdf(b"%PDF-sample", filename="transcript.pdf")

    assert exc_info.value.status_code == 502
