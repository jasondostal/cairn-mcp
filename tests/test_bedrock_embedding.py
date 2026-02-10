"""Tests for Bedrock Titan V2 embedding backend and factory routing."""

import json
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from cairn.config import EmbeddingConfig
from cairn.embedding import get_embedding_engine
from cairn.embedding.bedrock import BedrockEmbedding


# ── Helpers ──────────────────────────────────────────────────


def _make_invoke_response(embedding: list[float]) -> dict:
    """Build a mock invoke_model response with a readable body."""
    body = MagicMock()
    body.read.return_value = json.dumps({"embedding": embedding}).encode()
    return {"body": body}


def _make_client_error(code: str) -> ClientError:
    """Build a botocore ClientError with the given error code."""
    return ClientError(
        {"Error": {"Code": code, "Message": "test"}},
        "InvokeModel",
    )


# ── embed() ─────────────────────────────────────────────────


@patch("cairn.embedding.bedrock.boto3")
def test_embed_returns_correct_dimensions(mock_boto3):
    """embed() should return a vector of configured dimensions."""
    dims = 1024
    fake_embedding = [0.1] * dims
    mock_client = MagicMock()
    mock_client.invoke_model.return_value = _make_invoke_response(fake_embedding)
    mock_boto3.client.return_value = mock_client

    cfg = EmbeddingConfig(backend="bedrock", dimensions=dims)
    engine = BedrockEmbedding(cfg)
    result = engine.embed("test text")

    assert len(result) == dims
    assert result == fake_embedding


@patch("cairn.embedding.bedrock.boto3")
def test_embed_sends_correct_request_body(mock_boto3):
    """invoke_model should be called with correct model ID, dimensions, and normalize flag."""
    dims = 512
    mock_client = MagicMock()
    mock_client.invoke_model.return_value = _make_invoke_response([0.0] * dims)
    mock_boto3.client.return_value = mock_client

    model_id = "amazon.titan-embed-text-v2:0"
    cfg = EmbeddingConfig(
        backend="bedrock",
        dimensions=dims,
        bedrock_model=model_id,
        bedrock_region="us-west-2",
    )
    engine = BedrockEmbedding(cfg)
    engine.embed("hello world")

    call_kwargs = mock_client.invoke_model.call_args[1]
    assert call_kwargs["modelId"] == model_id
    assert call_kwargs["contentType"] == "application/json"

    body = json.loads(call_kwargs["body"])
    assert body["inputText"] == "hello world"
    assert body["dimensions"] == dims
    assert body["normalize"] is True


# ── embed_batch() ────────────────────────────────────────────


@patch("cairn.embedding.bedrock.boto3")
def test_embed_batch_returns_correct_count(mock_boto3):
    """embed_batch() should return one vector per input text."""
    dims = 256
    mock_client = MagicMock()
    mock_client.invoke_model.return_value = _make_invoke_response([0.1] * dims)
    mock_boto3.client.return_value = mock_client

    cfg = EmbeddingConfig(backend="bedrock", dimensions=dims)
    engine = BedrockEmbedding(cfg)
    results = engine.embed_batch(["one", "two", "three"])

    assert len(results) == 3
    assert mock_client.invoke_model.call_count == 3
    for vec in results:
        assert len(vec) == dims


# ── Retry logic ──────────────────────────────────────────────


@patch("cairn.embedding.bedrock.time.sleep")  # don't actually sleep in tests
@patch("cairn.embedding.bedrock.boto3")
def test_retry_on_throttling(mock_boto3, mock_sleep):
    """Should retry on ThrottlingException and succeed on second attempt."""
    dims = 1024
    mock_client = MagicMock()
    mock_client.invoke_model.side_effect = [
        _make_client_error("ThrottlingException"),
        _make_invoke_response([0.5] * dims),
    ]
    mock_boto3.client.return_value = mock_client

    cfg = EmbeddingConfig(backend="bedrock", dimensions=dims)
    engine = BedrockEmbedding(cfg)
    result = engine.embed("test")

    assert len(result) == dims
    assert mock_client.invoke_model.call_count == 2
    mock_sleep.assert_called_once_with(1)  # 2^0 = 1


@patch("cairn.embedding.bedrock.time.sleep")
@patch("cairn.embedding.bedrock.boto3")
def test_retry_exhausted_raises(mock_boto3, mock_sleep):
    """Should raise after 3 failed attempts on transient errors."""
    mock_client = MagicMock()
    mock_client.invoke_model.side_effect = [
        _make_client_error("ServiceUnavailableException"),
        _make_client_error("ServiceUnavailableException"),
        _make_client_error("ServiceUnavailableException"),
    ]
    mock_boto3.client.return_value = mock_client

    cfg = EmbeddingConfig(backend="bedrock", dimensions=1024)
    engine = BedrockEmbedding(cfg)

    with pytest.raises(ClientError):
        engine.embed("test")

    assert mock_client.invoke_model.call_count == 3


@patch("cairn.embedding.bedrock.boto3")
def test_non_retryable_error_raises_immediately(mock_boto3):
    """Non-transient errors should raise without retry."""
    mock_client = MagicMock()
    mock_client.invoke_model.side_effect = _make_client_error("ValidationException")
    mock_boto3.client.return_value = mock_client

    cfg = EmbeddingConfig(backend="bedrock", dimensions=1024)
    engine = BedrockEmbedding(cfg)

    with pytest.raises(ClientError):
        engine.embed("test")

    assert mock_client.invoke_model.call_count == 1


# ── Factory routing ──────────────────────────────────────────


@patch("cairn.embedding.bedrock.boto3")
def test_factory_routes_bedrock(mock_boto3):
    """Factory should return BedrockEmbedding for backend='bedrock'."""
    mock_boto3.client.return_value = MagicMock()

    cfg = EmbeddingConfig(backend="bedrock", dimensions=1024)
    engine = get_embedding_engine(cfg)
    assert isinstance(engine, BedrockEmbedding)
    assert engine.dimensions == 1024


# ── Interface contract ───────────────────────────────────────


@patch("cairn.embedding.bedrock.boto3")
def test_bedrock_satisfies_interface(mock_boto3):
    """BedrockEmbedding should satisfy EmbeddingInterface."""
    from cairn.embedding.interface import EmbeddingInterface

    mock_boto3.client.return_value = MagicMock()

    cfg = EmbeddingConfig(backend="bedrock", dimensions=1024)
    engine = BedrockEmbedding(cfg)
    assert isinstance(engine, EmbeddingInterface)
