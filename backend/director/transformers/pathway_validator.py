from typing import Dict, List, Set, Optional, Tuple
import logging
from dataclasses import dataclass
from .node_generator import NodeType

logger = logging.getLogger(__name__)

@dataclass
class ValidationError:
    """Represents a validation error in the pathway"""
    error_type: str
    message: str
    node_id: Optional[str] = None
    edge_id: Optional[str] = None

class PathwayValidator:
    """Validates the structure and completeness of conversation pathways"""

    def __init__(self):
        self.required_node_fields = {
            "id", "type", "data", "position", "width", "height"
        }
        self.required_node_data_fields = {
            "name", "prompt", "active", "modelOptions"
        }
        self.required_edge_fields = {
            "id", "source", "target", "type", "data"
        }

    def validate_pathway(self, nodes: List[Dict], edges: List[Dict]) -> List[ValidationError]:
        """
        Validates the entire pathway structure
        Returns a list of validation errors, empty list if valid
        """
        errors = []
        
        # Validate basic structure
        errors.extend(self._validate_basic_structure(nodes, edges))
        
        # If basic structure is invalid, don't proceed with deeper validation
        if errors:
            return errors
        
        # Validate node connections
        errors.extend(self._validate_node_connections(nodes, edges))
        
        # Validate pathway completeness
        errors.extend(self._validate_pathway_completeness(nodes, edges))
        
        # Validate logical flow
        errors.extend(self._validate_logical_flow(nodes, edges))
        
        return errors

    def _validate_basic_structure(self, nodes: List[Dict], edges: List[Dict]) -> List[ValidationError]:
        """
        Validates the basic structure of nodes and edges
        """
        errors = []
        
        # Validate nodes
        for node in nodes:
            # Check required node fields
            missing_fields = self.required_node_fields - set(node.keys())
            if missing_fields:
                errors.append(ValidationError(
                    error_type="missing_fields",
                    message=f"Node missing required fields: {missing_fields}",
                    node_id=node.get("id")
                ))
            
            # Check required node data fields
            if "data" in node:
                missing_data_fields = self.required_node_data_fields - set(node["data"].keys())
                if missing_data_fields:
                    errors.append(ValidationError(
                        error_type="missing_data_fields",
                        message=f"Node data missing required fields: {missing_data_fields}",
                        node_id=node.get("id")
                    ))
        
        # Validate edges
        for edge in edges:
            # Check required edge fields
            missing_fields = self.required_edge_fields - set(edge.keys())
            if missing_fields:
                errors.append(ValidationError(
                    error_type="missing_fields",
                    message=f"Edge missing required fields: {missing_fields}",
                    edge_id=edge.get("id")
                ))
        
        return errors

    def _validate_node_connections(self, nodes: List[Dict], edges: List[Dict]) -> List[ValidationError]:
        """
        Validates the connections between nodes
        """
        errors = []
        node_ids = {node["id"] for node in nodes}
        
        # Check for invalid edge connections
        for edge in edges:
            source_id = edge.get("source")
            target_id = edge.get("target")
            
            # Validate source node exists
            if source_id not in node_ids:
                errors.append(ValidationError(
                    error_type="invalid_connection",
                    message=f"Edge references non-existent source node: {source_id}",
                    edge_id=edge.get("id")
                ))
            
            # Validate target node exists
            if target_id not in node_ids:
                errors.append(ValidationError(
                    error_type="invalid_connection",
                    message=f"Edge references non-existent target node: {target_id}",
                    edge_id=edge.get("id")
                ))
            
            # Validate connection rules
            if source_id in node_ids and target_id in node_ids:
                source_node = next(n for n in nodes if n["id"] == source_id)
                target_node = next(n for n in nodes if n["id"] == target_id)
                
                if not self._is_valid_connection(source_node, target_node):
                    errors.append(ValidationError(
                        error_type="invalid_connection",
                        message=f"Invalid connection between nodes: {source_id} -> {target_id}",
                        edge_id=edge.get("id")
                    ))
        
        return errors

    def _is_valid_connection(self, source_node: Dict, target_node: Dict) -> bool:
        """
        Determines if a connection between two nodes is valid
        """
        # Start node can't be a target
        if target_node["data"].get("isStart"):
            return False
        
        # Can't connect to self
        if source_node["id"] == target_node["id"]:
            return False
        
        # Global nodes can only connect to transfer nodes
        if source_node["data"].get("isGlobal"):
            return target_node["type"] == NodeType.TRANSFER_CALL.value
        
        # End nodes can't be source nodes
        if source_node["type"] in [NodeType.END_CALL.value, NodeType.TRANSFER_CALL.value]:
            return False
        
        return True

    def _validate_pathway_completeness(self, nodes: List[Dict], edges: List[Dict]) -> List[ValidationError]:
        """
        Validates that the pathway is complete and properly connected
        """
        errors = []
        
        # Check for start node
        start_nodes = [n for n in nodes if n["data"].get("isStart")]
        if not start_nodes:
            errors.append(ValidationError(
                error_type="missing_start",
                message="Pathway missing start node"
            ))
        elif len(start_nodes) > 1:
            errors.append(ValidationError(
                error_type="multiple_starts",
                message="Pathway has multiple start nodes"
            ))
        
        # Check for end nodes
        end_nodes = [n for n in nodes if n["type"] in [NodeType.END_CALL.value, NodeType.TRANSFER_CALL.value]]
        if not end_nodes:
            errors.append(ValidationError(
                error_type="missing_end",
                message="Pathway missing end nodes"
            ))
        
        # Check for isolated nodes
        connected_nodes = self._get_connected_nodes(edges)
        isolated_nodes = [n for n in nodes if n["id"] not in connected_nodes]
        for node in isolated_nodes:
            errors.append(ValidationError(
                error_type="isolated_node",
                message="Node is not connected to the pathway",
                node_id=node["id"]
            ))
        
        return errors

    def _get_connected_nodes(self, edges: List[Dict]) -> Set[str]:
        """
        Gets all node IDs that are connected by edges
        """
        connected_nodes = set()
        for edge in edges:
            connected_nodes.add(edge["source"])
            connected_nodes.add(edge["target"])
        return connected_nodes

    def _validate_logical_flow(self, nodes: List[Dict], edges: List[Dict]) -> List[ValidationError]:
        """
        Validates the logical flow of the conversation pathway
        """
        errors = []
        
        # Build node position map
        node_positions = {node["id"]: node["position"]["y"] for node in nodes}
        
        # Check for circular references
        if self._has_circular_reference(edges):
            errors.append(ValidationError(
                error_type="circular_reference",
                message="Pathway contains circular references"
            ))
        
        # Check for backward flows
        for edge in edges:
            source_y = node_positions[edge["source"]]
            target_y = node_positions[edge["target"]]
            
            if target_y <= source_y and not self._is_special_case(nodes, edge):
                errors.append(ValidationError(
                    error_type="invalid_flow",
                    message="Edge creates backward flow in pathway",
                    edge_id=edge["id"]
                ))
        
        return errors

    def _has_circular_reference(self, edges: List[Dict]) -> bool:
        """
        Checks if the pathway contains any circular references
        """
        # Build adjacency list
        adj_list = {}
        for edge in edges:
            if edge["source"] not in adj_list:
                adj_list[edge["source"]] = set()
            adj_list[edge["source"]].add(edge["target"])
        
        # Check for cycles using DFS
        visited = set()
        path = set()
        
        def has_cycle(node: str) -> bool:
            if node in path:
                return True
            if node in visited:
                return False
            
            visited.add(node)
            path.add(node)
            
            for neighbor in adj_list.get(node, set()):
                if has_cycle(neighbor):
                    return True
            
            path.remove(node)
            return False
        
        for node in adj_list:
            if node not in visited:
                if has_cycle(node):
                    return True
        
        return False

    def _is_special_case(self, nodes: List[Dict], edge: Dict) -> bool:
        """
        Checks if an edge is a special case that allows backward flow
        """
        source_node = next(n for n in nodes if n["id"] == edge["source"])
        target_node = next(n for n in nodes if n["id"] == edge["target"])
        
        # Global nodes can connect backwards to transfer nodes
        if source_node["data"].get("isGlobal"):
            return target_node["type"] == NodeType.TRANSFER_CALL.value
        
        return False 