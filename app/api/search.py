"""Natural language search API"""

from typing import Dict
import time
from fastapi import APIRouter, Depends, HTTPException, Request
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
        raise HTTPException(
            status_code=500, detail=f"Query execution failed: {str(e)}"
        )


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
    search_request: SearchRequest, services: Dict = Depends(get_services)
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
        cypher, _ = cypher_generator.natural_to_cypher(
            search_request.query, entity_mappings
        )

        # Execute query with limit
        if search_request.limit and "LIMIT" not in cypher.upper():
            cypher += f" LIMIT {search_request.limit}"

        results = neo4j.execute_query(cypher)

        # Process results into graph format
        nodes_dict = {}  # Use dict to avoid duplicates
        edges_list = []

        for record in results:
            if not isinstance(record, dict):
                continue

            # Extract nodes and relationships from each record
            for key, value in record.items():
                if isinstance(value, dict) and "uuid" in value:
                    # This is a node
                    node_uuid = value["uuid"]
                    if node_uuid not in nodes_dict:
                        label = _determine_node_label(value)
                        nodes_dict[node_uuid] = {
                            "id": node_uuid,
                            "label": label,
                            "properties": {k: v for k, v in value.items() if k != "uuid"},
                            "display_name": value.get("name") or value.get("title") or node_uuid[:8]
                        }

        # Get relationships between result nodes
        if nodes_dict:
            node_uuids = list(nodes_dict.keys())
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
                            "properties": props
                        }
                        edges_list.append(edge_data)

        # Calculate execution time
        execution_time = (time.time() - start_time) * 1000  # Convert to ms

        return GraphSearchResponse(
            nodes=list(nodes_dict.values()),
            edges=edges_list,
            cypher_used=cypher,
            entity_mappings=entity_mappings,
            metadata={
                "node_count": len(nodes_dict),
                "edge_count": len(edges_list),
                "execution_time_ms": execution_time,
                "original_query": search_request.query
            }
        )

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Query execution failed: {str(e)}"
        )


@router.post("/validate-cypher")
def validate_cypher(
    cypher_query: str, services: Dict = Depends(get_services)
):
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
    """Determine node label from its properties"""
    if "dob" in node:
        return "Patient"
    elif "specialty" in node:
        return "Clinician"
    elif "date" in node and "dept" in node:
        return "Encounter"
    elif "value" in node and "unit" in node:
        return "TestResult"
    elif "loinc" in node:
        return "Test"
    elif "code" in node:
        system = node.get("system", "")
        if "ICD" in system:
            return "Disease"
        elif "RxNorm" in system:
            return "Medication"
        elif "CPT" in system or "HCPCS" in system:
            return "Procedure"
        else:
            return "Symptom"
    elif "title" in node:
        return "Guideline"
    else:
        return "Unknown"