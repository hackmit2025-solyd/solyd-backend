"""
BioPortal API integration for medical ontology mapping
"""
import requests
from typing import Dict, List, Optional
from urllib.parse import quote
import time
from app.config import settings


class BioPortalClient:
    """Client for BioPortal REST API"""

    BASE_URL = "https://data.bioontology.org"

    # Ontology acronyms in BioPortal
    ONTOLOGIES = {
        "symptom": ["SYMP", "SNOMEDCT", "HP"],  # Symptom Ontology, SNOMED, Human Phenotype
        "disease": ["ICD10", "ICD10CM", "SNOMEDCT", "DOID"],  # Disease ontologies
        "medication": ["RXNORM", "ATC", "CHEBI"],  # Drug ontologies
        "procedure": ["CPT", "SNOMEDCT", "ICD10PCS"],  # Procedure codes
        "anatomy": ["UBERON", "FMA"],  # Anatomical terms
        "lab": ["LOINC"],  # Laboratory tests
    }

    def __init__(self, api_key: Optional[str] = None):
        """Initialize with BioPortal API key"""
        self.api_key = api_key or getattr(settings, 'bioportal_api_key', None)
        if not self.api_key:
            # Use demo key with rate limits
            self.api_key = "DEMO_KEY"

        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"apikey token={self.api_key}",
            "Accept": "application/json"
        })

        # Cache for recent searches
        self.cache = {}
        self.cache_ttl = 3600  # 1 hour

    def search(self, query: str, ontologies: Optional[List[str]] = None,
              entity_type: Optional[str] = None, limit: int = 10) -> List[Dict]:
        """Search for terms across ontologies"""

        # Build cache key
        cache_key = f"{query}:{entity_type}:{limit}"
        if cache_key in self.cache:
            cached_time, cached_result = self.cache[cache_key]
            if time.time() - cached_time < self.cache_ttl:
                return cached_result

        # Determine which ontologies to search
        if entity_type and entity_type in self.ONTOLOGIES:
            ontologies = self.ONTOLOGIES[entity_type]
        elif not ontologies:
            # Search all medical ontologies by default
            ontologies = ["SNOMEDCT", "ICD10CM", "RXNORM", "LOINC"]

        # Build search URL
        params = {
            "q": query,
            "ontologies": ",".join(ontologies),
            "pagesize": limit,
            "include": "prefLabel,synonym,definition,semanticType",
            "require_exact_match": "false",
            "suggest": "true"
        }

        try:
            response = self.session.get(
                f"{self.BASE_URL}/search",
                params=params,
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                results = self._parse_search_results(data)

                # Cache results
                self.cache[cache_key] = (time.time(), results)
                return results
            else:
                print(f"BioPortal API error: {response.status_code}")
                return []

        except requests.exceptions.RequestException as e:
            print(f"BioPortal request failed: {e}")
            return []

    def _parse_search_results(self, data: Dict) -> List[Dict]:
        """Parse BioPortal search results into standardized format"""
        results = []

        for item in data.get("collection", []):
            # Extract relevant fields
            result = {
                "system": self._get_system_from_ontology(item.get("links", {}).get("ontology")),
                "code": item.get("@id", "").split("/")[-1],  # Extract code from URI
                "name": item.get("prefLabel"),
                "synonyms": item.get("synonym", []),
                "definition": item.get("definition", [""])[0] if item.get("definition") else None,
                "semantic_types": item.get("semanticType", []),
                "ontology": item.get("links", {}).get("ontology", "").split("/")[-1],
                "score": item.get("score", 0)
            }

            # Clean up code
            if "#" in result["code"]:
                result["code"] = result["code"].split("#")[-1]

            results.append(result)

        # Sort by score
        results.sort(key=lambda x: x["score"], reverse=True)
        return results

    def _get_system_from_ontology(self, ontology_url: str) -> str:
        """Map BioPortal ontology to standard system name"""
        if not ontology_url:
            return "UNKNOWN"

        ontology = ontology_url.split("/")[-1].upper()

        # Map to standard names
        mapping = {
            "SNOMEDCT": "SNOMED",
            "ICD10CM": "ICD10",
            "ICD10": "ICD10",
            "RXNORM": "RxNorm",
            "LOINC": "LOINC",
            "CPT": "CPT",
            "SYMP": "SYMP",
            "HP": "HPO",
            "DOID": "DOID",
            "CHEBI": "CHEBI",
            "ATC": "ATC"
        }

        return mapping.get(ontology, ontology)

    def get_term(self, ontology: str, term_id: str) -> Optional[Dict]:
        """Get detailed information about a specific term"""

        # URL encode the term ID
        encoded_id = quote(term_id, safe='')

        try:
            response = self.session.get(
                f"{self.BASE_URL}/ontologies/{ontology}/classes/{encoded_id}",
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                return self._parse_term_details(data, ontology)
            else:
                print(f"Failed to get term {term_id} from {ontology}: {response.status_code}")
                return None

        except requests.exceptions.RequestException as e:
            print(f"BioPortal request failed: {e}")
            return None

    def _parse_term_details(self, data: Dict, ontology: str) -> Dict:
        """Parse term details from BioPortal response"""
        return {
            "system": self._get_system_from_ontology(ontology),
            "code": data.get("@id", "").split("/")[-1],
            "name": data.get("prefLabel"),
            "synonyms": data.get("synonym", []),
            "definition": data.get("definition", [""])[0] if data.get("definition") else None,
            "parents": [p.split("/")[-1] for p in data.get("parents", [])],
            "semantic_types": data.get("semanticType", []),
            "ontology": ontology
        }

    def get_recommendations(self, text: str, entity_type: Optional[str] = None) -> List[Dict]:
        """Get ontology term recommendations for free text using BioPortal Annotator"""

        # Use the Annotator service for better context understanding
        params = {
            "text": text,
            "include": "prefLabel,synonym,definition,semanticType",
            "expand_class_hierarchy": "false",
            "class_hierarchy_max_level": "1",
            "expand_mappings": "false",
            "stop_words": "true",
            "minimum_match_length": "3",
            "exclude_numbers": "false",
            "whole_word_only": "true",
            "longest_only": "true"
        }

        # Add ontology filter if entity type specified
        if entity_type and entity_type in self.ONTOLOGIES:
            params["ontologies"] = ",".join(self.ONTOLOGIES[entity_type])

        try:
            response = self.session.post(
                f"{self.BASE_URL}/annotator",
                data=params,
                timeout=15
            )

            if response.status_code == 200:
                data = response.json()
                return self._parse_annotations(data)
            else:
                print(f"BioPortal Annotator error: {response.status_code}")
                return []

        except requests.exceptions.RequestException as e:
            print(f"BioPortal Annotator request failed: {e}")
            return []

    def _parse_annotations(self, data: List) -> List[Dict]:
        """Parse annotation results from BioPortal Annotator"""
        results = []
        seen = set()

        for annotation in data:
            annotated_class = annotation.get("annotatedClass", {})

            # Extract unique identifier
            term_id = annotated_class.get("@id", "")
            if term_id in seen:
                continue
            seen.add(term_id)

            # Parse annotation
            result = {
                "system": self._get_system_from_ontology(
                    annotated_class.get("links", {}).get("ontology", "")
                ),
                "code": term_id.split("/")[-1],
                "name": annotated_class.get("prefLabel"),
                "matched_text": annotation.get("annotations", [{}])[0].get("text", ""),
                "match_type": annotation.get("annotations", [{}])[0].get("matchType", ""),
                "confidence": self._calculate_confidence(annotation),
                "ontology": annotated_class.get("links", {}).get("ontology", "").split("/")[-1]
            }

            results.append(result)

        # Sort by confidence
        results.sort(key=lambda x: x["confidence"], reverse=True)
        return results

    def _calculate_confidence(self, annotation: Dict) -> float:
        """Calculate confidence score for an annotation"""
        # Base confidence on match type
        match_type = annotation.get("annotations", [{}])[0].get("matchType", "")

        confidence = 0.5
        if match_type == "PREF":
            confidence = 0.95
        elif match_type == "SYN":
            confidence = 0.85

        # Adjust based on coverage
        text_length = len(annotation.get("annotations", [{}])[0].get("text", ""))
        if text_length > 10:
            confidence += 0.05

        return min(confidence, 1.0)


# Singleton instance
bioportal_client = BioPortalClient()