import voyageai
from typing import List, Optional
import numpy as np
import logging
from app.config import settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    def __init__(self):
        self.client = None
        if settings.voyage_api_key:
            try:
                voyageai.api_key = settings.voyage_api_key
                self.client = voyageai.Client()
                self.model = "voyage-3-large"  # 1024 dimension model
                logger.info("Voyage AI client initialized successfully")
            except Exception as e:
                logger.warning(f"Failed to initialize Voyage AI client: {e}")
                self.client = None

    def generate_embedding(self, text: str) -> Optional[List[float]]:
        """Generate embedding for a single text"""
        if not text:
            return None

        if not self.client:
            # Return mock embedding for testing
            logger.warning("Voyage AI client not available, returning mock embedding")
            return self._get_mock_embedding()

        try:
            result = self.client.embed(
                [text],
                model=self.model,
                input_type="document",
            )
            return result.embeddings[0]
        except Exception as e:
            logger.error(f"Error generating embedding: {e}")
            return self._get_mock_embedding()

    def generate_embeddings(self, texts: List[str]) -> List[Optional[List[float]]]:
        """Generate embeddings for multiple texts"""
        if not texts:
            return []

        if not self.client:
            logger.warning("Voyage AI client not available, returning mock embeddings")
            return [self._get_mock_embedding() for _ in texts]

        try:
            # Filter out empty texts
            valid_texts = [t for t in texts if t]
            if not valid_texts:
                return [None] * len(texts)

            result = self.client.embed(
                valid_texts,
                model=self.model,
                input_type="document",
            )

            # Map back to original list, handling empty texts
            embeddings = []
            valid_idx = 0
            for text in texts:
                if text:
                    embeddings.append(result.embeddings[valid_idx])
                    valid_idx += 1
                else:
                    embeddings.append(None)

            return embeddings
        except Exception as e:
            logger.error(f"Error generating embeddings: {e}")
            return [self._get_mock_embedding() for _ in texts]

    def generate_query_embedding(self, query: str) -> Optional[List[float]]:
        """Generate embedding for a search query"""
        if not query:
            return None

        if not self.client:
            logger.warning("Voyage AI client not available, returning mock embedding")
            return self._get_mock_embedding()

        try:
            result = self.client.embed(
                [query],
                model=self.model,
                input_type="query",
            )
            return result.embeddings[0]
        except Exception as e:
            logger.error(f"Error generating query embedding: {e}")
            return self._get_mock_embedding()

    def _get_mock_embedding(self) -> List[float]:
        """Generate a mock embedding for testing"""
        # Generate a random 1024-dimensional vector normalized to unit length
        vec = np.random.randn(1024)
        vec = vec / np.linalg.norm(vec)
        return vec.tolist()

    def calculate_similarity(
        self, embedding1: List[float], embedding2: List[float]
    ) -> float:
        """Calculate cosine similarity between two embeddings"""
        if not embedding1 or not embedding2:
            return 0.0

        vec1 = np.array(embedding1)
        vec2 = np.array(embedding2)

        # Cosine similarity
        dot_product = np.dot(vec1, vec2)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return float(dot_product / (norm1 * norm2))
