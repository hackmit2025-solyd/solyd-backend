import pytest
import json
from unittest.mock import MagicMock
from app.services.extraction import ExtractionService
from app.models.schemas import ChunkData


class TestExtractionService:
    def test_extraction_with_mock_claude(self, extraction_service, sample_chunk):
        """Test entity extraction with mocked Claude"""
        chunk = ChunkData(**sample_chunk)
        source_id = "test_source"

        result = extraction_service.extract_entities_from_chunk(chunk, source_id)

        assert "entities" in result
        assert "assertions" in result
        assert "patients" in result["entities"]
        assert len(result["entities"]["patients"]) > 0

    def test_extraction_without_client(self):
        """Test extraction without Claude client (mock mode)"""
        service = ExtractionService()
        service.client = None  # No API key

        chunk = ChunkData(chunk_id="C1", seq=1, text="Test text")
        result = service.extract_entities_from_chunk(chunk, "test_source")

        # Should return mock data
        assert "entities" in result
        assert "assertions" in result
        assert result["entities"]["patients"][0]["id"] == "P_MOCK"

    def test_build_extraction_prompt(self, extraction_service):
        """Test prompt building"""
        text = "Patient has fever and cough."
        prompt = extraction_service._build_extraction_prompt(text)

        assert "Patient has fever and cough." in prompt
        assert "JSON" in prompt
        assert "entities" in prompt
        assert "assertions" in prompt

    def test_parse_extraction_response(self, extraction_service):
        """Test JSON parsing from response"""
        response_text = """
        Here is the extraction:
        {
            "entities": {
                "patients": [{"id": "P123", "name": "Test"}]
            },
            "assertions": []
        }
        Some additional text
        """

        result = extraction_service._parse_extraction_response(response_text)

        assert "entities" in result
        assert "patients" in result["entities"]
        assert result["entities"]["patients"][0]["id"] == "P123"

    def test_parse_extraction_response_invalid_json(self, extraction_service):
        """Test handling of invalid JSON"""
        response_text = "This is not valid JSON"

        result = extraction_service._parse_extraction_response(response_text)

        assert result == {"entities": {}, "assertions": []}

    def test_normalize_entities(self, extraction_service):
        """Test entity normalization"""
        entities = {
            "patients": [{"name": "John Doe"}],  # Missing ID
            "encounters": [{"date": "invalid-date"}],  # Invalid date
            "symptoms": [{"name": "fever"}, {}],  # One invalid
            "diseases": [{"name": "Flu"}],  # Missing code
        }

        normalized = extraction_service.normalize_entities(entities)

        # Patient should get auto-generated ID
        assert "id" in normalized["patients"][0]
        assert normalized["patients"][0]["id"].startswith("P_")

        # Encounter should get auto-generated ID and valid date
        assert "id" in normalized["encounters"][0]
        assert normalized["encounters"][0]["id"].startswith("E_")

        # Invalid symptom should be filtered out
        assert len(normalized["symptoms"]) == 1

        # Disease without code should be filtered out
        assert len(normalized["diseases"]) == 0

    def test_extraction_with_negation(self, mock_claude_client):
        """Test extraction handles negation"""
        service = ExtractionService()

        # Mock response with negated symptom
        mock_response = {
            "entities": {
                "symptoms": [{"name": "cough"}],
            },
            "assertions": [
                {
                    "id": "A1",
                    "predicate": "HAS_SYMPTOM",
                    "subject_ref": "E567",
                    "object_ref": "cough",
                    "negation": True,  # Negated
                    "confidence": 0.95,
                }
            ],
        }

        mock_claude_client.messages.create.return_value = MagicMock(
            content=[MagicMock(text=json.dumps(mock_response))]
        )
        service.client = mock_claude_client

        chunk = ChunkData(chunk_id="C1", seq=1, text="Patient denies cough")
        result = service.extract_entities_from_chunk(chunk, "test_source")

        assert result["assertions"][0]["negation"] is True

    def test_extraction_adds_chunk_ids(self, extraction_service, sample_chunk):
        """Test that chunk IDs are added to assertions"""
        chunk = ChunkData(**sample_chunk)
        source_id = "test_source"

        result = extraction_service.extract_entities_from_chunk(chunk, source_id)

        # All assertions should have chunk_ids and source_id
        for assertion in result.get("assertions", []):
            assert "chunk_ids" in assertion
            assert chunk.chunk_id in assertion["chunk_ids"]
            assert assertion["source_id"] == source_id