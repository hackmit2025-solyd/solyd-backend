from unittest.mock import patch


class TestIngestAPI:
    def test_upload_document(self, client, setup_test_neo4j):
        """Test POST /api/ingest/document"""
        # Mock the services
        with patch("app.api.ingest.IngestionService") as mock_ingestion:
            with patch("app.api.ingest.ExtractionService") as mock_extraction:
                with patch("app.api.ingest.ResolutionService") as mock_resolution:
                    # Setup mock returns
                    mock_ingestion_instance = mock_ingestion.return_value
                    mock_extraction_instance = mock_extraction.return_value
                    mock_resolution_instance = mock_resolution.return_value

                    mock_ingestion_instance.process_document.return_value = {
                        "source": {"source_id": "test_001"},
                        "chunks": [{"chunk_id": "C1", "seq": 1, "text": "Test"}],
                        "chunk_count": 1,
                    }

                    mock_extraction_instance.extract_entities_from_chunk.return_value = {
                        "entities": {"patients": [{"id": "P123"}]},
                        "assertions": [],
                    }

                    mock_ingestion_instance.merge_extractions.return_value = {
                        "entities": {"patients": [{"id": "P123"}]},
                        "assertions": [],
                    }

                    mock_extraction_instance.normalize_entities.return_value = {
                        "patients": [{"id": "P123"}]
                    }

                    mock_resolution_instance.resolve_entity.return_value = {
                        "decision": "new",
                        "entity": {"id": "P123"},
                        "entity_type": "patients",
                        "to_node_id": "P123",
                    }

                    mock_resolution_instance.create_upsert_plan.return_value = {
                        "nodes": [{"label": "Patient", "id_property": ("id", "P123")}],
                        "relationships": [],
                    }

                    response = client.post(
                        "/api/ingest/document",
                        json={
                            "source_id": "test_001",
                            "source_type": "EMR",
                            "title": "Test Document",
                            "content": "Test content",
                        },
                    )

                    assert response.status_code == 200
                    data = response.json()
                    assert data["source_id"] == "test_001"
                    assert data["chunks_processed"] == 1

    def test_extract_entities(self, client):
        """Test POST /api/ingest/extract"""
        with patch("app.api.ingest.ExtractionService") as mock_extraction:
            with patch("app.api.ingest.IngestionService") as mock_ingestion:
                mock_extraction_instance = mock_extraction.return_value
                mock_ingestion_instance = mock_ingestion.return_value

                mock_extraction_instance.extract_entities_from_chunk.return_value = {
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
                        }
                    ],
                }

                mock_ingestion_instance.merge_extractions.return_value = {
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
                        }
                    ],
                }

                response = client.post(
                    "/api/ingest/extract",
                    json={
                        "source": {
                            "source_id": "test_001",
                            "source_type": "EMR",
                            "title": "Test",
                            "content": "Test content",
                        },
                        "chunks": [
                            {"chunk_id": "C1", "seq": 1, "text": "Patient has fever"}
                        ],
                    },
                )

                assert response.status_code == 200
                data = response.json()
                assert "entities" in data
                assert "assertions" in data
                assert len(data["entities"]["patients"]) == 1

    def test_bulk_upload(self, client):
        """Test POST /api/ingest/bulk"""
        with patch("app.api.ingest.upload_document") as mock_upload:
            # First document succeeds
            mock_upload.side_effect = [
                {
                    "source_id": "doc1",
                    "chunks_processed": 1,
                    "entities_extracted": 2,
                    "assertions_created": 1,
                    "upsert_results": {},
                },
                # Second document fails
                Exception("Processing failed"),
            ]

            response = client.post(
                "/api/ingest/bulk",
                json=[
                    {
                        "source_id": "doc1",
                        "source_type": "EMR",
                        "title": "Doc 1",
                        "content": "Content 1",
                    },
                    {
                        "source_id": "doc2",
                        "source_type": "EMR",
                        "title": "Doc 2",
                        "content": "Content 2",
                    },
                ],
            )

            assert response.status_code == 200
            data = response.json()
            assert data["total"] == 2
            assert data["successful"] == 1
            assert data["failed"] == 1
            assert len(data["results"]) == 1
            assert len(data["errors"]) == 1
