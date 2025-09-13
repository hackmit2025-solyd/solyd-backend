from unittest.mock import patch, MagicMock
from app.services.embedding import EmbeddingService


class TestEmbeddingService:
    def test_init_without_api_key(self):
        """Test initialization without API key"""
        with patch("app.config.settings.voyage_api_key", None):
            service = EmbeddingService()
            assert service.client is None

    def test_init_with_api_key(self):
        """Test initialization with API key"""
        with patch("app.config.settings.voyage_api_key", "test-key"):
            with patch("voyageai.Client"):
                service = EmbeddingService()
                assert service.client is not None
                assert service.model == "voyage-3-large"

    def test_generate_embedding_without_client(self):
        """Test embedding generation without client (mock mode)"""
        with patch("app.config.settings.voyage_api_key", None):
            service = EmbeddingService()
            embedding = service.generate_embedding("test text")

            assert embedding is not None
            assert len(embedding) == 1024
            assert all(isinstance(x, float) for x in embedding)

    def test_generate_embedding_with_client(self):
        """Test embedding generation with client"""
        with patch("app.config.settings.voyage_api_key", "test-key"):
            service = EmbeddingService()
            mock_client = MagicMock()
            mock_result = MagicMock()
            mock_result.embeddings = [[0.1] * 1024]
            mock_client.embed.return_value = mock_result
            service.client = mock_client

            embedding = service.generate_embedding("test text")

            assert embedding == [0.1] * 1024
            mock_client.embed.assert_called_once_with(
                ["test text"], model="voyage-3-large", input_type="document"
            )

    def test_generate_embeddings_batch(self):
        """Test batch embedding generation"""
        with patch("app.config.settings.voyage_api_key", "test-key"):
            service = EmbeddingService()
            mock_client = MagicMock()
            mock_result = MagicMock()
            mock_result.embeddings = [[0.1] * 1024, [0.2] * 1024]
            mock_client.embed.return_value = mock_result
            service.client = mock_client

            texts = ["text1", "text2"]
            embeddings = service.generate_embeddings(texts)

            assert len(embeddings) == 2
            assert embeddings[0] == [0.1] * 1024
            assert embeddings[1] == [0.2] * 1024

    def test_generate_embeddings_with_empty_texts(self):
        """Test embedding generation with empty texts"""
        with patch("app.config.settings.voyage_api_key", None):
            service = EmbeddingService()

            embeddings = service.generate_embeddings(["text", "", "another"])
            assert len(embeddings) == 3
            assert embeddings[0] is not None
            assert embeddings[1] is None  # Empty text
            assert embeddings[2] is not None

    def test_generate_query_embedding(self):
        """Test query embedding generation"""
        with patch("app.config.settings.voyage_api_key", "test-key"):
            service = EmbeddingService()
            mock_client = MagicMock()
            mock_result = MagicMock()
            mock_result.embeddings = [[0.3] * 1024]
            mock_client.embed.return_value = mock_result
            service.client = mock_client

            embedding = service.generate_query_embedding("search query")

            assert embedding == [0.3] * 1024
            mock_client.embed.assert_called_once_with(
                ["search query"], model="voyage-3-large", input_type="query"
            )

    def test_calculate_similarity(self):
        """Test cosine similarity calculation"""
        service = EmbeddingService()

        # Same vectors should have similarity 1.0
        vec1 = [1.0, 0.0, 0.0]
        similarity = service.calculate_similarity(vec1, vec1)
        assert abs(similarity - 1.0) < 0.001

        # Orthogonal vectors should have similarity 0.0
        vec2 = [0.0, 1.0, 0.0]
        similarity = service.calculate_similarity(vec1, vec2)
        assert abs(similarity) < 0.001

        # Opposite vectors should have similarity -1.0
        vec3 = [-1.0, 0.0, 0.0]
        similarity = service.calculate_similarity(vec1, vec3)
        assert abs(similarity + 1.0) < 0.001

    def test_calculate_similarity_with_none(self):
        """Test similarity calculation with None embeddings"""
        service = EmbeddingService()

        assert service.calculate_similarity(None, [1.0, 0.0]) == 0.0
        assert service.calculate_similarity([1.0, 0.0], None) == 0.0
        assert service.calculate_similarity(None, None) == 0.0
