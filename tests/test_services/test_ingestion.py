from app.models.schemas import DocumentUpload, ChunkData


class TestIngestionService:
    def test_generate_source_id(self, ingestion_service):
        """Test source ID generation"""
        content = "Test medical document content"
        source_type = "EMR"

        source_id = ingestion_service.generate_source_id(content, source_type)

        assert source_id is not None
        assert len(source_id) == 16
        assert isinstance(source_id, str)

        # Same content should generate same ID
        source_id2 = ingestion_service.generate_source_id(content, source_type)
        assert source_id == source_id2

    def test_chunk_text(self, ingestion_service):
        """Test text chunking"""
        # Create a long text
        text = "This is a test sentence. " * 100  # ~2500 characters

        chunks = ingestion_service.chunk_text(text)

        assert len(chunks) > 0
        assert all(isinstance(chunk, ChunkData) for chunk in chunks)
        assert chunks[0].seq == 1
        assert chunks[0].chunk_id == "C1"

        # Check chunk sizes
        for chunk in chunks:
            assert len(chunk.text) <= ingestion_service.chunk_size * 4 + 100

    def test_chunk_text_short(self, ingestion_service):
        """Test chunking with short text"""
        text = "Short text that fits in one chunk."

        chunks = ingestion_service.chunk_text(text)

        assert len(chunks) == 1
        assert chunks[0].text == text
        assert chunks[0].seq == 1

    def test_process_document(self, ingestion_service, sample_document):
        """Test document processing"""
        document = DocumentUpload(**sample_document)

        result = ingestion_service.process_document(document)

        assert "source" in result
        assert "chunks" in result
        assert "chunk_count" in result
        assert result["source"]["source_id"] == sample_document["source_id"]
        assert result["chunk_count"] == len(result["chunks"])
        assert result["chunks"][0]["seq"] == 1

    def test_process_document_without_source_id(self, ingestion_service):
        """Test document processing without source ID"""
        document = DocumentUpload(
            source_id="",
            source_type="EMR",
            title="Test",
            content="Test content",
        )

        result = ingestion_service.process_document(document)

        assert result["source"]["source_id"] != ""
        assert len(result["source"]["source_id"]) == 16

    def test_is_duplicate(self, ingestion_service):
        """Test duplicate detection"""
        entity = {"id": "P123", "name": "John Doe"}
        entity_list = [
            {"id": "P123", "name": "John Doe"},
            {"id": "P124", "name": "Jane Doe"},
        ]

        assert ingestion_service._is_duplicate(entity, entity_list) is True

        new_entity = {"id": "P125", "name": "Bob Smith"}
        assert ingestion_service._is_duplicate(new_entity, entity_list) is False

    def test_merge_extractions(self, ingestion_service):
        """Test merging multiple chunk extractions"""
        chunk_extractions = [
            {
                "entities": {
                    "patients": [{"id": "P123", "name": "John Doe"}],
                    "symptoms": [{"name": "fever"}],
                },
                "assertions": [
                    {
                        "id": "A1",
                        "predicate": "HAS_SYMPTOM",
                        "subject_ref": "P123",
                        "object_ref": "fever",
                        "chunk_ids": ["C1"],
                    }
                ],
            },
            {
                "entities": {
                    "patients": [{"id": "P123", "name": "John Doe"}],  # Duplicate
                    "symptoms": [{"name": "cough"}],  # New
                },
                "assertions": [
                    {
                        "id": "A2",
                        "predicate": "HAS_SYMPTOM",
                        "subject_ref": "P123",
                        "object_ref": "cough",
                        "chunk_ids": ["C2"],
                    }
                ],
            },
        ]

        result = ingestion_service.merge_extractions(chunk_extractions)

        assert len(result["entities"]["patients"]) == 1  # Deduplicated
        assert len(result["entities"]["symptoms"]) == 2  # Both symptoms
        assert len(result["assertions"]) == 2

    def test_consolidate_assertions(self, ingestion_service):
        """Test assertion consolidation"""
        assertions = [
            {
                "id": "A1",
                "predicate": "HAS_SYMPTOM",
                "subject_ref": "E567",
                "object_ref": "fever",
                "confidence": 0.8,
                "chunk_ids": ["C1"],
            },
            {
                "id": "A2",
                "predicate": "HAS_SYMPTOM",
                "subject_ref": "E567",
                "object_ref": "fever",  # Same relation
                "confidence": 0.9,
                "chunk_ids": ["C2"],
            },
        ]

        result = ingestion_service._consolidate_assertions(assertions)

        assert len(result) == 1  # Consolidated into one
        assert set(result[0]["chunk_ids"]) == {"C1", "C2"}
        assert (
            abs(result[0]["confidence"] - 0.85) < 0.0001
        )  # Average of 0.8 and 0.9 with floating point tolerance
