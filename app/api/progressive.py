"""
Progressive graph rendering API for large-scale visualization
"""
from fastapi import APIRouter, HTTPException, Depends, Request, Query
from typing import Dict, List, Optional, Any, Tuple
from pydantic import BaseModel, Field
from app.services.query import QueryService


router = APIRouter()


class GraphExpansionRequest(BaseModel):
    """Request for expanding graph from a node"""
    node_id: str = Field(..., description="Node to expand from")
    depth: int = Field(1, ge=1, le=3, description="Expansion depth")
    relationship_types: Optional[List[str]] = Field(None, description="Filter by relationship types")
    limit_per_type: int = Field(10, ge=1, le=50, description="Max nodes per relationship type")
    exclude_nodes: Optional[List[str]] = Field(None, description="Nodes to exclude from expansion")


class GraphFilterRequest(BaseModel):
    """Request for filtering graph visualization"""
    show_negated: bool = Field(True, description="Show negated relationships")
    min_confidence: float = Field(0.5, ge=0.0, le=1.0, description="Minimum confidence threshold")
    time_range: Optional[Dict[str, str]] = Field(None, description="Time range filter")
    entity_types: Optional[List[str]] = Field(None, description="Entity types to include")


class VisualizationConfig(BaseModel):
    """Configuration for graph visualization"""
    layout: str = Field("force-directed", description="Layout algorithm")
    clustering: bool = Field(True, description="Enable node clustering")
    show_labels: bool = Field(True, description="Show node labels")
    highlight_conflicts: bool = Field(True, description="Highlight conflicting data")
    abstraction_level: str = Field("patient", description="patient, encounter, or ontology level")


def get_query_service(request: Request) -> QueryService:
    """Get query service with Neo4j connection"""
    return QueryService(request.app.state.neo4j)


