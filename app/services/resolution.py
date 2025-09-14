from typing import Dict, List, Any
from app.db.neo4j import Neo4jConnection


class ResolutionService:
    def __init__(self, neo4j_conn: Neo4jConnection):
        self.neo4j = neo4j_conn

    def resolve_entity(self, entity_type: str, entity_data: Dict) -> Dict[str, Any]:
        """
        Resolve whether an entity matches existing nodes or is new.
        For catalog nodes (Symptom, Disease, Test, Medication, Procedure),
        we check for matches based on code/name.
        For instance nodes (Patient, Encounter, Clinician, TestResult),
        we always create new nodes.
        """
        # Instance nodes - always create new
        if entity_type in ["patients", "encounters", "clinicians", "test_results"]:
            from app.services.id_generator import id_generator

            return {
                "decision": "new",
                "entity": entity_data,
                "to_node_id": id_generator.generate_entity_id(),
                "score": 1.0,
            }

        # Catalog nodes - check for existing matches
        matches = self._find_catalog_matches(entity_type, entity_data)

        if not matches:
            from app.services.id_generator import id_generator

            return {
                "decision": "new",
                "entity": entity_data,
                "to_node_id": id_generator.generate_entity_id(),
                "score": 1.0,
            }

        # Use the first match for catalog nodes
        best_match = matches[0]
        return {
            "decision": "match",
            "entity": entity_data,
            "to_node_id": best_match.get("uuid"),
            "score": 1.0,
        }

    def _find_catalog_matches(self, entity_type: str, entity_data: Dict) -> List[Dict]:
        """Find potential matches for catalog nodes based on code or name"""
        label = self._get_node_label(entity_type)

        # Build query based on available identifiers
        if entity_data.get("code") and entity_data.get("system"):
            # Match by code and system
            query = f"""
            MATCH (n:{label})
            WHERE n.code = $code AND n.system = $system
            RETURN n
            """
            params = {
                "code": entity_data.get("code"),
                "system": entity_data.get("system"),
            }
        elif entity_data.get("code"):
            # Match by code only
            query = f"""
            MATCH (n:{label})
            WHERE n.code = $code
            RETURN n
            """
            params = {"code": entity_data.get("code")}
        elif entity_data.get("name"):
            # Match by name (case-insensitive)
            query = f"""
            MATCH (n:{label})
            WHERE toLower(n.name) = toLower($name)
            RETURN n
            """
            params = {"name": entity_data.get("name")}
        else:
            # No identifiers to match
            return []

        try:
            results = self.neo4j.execute_query(query, params)
            return [r["n"] for r in results if r.get("n")]
        except Exception:
            return []

    def create_upsert_plan(
        self, resolved_entities: List[Dict], assertions: List[Dict]
    ) -> Dict:
        """Create a plan for upserting entities and relationships to Neo4j"""
        plan = {"nodes": [], "relationships": []}

        # Plan node upserts
        for resolution in resolved_entities:
            if resolution["decision"] in ["new", "match"]:
                entity = resolution["entity"].copy()
                # Set UUID
                entity["uuid"] = resolution["to_node_id"]

                plan["nodes"].append(
                    {
                        "operation": "MERGE",
                        "label": self._get_node_label(
                            resolution.get("entity_type", "Unknown")
                        ),
                        "uuid": entity["uuid"],
                        "properties": entity,
                    }
                )

        # Plan relationship upserts based on assertions
        for assertion in assertions:
            plan["relationships"].append(
                {
                    "operation": "MERGE",
                    "type": assertion["predicate"],
                    "from_uuid": assertion["subject_ref"],
                    "to_uuid": assertion["object_ref"],
                    "properties": {
                        "confidence": assertion.get("confidence", 1.0),
                        "source": assertion.get("source_id"),
                    },
                }
            )

        return plan

    def _get_node_label(self, entity_type: str) -> str:
        """Map entity type to Neo4j node label"""
        mapping = {
            "patients": "Patient",
            "patient": "Patient",
            "encounters": "Encounter",
            "encounter": "Encounter",
            "symptoms": "Symptom",
            "symptom": "Symptom",
            "diseases": "Disease",
            "disease": "Disease",
            "tests": "Test",
            "test": "Test",
            "test_results": "TestResult",
            "test_result": "TestResult",
            "medications": "Medication",
            "medication": "Medication",
            "clinicians": "Clinician",
            "clinician": "Clinician",
            "procedures": "Procedure",
            "procedure": "Procedure",
            "guidelines": "Guideline",
            "guideline": "Guideline",
        }
        return mapping.get(entity_type.lower(), "Unknown")
