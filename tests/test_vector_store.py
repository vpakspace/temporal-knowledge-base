"""Tests for vector store (cosine similarity)."""

from storage.vector_store import VectorStore


def test_cosine_similarity_identical():
    a = [1.0, 0.0, 0.0]
    b = [1.0, 0.0, 0.0]
    assert VectorStore.cosine_similarity(a, b) == 1.0


def test_cosine_similarity_orthogonal():
    a = [1.0, 0.0, 0.0]
    b = [0.0, 1.0, 0.0]
    assert abs(VectorStore.cosine_similarity(a, b)) < 0.01


def test_cosine_similarity_opposite():
    a = [1.0, 0.0]
    b = [-1.0, 0.0]
    assert VectorStore.cosine_similarity(a, b) == -1.0


def test_cosine_similarity_zero_vector():
    a = [0.0, 0.0, 0.0]
    b = [1.0, 0.0, 0.0]
    assert VectorStore.cosine_similarity(a, b) == 0.0


def test_cosine_similarity_partial():
    a = [1.0, 1.0, 0.0]
    b = [1.0, 0.0, 0.0]
    sim = VectorStore.cosine_similarity(a, b)
    assert 0.5 < sim < 1.0
