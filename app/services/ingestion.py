import hashlib
import uuid
from typing import List, Dict, Any, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from app.models.schemas import DocumentUpload, ChunkData
from app.db.models import Document, Chunk
from app.services.embedding import EmbeddingService
from app.services.s3 import S3Service
import logging

logger = logging.getLogger(__name__)


class IngestionService:
    def __init__(self, db_session: Optional[Session] = None):
        self.db = db_session
        self.chunk_size = 1500  # tokens approximately
        self.chunk_overlap = 200
        self.embedding_service = EmbeddingService()
        self.s3_service = S3Service()

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

    def process_document(
        self, document: DocumentUpload, s3_file_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """Process a document into chunks ready for extraction"""
        # Generate source ID if not provided
        if not document.source_id:
            document.source_id = self.generate_source_id(
                document.content, document.source_type
            )

        # Chunk the document
        chunks = self.chunk_text(document.content)

        # Generate embeddings for all chunks
        chunk_texts = [chunk.text for chunk in chunks]
        embeddings = self.embedding_service.generate_embeddings(chunk_texts)

        # Store in PostgreSQL if available
        if self.db:
            self._store_document(document, chunks, embeddings, s3_file_key)

        return {
            "source": {
                "source_id": document.source_id,
                "source_type": document.source_type,
                "title": document.title,
                "timestamp": datetime.now().isoformat(),
                "s3_url": s3_file_key if s3_file_key else None,
            },
            "chunks": [chunk.model_dump() for chunk in chunks],
            "chunk_count": len(chunks),
        }

    def _store_document(
        self,
        document: DocumentUpload,
        chunks: List[ChunkData],
        embeddings: List[Optional[List[float]]],
        s3_file_key: Optional[str] = None,
    ):
        """Store document and chunks in PostgreSQL with embeddings"""
        try:
            # Create document record
            db_document = Document(
                id=document.source_id,
                title=document.title,
                content=document.content,
                source_type=document.source_type,
                s3_url=s3_file_key,
                attributes=document.metadata if hasattr(document, "metadata") else {},
            )
            self.db.add(db_document)

            # Create chunk records with embeddings
            for chunk, embedding in zip(chunks, embeddings):
                db_chunk = Chunk(
                    id=f"{document.source_id}_{chunk.chunk_id}",
                    document_id=document.source_id,
                    content=chunk.text,
                    chunk_index=chunk.seq,
                    embedding=embedding,
                    attributes={"chunk_id": chunk.chunk_id},
                )
                self.db.add(db_chunk)

            self.db.commit()
            logger.info(
                f"Stored document {document.source_id} with {len(chunks)} chunks"
            )
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error storing document: {e}")
            raise

    def get_presigned_upload_url(
        self, content_type: str = "application/octet-stream", file_extension: str = ""
    ) -> Dict[str, str]:
        """Generate presigned URL for file upload with UUID as key"""
        # Use UUID as the file key
        file_uuid = str(uuid.uuid4())
        file_key = (
            f"documents/{file_uuid}{file_extension}"
            if file_extension
            else f"documents/{file_uuid}"
        )
        result = self.s3_service.generate_presigned_upload_url(file_key, content_type)
        result["file_uuid"] = file_uuid
        return result

    def search_similar_chunks(
        self, query: str, limit: int = 10, similarity_threshold: float = 0.7
    ) -> List[Dict[str, Any]]:
        """Search for similar chunks using vector similarity"""
        if not self.db:
            return []

        # Generate query embedding
        query_embedding = self.embedding_service.generate_query_embedding(query)
        if not query_embedding:
            return []

        try:
            # Use pgvector for similarity search
            from sqlalchemy import text

            query_sql = text(
                """
                SELECT
                    c.id,
                    c.document_id,
                    c.content,
                    c.chunk_index,
                    d.title as document_title,
                    1 - (c.embedding <=> :query_embedding::vector) as similarity
                FROM chunks c
                JOIN documents d ON c.document_id = d.id
                WHERE c.embedding IS NOT NULL
                ORDER BY c.embedding <=> :query_embedding::vector
                LIMIT :limit
            """
            )

            results = self.db.execute(
                query_sql, {"query_embedding": query_embedding, "limit": limit}
            ).fetchall()

            similar_chunks = []
            for row in results:
                if row.similarity >= similarity_threshold:
                    similar_chunks.append(
                        {
                            "chunk_id": row.id,
                            "document_id": row.document_id,
                            "document_title": row.document_title,
                            "content": row.content,
                            "chunk_index": row.chunk_index,
                            "similarity": float(row.similarity),
                        }
                    )

            return similar_chunks
        except Exception as e:
            logger.error(f"Error searching similar chunks: {e}")
            return []

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
