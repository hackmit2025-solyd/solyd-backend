from typing import Dict, List
import tempfile
import os

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from sqlalchemy.orm import Session
import PyPDF2

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


@router.post("/pdf")
def upload_pdf(
    file: UploadFile = File(...),
    services: Dict = Depends(get_services)
):
    """Upload and process a PDF file"""

    # Validate file type
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="File must be a PDF")

    # Create temporary file
    temp_file_path = None
    try:
        # Save uploaded file to temporary location
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_file:
            content = file.file.read()  # Read directly from file object
            temp_file.write(content)
            temp_file_path = temp_file.name

        # Extract text from PDF
        pdf_text = _extract_text_from_pdf(temp_file_path)

        if not pdf_text.strip():
            raise HTTPException(status_code=400, detail="Could not extract text from PDF")

        # Process the extracted text using existing document pipeline
        document_upload = DocumentUpload(text=pdf_text)
        result = upload_document(document_upload, services)

        # Add PDF filename to result
        result["source_filename"] = file.filename

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF processing failed: {e}")

    finally:
        # Clean up temporary file
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.unlink(temp_file_path)
            except Exception as e:
                print(f"Warning: Could not delete temporary file {temp_file_path}: {e}")


def _extract_text_from_pdf(pdf_path: str) -> str:
    """Extract text content from PDF file"""
    text = ""

    try:
        with open(pdf_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)

            # Extract text from all pages
            for page_num in range(len(pdf_reader.pages)):
                page = pdf_reader.pages[page_num]
                page_text = page.extract_text()

                if page_text:
                    text += page_text + "\n\n"

    except Exception as e:
        print(f"Error extracting text from PDF: {e}")
        raise

    return text.strip()


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
                embedding=embeddings[i] if embeddings[i] else None,
            )
            db.add(chunk_record)
            chunk_records.append(chunk_record)

        # Commit document and chunks to database
        db.commit()

        # Step 5: Extract entities from each chunk with context
        chunk_extractions = []
        previous_context = {}

        for i, chunk_record in enumerate(chunk_records):
            # Extract entities with previous context
            extracted = extraction.extract_entities(
                chunk_record.text, context=previous_context
            )
            chunk_extractions.append(extracted)

            # Build context for next chunk (key entities from current extraction)
            if extracted.get("entities"):
                previous_context = _build_context_from_entities(extracted["entities"])

        # Step 6: Merge and deduplicate entities across chunks
        merged_data = _merge_chunk_extractions(chunk_extractions)
        all_entities = merged_data["entities"]
        all_assertions = merged_data["assertions"]

        # Step 7: Normalize entities
        normalized = extraction.normalize_entities(all_entities)

        # Step 8: Resolve entities and build reference map
        resolved_entities = []
        reference_map = {}  # Map from "type[index]" to UUID

        for entity_type, entities in normalized.items():
            for idx, entity in enumerate(entities):
                resolution = resolution_service.resolve_entity(entity_type, entity)
                resolution["entity_type"] = entity_type
                resolved_entities.append(resolution)

                # Build reference map for assertions
                ref_key = f"{entity_type}[{idx}]"
                reference_map[ref_key] = resolution["to_node_id"]

        # Step 9: Update assertions with actual UUIDs
        resolved_assertions = []
        for assertion in all_assertions:
            resolved_assertion = assertion.copy()

            # Replace subject_ref and object_ref with actual UUIDs
            subject_ref = assertion.get("subject_ref")
            object_ref = assertion.get("object_ref")

            if subject_ref in reference_map:
                resolved_assertion["subject_ref"] = reference_map[subject_ref]
            else:
                print(f"Warning: Could not resolve subject_ref: {subject_ref}")
                continue

            if object_ref in reference_map:
                resolved_assertion["object_ref"] = reference_map[object_ref]
            else:
                print(f"Warning: Could not resolve object_ref: {object_ref}")
                continue

            resolved_assertions.append(resolved_assertion)

        # Step 10: Create upsert plan
        upsert_plan = resolution_service.create_upsert_plan(
            resolved_entities, resolved_assertions, document_id=str(doc_record.uuid)
        )

        # Step 11: Execute upserts to Neo4j
        upsert_results = _execute_upsert_plan(neo4j, upsert_plan, document_id=str(doc_record.uuid))

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


