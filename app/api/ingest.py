from typing import Dict

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.neo4j import Neo4jConnection
from app.models.schemas import DocumentUpload
from app.services.extraction import extraction_service
from app.services.resolution import ResolutionService

router = APIRouter()


def get_services(request: Request, db: Session = Depends(get_db)) -> Dict:
    """Get all required services"""
    neo4j_conn = request.app.state.neo4j
    return {
        "extraction": extraction_service,
        "resolution": ResolutionService(neo4j_conn),
        "neo4j": neo4j_conn,
        "db": db,
    }


@router.post("/document")
def upload_document(document: DocumentUpload, services: Dict = Depends(get_services)):
    """Upload and process a document"""
    extraction_service = services["extraction"]
    resolution_service = services["resolution"]
    neo4j = services["neo4j"]

    try:
        # Step 1: Extract entities from document text
        extracted = extraction_service.extract_entities(document.text)

        # Step 2: Normalize entities
        normalized = extraction_service.normalize_entities(extracted["entities"])

        # Step 3: Resolve entities
        resolved_entities = []
        for entity_type, entities in normalized.items():
            for entity in entities:
                resolution = resolution_service.resolve_entity(
                    entity_type, entity
                )
                resolution["entity_type"] = entity_type
                resolved_entities.append(resolution)

        # Step 4: Create upsert plan
        upsert_plan = resolution_service.create_upsert_plan(
            resolved_entities, extracted.get("assertions", [])
        )

        # Step 5: Execute upserts to Neo4j
        upsert_results = _execute_upsert_plan(neo4j, upsert_plan)

        return {
            "entities_extracted": sum(
                len(entities) for entities in normalized.values()
            ),
            "assertions_created": len(extracted.get("assertions", [])),
            "upsert_results": upsert_results,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Document processing failed: {e}")


def _execute_upsert_plan(neo4j: Neo4jConnection, plan: Dict) -> Dict:
    """Execute the upsert plan against Neo4j"""
    results = {"nodes_created": 0, "relationships_created": 0, "errors": []}

    # Upsert nodes
    for node_plan in plan.get("nodes", []):
        try:
            label = node_plan["label"]
            uuid = node_plan["uuid"]
            props = node_plan["properties"]

            # Build MERGE query using UUID
            query = f"""
            MERGE (n:{label} {{uuid: $uuid}})
            SET n += $props
            RETURN n
            """

            neo4j.execute_query(query, {"uuid": uuid, "props": props})
            results["nodes_created"] += 1

        except Exception as e:
            results["errors"].append(f"Node upsert failed: {e}")

    # Upsert relationships
    for rel_plan in plan.get("relationships", []):
        try:
            rel_type = rel_plan["type"]
            from_uuid = rel_plan["from_uuid"]
            to_uuid = rel_plan["to_uuid"]
            props = rel_plan["properties"]

            # Build MERGE query for relationship using UUIDs
            query = f"""
            MATCH (from {{uuid: $from_uuid}})
            MATCH (to {{uuid: $to_uuid}})
            MERGE (from)-[r:{rel_type}]->(to)
            SET r += $props
            RETURN r
            """

            neo4j.execute_query(
                query, {"from_uuid": from_uuid, "to_uuid": to_uuid, "props": props}
            )
            results["relationships_created"] += 1

        except Exception as e:
            error_msg = f"Relationship upsert failed - Type: {rel_type}, From: {from_uuid}, To: {to_uuid}, Error: {e}"
            print(error_msg)
            results["errors"].append(error_msg)

    return results