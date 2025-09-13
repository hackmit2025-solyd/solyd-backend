"""
Optimized and secure graph writing service for Neo4j
Implements batch processing with UNWIND and injection prevention
"""

from typing import Dict, List, Any, Optional, Tuple
import re
from app.db.neo4j import Neo4jConnection
from app.services.id_generator import id_generator
from datetime import datetime


class GraphWriter:
    """Secure and optimized graph writing operations"""

    # Whitelist of allowed node labels
    ALLOWED_LABELS = {
        "Patient",
        "Encounter",
        "Symptom",
        "Disease",
        "Test",
        "TestResult",
        "Medication",
        "Procedure",
        "Clinician",
        "Guideline",
        "SourceDocument",
        "Assertion",
        "OntologyTerm",
        "ExternalResource",
        "Chunk",
    }

    # Whitelist of allowed relationship types
    ALLOWED_RELATIONSHIPS = {
        "HAS_ENCOUNTER",
        "HAS_SYMPTOM",
        "DIAGNOSED_AS",
        "PRESCRIBED",
        "ORDERED_TEST",
        "YIELDED",
        "TREATED_BY",
        "REFERRED_TO",
        "ALLERGIC_TO",
        "CONTRAINDICATED",
        "PERFORMED",
        "EVIDENCED_BY",
        "ALIGNS_WITH",
        "CITES",
        "EXTRACTED_FROM",
        "CONFLICTS_WITH",
        "RESOLVES_TO",
        "PART_OF",
        "FOLLOWED_BY",
    }

    # Property types that need special handling
    TEMPORAL_PROPERTIES = {
        "valid_from",
        "valid_to",
        "created_at",
        "updated_at",
        "time",
        "date",
    }

    def __init__(self, neo4j_conn: Neo4jConnection):
        """Initialize with Neo4j connection"""
        self.neo4j = neo4j_conn

    def batch_upsert_nodes(
        self, nodes: List[Dict[str, Any]], batch_size: int = 100
    ) -> Dict[str, Any]:
        """Batch upsert nodes using UNWIND for optimal performance"""

        results = {"created": 0, "updated": 0, "errors": [], "batches_processed": 0}

        # Group nodes by label for efficient processing
        nodes_by_label = {}
        for node in nodes:
            label = self._validate_label(node.get("label"))
            if not label:
                results["errors"].append(f"Invalid label: {node.get('label')}")
                continue

            if label not in nodes_by_label:
                nodes_by_label[label] = []
            nodes_by_label[label].append(node)

        # Process each label group in batches
        for label, label_nodes in nodes_by_label.items():
            for i in range(0, len(label_nodes), batch_size):
                batch = label_nodes[i : i + batch_size]
                batch_result = self._upsert_node_batch(label, batch)

                results["created"] += batch_result.get("created", 0)
                results["updated"] += batch_result.get("updated", 0)
                results["errors"].extend(batch_result.get("errors", []))
                results["batches_processed"] += 1

        return results

    def _upsert_node_batch(self, label: str, nodes: List[Dict]) -> Dict[str, Any]:
        """Upsert a batch of nodes with the same label"""

        # Prepare node data for UNWIND
        node_data = []
        for node in nodes:
            properties = self._sanitize_properties(node.get("properties", {}))

            # Add temporal properties
            if "valid_from" not in properties:
                properties["valid_from"] = datetime.now().isoformat()

            # Determine unique identifier
            id_key = node.get("id_key", "id")
            id_value = properties.get(id_key)

            if not id_value:
                # Generate ID if missing
                id_value = id_generator.generate_entity_id(label.lower(), properties)
                properties[id_key] = id_value

            node_data.append(
                {"id_key": id_key, "id_value": id_value, "properties": properties}
            )

        # Build UNWIND query with MERGE
        query = f"""
        UNWIND $nodes AS node
        MERGE (n:{label} {{{node_data[0]['id_key']}: node.id_value}})
        ON CREATE SET
            n = node.properties,
            n.created_at = datetime(),
            n._created_count = 1
        ON MATCH SET
            n += node.properties,
            n.updated_at = datetime(),
            n._updated_count = coalesce(n._updated_count, 0) + 1
        RETURN
            CASE WHEN n._created_count = 1 THEN 'created' ELSE 'updated' END AS operation,
            n.{node_data[0]['id_key']} AS node_id
        """

        try:
            results = self.neo4j.execute_query(query, {"nodes": node_data})

            operation_counts = {"created": 0, "updated": 0}
            for record in results:
                operation_counts[record["operation"]] += 1

            return operation_counts

        except Exception as e:
            return {"errors": [f"Batch upsert failed for {label}: {str(e)}"]}

    def batch_upsert_relationships(
        self, relationships: List[Dict[str, Any]], batch_size: int = 100
    ) -> Dict[str, Any]:
        """Batch upsert relationships using UNWIND"""

        results = {"created": 0, "updated": 0, "errors": [], "batches_processed": 0}

        # Group relationships by type for efficient processing
        rels_by_type = {}
        for rel in relationships:
            rel_type = self._validate_relationship_type(rel.get("type"))
            if not rel_type:
                results["errors"].append(
                    f"Invalid relationship type: {rel.get('type')}"
                )
                continue

            if rel_type not in rels_by_type:
                rels_by_type[rel_type] = []
            rels_by_type[rel_type].append(rel)

        # Process each type group in batches
        for rel_type, type_rels in rels_by_type.items():
            for i in range(0, len(type_rels), batch_size):
                batch = type_rels[i : i + batch_size]
                batch_result = self._upsert_relationship_batch(rel_type, batch)

                results["created"] += batch_result.get("created", 0)
                results["updated"] += batch_result.get("updated", 0)
                results["errors"].extend(batch_result.get("errors", []))
                results["batches_processed"] += 1

        return results

    def _upsert_relationship_batch(
        self, rel_type: str, relationships: List[Dict]
    ) -> Dict[str, Any]:
        """Upsert a batch of relationships with the same type"""

        # Prepare relationship data for UNWIND
        rel_data = []
        for rel in relationships:
            properties = self._sanitize_properties(rel.get("properties", {}))

            # Add temporal properties
            if "valid_from" not in properties:
                properties["valid_from"] = datetime.now().isoformat()

            # Get node references
            from_node = rel.get("from_node")
            to_node = rel.get("to_node")

            if not from_node or not to_node:
                continue

            rel_data.append(
                {
                    "from_id": from_node.get("id")
                    if isinstance(from_node, dict)
                    else from_node,
                    "to_id": to_node.get("id")
                    if isinstance(to_node, dict)
                    else to_node,
                    "properties": properties,
                }
            )

        if not rel_data:
            return {"errors": ["No valid relationships to process"]}

        # Build UNWIND query
        query = f"""
        UNWIND $relationships AS rel
        MATCH (from {{id: rel.from_id}})
        MATCH (to {{id: rel.to_id}})
        MERGE (from)-[r:{rel_type}]->(to)
        ON CREATE SET
            r = rel.properties,
            r.created_at = datetime(),
            r._created = true
        ON MATCH SET
            r += rel.properties,
            r.updated_at = datetime(),
            r._updated = true
        RETURN
            CASE WHEN r._created THEN 'created' ELSE 'updated' END AS operation,
            id(r) AS rel_id
        """

        try:
            results = self.neo4j.execute_query(query, {"relationships": rel_data})

            operation_counts = {"created": 0, "updated": 0}
            for record in results:
                operation_counts[record["operation"]] += 1

            return operation_counts

        except Exception as e:
            return {
                "errors": [f"Batch relationship upsert failed for {rel_type}: {str(e)}"]
            }

    def upsert_assertion_with_evidence(
        self, assertion: Dict[str, Any], chunk_ids: List[str]
    ) -> Dict[str, Any]:
        """Create assertion node with EVIDENCED_BY relationships to chunks"""

        # Create assertion node
        assertion_id = assertion.get(
            "assertion_id"
        ) or id_generator.generate_assertion_id(
            assertion.get("predicate"),
            assertion.get("subject_ref"),
            assertion.get("object_ref"),
            assertion.get("source_id"),
            chunk_ids[0] if chunk_ids else None,
        )

        assertion_props = self._sanitize_properties(
            {
                "assertion_id": assertion_id,
                "predicate": assertion.get("predicate"),
                "subject_ref": assertion.get("subject_ref"),
                "object_ref": assertion.get("object_ref"),
                "negation": assertion.get("negation", False),
                "uncertainty": assertion.get("uncertainty", False),
                "confidence": assertion.get("confidence", 1.0),
                "time": assertion.get("time"),
                "source_id": assertion.get("source_id"),
                "valid_from": assertion.get("valid_from", datetime.now().isoformat()),
            }
        )

        # Create assertion node
        node_query = """
        MERGE (a:Assertion {assertion_id: $assertion_id})
        SET a = $properties
        RETURN a.assertion_id AS id
        """

        try:
            self.neo4j.execute_query(
                node_query,
                {"assertion_id": assertion_id, "properties": assertion_props},
            )

            # Create EVIDENCED_BY relationships to chunks
            if chunk_ids:
                evidence_query = """
                UNWIND $chunk_ids AS chunk_id
                MATCH (a:Assertion {assertion_id: $assertion_id})
                MATCH (c:Chunk {chunk_id: chunk_id})
                MERGE (a)-[:EVIDENCED_BY]->(c)
                """

                self.neo4j.execute_query(
                    evidence_query,
                    {"assertion_id": assertion_id, "chunk_ids": chunk_ids},
                )

            # Create relationship based on assertion predicate
            self._create_assertion_relationship(assertion_props)

            return {"assertion_id": assertion_id, "status": "created"}

        except Exception as e:
            return {"error": f"Failed to create assertion: {str(e)}"}

    def _create_assertion_relationship(self, assertion: Dict[str, Any]):
        """Create the actual relationship described by the assertion"""

        predicate = assertion.get("predicate")
        if predicate not in self.ALLOWED_RELATIONSHIPS:
            return

        # Build relationship with assertion reference
        query = f"""
        MATCH (from {{id: $from_id}})
        MATCH (to {{id: $to_id}})
        MATCH (a:Assertion {{assertion_id: $assertion_id}})
        MERGE (from)-[r:{predicate}]->(to)
        SET r.assertion_id = $assertion_id,
            r.negation = $negation,
            r.confidence = $confidence,
            r.time = $time
        MERGE (r)-[:FROM_ASSERTION]->(a)
        """

        try:
            self.neo4j.execute_query(
                query,
                {
                    "from_id": assertion.get("subject_ref"),
                    "to_id": assertion.get("object_ref"),
                    "assertion_id": assertion.get("assertion_id"),
                    "negation": assertion.get("negation", False),
                    "confidence": assertion.get("confidence", 1.0),
                    "time": assertion.get("time"),
                },
            )
        except Exception as e:
            print(f"Failed to create assertion relationship: {e}")

    def _validate_label(self, label: str) -> Optional[str]:
        """Validate and sanitize node label to prevent injection"""
        if not label:
            return None

        # Remove any special characters
        clean_label = re.sub(r"[^a-zA-Z0-9_]", "", label)

        # Check against whitelist
        if clean_label not in self.ALLOWED_LABELS:
            return None

        return clean_label

    def _validate_relationship_type(self, rel_type: str) -> Optional[str]:
        """Validate and sanitize relationship type to prevent injection"""
        if not rel_type:
            return None

        # Remove any special characters and convert to uppercase
        clean_type = re.sub(r"[^a-zA-Z0-9_]", "", rel_type).upper()

        # Check against whitelist
        if clean_type not in self.ALLOWED_RELATIONSHIPS:
            return None

        return clean_type

    def _sanitize_properties(self, properties: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitize properties to prevent injection and ensure compatibility"""
        sanitized = {}

        for key, value in properties.items():
            # Sanitize key - remove special characters
            clean_key = re.sub(r"[^a-zA-Z0-9_]", "_", key)

            # Skip if key starts with underscore (internal)
            if clean_key.startswith("_"):
                continue

            # Handle different value types
            if value is None:
                continue
            elif isinstance(value, (str, int, float, bool)):
                sanitized[clean_key] = value
            elif isinstance(value, datetime):
                sanitized[clean_key] = value.isoformat()
            elif isinstance(value, (list, tuple)):
                # Convert lists to strings for Neo4j
                sanitized[clean_key] = str(value)
            elif isinstance(value, dict):
                # Convert nested dicts to JSON strings
                import json

                sanitized[clean_key] = json.dumps(value)
            else:
                # Convert other types to string
                sanitized[clean_key] = str(value)

        return sanitized

    def validate_schema(
        self, operation: str, data: Dict[str, Any]
    ) -> Tuple[bool, Optional[str]]:
        """Validate operation against schema whitelist"""

        if operation == "create_node":
            label = data.get("label")
            if not self._validate_label(label):
                return False, f"Invalid label: {label}"

        elif operation == "create_relationship":
            rel_type = data.get("type")
            if not self._validate_relationship_type(rel_type):
                return False, f"Invalid relationship type: {rel_type}"

        return True, None


# Singleton instance (initialized in main app)
graph_writer = None
