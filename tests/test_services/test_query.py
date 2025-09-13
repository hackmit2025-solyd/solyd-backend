import pytest
from unittest.mock import MagicMock


class TestQueryService:
    def test_get_patient_summary(self, query_service):
        """Test getting patient summary"""
        mock_result = [
            {
                "p": {"id": "P123", "name": "John Doe"},
                "encounters": [{"id": "E567", "date": "2025-09-13"}],
                "symptoms": [{"name": "fever"}],
                "diseases": [{"code": "ICD10:J10", "name": "Influenza"}],
                "medications": [{"code": "RxNorm:198440", "name": "Acetaminophen"}],
                "tests": [{"test": {"name": "CRP"}, "result": {"value": 12.3}}],
            }
        ]
        query_service.neo4j.execute_query = MagicMock(return_value=mock_result)

        result = query_service.get_patient_summary("P123")

        assert result is not None
        assert result["patient"]["id"] == "P123"
        assert len(result["encounters"]) == 1
        assert len(result["symptoms"]) == 1
        assert len(result["diseases"]) == 1

    def test_get_patient_summary_not_found(self, query_service):
        """Test getting patient summary when not found"""
        query_service.neo4j.execute_query = MagicMock(return_value=[])

        result = query_service.get_patient_summary("P999")

        assert result is None

    def test_get_encounter_details(self, query_service):
        """Test getting encounter details"""
        mock_result = [
            {
                "e": {"id": "E567", "date": "2025-09-13", "dept": "IM"},
                "p": {"id": "P123", "name": "John Doe"},
                "symptoms": [
                    {
                        "symptom": {"name": "fever"},
                        "negation": False,
                        "confidence": 0.95,
                    }
                ],
                "diagnoses": [
                    {
                        "disease": {"code": "ICD10:J10", "name": "Influenza"},
                        "status": "suspected",
                    }
                ],
                "prescriptions": [
                    {
                        "medication": {"name": "Acetaminophen"},
                        "dose": "500mg",
                        "route": "oral",
                    }
                ],
                "test_results": [],
            }
        ]
        query_service.neo4j.execute_query = MagicMock(return_value=mock_result)

        result = query_service.get_encounter_details("E567")

        assert result is not None
        assert result["encounter"]["id"] == "E567"
        assert result["patient"]["id"] == "P123"
        assert len(result["symptoms"]) == 1
        assert result["symptoms"][0]["symptom"]["name"] == "fever"

    def test_get_subgraph(self, query_service):
        """Test getting subgraph around a node"""
        mock_result = [
            {
                "nodes": [
                    {"id": "P123", "label": "Patient", "properties": {}},
                    {"id": "E567", "label": "Encounter", "properties": {}},
                ],
                "relationships": [
                    {
                        "id": 1,
                        "type": "HAS_ENCOUNTER",
                        "from": "P123",
                        "to": "E567",
                        "properties": {},
                    }
                ],
            }
        ]
        query_service.neo4j.execute_query = MagicMock(return_value=mock_result)

        result = query_service.get_subgraph("P123", "Patient", depth=2)

        assert result["center_node"] == "P123"
        assert len(result["nodes"]) == 2
        assert len(result["relationships"]) == 1

    def test_find_path_between_nodes(self, query_service):
        """Test finding path between two nodes"""
        mock_result = [
            {
                "nodes": [
                    {"id": "P123", "label": "Patient", "properties": {}},
                    {"id": "E567", "label": "Encounter", "properties": {}},
                    {"id": "fever", "label": "Symptom", "properties": {}},
                ],
                "relationships": [
                    {"type": "HAS_ENCOUNTER", "properties": {}},
                    {"type": "HAS_SYMPTOM", "properties": {}},
                ],
            }
        ]
        query_service.neo4j.execute_query = MagicMock(return_value=mock_result)

        result = query_service.find_path_between_nodes("P123", "fever", max_depth=3)

        assert len(result) == 1
        assert len(result[0]["nodes"]) == 3

    def test_find_path_between_nodes_not_found(self, query_service):
        """Test when no path exists between nodes"""
        query_service.neo4j.execute_query = MagicMock(return_value=[])

        result = query_service.find_path_between_nodes("P123", "P999")

        assert result == []

    def test_search_by_symptoms(self, query_service):
        """Test searching diseases by symptoms"""
        mock_result = [
            {
                "result": {
                    "disease": {"code": "ICD10:J10", "name": "Influenza"},
                    "symptom_count": 3,
                    "matching_symptoms": ["fever", "cough", "fatigue"],
                }
            },
            {
                "result": {
                    "disease": {"code": "ICD10:J00", "name": "Common Cold"},
                    "symptom_count": 2,
                    "matching_symptoms": ["fever", "cough"],
                }
            },
        ]
        query_service.neo4j.execute_query = MagicMock(return_value=mock_result)

        results = query_service.search_by_symptoms(["fever", "cough", "fatigue"])

        assert len(results) == 2
        assert results[0]["disease"]["name"] == "Influenza"
        assert results[0]["symptom_count"] == 3

    def test_get_evidence_trail(self, query_service):
        """Test getting evidence trail for an assertion"""
        mock_result = [
            {
                "assertion": {
                    "assertion_id": "A1",
                    "predicate": "HAS_SYMPTOM",
                    "confidence": 0.95,
                },
                "source": {"source_id": "doc_001", "source_type": "EMR"},
                "subject": {"id": "E567"},
                "object": {"name": "fever"},
            }
        ]
        query_service.neo4j.execute_query = MagicMock(return_value=mock_result)

        result = query_service.get_evidence_trail("A1")

        assert result is not None
        assert result["assertion"]["assertion_id"] == "A1"
        assert result["source"]["source_type"] == "EMR"

    def test_execute_custom_query(self, query_service):
        """Test executing custom Cypher query"""
        mock_result = [{"count": 10}]
        query_service.neo4j.execute_query = MagicMock(return_value=mock_result)

        cypher = "MATCH (n) RETURN count(n) as count"
        result = query_service.execute_custom_query(cypher)

        assert len(result) == 1
        assert result[0]["count"] == 10

    def test_execute_custom_query_blocks_destructive(self, query_service):
        """Test that destructive queries are blocked"""
        cypher = "MATCH (n) DELETE n"

        with pytest.raises(ValueError, match="Destructive operations"):
            query_service.execute_custom_query(cypher)
