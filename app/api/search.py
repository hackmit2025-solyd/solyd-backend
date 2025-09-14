"""Natural language search API"""

from typing import Dict
import time
from fastapi import APIRouter, Depends, HTTPException, Request
from app.db.neo4j import Neo4jConnection
from app.models.search_schemas import (
    SearchRequest,
    SearchResponse,
    CypherResponse,
    ErrorResponse,
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
async def natural_to_cypher(
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
async def natural_language_query(
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
        cypher, validation_status = cypher_generator.natural_to_cypher(
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
async def test_fulltext_search(
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


@router.post("/validate-cypher")
async def validate_cypher(
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