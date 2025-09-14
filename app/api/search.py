"""Natural language search API"""

from typing import Dict
import time
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from app.models.search_schemas import (
    SearchRequest,
    SearchResponse,
    CypherResponse,
    GraphSearchResponse,
)
from app.services.entity_matcher import EntityMatcher
from app.services.cypher_generator import CypherGenerator

router = APIRouter()


def get_services(request: Request) -> Dict:
    """Get required services for search"""
    neo4j_conn = request.app.state.neo4j
    return {
        "neo4j": neo4j_conn,
        "entity_matcher": EntityMatcher(neo4j_conn),
        "cypher_generator": CypherGenerator(neo4j_conn),
    }


@router.post("/to-cypher", response_model=CypherResponse)
def natural_to_cypher(
    search_request: SearchRequest, services: Dict = Depends(get_services)
):
    """
    Convert natural language query to Cypher query

    This endpoint:
    1. Extracts entities from the natural language query
    2. Matches them to database entities using full-text search
    3. Generates a Cypher query
    4. Validates the query syntax
    """
    try:
        entity_matcher = services["entity_matcher"]
        cypher_generator = services["cypher_generator"]

        # Extract entities from natural language query
        extracted_entities = cypher_generator.extract_entities_from_query(
            search_request.query
        )

        # Match extracted entities to database entities
        entity_mappings = entity_matcher.find_best_matches(extracted_entities)

        # Generate Cypher query
        cypher, validation_status = cypher_generator.natural_to_cypher(
            search_request.query, entity_mappings
        )

        # Convert entity mappings to serializable format
        mappings_dict = {}
        for key, match in entity_mappings.items():
            mappings_dict[key] = {
                "uuid": match.uuid,
                "matched_name": match.matched_entity.get("name", "Unknown"),
                "score": match.score,
                "match_type": match.match_type,
            }

        return CypherResponse(
            cypher=cypher,
            entity_mappings=mappings_dict,
            validation_status=validation_status,
        )

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to generate Cypher: {str(e)}"
        )


@router.post("/query", response_model=SearchResponse)
def natural_language_query(
    search_request: SearchRequest, services: Dict = Depends(get_services)
):
    """
    Execute natural language query and return results

    This endpoint:
    1. Converts natural language to Cypher
    2. Executes the query
    3. Returns formatted results
    """
    try:
        neo4j = services["neo4j"]
        entity_matcher = services["entity_matcher"]
        cypher_generator = services["cypher_generator"]

        # Start timing
        start_time = time.time()

        # Extract and match entities
        extracted_entities = cypher_generator.extract_entities_from_query(
            search_request.query
        )
        entity_mappings = entity_matcher.find_best_matches(extracted_entities)

        # Generate Cypher
        cypher, _ = cypher_generator.natural_to_cypher(
            search_request.query, entity_mappings
        )

        # Execute query with limit
        if search_request.limit and "LIMIT" not in cypher.upper():
            cypher += f" LIMIT {search_request.limit}"

        results = neo4j.execute_query(cypher)

        # Calculate execution time
        execution_time = (time.time() - start_time) * 1000  # Convert to ms

        return SearchResponse(
            results=results,
            cypher_used=cypher,
            entity_mappings=entity_mappings,
            execution_time_ms=execution_time,
            result_count=len(results),
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query execution failed: {str(e)}")


@router.get("/test-fulltext/{entity_type}/{search_text}")
def test_fulltext_search(
    entity_type: str, search_text: str, services: Dict = Depends(get_services)
):
    """
    Test full-text search for debugging

    Args:
        entity_type: Type of entity (patient, disease, etc.)
        search_text: Text to search for
    """
    try:
        entity_matcher = services["entity_matcher"]

        # Try to find match
        match = entity_matcher.find_entity_match(entity_type, search_text)

        if match:
            return {
                "found": True,
                "match": {
                    "uuid": match.uuid,
                    "entity": match.matched_entity,
                    "score": match.score,
                    "match_type": match.match_type,
                },
            }
        else:
            return {"found": False, "message": f"No match found for '{search_text}'"}

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Full-text search failed: {str(e)}"
        )


