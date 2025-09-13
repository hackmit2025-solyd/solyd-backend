"""
Standardized ID generation service for consistent entity identification
"""
import hashlib
import time
from typing import Optional, Dict, Any
from datetime import datetime


class IDGenerator:
    """Generates consistent IDs across all services"""

    # Prefixes for different entity types
    PREFIXES = {
        "patient": "P",
        "encounter": "E",
        "symptom": "S",
        "disease": "D",
        "test": "T",
        "test_result": "TR",
        "medication": "M",
        "procedure": "PR",
        "clinician": "CL",
        "guideline": "GL",
        "assertion": "A",
        "document": "DOC",
        "chunk": "C",
        "ontology": "ONT",
        "resource": "RES"
    }

    def __init__(self):
        self.counter = {}

    def generate_entity_id(self, entity_type: str, entity_data: Dict[str, Any],
                          source_id: Optional[str] = None) -> str:
        """Generate a consistent ID for an entity"""

        # Special handling for encounters - ALWAYS generate new ID
        if entity_type == "encounter":
            return self._generate_encounter_id(entity_data, source_id)

        # If entity already has an ID, validate and return it
        if "id" in entity_data and entity_data["id"]:
            return self._validate_id(entity_type, entity_data["id"])

        # For coded entities, use the code as primary ID
        if "code" in entity_data and entity_data["code"]:
            system = entity_data.get("system", entity_data.get("coding_system", ""))
            if system:
                return f"{system}:{entity_data['code']}"
            return entity_data["code"]

        # Generate new ID based on entity type
        prefix = self.PREFIXES.get(entity_type.lower(), "UNK")

        # For deterministic IDs based on content
        if entity_type in ["symptom", "disease", "medication", "test"]:
            # Use name for consistent ID across documents
            if "name" in entity_data:
                name_hash = hashlib.md5(entity_data["name"].lower().encode()).hexdigest()[:8]
                return f"{prefix}_{name_hash}"

        # For temporal entities (excluding encounter)
        if entity_type in ["test_result", "assertion"]:
            timestamp = entity_data.get("time") or entity_data.get("date")
            if timestamp:
                if isinstance(timestamp, str):
                    try:
                        dt = datetime.fromisoformat(timestamp)
                        timestamp_str = dt.strftime("%Y%m%d_%H%M%S")
                    except (ValueError, TypeError):
                        timestamp_str = hashlib.md5(timestamp.encode()).hexdigest()[:6]
                else:
                    timestamp_str = timestamp.strftime("%Y%m%d_%H%M%S")

                # Add source context if available
                if source_id:
                    source_hash = hashlib.md5(source_id.encode()).hexdigest()[:4]
                    return f"{prefix}_{timestamp_str}_{source_hash}"
                return f"{prefix}_{timestamp_str}"

        # Default: sequential ID with timestamp
        return self._generate_sequential_id(prefix)

    def _generate_encounter_id(self, entity_data: Dict[str, Any],
                              source_id: Optional[str] = None) -> str:
        """Generate unique encounter ID based on all available context"""
        prefix = self.PREFIXES["encounter"]

        # Collect all meaningful attributes for uniqueness
        components = []

        # Always include source if available
        if source_id:
            components.append(f"src:{source_id}")

        # Include all available encounter attributes
        for key in ["patient_id", "date", "time", "dept", "type", "reason", "provider", "location"]:
            if key in entity_data and entity_data[key]:
                components.append(f"{key}:{entity_data[key]}")

        # If we have an existing ID, include it to maintain consistency
        if "id" in entity_data and entity_data["id"] and not entity_data["id"].startswith(prefix):
            components.append(f"orig:{entity_data['id']}")

        # Create deterministic hash from all components
        if components:
            content_hash = hashlib.sha256("|".join(sorted(components)).encode()).hexdigest()[:12]
        else:
            # Fallback to timestamp-based unique ID
            content_hash = f"{int(time.time() * 1000000)}"[:12]

        return f"{prefix}_{content_hash}"

    def _validate_id(self, entity_type: str, existing_id: str) -> str:
        """Validate and potentially reformat an existing ID"""
        prefix = self.PREFIXES.get(entity_type.lower(), "")

        # If ID doesn't start with expected prefix, add it
        if prefix and not existing_id.startswith(prefix):
            # Unless it's a coded ID (contains colon)
            if ":" not in existing_id:
                return f"{prefix}_{existing_id}"

        return existing_id

    def _generate_sequential_id(self, prefix: str) -> str:
        """Generate a sequential ID with timestamp"""
        timestamp = int(time.time() * 1000)  # Millisecond precision

        # Increment counter for this prefix
        if prefix not in self.counter:
            self.counter[prefix] = 0
        self.counter[prefix] += 1

        return f"{prefix}_{timestamp}_{self.counter[prefix]:04d}"

    def generate_assertion_id(self, predicate: str, subject: str, object: str,
                            source_id: str, chunk_id: Optional[str] = None) -> str:
        """Generate deterministic ID for assertions to prevent duplicates"""
        # Create a deterministic hash from assertion components
        components = [predicate, subject, object, source_id]
        if chunk_id:
            components.append(chunk_id)

        assertion_hash = hashlib.sha256("_".join(components).encode()).hexdigest()[:12]
        return f"A_{assertion_hash}"

    def generate_chunk_id(self, source_id: str, sequence: int) -> str:
        """Generate chunk ID with source context"""
        source_hash = hashlib.md5(source_id.encode()).hexdigest()[:6]
        return f"C_{source_hash}_{sequence:04d}"

    def generate_document_id(self, content: str, source_type: str) -> str:
        """Generate document ID based on content hash"""
        # Use first 1000 chars for hash to be consistent
        content_sample = content[:1000] if len(content) > 1000 else content
        content_hash = hashlib.sha256(f"{source_type}:{content_sample}".encode()).hexdigest()[:16]
        return f"DOC_{content_hash}"


# Singleton instance
id_generator = IDGenerator()