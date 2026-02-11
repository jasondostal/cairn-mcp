"""Test OpenAI-compatible embedding backend: request format, retry, batch, stats, auth."""

import json
from unittest.mock import patch, MagicMock

import pytest

from cairn.config import EmbeddingConfig
from cairn.embedding.openai_compat import OpenAICompatibleEmbedding


def _make_config(**overrides):
    defaults = {
        "backend": "openai",
        "dimensions": 384,
        "openai_base_url": "http://localhost:11434",
        "openai_model": "nomic-embed-text",
        "openai_api_key": "",
    }
    defaults.update(overrides)
    return EmbeddingConfig(**defaults)


def _mock_response(data):
    """Create a mock urllib response."""
    body = json.dumps(data).encode()
    mock = MagicMock()
    mock.read.return_value = body
    mock.__enter__ = MagicMock(return_value=mock)
    mock.__exit__ = MagicMock(return_value=False)
    return mock


# ── Request format ────────────────────────────────────────────


@patch("cairn.embedding.openai_compat.urllib.request.urlopen")
def test_embed_request_format(mock_urlopen):
    """embed() should POST to /v1/embeddings with correct payload."""
    mock_urlopen.return_value = _mock_response({
        "data": [{"embedding": [0.1] * 384, "index": 0}],
    })

    cfg = _make_config()
    engine = OpenAICompatibleEmbedding(cfg)
    result = engine.embed("hello world")

    assert len(result) == 384
    # Verify the request was made
    call_args = mock_urlopen.call_args
    req = call_args[0][0]
    assert "/v1/embeddings" in req.full_url
    body = json.loads(req.data)
    assert body["model"] == "nomic-embed-text"
    assert body["input"] == "hello world"


# ── Empty key = no Authorization header ───────────────────────


@patch("cairn.embedding.openai_compat.urllib.request.urlopen")
def test_no_auth_header_when_key_empty(mock_urlopen):
    """When api_key is empty, no Authorization header should be sent."""
    mock_urlopen.return_value = _mock_response({
        "data": [{"embedding": [0.1] * 384, "index": 0}],
    })

    cfg = _make_config(openai_api_key="")
    engine = OpenAICompatibleEmbedding(cfg)
    engine.embed("test")

    req = mock_urlopen.call_args[0][0]
    assert "Authorization" not in req.headers


@patch("cairn.embedding.openai_compat.urllib.request.urlopen")
def test_auth_header_when_key_set(mock_urlopen):
    """When api_key is set, Authorization header should be present."""
    mock_urlopen.return_value = _mock_response({
        "data": [{"embedding": [0.1] * 384, "index": 0}],
    })

    cfg = _make_config(openai_api_key="sk-test-key")
    engine = OpenAICompatibleEmbedding(cfg)
    engine.embed("test")

    req = mock_urlopen.call_args[0][0]
    assert req.headers.get("Authorization") == "Bearer sk-test-key"


# ── Batch support ─────────────────────────────────────────────


@patch("cairn.embedding.openai_compat.urllib.request.urlopen")
def test_embed_batch_sorts_by_index(mock_urlopen):
    """embed_batch() should sort by index to match input order."""
    # Return out of order on purpose
    mock_urlopen.return_value = _mock_response({
        "data": [
            {"embedding": [0.3] * 384, "index": 2},
            {"embedding": [0.1] * 384, "index": 0},
            {"embedding": [0.2] * 384, "index": 1},
        ],
    })

    cfg = _make_config()
    engine = OpenAICompatibleEmbedding(cfg)
    results = engine.embed_batch(["a", "b", "c"])

    assert len(results) == 3
    assert results[0][0] == pytest.approx(0.1)
    assert results[1][0] == pytest.approx(0.2)
    assert results[2][0] == pytest.approx(0.3)


@patch("cairn.embedding.openai_compat.urllib.request.urlopen")
def test_embed_batch_empty_input(mock_urlopen):
    """embed_batch([]) should return [] without making a request."""
    cfg = _make_config()
    engine = OpenAICompatibleEmbedding(cfg)
    results = engine.embed_batch([])

    assert results == []
    mock_urlopen.assert_not_called()


# ── Retry logic ───────────────────────────────────────────────


@patch("cairn.embedding.openai_compat.time.sleep")
@patch("cairn.embedding.openai_compat.urllib.request.urlopen")
def test_retry_on_429(mock_urlopen, mock_sleep):
    """Should retry on HTTP 429 with exponential backoff."""
    import urllib.error

    error_resp = MagicMock()
    error_resp.read.return_value = b""
    error_resp.headers = {}

    mock_urlopen.side_effect = [
        urllib.error.HTTPError("url", 429, "Rate limited", {}, error_resp),
        _mock_response({"data": [{"embedding": [0.1] * 384, "index": 0}]}),
    ]

    cfg = _make_config()
    engine = OpenAICompatibleEmbedding(cfg)
    result = engine.embed("test")

    assert len(result) == 384
    assert mock_urlopen.call_count == 2
    mock_sleep.assert_called_once_with(1)  # 2^0 = 1


@patch("cairn.embedding.openai_compat.time.sleep")
@patch("cairn.embedding.openai_compat.urllib.request.urlopen")
def test_retry_exhaustion_raises(mock_urlopen, mock_sleep):
    """Should raise after 3 failed retries."""
    import urllib.error

    error_resp = MagicMock()
    error_resp.read.return_value = b""
    error_resp.headers = {}

    mock_urlopen.side_effect = urllib.error.HTTPError(
        "url", 500, "Server error", {}, error_resp,
    )

    cfg = _make_config()
    engine = OpenAICompatibleEmbedding(cfg)

    with pytest.raises(urllib.error.HTTPError):
        engine.embed("test")

    assert mock_urlopen.call_count == 3


# ── Stats recording ───────────────────────────────────────────


@patch("cairn.embedding.openai_compat.urllib.request.urlopen")
def test_stats_recorded_on_success(mock_urlopen):
    """Successful embed should call embedding_stats.record_call()."""
    mock_urlopen.return_value = _mock_response({
        "data": [{"embedding": [0.1] * 384, "index": 0}],
    })

    mock_stats = MagicMock()
    with patch("cairn.embedding.openai_compat.stats") as stats_mod:
        stats_mod.embedding_stats = mock_stats
        cfg = _make_config()
        engine = OpenAICompatibleEmbedding(cfg)
        engine.embed("hello")

    mock_stats.record_call.assert_called_once()


# ── Dimensions ────────────────────────────────────────────────


def test_dimensions_from_config():
    """dimensions property should reflect config."""
    cfg = _make_config(dimensions=1536)
    engine = OpenAICompatibleEmbedding(cfg)
    assert engine.dimensions == 1536


# ── Factory integration ───────────────────────────────────────


def test_factory_routes_openai():
    """Factory should route 'openai' backend to OpenAICompatibleEmbedding."""
    from cairn.embedding import get_embedding_engine
    cfg = _make_config()
    engine = get_embedding_engine(cfg)
    assert isinstance(engine, OpenAICompatibleEmbedding)
