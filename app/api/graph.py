"""Graph data export API"""

from typing import Dict, List, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from app.db.neo4j import Neo4jConnection

router = APIRouter()


def get_neo4j(request: Request) -> Neo4jConnection:
    """Get Neo4j connection from app state"""
    return request.app.state.neo4j


@router.get("/full")
def get_full_graph(
    neo4j: Neo4jConnection = Depends(get_neo4j),
    limit: Optional[int] = Query(None, description="Limit number of nodes (default: all)"),
):
    """
    Get entire graph as JSON for client-side visualization

    Returns nodes and relationships in a format suitable for graph visualization libraries
    like D3.js, vis.js, or Cytoscape.js
    """
    try:
        # Get all nodes
        if limit:
            nodes_query = f"MATCH (n) RETURN n LIMIT {limit}"
        else:
            nodes_query = "MATCH (n) RETURN n"

        nodes_result = neo4j.execute_query(nodes_query)

        # Get all relationships
        if limit and nodes_result:
            # Get relationships for limited nodes
            node_ids = []
            for record in nodes_result:
                if isinstance(record, dict) and "n" in record:
                    node = record["n"]
                    if isinstance(node, dict) and "uuid" in node:
                        node_ids.append(node["uuid"])

            if node_ids:
                rels_query = """
                MATCH (n)-[r]->(m)
                WHERE n.uuid IN $node_ids OR m.uuid IN $node_ids
                RETURN n.uuid as source, m.uuid as target, type(r) as type, properties(r) as props
                """
                rels_result = neo4j.execute_query(rels_query, {"node_ids": node_ids})
            else:
                rels_result = []
        else:
            # Get all relationships
            rels_query = """
            MATCH (n)-[r]->(m)
            RETURN n.uuid as source, m.uuid as target, type(r) as type, properties(r) as props
            """
            rels_result = neo4j.execute_query(rels_query)

        # Process nodes
        nodes_data = []
        processed_uuids = set()

        for record in nodes_result:
            if not isinstance(record, dict):
                continue

            node = record.get("n")
            if not isinstance(node, dict):
                continue

            node_uuid = node.get("uuid")
            if not node_uuid or node_uuid in processed_uuids:
                continue

            processed_uuids.add(node_uuid)

            # Determine node type/label
            label = _determine_node_label(node)

            node_data = {
                "id": node_uuid,
                "label": label,
                "properties": {k: v for k, v in node.items() if k != "uuid"},
                "display_name": node.get("name") or node.get("title") or node_uuid[:8]
            }
            nodes_data.append(node_data)

        # Process relationships
        edges_data = []
        for record in rels_result:
            if not isinstance(record, dict):
                continue

            source = record.get("source")
            target = record.get("target")
            rel_type = record.get("type")

            if source and target and rel_type:
                props = record.get("props", {})
                if not isinstance(props, dict):
                    props = {}

                edge_data = {
                    "id": f"{source}-{rel_type}-{target}",
                    "source": source,
                    "target": target,
                    "type": rel_type,
                    "properties": props
                }
                edges_data.append(edge_data)

        return {
            "nodes": nodes_data,
            "edges": edges_data,
            "metadata": {
                "node_count": len(nodes_data),
                "edge_count": len(edges_data),
                "limit_applied": limit is not None
            }
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to export graph: {str(e)}"
        )


