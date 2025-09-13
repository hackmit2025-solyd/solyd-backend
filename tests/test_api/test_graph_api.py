import pytest
from unittest.mock import MagicMock


class TestGraphAPI:
    def test_get_patient(self, client, setup_test_neo4j):
        """Test GET /api/graph/patient/{patient_id}"""
        # Mock Neo4j response
        setup_test_neo4j.execute_query = MagicMock(
            return_value=[
                {
                    "p": {"id": "P123", "name": "John Doe"},
                    "encounters": [{"id": "E567"}],
                    "symptoms": [{"name": "fever"}],
                    "diseases": [],
                    "medications": [],
                    "tests": [],
                }
            ]
        )

        response = client.get("/api/graph/patient/P123")

        assert response.status_code == 200
        data = response.json()
        assert data["patient"]["id"] == "P123"
        assert len(data["encounters"]) == 1

    def test_get_patient_not_found(self, client, setup_test_neo4j):
        """Test GET /api/graph/patient/{patient_id} when not found"""
        setup_test_neo4j.execute_query = MagicMock(return_value=[])

        response = client.get("/api/graph/patient/P999")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_get_encounter(self, client, setup_test_neo4j):
        """Test GET /api/graph/encounter/{encounter_id}"""
        setup_test_neo4j.execute_query = MagicMock(
            return_value=[
                {
                    "e": {"id": "E567", "date": "2025-09-13"},
                    "p": {"id": "P123"},
                    "symptoms": [{"symptom": {"name": "fever"}, "negation": False}],
                    "diagnoses": [],
                    "prescriptions": [],
                    "test_results": [],
                }
            ]
        )

        response = client.get("/api/graph/encounter/E567")

        assert response.status_code == 200
        data = response.json()
        assert data["encounter"]["id"] == "E567"
        assert data["patient"]["id"] == "P123"

    def test_post_subgraph(self, client, setup_test_neo4j):
        """Test POST /api/graph/subgraph"""
        setup_test_neo4j.execute_query = MagicMock(
            return_value=[
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
        )

        response = client.post(
            "/api/graph/subgraph", json={"node_id": "P123", "depth": 2}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["center_node"] == "P123"
        assert len(data["nodes"]) == 2
        assert len(data["relationships"]) == 1

    def test_find_path(self, client, setup_test_neo4j):
        """Test GET /api/graph/path/{start_id}/{end_id}"""
        setup_test_neo4j.execute_query = MagicMock(
            return_value=[
                {
                    "nodes": [
                        {"id": "P123", "label": "Patient", "properties": {}},
                        {"id": "E567", "label": "Encounter", "properties": {}},
                    ],
                    "relationships": [{"type": "HAS_ENCOUNTER", "properties": {}}],
                }
            ]
        )

        response = client.get("/api/graph/path/P123/E567")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert len(data[0]["nodes"]) == 2

    def test_find_path_not_found(self, client, setup_test_neo4j):
        """Test GET /api/graph/path when no path exists"""
        setup_test_neo4j.execute_query = MagicMock(return_value=[])

        response = client.get("/api/graph/path/P123/P999")

        assert response.status_code == 404

    def test_search_by_symptoms(self, client, setup_test_neo4j):
        """Test POST /api/graph/search/symptoms"""
        setup_test_neo4j.execute_query = MagicMock(
            return_value=[
                {
                    "result": {
                        "disease": {"code": "ICD10:J10", "name": "Influenza"},
                        "symptom_count": 2,
                        "matching_symptoms": ["fever", "cough"],
                    }
                }
            ]
        )

        response = client.post(
            "/api/graph/search/symptoms", json=["fever", "cough"]
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["associated_diseases"]) == 1
        assert data["associated_diseases"][0]["disease"]["name"] == "Influenza"

    def test_execute_query(self, client, setup_test_neo4j):
        """Test POST /api/graph/query"""
        setup_test_neo4j.execute_query = MagicMock(
            return_value=[{"count": 10}]
        )

        response = client.post(
            "/api/graph/query",
            json={"query": "MATCH (n) RETURN count(n) as count"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        assert data["results"][0]["count"] == 10

    def test_execute_query_blocked_destructive(self, client):
        """Test that destructive queries are blocked"""
        response = client.post(
            "/api/graph/query",
            json={"query": "MATCH (n) DELETE n"},
        )

        assert response.status_code == 400
        assert "Destructive operations" in response.json()["detail"]

    def test_get_evidence(self, client, setup_test_neo4j):
        """Test GET /api/graph/evidence/{assertion_id}"""
        setup_test_neo4j.execute_query = MagicMock(
            return_value=[
                {
                    "assertion": {"assertion_id": "A1", "predicate": "HAS_SYMPTOM"},
                    "source": {"source_id": "doc_001", "source_type": "EMR"},
                    "subject": {"id": "E567"},
                    "object": {"name": "fever"},
                }
            ]
        )

        response = client.get("/api/graph/evidence/A1")

        assert response.status_code == 200
        data = response.json()
        assert data["assertion"]["assertion_id"] == "A1"
        assert data["source"]["source_type"] == "EMR"