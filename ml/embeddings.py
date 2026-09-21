"""
Embedding functions using OpenAI text-embedding-3-small.

Creates and compares text embeddings for semantic search.
"""

import logging

import numpy as np
from openai import AsyncOpenAI

from common.config import config

logger = logging.getLogger(__name__)

# =============================================================================
# OpenAI Client (singleton)
# =============================================================================

_client: AsyncOpenAI | None = None


def get_client() -> AsyncOpenAI:
    """Get or create OpenAI client (singleton)"""
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=config.OPENAI_API_KEY, base_url=config.OPENAI_BASE_URL)
    return _client


# =============================================================================
# Embedding Functions
# =============================================================================

MAX_EMBEDDING_CHARS = 15000  # ~6000-7500 tokens for Russian, safely under 8192 limit


async def create_embedding(text: str) -> list[float]:
    """
    Create embedding for a single text.

    Args:
        text: Input text to embed

    Returns:
        List of floats representing the embedding vector (1536 dimensions)
    """
    if not text or not text.strip():
        raise ValueError("Text cannot be empty")

    client = get_client()
    truncated = text.strip()[:MAX_EMBEDDING_CHARS]

    try:
        response = await client.embeddings.create(model=config.EMBEDDING_MODEL, input=truncated)
        return response.data[0].embedding
    except Exception as e:
        logger.error(f"Failed to create embedding: {e}")
        raise


async def batch_create_embeddings(texts: list[str]) -> list[list[float]]:
    """
    Create embeddings for multiple texts (more efficient).

    Args:
        texts: List of input texts

    Returns:
        List of embedding vectors
    """
    # Filter out empty texts
    valid_texts = [t.strip() for t in texts if t and t.strip()]

    if not valid_texts:
        return []

    client = get_client()

    try:
        response = await client.embeddings.create(model=config.EMBEDDING_MODEL, input=valid_texts)
        return [item.embedding for item in response.data]
    except Exception as e:
        logger.error(f"Failed to create batch embeddings: {e}")
        raise


# =============================================================================
# Similarity Functions
# =============================================================================


def cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    """
    Calculate cosine similarity between two vectors.

    Args:
        vec1: First vector
        vec2: Second vector (must be same length as vec1)

    Returns:
        Similarity score between 0 and 1, where:
        - 1.0 = identical
        - 0.0 = orthogonal
        - Values closer to 1 = more similar
    """
    if len(vec1) != len(vec2):
        raise ValueError(f"Vector lengths don't match: {len(vec1)} != {len(vec2)}")

    # Convert to numpy arrays for efficient computation
    a = np.array(vec1)
    b = np.array(vec2)

    # Cosine similarity: (A . B) / (||A|| * ||B||)
    dot_product = np.dot(a, b)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return float(dot_product / (norm_a * norm_b))


def normalize_text(text: str) -> str:
    """
    Normalize text for embedding (lowercase, trim whitespace).

    Args:
        text: Input text

    Returns:
        Normalized text
    """
    return " ".join(text.strip().lower().split())


# =============================================================================
# Cache
# =============================================================================


class EmbeddingCache:
    """
    Simple in-memory cache for embeddings to avoid recomputation.

    For production, consider using Redis or similar.
    """

    def __init__(self):
        self._cache: dict[str, list[float]] = {}

    def get(self, text: str) -> list[float] | None:
        """Get cached embedding for text"""
        key = self._normalize(text)
        return self._cache.get(key)

    def set(self, text: str, embedding: list[float]) -> None:
        """Cache embedding for text"""
        key = self._normalize(text)
        self._cache[key] = embedding

    def _normalize(self, text: str) -> str:
        """Normalize text for cache key"""
        return text.strip().lower()[:200]  # Truncate for cache key

    def clear(self) -> None:
        """Clear all cached embeddings"""
        self._cache.clear()

    def size(self) -> int:
        """Get number of cached embeddings"""
        return len(self._cache)


# Global cache instance
embedding_cache = EmbeddingCache()


# =============================================================================
# Utility Functions
# =============================================================================


def to_list(embedding) -> list[float] | None:
    """
    Safely convert embedding (numpy array or list) to list.

    Args:
        embedding: Numpy array, list, or None

    Returns:
        List of floats or None
    """
    if embedding is None:
        return None
    if hasattr(embedding, "tolist"):
        return embedding.tolist()
    if hasattr(embedding, "__iter__"):
        return list(embedding)
    return None


# =============================================================================
# High-level Functions
# =============================================================================


async def get_embedding(text: str, use_cache: bool = True) -> list[float]:
    """
    Get embedding for text (with optional caching).

    Args:
        text: Input text
        use_cache: Whether to use cache (default: True)

    Returns:
        Embedding vector
    """
    if use_cache:
        cached = embedding_cache.get(text)
        if cached is not None:
            return cached

    embedding = await create_embedding(text)

    if use_cache:
        embedding_cache.set(text, embedding)

    return embedding