def _build_context_from_entities(entities: Dict) -> Dict:
    """Build context from extracted entities for next chunk processing"""
    context = {}

    # Include key instance nodes
    if "patients" in entities and entities["patients"]:
        patient = entities["patients"][0]  # Assume first patient is primary
        context["patient"] = {
            "name": patient.get("name"),
            "dob": patient.get("dob"),
            "sex": patient.get("sex"),
        }

    if "encounters" in entities and entities["encounters"]:
        encounter = entities["encounters"][0]  # Most recent encounter
        context["encounter"] = {
            "date": encounter.get("date"),
            "dept": encounter.get("dept"),
        }

    if "clinicians" in entities and entities["clinicians"]:
        clinician = entities["clinicians"][0]
        context["clinician"] = {
            "name": clinician.get("name"),
            "specialty": clinician.get("specialty"),
        }

    return context


def _merge_chunk_extractions(chunk_extractions: List[Dict]) -> Dict:
    """Merge and deduplicate entities from multiple chunk extractions"""
    merged_entities = {}
    merged_assertions = []

    for chunk_idx, extraction in enumerate(chunk_extractions):
        chunk_mapping = {}  # Map from chunk's entity reference to global reference

        for entity_type, entities in extraction.get("entities", {}).items():
            if entity_type not in merged_entities:
                merged_entities[entity_type] = []

            for local_idx, entity in enumerate(entities):
                # Check for duplicates
                global_idx = _find_duplicate_entity(
                    entity, entity_type, merged_entities[entity_type]
                )

                if global_idx == -1:
                    # New unique entity
                    global_idx = len(merged_entities[entity_type])
                    merged_entities[entity_type].append(entity)

                # Track mapping for assertion remapping
                chunk_ref = f"{entity_type}[{local_idx}]"
                global_ref = f"{entity_type}[{global_idx}]"
                chunk_mapping[chunk_ref] = global_ref

        # Remap and merge assertions
        for assertion in extraction.get("assertions", []):
            remapped_assertion = assertion.copy()

            # Remap subject and object references
            if assertion.get("subject_ref") in chunk_mapping:
                remapped_assertion["subject_ref"] = chunk_mapping[assertion["subject_ref"]]
            if assertion.get("object_ref") in chunk_mapping:
                remapped_assertion["object_ref"] = chunk_mapping[assertion["object_ref"]]

            # Check for duplicate assertions
            if not _is_duplicate_assertion(remapped_assertion, merged_assertions):
                merged_assertions.append(remapped_assertion)

    return {"entities": merged_entities, "assertions": merged_assertions}


def _find_duplicate_entity(entity: Dict, entity_type: str, existing_entities: List[Dict]) -> int:
    """Find if entity already exists in the list, return index or -1"""

    # Instance nodes: check for duplicates based on key attributes
    if entity_type == "patients":
        for idx, existing in enumerate(existing_entities):
            if (
                entity.get("name") == existing.get("name")
                and entity.get("dob") == existing.get("dob")
            ):
                return idx

    elif entity_type == "encounters":
        for idx, existing in enumerate(existing_entities):
            if (
                entity.get("date") == existing.get("date")
                and entity.get("dept") == existing.get("dept")
            ):
                return idx

    elif entity_type == "clinicians":
        for idx, existing in enumerate(existing_entities):
            if entity.get("name") == existing.get("name"):
                return idx

    # Catalog nodes: check by code/name
    elif entity_type in ["symptoms", "diseases", "tests", "medications", "procedures"]:
        for idx, existing in enumerate(existing_entities):
            # Check by code if available
            if entity.get("code") and entity.get("code") == existing.get("code"):
                if entity.get("system") == existing.get("system"):
                    return idx
            # Otherwise check by name
            elif entity.get("name") and entity.get("name").lower() == existing.get("name", "").lower():
                return idx

    return -1


def _is_duplicate_assertion(assertion: Dict, existing_assertions: List[Dict]) -> bool:
    """Check if assertion already exists"""
    for existing in existing_assertions:
        if (
            assertion.get("predicate") == existing.get("predicate")
            and assertion.get("subject_ref") == existing.get("subject_ref")
            and assertion.get("object_ref") == existing.get("object_ref")
        ):
            return True
    return False


def _execute_upsert_plan(neo4j: Neo4jConnection, plan: Dict, document_id: str = None) -> Dict:
    """Execute the upsert plan against Neo4j"""
    results = {"nodes_created": 0, "relationships_created": 0, "errors": []}

    # Upsert nodes
    for node_plan in plan.get("nodes", []):
        try:
            label = node_plan["label"]
            uuid = node_plan["uuid"]
            props = node_plan["properties"]

            # Add document_id to properties if provided
            if document_id:
                props["document_id"] = document_id

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

            # Add document_id to relationship properties if provided
            if document_id:
                props["document_id"] = document_id

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