@router.get("/subgraph/{node_uuid}")
def get_node_subgraph(
    node_uuid: str,
    neo4j: Neo4jConnection = Depends(get_neo4j),
    depth: int = Query(1, ge=1, le=3, description="Depth of relationships to traverse"),
    max_nodes: int = Query(100, description="Maximum number of nodes to return")
):
    """
    Get subgraph centered around a specific node

    Args:
        node_uuid: UUID of the center node
        depth: How many hops from the center node to include
        max_nodes: Maximum nodes to return
    """
    try:
        # Get connected nodes within depth
        nodes_query = f"""
        MATCH (center {{uuid: $uuid}})
        OPTIONAL MATCH path = (center)-[*0..{depth}]-(connected)
        WITH center, collect(DISTINCT connected) as connected_nodes
        RETURN center, connected_nodes[0..{max_nodes}] as connected
        """

        result = neo4j.execute_query(nodes_query, {"uuid": node_uuid})

        if not result or not result[0].get("center"):
            raise HTTPException(status_code=404, detail=f"Node {node_uuid} not found")

        # Extract center and connected nodes
        center_node = result[0].get("center")
        connected_nodes = result[0].get("connected", [])

        all_nodes = [center_node] + [n for n in connected_nodes if n]
        node_uuids = [n["uuid"] for n in all_nodes if isinstance(n, dict) and n.get("uuid")]

        # Get relationships between these nodes
        if node_uuids:
            rels_query = """
            MATCH (n)-[r]->(m)
            WHERE n.uuid IN $uuids AND m.uuid IN $uuids
            RETURN n.uuid as source, m.uuid as target, type(r) as type, properties(r) as props
            """
            rels_result = neo4j.execute_query(rels_query, {"uuids": node_uuids})
        else:
            rels_result = []

        # Process nodes
        nodes_data = []
        for node in all_nodes:
            if not isinstance(node, dict) or not node.get("uuid"):
                continue

            label = _determine_node_label(node)

            node_data = {
                "id": node["uuid"],
                "label": label,
                "properties": {k: v for k, v in node.items() if k != "uuid"},
                "display_name": node.get("name") or node.get("title") or node["uuid"][:8],
                "is_center": node["uuid"] == node_uuid
            }
            nodes_data.append(node_data)

        # Process relationships
        edges_data = []
        for record in rels_result:
            if not isinstance(record, dict):
                continue

            source = record.get("source")
            target = record.get("target")
            rel_type = record.get("type")

            if source and target and rel_type:
                props = record.get("props", {})
                if not isinstance(props, dict):
                    props = {}

                edge_data = {
                    "id": f"{source}-{rel_type}-{target}",
                    "source": source,
                    "target": target,
                    "type": rel_type,
                    "properties": props
                }
                edges_data.append(edge_data)

        return {
            "nodes": nodes_data,
            "edges": edges_data,
            "metadata": {
                "center_node": node_uuid,
                "depth": depth,
                "node_count": len(nodes_data),
                "edge_count": len(edges_data)
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get subgraph: {str(e)}"
        )


@router.get("/statistics")
def get_graph_statistics(neo4j: Neo4jConnection = Depends(get_neo4j)):
    """
    Get statistics about the graph
    """
    try:
        # Count nodes by label
        node_stats_query = """
        MATCH (n)
        RETURN labels(n)[0] as label, count(n) as count
        ORDER BY count DESC
        """

        # Count relationships by type
        rel_stats_query = """
        MATCH ()-[r]->()
        RETURN type(r) as type, count(r) as count
        ORDER BY count DESC
        """

        # Get total counts
        total_query = """
        MATCH (n)
        WITH count(n) as node_count
        OPTIONAL MATCH ()-[r]->()
        RETURN node_count, count(r) as relationship_count
        """

        node_stats = neo4j.execute_query(node_stats_query)
        rel_stats = neo4j.execute_query(rel_stats_query)
        totals = neo4j.execute_query(total_query)

        # Build response
        nodes_by_type = {}
        for stat in node_stats:
            if isinstance(stat, dict) and "label" in stat and "count" in stat:
                nodes_by_type[stat["label"]] = stat["count"]

        relationships_by_type = {}
        for stat in rel_stats:
            if isinstance(stat, dict) and "type" in stat and "count" in stat:
                relationships_by_type[stat["type"]] = stat["count"]

        total_nodes = 0
        total_relationships = 0
        if totals and isinstance(totals[0], dict):
            total_nodes = totals[0].get("node_count", 0)
            total_relationships = totals[0].get("relationship_count", 0)

        return {
            "totals": {
                "nodes": total_nodes,
                "relationships": total_relationships
            },
            "nodes_by_type": nodes_by_type,
            "relationships_by_type": relationships_by_type
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get statistics: {str(e)}"
        )


def _determine_node_label(node: dict) -> str:
    """Determine node label from its properties"""
    if "dob" in node:
        return "Patient"
    elif "specialty" in node:
        return "Clinician"
    elif "date" in node and "dept" in node:
        return "Encounter"
    elif "value" in node and "unit" in node:
        return "TestResult"
    elif "loinc" in node:
        return "Test"
    elif "code" in node:
        system = node.get("system", "")
        if "ICD" in system:
            return "Disease"
        elif "RxNorm" in system:
            return "Medication"
        elif "CPT" in system or "HCPCS" in system:
            return "Procedure"
        else:
            return "Symptom"
    elif "title" in node:
        return "Guideline"
    else:
        return "Unknown"