import json
from typing import Dict, List, Any, Optional
from datetime import datetime
from app.models.schemas import ChunkData
from app.config import settings
import anthropic
from app.services.validation import SchemaValidator


class ExtractionService:
    def __init__(self):
        self.client = None
        if settings.anthropic_api_key:
            self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self.validator = SchemaValidator()

    def extract_entities_from_chunk(
        self, chunk: ChunkData, source_id: str
    ) -> Dict[str, Any]:
        """Extract entities and assertions from a single chunk using Claude"""
        if not self.client:
            print("Warning: No Anthropic API client configured")
            return {"entities": {}, "assertions": []}

        prompt = self._build_extraction_prompt(chunk.text)

        try:
            response = self.client.messages.create(
                model=settings.claude_model,
                max_tokens=8192,  # Required parameter for Claude API
                temperature=0.3,
                messages=[{"role": "user", "content": prompt}],
            )

            # Parse Claude's response
            result = self._parse_extraction_response(response.content[0].text)

            # Add chunk IDs to assertions
            for assertion in result.get("assertions", []):
                assertion["chunk_ids"] = [chunk.chunk_id]
                assertion["source_id"] = source_id

            return result

        except Exception as e:
            import traceback
            print(f"Extraction error: {e}")
            print(f"Traceback: {traceback.format_exc()}")
            return {"entities": {}, "assertions": []}

    def _build_extraction_prompt(self, text: str) -> str:
        """Build prompt for entity extraction"""
        return f"""Extract medical entities and relationships from the following clinical text.

Return a JSON object with this structure:
{{
  "entities": {{
    "patients": [
      {{"id": "P123", "name": "John Doe", "sex": "M", "dob": "1980-01-15"}}
    ],
    "encounters": [
      {{"id": "E567", "date": "2025-09-13", "dept": "Internal Medicine"}}
    ],
    "symptoms": [
      {{"name": "fever", "code": "SNOMED:386661006"}},
      {{"name": "myalgia", "code": "SNOMED:68962001"}},
      {{"name": "cough", "code": "SNOMED:49727002"}}
    ],
    "diseases": [
      {{"code": "ICD10:J10", "name": "Influenza", "status": "suspected"}}
    ],
    "tests": [
      {{"name": "CRP", "loinc": "1988-5", "category": "lab"}}
    ],
    "test_results": [
      {{"id": "TR001", "test": "CRP", "value": 12.3, "unit": "mg/L", "time": "2025-09-13T10:30:00"}}
    ],
    "medications": [
      {{"code": "RxNorm:198440", "name": "Acetaminophen", "dose": "500mg"}}
    ]
  }},
  "assertions": [
    {{
      "id": "A1",
      "predicate": "HAS_SYMPTOM",
      "subject_ref": "E567",
      "object_ref": "fever",
      "time": "2025-09-12",
      "negation": false,
      "confidence": 0.95
    }},
    {{
      "id": "A2",
      "predicate": "ORDERED_TEST",
      "subject_ref": "E567",
      "object_ref": "CRP",
      "time": "2025-09-13",
      "confidence": 0.90
    }}
  ]
}}

Important:
- For symptoms explicitly denied, set negation=true
- Use standard codes (SNOMED, ICD10, LOINC, RxNorm) when identifiable
- Generate unique IDs for entities that need them
- Confidence scores should reflect certainty (0.0-1.0)

Text to analyze:
{text}

Return only valid JSON, no additional text."""

    def _parse_extraction_response(self, response_text: str) -> Dict[str, Any]:
        """Parse and validate Claude's response with auto-repair"""
        try:
            # First try to extract JSON from response
            json_start = response_text.find("{")
            json_end = response_text.rfind("}") + 1
            if json_start != -1 and json_end > json_start:
                json_str = response_text[json_start:json_end]

                # Try auto-repair if initial parsing fails
                try:
                    return json.loads(json_str)
                except json.JSONDecodeError as e:
                    print(f"Initial JSON parse failed: {e}")
                    # Attempt to repair common JSON issues
                    repaired = self.validator.auto_repair_json(json_str)
                    if repaired:
                        print("JSON auto-repair successful")
                        return json.loads(repaired)

        except Exception as e:
            print(f"Failed to parse extraction response: {e}")
            print(f"Response text: {response_text[:500]}...")  # Log first 500 chars for debugging

        return {"entities": {}, "assertions": []}


    def normalize_entities(self, entities: Dict[str, List]) -> Dict[str, List]:
        """Normalize extracted entities to standard formats"""
        normalized = {}

        for entity_type, entity_list in entities.items():
            normalized[entity_type] = []
            for entity in entity_list:
                norm_entity = self._normalize_entity(entity_type, entity)
                if norm_entity:
                    normalized[entity_type].append(norm_entity)

        return normalized

    def _normalize_entity(self, entity_type: str, entity: Dict) -> Optional[Dict]:
        """Normalize a single entity"""
        # Add normalization logic here
        # For MVP, just pass through with basic validation

        if entity_type == "patients":
            if "id" not in entity:
                entity["id"] = f"P_{datetime.now().timestamp()}"

        elif entity_type == "encounters":
            if "id" not in entity:
                entity["id"] = f"E_{datetime.now().timestamp()}"
            if "date" in entity and isinstance(entity["date"], str):
                # Ensure date format
                try:
                    datetime.fromisoformat(entity["date"])
                except (ValueError, TypeError):
                    entity["date"] = datetime.now().date().isoformat()

        elif entity_type == "symptoms":
            if "name" not in entity:
                return None

        elif entity_type == "diseases":
            if "code" not in entity:
                return None
            if "name" not in entity:
                entity["name"] = entity["code"]

        return entity
