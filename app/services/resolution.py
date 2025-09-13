from typing import Dict, List, Any, Optional
from app.db.neo4j import Neo4jConnection


class ResolutionService:
    def __init__(self, neo4j_conn: Neo4jConnection):
        self.neo4j = neo4j_conn

    def resolve_entity(self, entity_type: str, entity_data: Dict,
                      source_id: Optional[str] = None) -> Dict[str, Any]:
        """Resolve whether an entity matches existing nodes or is new"""
        # Get potential matches from graph
        matches = self._find_potential_matches(entity_type, entity_data)

        if not matches:
            return {
                "decision": "new",
                "entity": entity_data,
                "to_node_id": self._generate_node_id(entity_type, entity_data, source_id),
                "score": 1.0,
            }

        # Calculate similarity scores
        best_match = self._find_best_match(entity_data, matches)

        if best_match["score"] > 0.8:  # Threshold for matching
            return {
                "decision": "match",
                "entity": entity_data,
                "to_node_id": best_match["node_id"],
                "score": best_match["score"],
            }
        elif best_match["score"] > 0.5:  # Uncertain range
            return {
                "decision": "abstain",
                "entity": entity_data,
                "to_node_id": None,
                "score": best_match["score"],
                "potential_match": best_match["node_id"],
            }
        else:
            return {
                "decision": "new",
                "entity": entity_data,
                "to_node_id": self._generate_node_id(entity_type, entity_data, source_id),
                "score": 1.0 - best_match["score"],
            }

    def _find_potential_matches(
        self, entity_type: str, entity_data: Dict
    ) -> List[Dict]:
        """Find potential matching nodes in the graph"""
        label = self._get_node_label(entity_type)

        # Build match query based on entity type
        if entity_type == "patients":
            query = f"""
            MATCH (n:{label})
            WHERE n.id = $id OR n.name = $name
            RETURN n
            """
            params = {"id": entity_data.get("id"), "name": entity_data.get("name")}

        elif entity_type == "symptoms":
            query = f"""
            MATCH (n:{label})
            WHERE n.code = $code OR n.name = $name
            RETURN n
            """
            params = {"code": entity_data.get("code"), "name": entity_data.get("name")}

        elif entity_type in ["diseases", "medications", "procedures"]:
            query = f"""
            MATCH (n:{label})
            WHERE n.code = $code
            RETURN n
            """
            params = {"code": entity_data.get("code")}

        else:
            query = f"""
            MATCH (n:{label})
            WHERE n.id = $id
            RETURN n
            """
            params = {"id": entity_data.get("id")}

        try:
            results = self.neo4j.execute_query(query, params)
            return [r["n"] for r in results if r.get("n")]
        except Exception as e:
            print(f"Error finding matches: {e}")
            return []

    def _find_best_match(self, entity_data: Dict, matches: List[Dict]) -> Dict:
        """Find the best match from potential matches"""
        best_score = 0
        best_match = None

        for match in matches:
            score = self._calculate_similarity(entity_data, match)
            if score > best_score:
                best_score = score
                best_match = match

        if best_match:
            node_id = (
                best_match.get("id") or best_match.get("code") or best_match.get("name")
            )
            return {"node_id": node_id, "score": best_score, "data": best_match}

        return {"node_id": None, "score": 0, "data": None}

    def _calculate_similarity(self, entity1: Dict, entity2: Dict) -> float:
        """Calculate similarity score between two entities"""
        score = 0.0
        comparisons = 0

        # Compare common fields
        for field in ["id", "code", "name"]:
            if field in entity1 and field in entity2:
                comparisons += 1
                if entity1[field] == entity2[field]:
                    score += 1.0
                elif isinstance(entity1[field], str) and isinstance(
                    entity2[field], str
                ):
                    # Partial string matching
                    str1 = entity1[field].lower()
                    str2 = entity2[field].lower()
                    if str1 in str2 or str2 in str1:
                        score += 0.5

        return score / comparisons if comparisons > 0 else 0.0

    def _generate_node_id(self, entity_type: str, entity_data: Dict,
                         source_id: Optional[str] = None) -> str:
        """Generate a new node ID for an entity using centralized ID generator"""
        from app.services.id_generator import id_generator

        # Use the centralized ID generator for consistent ID generation
        # This is especially important for encounters
        return id_generator.generate_entity_id(entity_type, entity_data, source_id)

    def _get_node_label(self, entity_type: str) -> str:
        """Map entity type to Neo4j node label"""
        mapping = {
            "patients": "Patient",
            "encounters": "Encounter",
            "symptoms": "Symptom",
            "diseases": "Disease",
            "tests": "Test",
            "test_results": "TestResult",
            "medications": "Medication",
            "procedures": "Procedure",
            "clinicians": "Clinician",
            "guidelines": "Guideline",
        }
        return mapping.get(entity_type, entity_type.capitalize())

    def create_upsert_plan(
        self, resolved_entities: List[Dict], assertions: List[Dict]
    ) -> Dict:
        """Create a plan for upserting entities and relationships to Neo4j"""
        plan = {"nodes": [], "relationships": []}

        # Plan node upserts
        for resolution in resolved_entities:
            if resolution["decision"] in ["new", "match"]:
                plan["nodes"].append(
                    {
                        "operation": "MERGE",
                        "label": self._get_node_label(
                            resolution.get("entity_type", "Unknown")
                        ),
                        "id_property": self._get_id_property(resolution["entity"]),
                        "properties": resolution["entity"],
                        "node_id": resolution["to_node_id"],
                    }
                )

        # Plan relationship upserts based on assertions
        for assertion in assertions:
            plan["relationships"].append(
                {
                    "operation": "MERGE",
                    "type": assertion["predicate"],
                    "from_node": assertion["subject_ref"],
                    "to_node": assertion["object_ref"],
                    "properties": {
                        "confidence": assertion.get("confidence", 1.0),
                        "negation": assertion.get("negation", False),
                        "source_id": assertion.get("source_id"),
                        "time": assertion.get("time"),
                    },
                }
            )

        return plan

    def _get_id_property(self, entity: Dict) -> tuple:
        """Get the ID property name and value for an entity"""
        if "id" in entity:
            return ("id", entity["id"])
        elif "code" in entity:
            return ("code", entity["code"])
        elif "name" in entity:
            return ("name", entity["name"])
        else:
            return ("id", "unknown")
