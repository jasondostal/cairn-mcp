"""Test embedding engine factory: registration, routing, interface contract."""

import pytest

from cairn.config import EmbeddingConfig
from cairn.embedding import get_embedding_engine, register_embedding_provider, _providers
from cairn.embedding.interface import EmbeddingInterface


class StubEmbedding(EmbeddingInterface):
    """Minimal stub for factory tests."""

    @property
    def dimensions(self):
        return 42

    def embed(self, text):
        return [0.1] * 42

    def embed_batch(self, texts):
        return [[0.1] * 42 for _ in texts]


# ── Factory routing ──────────────────────────────────────────


def test_factory_routes_local():
    """Default 'local' backend should return EmbeddingEngine."""
    from cairn.embedding.engine import EmbeddingEngine

    cfg = EmbeddingConfig(backend="local")
    engine = get_embedding_engine(cfg)
    assert isinstance(engine, EmbeddingEngine)


def test_factory_unknown_backend():
    """Unknown backend should raise ValueError."""
    cfg = EmbeddingConfig(backend="does-not-exist")
    with pytest.raises(ValueError, match="does-not-exist"):
        get_embedding_engine(cfg)


# ── Registry ─────────────────────────────────────────────────


def test_register_and_retrieve():
    """Registered embedding provider should be returned by factory."""
    register_embedding_provider("test-stub", lambda cfg: StubEmbedding())
    try:
        cfg = EmbeddingConfig(backend="test-stub")
        engine = get_embedding_engine(cfg)
        assert isinstance(engine, StubEmbedding)
        assert engine.dimensions == 42
        assert len(engine.embed("hello")) == 42
    finally:
        _providers.pop("test-stub", None)


def test_registry_overrides_builtin():
    """A registered provider with a built-in name should take priority."""
    register_embedding_provider("local", lambda cfg: StubEmbedding())
    try:
        cfg = EmbeddingConfig(backend="local")
        engine = get_embedding_engine(cfg)
        assert isinstance(engine, StubEmbedding)
    finally:
        _providers.pop("local", None)


# ── Interface contract ───────────────────────────────────────


def test_interface_cannot_instantiate():
    """EmbeddingInterface should not be instantiable directly."""
    with pytest.raises(TypeError):
        EmbeddingInterface()


def test_stub_satisfies_interface():
    """A proper implementation should pass isinstance check."""
    stub = StubEmbedding()
    assert isinstance(stub, EmbeddingInterface)


def test_embed_batch_matches_dimensions():
    """embed_batch should return vectors matching dimensions."""
    stub = StubEmbedding()
    results = stub.embed_batch(["hello", "world", "test"])
    assert len(results) == 3
    for vec in results:
        assert len(vec) == stub.dimensions
