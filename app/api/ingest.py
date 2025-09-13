from fastapi import APIRouter, HTTPException, Depends, Request, UploadFile, File
from typing import Dict, List
from app.services.ingestion import IngestionService
from app.services.extraction import ExtractionService
from app.services.resolution import ResolutionService
from app.models.schemas import DocumentUpload, ExtractionRequest, ChunkData
from app.db.neo4j import Neo4jConnection

router = APIRouter()


def get_services(request: Request) -> Dict:
    """Get all required services"""
    neo4j_conn = request.app.state.neo4j
    return {
        "ingestion": IngestionService(),
        "extraction": ExtractionService(),
        "resolution": ResolutionService(neo4j_conn),
        "neo4j": neo4j_conn,
    }


@router.post("/document")
def upload_document(document: DocumentUpload, services: Dict = Depends(get_services)):
    """Upload and process a document"""
    ingestion_service = services["ingestion"]
    extraction_service = services["extraction"]
    resolution_service = services["resolution"]
    neo4j = services["neo4j"]

    try:
        # Step 1: Process document into chunks
        processed = ingestion_service.process_document(document)

        # Step 2: Extract entities from each chunk
        chunk_extractions = []
        for chunk_dict in processed["chunks"]:
            chunk = ChunkData(**chunk_dict)
            extraction = extraction_service.extract_entities_from_chunk(
                chunk, document.source_id
            )
            chunk_extractions.append(extraction)

        # Step 3: Merge extractions
        merged = ingestion_service.merge_extractions(chunk_extractions)

        # Step 4: Normalize entities
        normalized = extraction_service.normalize_entities(merged["entities"])

        # Step 5: Resolve entities
        resolved_entities = []
        for entity_type, entities in normalized.items():
            for entity in entities:
                resolution = resolution_service.resolve_entity(entity_type, entity)
                resolution["entity_type"] = entity_type
                resolved_entities.append(resolution)

        # Step 6: Create upsert plan
        upsert_plan = resolution_service.create_upsert_plan(
            resolved_entities, merged["assertions"]
        )

        # Step 7: Execute upserts to Neo4j
        upsert_results = _execute_upsert_plan(neo4j, upsert_plan)

        return {
            "source_id": document.source_id,
            "chunks_processed": len(processed["chunks"]),
            "entities_extracted": sum(
                len(entities) for entities in normalized.values()
            ),
            "assertions_created": len(merged["assertions"]),
            "upsert_results": upsert_results,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Document processing failed: {e}")


@router.post("/file")
def upload_file(
    file: UploadFile = File(...),
    source_type: str = "PDF",
    services: Dict = Depends(get_services),
):
    """Upload a file for processing"""
    try:
        content = file.file.read().decode("utf-8")
        document = DocumentUpload(
            source_id=file.filename,
            source_type=source_type,
            title=file.filename,
            content=content,
        )
        return upload_document(document, services)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"File upload failed: {e}")


@router.post("/extract")
def extract_entities(
    request: ExtractionRequest, services: Dict = Depends(get_services)
):
    """Extract entities from pre-chunked text"""
    extraction_service = services["extraction"]

    try:
        chunk_extractions = []
        for chunk in request.chunks:
            extraction = extraction_service.extract_entities_from_chunk(
                chunk, request.source.source_id
            )
            chunk_extractions.append(extraction)

        # Merge all extractions
        ingestion_service = services["ingestion"]
        merged = ingestion_service.merge_extractions(chunk_extractions)

        return merged

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Extraction failed: {e}")


@router.post("/bulk")
def bulk_upload(
    documents: List[DocumentUpload], services: Dict = Depends(get_services)
):
    """Process multiple documents in bulk"""
    results = []
    errors = []

    for doc in documents:
        try:
            result = upload_document(doc, services)
            results.append({"source_id": doc.source_id, "status": "success", **result})
        except Exception as e:
            errors.append(
                {"source_id": doc.source_id, "status": "failed", "error": str(e)}
            )

    return {
        "total": len(documents),
        "successful": len(results),
        "failed": len(errors),
        "results": results,
        "errors": errors,
    }


def _execute_upsert_plan(neo4j: Neo4jConnection, plan: Dict) -> Dict:
    """Execute the upsert plan against Neo4j"""
    results = {"nodes_created": 0, "relationships_created": 0, "errors": []}

    # Upsert nodes
    for node_plan in plan.get("nodes", []):
        try:
            label = node_plan["label"]
            id_prop, id_val = node_plan["id_property"]
            props = node_plan["properties"]

            # Build MERGE query
            query = f"""
            MERGE (n:{label} {{{id_prop}: $id_val}})
            SET n += $props
            RETURN n
            """

            neo4j.execute_query(query, {"id_val": id_val, "props": props})
            results["nodes_created"] += 1

        except Exception as e:
            results["errors"].append(f"Node upsert failed: {e}")

    # Upsert relationships
    for rel_plan in plan.get("relationships", []):
        try:
            rel_type = rel_plan["type"]
            from_node = rel_plan["from_node"]
            to_node = rel_plan["to_node"]
            props = rel_plan["properties"]

            # Build MERGE query for relationship
            query = f"""
            MATCH (from {{id: $from_id}})
            MATCH (to {{id: $to_id}})
            MERGE (from)-[r:{rel_type}]->(to)
            SET r += $props
            RETURN r
            """

            neo4j.execute_query(
                query, {"from_id": from_node, "to_id": to_node, "props": props}
            )
            results["relationships_created"] += 1

        except Exception as e:
            results["errors"].append(f"Relationship upsert failed: {e}")

    return results
