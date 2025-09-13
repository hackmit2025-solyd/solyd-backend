from unittest.mock import patch


class TestGraphAPI:
    def test_get_patient(self, client):
        """Test GET /api/graph/patient/{patient_id}"""
        with patch("app.api.graph.QueryService") as mock_query_service:
            mock_instance = mock_query_service.return_value
            mock_instance.get_patient_summary.return_value = {
                "patient": {"id": "P123", "name": "John Doe"},
                "encounters": [{"id": "E567"}],
                "symptoms": [{"name": "fever"}],
                "diseases": [],
                "medications": [],
                "tests": [],
            }

            response = client.get("/api/graph/patient/P123")

            assert response.status_code == 200
            data = response.json()
            assert data["patient"]["id"] == "P123"

    def test_get_patient_not_found(self, client):
        """Test GET /api/graph/patient/{patient_id} when not found"""
        with patch("app.api.graph.QueryService") as mock_query_service:
            mock_instance = mock_query_service.return_value
            mock_instance.get_patient_summary.return_value = None

            response = client.get("/api/graph/patient/P999")

            assert response.status_code == 404

    def test_get_encounter(self, client):
        """Test GET /api/graph/encounter/{encounter_id}"""
        with patch("app.api.graph.QueryService") as mock_query_service:
            mock_instance = mock_query_service.return_value
            mock_instance.get_encounter_details.return_value = {
                "encounter": {"id": "E567", "date": "2025-09-13"},
                "patient": {"id": "P123"},
                "symptoms": [{"symptom": {"name": "fever"}, "negation": False}],
                "diagnoses": [],
                "prescriptions": [],
                "test_results": [],
            }

            response = client.get("/api/graph/encounter/E567")

            assert response.status_code == 200
            data = response.json()
            assert data["encounter"]["id"] == "E567"

    def test_post_subgraph(self, client):
        """Test POST /api/graph/subgraph"""
        with patch("app.api.graph.QueryService") as mock_query_service:
            mock_instance = mock_query_service.return_value
            mock_instance.get_subgraph.return_value = {
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
                "center_node": "P123",
            }

            response = client.post(
                "/api/graph/subgraph", json={"node_id": "P123", "depth": 2}
            )

            assert response.status_code == 200
            data = response.json()
            assert data["center_node"] == "P123"
            assert len(data["nodes"]) == 2

    def test_find_path(self, client):
        """Test GET /api/graph/path/{start_id}/{end_id}"""
        with patch("app.api.graph.QueryService") as mock_query_service:
            mock_instance = mock_query_service.return_value
            mock_instance.find_path_between_nodes.return_value = [
                {
                    "nodes": [
                        {"id": "P123", "label": "Patient", "properties": {}},
                        {"id": "E567", "label": "Encounter", "properties": {}},
                    ],
                    "relationships": [{"type": "HAS_ENCOUNTER", "properties": {}}],
                }
            ]

            response = client.get("/api/graph/path/P123/E567")

            assert response.status_code == 200
            data = response.json()
            assert len(data) == 1

    def test_search_by_symptoms(self, client):
        """Test POST /api/graph/search/symptoms"""
        with patch("app.api.graph.QueryService") as mock_query_service:
            mock_instance = mock_query_service.return_value
            mock_instance.search_by_symptoms.return_value = [
                {
                    "disease": {"code": "ICD10:J10", "name": "Influenza"},
                    "symptom_count": 2,
                    "matching_symptoms": ["fever", "cough"],
                }
            ]

            response = client.post(
                "/api/graph/search/symptoms", json=["fever", "cough"]
            )

            assert response.status_code == 200
            data = response.json()
            assert len(data["associated_diseases"]) == 1

    def test_execute_query(self, client):
        """Test POST /api/graph/query"""
        with patch("app.api.graph.QueryService") as mock_query_service:
            mock_instance = mock_query_service.return_value
            mock_instance.execute_custom_query.return_value = [{"count": 10}]

            response = client.post(
                "/api/graph/query",
                json={"query": "MATCH (n) RETURN count(n) as count"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["count"] == 1
            assert data["results"][0]["count"] == 10

    def test_get_evidence(self, client):
        """Test GET /api/graph/evidence/{assertion_id}"""
        with patch("app.api.graph.QueryService") as mock_query_service:
            mock_instance = mock_query_service.return_value
            mock_instance.get_evidence_trail.return_value = {
                "assertion": {"assertion_id": "A1", "predicate": "HAS_SYMPTOM"},
                "source": {"source_id": "doc_001", "source_type": "EMR"},
                "subject": {"id": "E567"},
                "object": {"name": "fever"},
            }

            response = client.get("/api/graph/evidence/A1")

            assert response.status_code == 200
            data = response.json()
            assert data["assertion"]["assertion_id"] == "A1"

    def test_execute_query_blocked_destructive(self, client):
        """Test that destructive queries are blocked"""
        with patch("app.api.graph.QueryService") as mock_query_service:
            mock_instance = mock_query_service.return_value
            mock_instance.execute_custom_query.side_effect = ValueError(
                "Destructive operations are not allowed"
            )

            response = client.post(
                "/api/graph/query",
                json={"query": "MATCH (n) DELETE n"},
            )

            assert response.status_code == 400
            assert "Destructive operations" in response.json()["detail"]

    def test_find_path_not_found(self, client):
        """Test GET /api/graph/path when no path exists"""
        with patch("app.api.graph.QueryService") as mock_query_service:
            mock_instance = mock_query_service.return_value
            mock_instance.find_path_between_nodes.return_value = []

            response = client.get("/api/graph/path/P123/P999")

            assert response.status_code == 404