@router.post("/graph/progressive/{start_node}")
def get_progressive_graph(
    start_node: str,
    depth: int = Query(1, ge=1, le=3),
    query_service: QueryService = Depends(get_query_service)
) -> Dict[str, Any]:
    """Get initial graph centered on a node with progressive loading capability"""

    # Get initial subgraph
    query = """
    MATCH (n {id: $node_id})
    CALL apoc.path.subgraphAll(n, {
        maxLevel: $depth,
        limit: 100
    })
    YIELD nodes, relationships
    RETURN nodes, relationships
    """

    try:
        results = query_service.neo4j.execute_query(query, {
            "node_id": start_node,
            "depth": depth
        })

        if not results:
            raise HTTPException(status_code=404, detail=f"Node {start_node} not found")

        # Process results for visualization
        nodes, relationships = _process_graph_data(results[0])

        # Calculate graph statistics
        stats = _calculate_graph_stats(nodes, relationships)

        # Identify expandable nodes (leaf nodes with potential connections)
        expandable = _identify_expandable_nodes(nodes, relationships, query_service)

        return {
            "center_node": start_node,
            "nodes": nodes,
            "relationships": relationships,
            "statistics": stats,
            "expandable_nodes": expandable,
            "total_nodes": len(nodes),
            "total_relationships": len(relationships)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Graph query failed: {e}")


@router.post("/graph/expand")
def expand_graph_node(
    request: GraphExpansionRequest,
    query_service: QueryService = Depends(get_query_service)
) -> Dict[str, Any]:
    """Expand graph from a specific node"""

    # Build relationship filter
    rel_filter = ""
    if request.relationship_types:
        rel_types = "|".join(request.relationship_types)
        rel_filter = f"[:{rel_types}]"

    # Query for expansion
    query = f"""
    MATCH (n {{id: $node_id}})
    MATCH (n)-{rel_filter}-(connected)
    WHERE NOT connected.id IN $exclude_ids
    WITH connected, type(last(relationships(path))) AS rel_type
    ORDER BY connected.confidence DESC, connected.created_at DESC
    RETURN
        collect(DISTINCT connected)[..{{limit_per_type}}] AS nodes,
        rel_type
    """

    exclude_ids = request.exclude_nodes or []

    try:
        results = query_service.neo4j.execute_query(query, {
            "node_id": request.node_id,
            "exclude_ids": exclude_ids,
            "limit_per_type": request.limit_per_type
        })

        # Collect expanded nodes and relationships
        new_nodes = []
        new_relationships = []

        for record in results:
            nodes = record.get("nodes", [])
            for node in nodes:
                node_data = _format_node(node)
                if node_data["id"] not in exclude_ids:
                    new_nodes.append(node_data)

        # Get relationships between new nodes and existing graph
        if new_nodes:
            rel_query = """
            MATCH (n {id: $center_id})-[r]-(m)
            WHERE m.id IN $new_node_ids
            RETURN r, n.id AS from_id, m.id AS to_id
            """

            rel_results = query_service.neo4j.execute_query(rel_query, {
                "center_id": request.node_id,
                "new_node_ids": [n["id"] for n in new_nodes]
            })

            for record in rel_results:
                new_relationships.append(_format_relationship(record))

        return {
            "expanded_from": request.node_id,
            "new_nodes": new_nodes,
            "new_relationships": new_relationships,
            "nodes_added": len(new_nodes),
            "relationships_added": len(new_relationships)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Expansion failed: {e}")


@router.post("/graph/filter")
def filter_graph(
    filter_request: GraphFilterRequest,
    nodes: List[Dict[str, Any]],
    relationships: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Filter graph based on criteria"""

    filtered_nodes = nodes.copy()
    filtered_relationships = []

    # Filter relationships
    for rel in relationships:
        # Check negation filter
        if not filter_request.show_negated and rel.get("negation", False):
            continue

        # Check confidence filter
        if rel.get("confidence", 1.0) < filter_request.min_confidence:
            continue

        # Check time range filter
        if filter_request.time_range:
            rel_time = rel.get("time") or rel.get("created_at")
            if rel_time:
                if not _in_time_range(rel_time, filter_request.time_range):
                    continue

        filtered_relationships.append(rel)

    # Filter nodes by entity type
    if filter_request.entity_types:
        filtered_nodes = [
            node for node in filtered_nodes
            if node.get("label") in filter_request.entity_types
        ]

    # Remove orphaned nodes
    connected_node_ids = set()
    for rel in filtered_relationships:
        connected_node_ids.add(rel["from"])
        connected_node_ids.add(rel["to"])

    filtered_nodes = [
        node for node in filtered_nodes
        if node["id"] in connected_node_ids
    ]

    return {
        "nodes": filtered_nodes,
        "relationships": filtered_relationships,
        "filters_applied": filter_request.model_dump(),
        "nodes_filtered": len(nodes) - len(filtered_nodes),
        "relationships_filtered": len(relationships) - len(filtered_relationships)
    }


@router.post("/graph/cluster/{node_id}")
def get_node_cluster(
    node_id: str,
    cluster_type: str = Query("similar", description="similar, temporal, or structural"),
    limit: int = Query(20, ge=1, le=100),
    query_service: QueryService = Depends(get_query_service)
) -> Dict[str, Any]:
    """Get cluster of related nodes for visualization"""

    if cluster_type == "similar":
        # Find nodes with similar relationships
        query = """
        MATCH (n {id: $node_id})-[r]-(connected)
        MATCH (similar)-[r2]-(connected)
        WHERE similar.id <> n.id AND type(r) = type(r2)
        WITH similar, count(DISTINCT connected) AS shared_connections
        ORDER BY shared_connections DESC
        LIMIT $limit
        RETURN collect(similar) AS cluster_nodes
        """

    elif cluster_type == "temporal":
        # Find nodes within same time window
        query = """
        MATCH (n {id: $node_id})
        MATCH (other)
        WHERE other.id <> n.id
        AND abs(duration.between(n.created_at, other.created_at).days) <= 7
        ORDER BY other.created_at DESC
        LIMIT $limit
        RETURN collect(other) AS cluster_nodes
        """

    elif cluster_type == "structural":
        # Find nodes with similar graph structure
        query = """
        MATCH (n {id: $node_id})
        WITH n, labels(n) AS node_labels
        MATCH (similar)
        WHERE similar.id <> n.id
        AND labels(similar) = node_labels
        WITH similar, n
        MATCH (n)-[r1]-()
        WITH similar, count(r1) AS n_degree
        MATCH (similar)-[r2]-()
        WITH similar, n_degree, count(r2) AS similar_degree
        WHERE abs(n_degree - similar_degree) <= 3
        ORDER BY abs(n_degree - similar_degree)
        LIMIT $limit
        RETURN collect(similar) AS cluster_nodes
        """

    else:
        raise HTTPException(status_code=400, detail=f"Invalid cluster type: {cluster_type}")

    try:
        results = query_service.neo4j.execute_query(query, {
            "node_id": node_id,
            "limit": limit
        })

        if not results:
            return {"cluster_nodes": [], "cluster_type": cluster_type}

        cluster_nodes = []
        for node in results[0].get("cluster_nodes", []):
            cluster_nodes.append(_format_node(node))

        return {
            "center_node": node_id,
            "cluster_type": cluster_type,
            "cluster_nodes": cluster_nodes,
            "cluster_size": len(cluster_nodes)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Clustering failed: {e}")


@router.get("/graph/conflicts/{node_id}")
def get_node_conflicts(
    node_id: str,
    query_service: QueryService = Depends(get_query_service)
) -> Dict[str, Any]:
    """Get conflicting data related to a node"""

    query = """
    MATCH (n {id: $node_id})-[r1]-(target)
    MATCH (n)-[r2]-(target)
    WHERE id(r1) < id(r2)
    AND type(r1) = type(r2)
    AND (
        (r1.negation <> r2.negation) OR
        (abs(r1.confidence - r2.confidence) > 0.3)
    )
    RETURN
        type(r1) AS relationship_type,
        target.id AS target_id,
        {rel1: properties(r1), rel2: properties(r2)} AS conflicting_data
    """

    try:
        results = query_service.neo4j.execute_query(query, {"node_id": node_id})

        conflicts = []
        for record in results:
            conflicts.append({
                "relationship_type": record["relationship_type"],
                "target_id": record["target_id"],
                "conflicting_data": record["conflicting_data"]
            })

        return {
            "node_id": node_id,
            "conflicts": conflicts,
            "conflict_count": len(conflicts)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Conflict detection failed: {e}")


def _process_graph_data(raw_data: Dict) -> Tuple[List[Dict], List[Dict]]:
    """Process raw Neo4j data for visualization"""
    nodes = []
    relationships = []

    # Process nodes
    for node in raw_data.get("nodes", []):
        nodes.append(_format_node(node))

    # Process relationships
    for rel in raw_data.get("relationships", []):
        relationships.append(_format_relationship(rel))

    return nodes, relationships


def _format_node(node: Any) -> Dict[str, Any]:
    """Format node for visualization"""
    # Extract properties based on node type
    props = dict(node) if isinstance(node, dict) else {}

    return {
        "id": props.get("id") or props.get("assertion_id") or str(id(node)),
        "label": props.get("__labels__", ["Unknown"])[0] if "__labels__" in props else "Unknown",
        "properties": props,
        "display_name": _get_display_name(props),
        "category": _get_node_category(props)
    }


def _format_relationship(rel: Any) -> Dict[str, Any]:
    """Format relationship for visualization"""
    props = dict(rel) if isinstance(rel, dict) else {}

    return {
        "id": props.get("__id__") or str(id(rel)),
        "type": props.get("__type__") or "UNKNOWN",
        "from": props.get("from_id"),
        "to": props.get("to_id") or props.get("target_id"),
        "properties": props,
        "negation": props.get("negation", False),
        "confidence": props.get("confidence", 1.0),
        "display_type": "negated" if props.get("negation") else "confirmed"
    }


def _get_display_name(props: Dict) -> str:
    """Get display name for node"""
    return (props.get("name") or
           props.get("title") or
           props.get("id") or
           "Unknown")


def _get_node_category(props: Dict) -> str:
    """Categorize node for visualization"""
    # Map node types to categories
    label = props.get("__labels__", [""])[0] if "__labels__" in props else ""

    category_map = {
        "Patient": "entity",
        "Encounter": "event",
        "Symptom": "observation",
        "Disease": "condition",
        "Medication": "intervention",
        "Test": "diagnostic",
        "TestResult": "result",
        "Assertion": "evidence"
    }

    return category_map.get(label, "other")


def _calculate_graph_stats(nodes: List[Dict], relationships: List[Dict]) -> Dict[str, Any]:
    """Calculate graph statistics for visualization"""
    stats = {
        "node_types": {},
        "relationship_types": {},
        "avg_degree": 0,
        "density": 0,
        "conflict_count": 0
    }

    # Count node types
    for node in nodes:
        label = node.get("label", "Unknown")
        stats["node_types"][label] = stats["node_types"].get(label, 0) + 1

    # Count relationship types and conflicts
    degree_count = {}
    for rel in relationships:
        rel_type = rel.get("type", "Unknown")
        stats["relationship_types"][rel_type] = stats["relationship_types"].get(rel_type, 0) + 1

        # Track degree
        from_id = rel.get("from")
        to_id = rel.get("to")
        degree_count[from_id] = degree_count.get(from_id, 0) + 1
        degree_count[to_id] = degree_count.get(to_id, 0) + 1

        # Count conflicts (negated relationships)
        if rel.get("negation"):
            stats["conflict_count"] += 1

    # Calculate average degree
    if degree_count:
        stats["avg_degree"] = sum(degree_count.values()) / len(degree_count)

    # Calculate density
    if len(nodes) > 1:
        max_edges = len(nodes) * (len(nodes) - 1) / 2
        stats["density"] = len(relationships) / max_edges if max_edges > 0 else 0

    return stats


def _identify_expandable_nodes(nodes: List[Dict], relationships: List[Dict],
                              query_service: QueryService) -> List[str]:
    """Identify nodes that can be expanded"""
    expandable = []

    # Get leaf nodes (nodes with degree 1)
    degree_count = {}
    for rel in relationships:
        from_id = rel.get("from")
        to_id = rel.get("to")
        degree_count[from_id] = degree_count.get(from_id, 0) + 1
        degree_count[to_id] = degree_count.get(to_id, 0) + 1

    leaf_nodes = [node_id for node_id, degree in degree_count.items() if degree == 1]

    # Check if leaf nodes have more connections
    for node_id in leaf_nodes[:10]:  # Limit check to first 10
        query = """
        MATCH (n {id: $node_id})-[r]-()
        RETURN count(r) AS total_connections
        """

        results = query_service.neo4j.execute_query(query, {"node_id": node_id})
        if results and results[0]["total_connections"] > 1:
            expandable.append(node_id)

    return expandable


def _in_time_range(time_str: str, time_range: Dict[str, str]) -> bool:
    """Check if time is within range"""
    from datetime import datetime

    try:
        time = datetime.fromisoformat(time_str)
        if "start" in time_range:
            start = datetime.fromisoformat(time_range["start"])
            if time < start:
                return False
        if "end" in time_range:
            end = datetime.fromisoformat(time_range["end"])
            if time > end:
                return False
        return True
    except (ValueError, TypeError):
        return True  # If parsing fails, include the item