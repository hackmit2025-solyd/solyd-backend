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
        # Simpler approach: Get nodes and relationships separately

        # Get all nodes
        if limit:
            nodes_query = f"MATCH (n) RETURN n LIMIT {limit}"
        else:
            nodes_query = "MATCH (n) RETURN n"

        nodes_result = neo4j.execute_query(nodes_query)

        # Get all relationships
        if limit:
            rels_query = f"""
            MATCH (n)-[r]->(m)
            WHERE n.uuid IN $node_ids OR m.uuid IN $node_ids
            RETURN n.uuid as source, m.uuid as target, type(r) as type, r as rel
            """
            node_ids = [node["n"]["uuid"] for node in nodes_result if node.get("n", {}).get("uuid")]
            rels_result = neo4j.execute_query(rels_query, {"node_ids": node_ids})
        else:
            rels_query = """
            MATCH (n)-[r]->(m)
            RETURN n.uuid as source, m.uuid as target, type(r) as type, r as rel
            """
            rels_result = neo4j.execute_query(rels_query)

        # Process nodes
        nodes_data = []
        for record in nodes_result:
            node = record.get("n")
            if node and node.get("uuid"):
                # Determine node type/label
                label = "Unknown"
                if "name" in node:
                    if "dob" in node:
                        label = "Patient"
                    elif "specialty" in node:
                        label = "Clinician"
                    elif "date" in node:
                        label = "Encounter"
                    elif "code" in node:
                        if "system" in node:
                            label = "Disease" if node.get("system") == "ICD10" else "Medication"
                        else:
                            label = "Symptom"
                    elif "loinc" in node:
                        label = "Test"
                    elif "value" in node and "unit" in node:
                        label = "TestResult"

                node_data = {
                    "id": node["uuid"],
                    "label": label,
                    "properties": {k: v for k, v in node.items() if k != "uuid"},
                    "display_name": node.get("name") or node.get("title") or node["uuid"][:8]
                }
                nodes_data.append(node_data)

        # Process relationships
        edges_data = []
        for record in rels_result:
            if record.get("source") and record.get("target"):
                rel = record.get("rel", {})
                edge_data = {
                    "id": f"{record['source']}-{record['type']}-{record['target']}",
                    "source": record["source"],
                    "target": record["target"],
                    "type": record["type"],
                    "properties": {k: v for k, v in rel.items() if k not in ["uuid", "source", "target"]}
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

        if not result:
            raise HTTPException(status_code=404, detail=f"Node {node_uuid} not found")

        # Extract center and connected nodes
        center_node = result[0].get("center")
        connected_nodes = result[0].get("connected", [])

        all_nodes = [center_node] + [n for n in connected_nodes if n]
        node_uuids = [n["uuid"] for n in all_nodes if n and n.get("uuid")]

        # Get relationships between these nodes
        rels_query = """
        MATCH (n)-[r]->(m)
        WHERE n.uuid IN $uuids AND m.uuid IN $uuids
        RETURN n.uuid as source, m.uuid as target, type(r) as type, r as rel
        """

        rels_result = neo4j.execute_query(rels_query, {"uuids": node_uuids})

        # Process nodes
        nodes_data = []
        for node in all_nodes:
            if node and node.get("uuid"):
                # Determine node type
                label = "Unknown"
                if "dob" in node:
                    label = "Patient"
                elif "specialty" in node:
                    label = "Clinician"
                elif "date" in node and "dept" in node:
                    label = "Encounter"
                elif "code" in node:
                    label = "Disease" if node.get("system") == "ICD10" else "Medication"
                elif "loinc" in node:
                    label = "Test"

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
            if record.get("source") and record.get("target"):
                rel = record.get("rel", {})
                edge_data = {
                    "id": f"{record['source']}-{record['type']}-{record['target']}",
                    "source": record["source"],
                    "target": record["target"],
                    "type": record["type"],
                    "properties": {k: v for k, v in rel.items() if k not in ["uuid", "source", "target"]}
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
        MATCH ()-[r]->()
        RETURN node_count, count(r) as relationship_count
        """

        node_stats = neo4j.execute_query(node_stats_query)
        rel_stats = neo4j.execute_query(rel_stats_query)
        totals = neo4j.execute_query(total_query)

        return {
            "totals": {
                "nodes": totals[0]["node_count"] if totals else 0,
                "relationships": totals[0]["relationship_count"] if totals else 0
            },
            "nodes_by_type": {
                stat["label"]: stat["count"]
                for stat in node_stats
            },
            "relationships_by_type": {
                stat["type"]: stat["count"]
                for stat in rel_stats
            }
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get statistics: {str(e)}"
        )