@router.post("/query-graph", response_model=GraphSearchResponse)
def natural_language_query_graph(
    search_request: SearchRequest,
    services: Dict = Depends(get_services),
    hipaa: bool = Query(
        False, description="Enable HIPAA compliance mode to mask patient PII"
    ),
):
    """
    Execute natural language query and return results in graph format

    This endpoint:
    1. Converts natural language to Cypher
    2. Executes the query
    3. Returns results as nodes and edges for visualization
    """
    try:
        neo4j = services["neo4j"]
        entity_matcher = services["entity_matcher"]
        cypher_generator = services["cypher_generator"]

        # Start timing
        start_time = time.time()

        # Extract and match entities
        extracted_entities = cypher_generator.extract_entities_from_query(
            search_request.query
        )
        entity_mappings = entity_matcher.find_best_matches(extracted_entities)

        # Generate Cypher
        original_cypher, _ = cypher_generator.natural_to_cypher(
            search_request.query, entity_mappings
        )

        # Extract MATCH and WHERE clauses from original query
        import re

        # Extract everything before RETURN
        match_pattern = re.search(
            r"^(.*?)(?:RETURN|$)", original_cypher, re.IGNORECASE | re.DOTALL
        )

        if match_pattern:
            query_base = match_pattern.group(1).strip()
        else:
            query_base = original_cypher

        # Extract all node variables from MATCH patterns
        node_vars = set()
        # Find all patterns like (var), (var:Label), or (var:Label {...})
        # This regex captures the variable name from various node patterns
        node_patterns = re.findall(r"\((\w+)(?::\w+)?(?:\s*\{[^}]*\})?\)", query_base)
        node_vars.update(node_patterns)

        # Build new Cypher for nodes with labels
        if node_vars:
            # Create RETURN clause with nodes and their labels
            return_items = []
            for var in sorted(node_vars):
                return_items.append(var)
                return_items.append(f"labels({var}) as {var}_labels")
            return_clause = "RETURN " + ", ".join(return_items)
            nodes_cypher = f"{query_base}\n{return_clause}"
        else:
            # Fallback to original if no nodes found
            nodes_cypher = original_cypher

        # Apply limit
        if search_request.limit and "LIMIT" not in nodes_cypher.upper():
            nodes_cypher += f" LIMIT {search_request.limit}"

        # Execute query for nodes
        results = neo4j.execute_query(nodes_cypher)

        # Process results into graph format
        nodes_dict = {}  # Use dict to avoid duplicates
        edges_list = []

        for record in results:
            if not isinstance(record, dict):
                continue

            # Extract all nodes from the record
            for key, value in record.items():
                if isinstance(value, dict) and "uuid" in value:
                    # This is a node
                    node_uuid = value["uuid"]
                    if node_uuid not in nodes_dict:
                        # Check if we have labels for this node
                        labels_key = f"{key}_labels"
                        if labels_key in record and isinstance(
                            record[labels_key], list
                        ):
                            value["__labels__"] = record[labels_key]

                        label = _determine_node_label(value)

                        # Apply HIPAA masking for Patient nodes
                        properties = {
                            k: v
                            for k, v in value.items()
                            if k not in ["uuid", "__labels__"]
                        }
                        display_name = (
                            value.get("name") or value.get("title") or node_uuid[:8]
                        )

                        if hipaa and label == "Patient":
                            # Mask patient name
                            if "name" in properties:
                                properties["name"] = "MASKED"
                            display_name = "MASKED"

                            # Mask DOB to show only year
                            if "dob" in properties and isinstance(
                                properties["dob"], str
                            ):
                                # Keep only the year part (YYYY-**-**)
                                year = (
                                    properties["dob"][:4]
                                    if len(properties["dob"]) >= 4
                                    else "****"
                                )
                                properties["dob"] = f"{year}-**-**"

                        nodes_dict[node_uuid] = {
                            "id": node_uuid,
                            "label": label,
                            "properties": properties,
                            "display_name": display_name,
                        }

        # Get relationships between result nodes
        if nodes_dict:
            node_uuids = list(nodes_dict.keys())

            # Query for all relationships between these nodes
            rels_query = """
            MATCH (n)-[r]->(m)
            WHERE n.uuid IN $uuids AND m.uuid IN $uuids
            RETURN n.uuid as source, m.uuid as target, type(r) as type, properties(r) as props
            """
            rels_result = neo4j.execute_query(rels_query, {"uuids": node_uuids})

            for rel in rels_result:
                if isinstance(rel, dict):
                    source = rel.get("source")
                    target = rel.get("target")
                    rel_type = rel.get("type")

                    if source and target and rel_type:
                        props = rel.get("props", {})
                        if not isinstance(props, dict):
                            props = {}

                        edge_data = {
                            "id": f"{source}-{rel_type}-{target}",
                            "source": source,
                            "target": target,
                            "type": rel_type,
                            "properties": props,
                        }
                        edges_list.append(edge_data)

        # Calculate execution time
        execution_time = (time.time() - start_time) * 1000  # Convert to ms

        return GraphSearchResponse(
            nodes=list(nodes_dict.values()),
            edges=edges_list,
            cypher_used=nodes_cypher,  # Return the actually executed query
            entity_mappings=entity_mappings,
            metadata={
                "node_count": len(nodes_dict),
                "edge_count": len(edges_list),
                "execution_time_ms": execution_time,
                "original_query": search_request.query,
            },
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query execution failed: {str(e)}")


@router.post("/validate-cypher")
def validate_cypher(cypher_query: str, services: Dict = Depends(get_services)):
    """
    Validate a Cypher query without executing it

    Args:
        cypher_query: Cypher query to validate
    """
    try:
        neo4j = services["neo4j"]

        # Try EXPLAIN to validate
        explain_query = f"EXPLAIN {cypher_query}"
        neo4j.execute_query(explain_query)

        return {"valid": True, "message": "Query is valid"}

    except Exception as e:
        return {"valid": False, "error": str(e)}


def _determine_node_label(node: dict) -> str:
    """Determine node label from its properties or metadata"""

    # Priority 1: Use Neo4j label metadata if available
    if "__labels__" in node and isinstance(node["__labels__"], list):
        if node["__labels__"]:
            return node["__labels__"][0]

    if "__label__" in node:
        return node["__label__"]

    # Priority 2: Infer from properties (more flexible rules)

    # Patient: has date of birth
    if "dob" in node:
        return "Patient"

    # Clinician: has specialty or npi
    if "specialty" in node or "npi" in node:
        return "Clinician"

    # Encounter: has date with reason or department
    if "date" in node:
        if "reason" in node or "dept" in node:
            return "Encounter"

    # TestResult: has value and/or unit
    if "value" in node or ("unit" in node and "ref_low" in node):
        return "TestResult"

    # Test: has loinc or is named like a test
    if "loinc" in node or "category" in node:
        return "Test"

    # Code-based entities (Disease, Medication, Procedure, Symptom)
    if "code" in node:
        system = node.get("system", "")
        if "ICD" in system.upper():
            return "Disease"
        elif "RXNORM" in system.upper():
            return "Medication"
        elif "CPT" in system.upper() or "HCPCS" in system.upper():
            return "Procedure"
        elif "SNOMED" in system.upper():
            return "Symptom"
        else:
            # Generic coded entity
            return "ClinicalConcept"

    # Document-like entities
    if "title" in node or "content" in node:
        return "Document"

    # Source document
    if "source_id" in node or "source_type" in node:
        return "SourceDocument"

    # Default: Generic entity instead of Unknown
    return "Entity"
