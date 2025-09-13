from unittest.mock import MagicMock


class TestResolutionService:
    def test_resolve_entity_new(self, resolution_service):
        """Test resolving a new entity"""
        # Mock no existing matches
        resolution_service.neo4j.execute_query = MagicMock(return_value=[])

        entity_data = {"id": "P999", "name": "New Patient"}
        result = resolution_service.resolve_entity("patients", entity_data)

        assert result["decision"] == "new"
        assert result["to_node_id"] == "P999"
        assert result["score"] == 1.0

    def test_resolve_entity_match(self, resolution_service):
        """Test resolving an existing entity"""
        # Mock existing match
        resolution_service.neo4j.execute_query = MagicMock(
            return_value=[{"n": {"id": "P123", "name": "John Doe"}}]
        )

        entity_data = {"id": "P123", "name": "John Doe"}
        result = resolution_service.resolve_entity("patients", entity_data)

        assert result["decision"] == "match"
        assert result["to_node_id"] == "P123"
        assert result["score"] > 0.8

    def test_resolve_entity_abstain(self, resolution_service):
        """Test uncertain entity resolution"""
        # Mock partial match
        resolution_service.neo4j.execute_query = MagicMock(
            return_value=[{"n": {"id": "P123", "name": "John Smith"}}]
        )

        # Patch similarity calculation to return uncertain score
        resolution_service._calculate_similarity = MagicMock(return_value=0.6)

        entity_data = {"id": "P124", "name": "John Doe"}
        result = resolution_service.resolve_entity("patients", entity_data)

        assert result["decision"] == "abstain"
        assert result["score"] == 0.6
        assert "potential_match" in result

    def test_calculate_similarity_exact_match(self, resolution_service):
        """Test similarity calculation for exact match"""
        entity1 = {"id": "P123", "name": "John Doe"}
        entity2 = {"id": "P123", "name": "John Doe"}

        score = resolution_service._calculate_similarity(entity1, entity2)

        assert score == 1.0

    def test_calculate_similarity_partial_match(self, resolution_service):
        """Test similarity calculation for partial match"""
        entity1 = {"id": "P123", "name": "John Doe"}
        entity2 = {"id": "P124", "name": "John Doe"}

        score = resolution_service._calculate_similarity(entity1, entity2)

        assert 0 < score < 1.0

    def test_calculate_similarity_no_match(self, resolution_service):
        """Test similarity calculation for no match"""
        entity1 = {"id": "P123", "name": "John Doe"}
        entity2 = {"id": "P999", "name": "Jane Smith"}

        score = resolution_service._calculate_similarity(entity1, entity2)

        assert score == 0.0

    def test_generate_node_id_with_id(self, resolution_service):
        """Test node ID generation when ID exists"""
        entity_data = {"id": "P123", "name": "John Doe"}
        node_id = resolution_service._generate_node_id("patients", entity_data)

        assert node_id == "P123"

    def test_generate_node_id_with_code(self, resolution_service):
        """Test node ID generation when code exists"""
        entity_data = {"code": "ICD10:J10", "name": "Influenza"}
        node_id = resolution_service._generate_node_id("diseases", entity_data)

        assert node_id == "ICD10:J10"

    def test_generate_node_id_with_name(self, resolution_service):
        """Test node ID generation when only name exists"""
        entity_data = {"name": "fever symptom"}
        node_id = resolution_service._generate_node_id("symptoms", entity_data)

        assert node_id == "symptoms:fever_symptom"

    def test_get_node_label(self, resolution_service):
        """Test entity type to node label mapping"""
        assert resolution_service._get_node_label("patients") == "Patient"
        assert resolution_service._get_node_label("encounters") == "Encounter"
        assert resolution_service._get_node_label("symptoms") == "Symptom"
        assert resolution_service._get_node_label("diseases") == "Disease"
        assert resolution_service._get_node_label("unknown") == "Unknown"

    def test_create_upsert_plan(self, resolution_service):
        """Test creating upsert plan"""
        resolved_entities = [
            {
                "decision": "new",
                "entity": {"id": "P123", "name": "John Doe"},
                "entity_type": "patients",
                "to_node_id": "P123",
            },
            {
                "decision": "match",
                "entity": {"code": "SNOMED:386661006", "name": "Fever"},
                "entity_type": "symptoms",
                "to_node_id": "SNOMED:386661006",
            },
            {
                "decision": "abstain",  # Should be skipped
                "entity": {"id": "E999"},
                "entity_type": "encounters",
                "to_node_id": None,
            },
        ]

        assertions = [
            {
                "predicate": "HAS_SYMPTOM",
                "subject_ref": "E567",
                "object_ref": "fever",
                "confidence": 0.95,
                "negation": False,
            }
        ]

        plan = resolution_service.create_upsert_plan(resolved_entities, assertions)

        assert len(plan["nodes"]) == 2  # Only new and match, not abstain
        assert len(plan["relationships"]) == 1
        assert plan["nodes"][0]["label"] == "Patient"
        assert plan["relationships"][0]["type"] == "HAS_SYMPTOM"

    def test_find_potential_matches_patients(self, resolution_service):
        """Test finding potential matches for patients"""
        entity_data = {"id": "P123", "name": "John Doe"}
        mock_results = [{"n": {"id": "P123", "name": "John Doe"}}]
        resolution_service.neo4j.execute_query = MagicMock(return_value=mock_results)

        matches = resolution_service._find_potential_matches("patients", entity_data)

        assert len(matches) == 1
        assert matches[0]["id"] == "P123"

    def test_find_potential_matches_symptoms(self, resolution_service):
        """Test finding potential matches for symptoms"""
        entity_data = {"code": "SNOMED:386661006", "name": "fever"}
        mock_results = [{"n": {"code": "SNOMED:386661006", "name": "Fever"}}]
        resolution_service.neo4j.execute_query = MagicMock(return_value=mock_results)

        matches = resolution_service._find_potential_matches("symptoms", entity_data)

        assert len(matches) == 1
        assert matches[0]["code"] == "SNOMED:386661006"
