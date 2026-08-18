"""
Real Local Semantic Code Embedding Encoder using pretrained ONNX BAAI/bge-small-en-v1.5 model via FastEmbed.

Transforms source code snippets, Tree-sitter symbols, and search queries into dense
384-dimensional normalized semantic vectors for Qdrant storage and similarity retrieval.
"""

from __future__ import annotations

import math

from shared.config.settings import get_settings
from shared.exceptions.handlers import ServiceUnavailableException
from shared.logging.logger import logger

_model_instance = None


def get_embedding_model():
    """Retrieve or initialize the global local semantic TextEmbedding model instance."""
    global _model_instance
    if _model_instance is None:
        settings = get_settings()
        try:
            import os
            # Suppress symlink warning on Windows systems
            os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
            from fastembed import TextEmbedding

            logger.info(f"Loading local semantic embedding model '{settings.embedding_model_name}'...")
            _model_instance = TextEmbedding(model_name=settings.embedding_model_name)
            logger.info(f"Successfully loaded local embedding model '{settings.embedding_model_name}'")
        except Exception as err:
            logger.error(f"Failed to load local embedding model '{settings.embedding_model_name}': {err}")
            raise ServiceUnavailableException(
                message=f"Local semantic embedding model '{settings.embedding_model_name}' failed to load",
                details={"error": str(err)},
            ) from err
    return _model_instance


class CodeVectorEncoder:
    """
    Production Real Semantic Code Vector Encoder.
    Generates 384-dimensional dense semantic vectors using local neural embeddings.
    """

    def __init__(self, model_name: str | None = None) -> None:
        settings = get_settings()
        self.model_name = model_name or settings.embedding_model_name
        self._dimension = settings.embedding_dimension

    @property
    def dimension(self) -> int:
        """Return the vector dimension produced by the local embedding model."""
        return self._dimension

    @classmethod
    def encode(cls, text: str) -> list[float]:
        """Encode a single text snippet into a normalized dense 384-dimensional semantic vector."""
        if not text or not text.strip():
            # Return zero vector for empty input if explicitly requested, otherwise embed whitespace
            text = "empty code snippet"

        vectors = cls.encode_batch([text])
        return vectors[0]

    @classmethod
    def encode_batch(cls, texts: list[str]) -> list[list[float]]:
        """Batch encode multiple text snippets into dense normalized semantic vectors."""
        if not texts:
            return []

        # Sanitize empty text items
        cleaned_texts = [t.strip() if (t and t.strip()) else "empty symbol" for t in texts]

        try:
            model = get_embedding_model()
            embeddings_generator = model.embed(cleaned_texts)
            results: list[list[float]] = []

            for raw_arr in embeddings_generator:
                vec = raw_arr.tolist() if hasattr(raw_arr, "tolist") else list(raw_arr)

                # L2 normalize vector for cosine similarity compatibility
                norm = math.sqrt(sum(v * v for v in vec))
                if norm > 0:
                    vec = [v / norm for v in vec]

                results.append(vec)

            return results
        except Exception as err:
            logger.error(f"Batch embedding generation failed: {err}")
            raise ServiceUnavailableException(
                message="Real semantic embedding generation failed",
                details={"error": str(err)},
            ) from err

    @classmethod
    def cosine_similarity(cls, vec_a: list[float], vec_b: list[float]) -> float:
        """Compute cosine similarity score between two normalized dense vectors."""
        if len(vec_a) != len(vec_b) or not vec_a:
            return 0.0

        dot_product = sum(a * b for a, b in zip(vec_a, vec_b, strict=False))
        norm_a = math.sqrt(sum(a * a for a in vec_a))
        norm_b = math.sqrt(sum(b * b for b in vec_b))

        if norm_a == 0 or norm_b == 0:
            return 0.0

        return max(0.0, min(1.0, dot_product / (norm_a * norm_b)))

    def check_health(self) -> dict:
        """Check embedding model readiness and status without blocking."""
        global _model_instance
        is_ready = _model_instance is not None
        return {
            "status": "healthy" if is_ready else "initializing",
            "model_name": self.model_name,
            "dimension": self.dimension,
            "provider": "FastEmbed (ONNX Local)",
        }




_encoder_instance: CodeVectorEncoder | None = None


def get_code_vector_encoder() -> CodeVectorEncoder:
    """Retrieve global CodeVectorEncoder singleton instance."""
    global _encoder_instance
    if _encoder_instance is None:
        _encoder_instance = CodeVectorEncoder()
    return _encoder_instance
