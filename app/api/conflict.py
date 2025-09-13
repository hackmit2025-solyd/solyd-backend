"""
Conflict resolution API for handling contradictory medical data
"""
from fastapi import APIRouter, HTTPException
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
from datetime import datetime
from app.services.session import session_manager
from app.services.id_generator import id_generator


router = APIRouter()


class ConflictData(BaseModel):
    """Conflicting data requiring resolution"""
    entity_type: str = Field(..., description="Type of entity (symptom, disease, etc.)")
    entity_id: str = Field(..., description="Entity identifier")
    conflicting_values: List[Dict[str, Any]] = Field(..., description="List of conflicting values with sources")
    context: Optional[Dict[str, Any]] = Field(None, description="Additional context")


class ConflictResolution(BaseModel):
    """Resolution for a conflict"""
    conflict_id: str = Field(..., description="Conflict identifier")
    resolution_type: str = Field(..., description="Type of resolution: accept_one, merge, reject_all, defer")
    selected_value: Optional[Dict[str, Any]] = Field(None, description="Selected or merged value")
    rationale: Optional[str] = Field(None, description="Reason for resolution")
    resolver_id: Optional[str] = Field(None, description="ID of person/system resolving")


class ConflictReview(BaseModel):
    """Human review input for conflict"""
    decision: str = Field(..., description="accept, reject, or modify")
    value: Optional[Dict[str, Any]] = Field(None, description="Modified or selected value")
    notes: Optional[str] = Field(None, description="Review notes")
    reviewer_id: str = Field(..., description="Reviewer identifier")


@router.post("/conflict/create")
def create_conflict(conflict_data: ConflictData) -> Dict[str, Any]:
    """Create a new conflict for resolution"""

    conflict_id = id_generator.generate_sequential_id("CONF")

    # Structure conflict data
    conflict = {
        "conflict_id": conflict_id,
        "entity_type": conflict_data.entity_type,
        "entity_id": conflict_data.entity_id,
        "conflicting_values": conflict_data.conflicting_values,
        "context": conflict_data.context or {},
        "status": "pending",
        "created_at": datetime.now().isoformat(),
        "auto_resolution": None,
        "human_review": None
    }

    # Attempt automatic resolution
    auto_resolution = _attempt_auto_resolution(conflict_data)
    if auto_resolution:
        conflict["auto_resolution"] = auto_resolution
        conflict["status"] = "auto_resolved"

    # Store conflict
    session_manager.store_conflict(conflict_id, conflict)

    return {
        "conflict_id": conflict_id,
        "status": conflict["status"],
        "auto_resolution": auto_resolution,
        "requires_human_review": auto_resolution is None
    }


@router.get("/conflict/{conflict_id}")
def get_conflict(conflict_id: str) -> Dict[str, Any]:
    """Get conflict details"""

    conflict = session_manager.get_conflict(conflict_id)
    if not conflict:
        raise HTTPException(status_code=404, detail=f"Conflict {conflict_id} not found")

    return conflict


@router.get("/conflicts/pending")
def get_pending_conflicts(limit: int = 10) -> List[Dict[str, Any]]:
    """Get pending conflicts requiring human review"""

    conflicts = session_manager.get_pending_conflicts(limit)

    # Add analysis for each conflict
    for conflict in conflicts:
        conflict["analysis"] = _analyze_conflict(conflict)

    return conflicts


@router.post("/conflict/{conflict_id}/resolve")
def resolve_conflict(conflict_id: str, resolution: ConflictResolution) -> Dict[str, Any]:
    """Resolve a conflict"""

    conflict = session_manager.get_conflict(conflict_id)
    if not conflict:
        raise HTTPException(status_code=404, detail=f"Conflict {conflict_id} not found")

    # Store resolution
    resolution_data = {
        "type": resolution.resolution_type,
        "selected_value": resolution.selected_value,
        "rationale": resolution.rationale,
        "resolver_id": resolution.resolver_id,
        "timestamp": datetime.now().isoformat()
    }

    session_manager.resolve_conflict(conflict_id, resolution_data)

    return {
        "conflict_id": conflict_id,
        "status": "resolved",
        "resolution": resolution_data
    }


