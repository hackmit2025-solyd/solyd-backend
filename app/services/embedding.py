"""Embedding service using VoyageAI"""

from typing import List
import voyageai
from app.config import settings


class EmbeddingService:
    """Service for generating text embeddings using VoyageAI"""

    def __init__(self):
        self.client = voyageai.Client(api_key=settings.voyage_api_key)
        self.model = settings.voyage_model

    def generate_embedding(self, text: str) -> List[float]:
        """
        Generate embedding for a single text

        Args:
            text: Text to embed

        Returns:
            List of float values representing the embedding
        """
        try:
            result = self.client.embed(
                texts=[text], model=self.model, input_type="document"
            )
            return result.embeddings[0]
        except Exception as e:
            print(f"Embedding generation error: {e}")
            return None

    def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple texts

        Args:
            texts: List of texts to embed

        Returns:
            List of embeddings
        """
        try:
            result = self.client.embed(
                texts=texts, model=self.model, input_type="document"
            )
            return result.embeddings
        except Exception as e:
            print(f"Batch embedding generation error: {e}")
            return [None] * len(texts)


# Singleton instance
embedding_service = EmbeddingService()
