"""Entity matching service using full-text search"""

from typing import Dict, List, Optional
from app.db.neo4j import Neo4jConnection
from app.models.search_schemas import EntityMatch


class EntityMatcher:
    """Service for matching natural language entities to database entities"""

    def __init__(self, neo4j: Neo4jConnection):
        self.neo4j = neo4j

    def find_best_matches(
        self, extracted_entities: Dict[str, List[str]]
    ) -> Dict[str, EntityMatch]:
        """
        Find best matches for extracted entities using full-text search

        Args:
            extracted_entities: Dict with entity types as keys and entity names as values

        Returns:
            Dict mapping original text to EntityMatch objects
        """
        matches = {}

        for entity_type, entity_names in extracted_entities.items():
            for entity_name in entity_names:
                match = self.find_entity_match(entity_type, entity_name)
                if match:
                    matches[entity_name] = match

        return matches

    def find_entity_match(
        self, entity_type: str, query_text: str, min_score: float = 0.5
    ) -> Optional[EntityMatch]:
        """
        Find best matching entity using full-text search

        Args:
            entity_type: Type of entity (patient, disease, etc.)
            query_text: Text to search for
            min_score: Minimum similarity score to accept

        Returns:
            EntityMatch object or None if no good match found
        """
        # Map entity type to full-text index name
        index_map = {
            "patient": "patient_search",
            "patients": "patient_search",
            "clinician": "clinician_search",
            "clinicians": "clinician_search",
            "disease": "disease_search",
            "diseases": "disease_search",
            "symptom": "symptom_search",
            "symptoms": "symptom_search",
            "medication": "medication_search",
            "medications": "medication_search",
            "procedure": "procedure_search",
            "procedures": "procedure_search",
            "test": "test_search",
            "tests": "test_search",
        }

        index_name = index_map.get(entity_type.lower())
        if not index_name:
            return None

        # Try different matching strategies
        # 1. Exact match
        exact_match = self._exact_match(index_name, query_text)
        if exact_match:
            return exact_match

        # 2. Fuzzy match (allows typos)
        fuzzy_match = self._fuzzy_match(index_name, query_text, min_score)
        if fuzzy_match:
            return fuzzy_match

        # 3. Partial match (wildcard)
        partial_match = self._partial_match(index_name, query_text, min_score)
        if partial_match:
            return partial_match

        return None

    def _exact_match(self, index_name: str, query_text: str) -> Optional[EntityMatch]:
        """Try exact match using full-text search"""
        try:
            query = f"""
            CALL db.index.fulltext.queryNodes('{index_name}', $query)
            YIELD node, score
            WHERE score > 0.9
            RETURN node, score
            ORDER BY score DESC
            LIMIT 1
            """

            results = self.neo4j.execute_query(query, {"query": f'"{query_text}"'})

            if results:
                node = results[0]["node"]
                return EntityMatch(
                    original_text=query_text,
                    matched_entity=dict(node),
                    uuid=node.get("uuid"),
                    score=results[0]["score"],
                    match_type="exact",
                )
        except Exception as e:
            print(f"Exact match error: {e}")

        return None

    def _fuzzy_match(
        self, index_name: str, query_text: str, min_score: float
    ) -> Optional[EntityMatch]:
        """Try fuzzy match allowing typos"""
        try:
            # Add fuzzy operator (~) to allow typos
            # ~2 means allow up to 2 character edits
            fuzzy_query = f"{query_text}~2"

            query = f"""
            CALL db.index.fulltext.queryNodes('{index_name}', $query)
            YIELD node, score
            WHERE score > $min_score
            RETURN node, score
            ORDER BY score DESC
            LIMIT 1
            """

            results = self.neo4j.execute_query(
                query, {"query": fuzzy_query, "min_score": min_score}
            )

            if results:
                node = results[0]["node"]
                return EntityMatch(
                    original_text=query_text,
                    matched_entity=dict(node),
                    uuid=node.get("uuid"),
                    score=results[0]["score"],
                    match_type="fuzzy",
                )
        except Exception as e:
            print(f"Fuzzy match error: {e}")

        return None

    def _partial_match(
        self, index_name: str, query_text: str, min_score: float
    ) -> Optional[EntityMatch]:
        """Try partial match using wildcards"""
        try:
            # Try prefix match first
            wildcard_query = f"{query_text}*"

            query = f"""
            CALL db.index.fulltext.queryNodes('{index_name}', $query)
            YIELD node, score
            WHERE score > $min_score
            RETURN node, score
            ORDER BY score DESC
            LIMIT 1
            """

            results = self.neo4j.execute_query(
                query, {"query": wildcard_query, "min_score": min_score}
            )

            if results:
                node = results[0]["node"]
                return EntityMatch(
                    original_text=query_text,
                    matched_entity=dict(node),
                    uuid=node.get("uuid"),
                    score=results[0]["score"],
                    match_type="partial",
                )

            # Try contains match if prefix didn't work
            wildcard_query = f"*{query_text}*"
            results = self.neo4j.execute_query(
                query, {"query": wildcard_query, "min_score": min_score * 0.8}
            )

            if results:
                node = results[0]["node"]
                return EntityMatch(
                    original_text=query_text,
                    matched_entity=dict(node),
                    uuid=node.get("uuid"),
                    score=results[0]["score"],
                    match_type="partial",
                )
        except Exception as e:
            print(f"Partial match error: {e}")

        return None

    def batch_match_entities(
        self, entity_list: List[str], entity_type: str
    ) -> Dict[str, EntityMatch]:
        """
        Match multiple entities of the same type

        Args:
            entity_list: List of entity names to match
            entity_type: Type of all entities

        Returns:
            Dict mapping original names to EntityMatch objects
        """
        matches = {}
        for entity_name in entity_list:
            match = self.find_entity_match(entity_type, entity_name)
            if match:
                matches[entity_name] = match

        return matches