import hashlib
from typing import List, Dict, Any
from datetime import datetime
from app.models.schemas import DocumentUpload, ChunkData


class IngestionService:
    def __init__(self, postgres_conn=None):
        self.postgres = postgres_conn
        self.chunk_size = 1500  # tokens approximately
        self.chunk_overlap = 200

    def generate_source_id(self, content: str, source_type: str) -> str:
        """Generate unique source ID based on content hash"""
        hash_input = f"{source_type}:{content[:1000]}"
        return hashlib.sha256(hash_input.encode()).hexdigest()[:16]

    def chunk_text(self, text: str) -> List[ChunkData]:
        """Split text into overlapping chunks"""
        # Simple character-based chunking for MVP
        # In production, use tiktoken or similar for proper token counting
        chunks = []
        chunk_chars = self.chunk_size * 4  # Rough estimate: 1 token ≈ 4 chars
        overlap_chars = self.chunk_overlap * 4

        start = 0
        seq = 1

        while start < len(text):
            end = min(start + chunk_chars, len(text))
            chunk_text = text[start:end]

            chunk = ChunkData(chunk_id=f"C{seq}", seq=seq, text=chunk_text)
            chunks.append(chunk)

            start = end - overlap_chars if end < len(text) else end
            seq += 1

        return chunks

    def process_document(self, document: DocumentUpload) -> Dict[str, Any]:
        """Process a document into chunks ready for extraction"""
        # Generate source ID if not provided
        if not document.source_id:
            document.source_id = self.generate_source_id(
                document.content, document.source_type
            )

        # Chunk the document
        chunks = self.chunk_text(document.content)

        # Store in PostgreSQL if available
        if self.postgres:
            self._store_document(document, chunks)

        return {
            "source": {
                "source_id": document.source_id,
                "source_type": document.source_type,
                "title": document.title,
                "timestamp": datetime.now().isoformat(),
            },
            "chunks": [chunk.dict() for chunk in chunks],
            "chunk_count": len(chunks),
        }

    def _store_document(self, document: DocumentUpload, chunks: List[ChunkData]):
        """Store document and chunks in PostgreSQL"""
        # TODO: Implement PostgreSQL storage
        pass

    def merge_extractions(self, chunk_extractions: List[Dict]) -> Dict[str, Any]:
        """Merge entity extractions from multiple chunks"""
        merged_entities = {}
        merged_assertions = []

        for extraction in chunk_extractions:
            # Merge entities
            for entity_type, entities in extraction.get("entities", {}).items():
                if entity_type not in merged_entities:
                    merged_entities[entity_type] = []

                for entity in entities:
                    # Simple deduplication based on ID/code
                    if not self._is_duplicate(entity, merged_entities[entity_type]):
                        merged_entities[entity_type].append(entity)

            # Collect assertions
            for assertion in extraction.get("assertions", []):
                merged_assertions.append(assertion)

        # Consolidate assertions with same predicate and entities
        consolidated_assertions = self._consolidate_assertions(merged_assertions)

        return {"entities": merged_entities, "assertions": consolidated_assertions}

    def _is_duplicate(self, entity: Dict, entity_list: List[Dict]) -> bool:
        """Check if entity already exists in list"""
        id_field = "id" if "id" in entity else "code" if "code" in entity else "name"
        entity_id = entity.get(id_field)

        for existing in entity_list:
            if existing.get(id_field) == entity_id:
                return True
        return False

    def _consolidate_assertions(self, assertions: List[Dict]) -> List[Dict]:
        """Consolidate duplicate assertions by combining evidence"""
        consolidated = {}

        for assertion in assertions:
            # Create key from predicate and entities
            key = f"{assertion.get('predicate')}:{assertion.get('subject_ref')}:{assertion.get('object_ref')}"

            if key in consolidated:
                # Merge chunk_ids
                existing_chunks = set(consolidated[key].get("chunk_ids", []))
                new_chunks = set(assertion.get("chunk_ids", []))
                consolidated[key]["chunk_ids"] = list(existing_chunks | new_chunks)

                # Average confidence scores
                existing_conf = consolidated[key].get("confidence", 1.0)
                new_conf = assertion.get("confidence", 1.0)
                consolidated[key]["confidence"] = (existing_conf + new_conf) / 2
            else:
                consolidated[key] = assertion

        return list(consolidated.values())