@router.post("/conflict/{conflict_id}/review")
def review_conflict(conflict_id: str, review: ConflictReview) -> Dict[str, Any]:
    """Submit human review for a conflict"""

    conflict = session_manager.get_conflict(conflict_id)
    if not conflict:
        raise HTTPException(status_code=404, detail=f"Conflict {conflict_id} not found")

    # Add human review
    review_data = {
        "decision": review.decision,
        "value": review.value,
        "notes": review.notes,
        "reviewer_id": review.reviewer_id,
        "timestamp": datetime.now().isoformat()
    }

    conflict["human_review"] = review_data
    conflict["status"] = "reviewed"

    # Update in storage
    session_manager.store_conflict(conflict_id, conflict)

    # If accepted, create resolution
    if review.decision == "accept":
        resolution = ConflictResolution(
            conflict_id=conflict_id,
            resolution_type="human_review",
            selected_value=review.value,
            rationale=review.notes,
            resolver_id=review.reviewer_id
        )
        return resolve_conflict(conflict_id, resolution)

    return {
        "conflict_id": conflict_id,
        "status": "reviewed",
        "review": review_data
    }


@router.post("/conflict/batch")
def create_batch_conflicts(conflicts: List[ConflictData]) -> Dict[str, Any]:
    """Create multiple conflicts at once"""

    results = []
    for conflict_data in conflicts:
        try:
            result = create_conflict(conflict_data)
            results.append(result)
        except Exception as e:
            results.append({
                "error": str(e),
                "entity_id": conflict_data.entity_id
            })

    return {
        "total": len(conflicts),
        "created": len([r for r in results if "conflict_id" in r]),
        "errors": len([r for r in results if "error" in r]),
        "results": results
    }


def _attempt_auto_resolution(conflict_data: ConflictData) -> Optional[Dict[str, Any]]:
    """Attempt automatic conflict resolution based on rules"""

    values = conflict_data.conflicting_values

    # Rule 1: If all values are identical after normalization, accept
    normalized_values = [_normalize_value(v) for v in values]
    if len(set(str(v) for v in normalized_values)) == 1:
        return {
            "method": "identical_after_normalization",
            "selected_value": normalized_values[0],
            "confidence": 1.0
        }

    # Rule 2: For timestamps, prefer most recent
    if conflict_data.entity_type in ["encounter", "test_result", "observation"]:
        if all("timestamp" in v or "date" in v for v in values):
            sorted_values = sorted(
                values,
                key=lambda x: x.get("timestamp", x.get("date", "")),
                reverse=True
            )
            return {
                "method": "most_recent",
                "selected_value": sorted_values[0],
                "confidence": 0.9
            }

    # Rule 3: For numerical values, check if within acceptable range
    if conflict_data.entity_type in ["lab_result", "vital_sign"]:
        numeric_values = []
        for v in values:
            if "value" in v and isinstance(v["value"], (int, float)):
                numeric_values.append(v["value"])

        if numeric_values:
            mean_val = sum(numeric_values) / len(numeric_values)
            std_dev = (sum((x - mean_val) ** 2 for x in numeric_values) / len(numeric_values)) ** 0.5

            # If standard deviation is low, values are consistent
            if std_dev < mean_val * 0.1:  # Within 10% variation
                return {
                    "method": "statistical_consensus",
                    "selected_value": {"value": mean_val, "std_dev": std_dev},
                    "confidence": 0.85
                }

    # Rule 4: For boolean negation conflicts, defer to human
    if conflict_data.entity_type == "symptom":
        negations = [v.get("negation", False) for v in values]
        has_true = any(n for n in negations)
        has_false = any(not n for n in negations)
        if has_true and has_false:
            # Direct contradiction - needs human review
            return None

    # Rule 5: Source reliability scoring
    source_scores = []
    for v in values:
        source = v.get("source", {})
        score = _calculate_source_reliability(source)
        source_scores.append((v, score))

    if source_scores:
        # Sort by reliability score
        source_scores.sort(key=lambda x: x[1], reverse=True)
        best_value, best_score = source_scores[0]

        # If best source is significantly more reliable
        if best_score > 0.8 and (len(source_scores) == 1 or best_score - source_scores[1][1] > 0.2):
            return {
                "method": "source_reliability",
                "selected_value": best_value,
                "confidence": best_score
            }

    # No automatic resolution possible
    return None


