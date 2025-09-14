from typing import Dict

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.db.neo4j import Neo4jConnection
from app.db.database import get_db
from app.db.models import Document, Chunk
from app.models.schemas import DocumentUpload
from app.services.extraction import extraction_service
from app.services.resolution import ResolutionService
from app.services.chunking import chunking_service
from app.services.embedding import embedding_service

router = APIRouter()


def get_services(request: Request, db: Session = Depends(get_db)) -> Dict:
    """Get all required services"""
    neo4j_conn = request.app.state.neo4j
    return {
        "extraction": extraction_service,
        "resolution": ResolutionService(neo4j_conn),
        "chunking": chunking_service,
        "embedding": embedding_service,
        "neo4j": neo4j_conn,
        "db": db,
    }


@router.post("/document")
def upload_document(document: DocumentUpload, services: Dict = Depends(get_services)):
    """Upload and process a document with chunking and embedding"""
    db = services["db"]
    chunking = services["chunking"]
    embedding = services["embedding"]
    extraction = services["extraction"]
    resolution_service = services["resolution"]
    neo4j = services["neo4j"]

    try:
        # Step 1: Save document to PostgreSQL
        doc_record = Document(text=document.text)
        db.add(doc_record)
        db.flush()  # Get the UUID without committing

        # Step 2: Chunk the text
        chunks = chunking.chunk_text(document.text)

        # Step 3: Generate embeddings for chunks
        chunk_texts = [chunk["text"] for chunk in chunks]
        embeddings = embedding.generate_embeddings(chunk_texts)

        # Step 4: Save chunks with embeddings to PostgreSQL
        chunk_records = []
        for i, chunk in enumerate(chunks):
            chunk_record = Chunk(
                document_id=doc_record.uuid,
                chunk_index=chunk["chunk_index"],
                text=chunk["text"],
                embedding=embeddings[i] if embeddings[i] else None
            )
            db.add(chunk_record)
            chunk_records.append(chunk_record)

        # Commit document and chunks to database
        db.commit()

        # Step 5: Extract entities from each chunk and merge
        all_entities = {}
        all_assertions = []

        for chunk_record in chunk_records:
            extracted = extraction.extract_entities(chunk_record.text)

            # Merge entities
            for entity_type, entities in extracted.get("entities", {}).items():
                if entity_type not in all_entities:
                    all_entities[entity_type] = []
                all_entities[entity_type].extend(entities)

            # Merge assertions
            all_assertions.extend(extracted.get("assertions", []))

        # Step 6: Normalize entities
        normalized = extraction.normalize_entities(all_entities)

        # Step 7: Resolve entities
        resolved_entities = []
        for entity_type, entities in normalized.items():
            for entity in entities:
                resolution = resolution_service.resolve_entity(entity_type, entity)
                resolution["entity_type"] = entity_type
                resolved_entities.append(resolution)

        # Step 8: Create upsert plan
        upsert_plan = resolution_service.create_upsert_plan(
            resolved_entities, all_assertions
        )

        # Step 9: Execute upserts to Neo4j
        upsert_results = _execute_upsert_plan(neo4j, upsert_plan)

        return {
            "document_id": str(doc_record.uuid),
            "chunks_created": len(chunk_records),
            "entities_extracted": sum(
                len(entities) for entities in normalized.values()
            ),
            "assertions_created": len(all_assertions),
            "upsert_results": upsert_results,
        }

    except Exception as e:
        db.rollback()
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