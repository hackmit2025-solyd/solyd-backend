"""
UUID-based ID generation service for all entities
"""

import uuid
from typing import Dict, Any


class IDGenerator:
    """Generates UUIDs for all entities"""

    def generate_entity_id(
        self, entity_type: str = None, entity_data: Dict[str, Any] = None
    ) -> str:
        """Generate a UUID for any entity - no content-based IDs"""
        return str(uuid.uuid4())

    def generate_assertion_id(self) -> str:
        """Generate UUID for assertions/relationships"""
        return str(uuid.uuid4())

    def generate_chunk_id(self) -> str:
        """Generate UUID for document chunks"""
        return str(uuid.uuid4())

    def generate_document_id(self) -> str:
        """Generate UUID for documents"""
        return str(uuid.uuid4())


# Singleton instance
id_generator = IDGenerator()