def _normalize_value(value: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize value for comparison"""
    normalized = value.copy()

    # Normalize text fields
    for field in ["name", "text", "description"]:
        if field in normalized and isinstance(normalized[field], str):
            normalized[field] = normalized[field].lower().strip()

    # Normalize units
    if "unit" in normalized and isinstance(normalized["unit"], str):
        unit_map = {
            "mg/l": "mg/L",
            "mg/dl": "mg/dL",
            "g/dl": "g/dL",
            "mmol/l": "mmol/L"
        }
        normalized["unit"] = unit_map.get(normalized["unit"].lower(), normalized["unit"])

    return normalized


def _calculate_source_reliability(source: Dict[str, Any]) -> float:
    """Calculate reliability score for a source"""
    score = 0.5  # Base score

    # Document type scoring
    doc_type = source.get("type", "").lower()
    if doc_type in ["clinical_note", "discharge_summary"]:
        score += 0.3
    elif doc_type in ["lab_report", "radiology"]:
        score += 0.25
    elif doc_type in ["patient_reported"]:
        score += 0.1

    # Confidence from extraction
    if "confidence" in source:
        score = score * 0.7 + source["confidence"] * 0.3

    # Author credentials
    if "author" in source:
        author = source["author"]
        if "MD" in author or "physician" in author.lower():
            score += 0.1
        elif "RN" in author or "nurse" in author.lower():
            score += 0.05

    # Recency bonus
    if "timestamp" in source:
        try:
            source_date = datetime.fromisoformat(source["timestamp"])
            days_old = (datetime.now() - source_date).days
            if days_old < 7:
                score += 0.1
            elif days_old < 30:
                score += 0.05
        except (ValueError, TypeError):
            pass

    return min(score, 1.0)


def _analyze_conflict(conflict: Dict[str, Any]) -> Dict[str, Any]:
    """Analyze conflict to provide insights"""

    analysis = {
        "severity": "low",
        "type": "unknown",
        "recommendations": []
    }

    values = conflict.get("conflicting_values", [])
    entity_type = conflict.get("entity_type", "")

    # Determine conflict type
    if len(values) == 2:
        has_true_negation = any(v.get("negation") for v in values)
        has_false_negation = any(not v.get("negation") for v in values if "negation" in v)
        if has_true_negation and has_false_negation:
            analysis["type"] = "negation_conflict"
            analysis["severity"] = "high"
            analysis["recommendations"].append("Review clinical context for symptom presence/absence")

    # Check for measurement conflicts
    if entity_type in ["lab_result", "vital_sign"]:
        numeric_values = [v.get("value") for v in values if isinstance(v.get("value"), (int, float))]
        if numeric_values:
            range_val = max(numeric_values) - min(numeric_values)
            mean_val = sum(numeric_values) / len(numeric_values)
            if range_val > mean_val * 0.5:  # >50% variation
                analysis["type"] = "measurement_discrepancy"
                analysis["severity"] = "medium"
                analysis["recommendations"].append("Verify measurement units and timing")

    # Check for temporal conflicts
    timestamps = [v.get("timestamp") or v.get("date") for v in values if v.get("timestamp") or v.get("date")]
    if len(set(timestamps)) > 1:
        analysis["has_temporal_variation"] = True
        analysis["recommendations"].append("Consider most recent value if clinically appropriate")

    return analysis