from typing import Dict, List, Optional
import uuid
import logging
from .node_generator import NodeType

logger = logging.getLogger(__name__)

class EdgeManager:
    """Manages the creation and validation of edges between conversation nodes"""

    def __init__(self):
        self.edge_types = {
            "default": "custom",
            "transfer": "transfer",
            "end": "end"
        }

    def create_edge(self, source_node: Dict, target_node: Dict) -> Optional[Dict]:
        """
        Creates an edge between two nodes if the connection is valid
        Returns None if the connection is not valid
        """
        try:
            # Validate the connection
            if not self._is_valid_connection(source_node, target_node):
                return None

            edge_id = f"reactflow__edge-{source_node['id']}-{target_node['id']}"
            edge_data = self._generate_edge_metadata(source_node, target_node)

            edge = {
                "id": edge_id,
                "source": source_node["id"],
                "target": target_node["id"],
                "type": "custom",
                "animated": True,
                "data": edge_data,
                "selected": False,
                "sourceHandle": None,
                "targetHandle": None
            }

            return edge

        except Exception as e:
            logger.error(f"Error creating edge: {str(e)}")
            return None

    def _is_valid_connection(self, source_node: Dict, target_node: Dict) -> bool:
        """
        Determines if a connection between two nodes is valid based on node types and context
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

    def _generate_edge_metadata(self, source_node: Dict, target_node: Dict) -> Dict:
        """
        Generates descriptive metadata for edges based on node types and context
        """
        # Handle end call scenarios
        if target_node["type"] == NodeType.END_CALL.value:
            if "success" in target_node["data"].get("name", "").lower():
                return {
                    "label": "Successful Completion",
                    "description": "Successfully conclude the conversation with positive outcome",
                    "condition": "User has agreed to proceed or shown clear positive intent",
                    "user_signals": [
                        "Clear agreement",
                        "Positive acknowledgment",
                        "Ready to proceed"
                    ]
                }
            else:
                return {
                    "label": "Polite Conclusion",
                    "description": "End conversation respectfully when continuation is not possible",
                    "condition": "User has clearly indicated they do not wish to proceed",
                    "user_signals": [
                        "Clear rejection",
                        "Not interested",
                        "Request to end call"
                    ]
                }

        # Handle transfer scenarios
        if target_node["type"] == NodeType.TRANSFER_CALL.value:
            return {
                "label": "Expert Assistance Required",
                "description": "Transfer to human expert for specialized support",
                "condition": "Issue complexity requires human expertise",
                "user_signals": [
                    "Complex requirements",
                    "Specific expertise needed",
                    "Direct request for human"
                ]
            }

        # Generate context-aware metadata based on node names and types
        return self._generate_contextual_metadata(source_node, target_node)

    def _generate_contextual_metadata(self, source_node: Dict, target_node: Dict) -> Dict:
        """
        Generates context-aware metadata based on the relationship between nodes
        """
        source_name = source_node["data"].get("name", "").lower()
        target_name = target_node["data"].get("name", "").lower()

        # Value proposition flow
        if "value" in source_name and "objection" in target_name:
            return {
                "label": "Value Clarification",
                "description": "Address concerns about proposed value",
                "condition": "User expresses concern or seeks clarification",
                "user_signals": [
                    "Questions about value",
                    "Concern about benefits",
                    "Need for clarification"
                ]
            }

        # Discovery to solution flow
        if "discovery" in source_name and "solution" in target_name:
            return {
                "label": "Solution Presentation",
                "description": "Present tailored solution based on discovered needs",
                "condition": "User needs identified and ready for solution",
                "user_signals": [
                    "Clear need expressed",
                    "Interest in solutions",
                    "Readiness to learn more"
                ]
            }

        # Objection handling flow
        if "objection" in source_name:
            return {
                "label": "Objection Resolution",
                "description": "Address and resolve user concerns",
                "condition": "User concern needs to be addressed",
                "user_signals": [
                    "Expressed concern",
                    "Seeking clarification",
                    "Showing hesitation"
                ]
            }

        # Commitment flow
        if "commitment" in target_name:
            return {
                "label": "Decision Point",
                "description": "Guide user towards making a decision",
                "condition": "User shows readiness for commitment",
                "user_signals": [
                    "Positive engagement",
                    "Understanding shown",
                    "Interest expressed"
                ]
            }

        # Default progression
        return {
            "label": "Natural Progression",
            "description": "Continue the conversation flow",
            "condition": "User is engaged and responsive",
            "user_signals": [
                "Active participation",
                "Continued engagement",
                "Positive response signals"
            ]
        }

    def create_edges_for_nodes(self, nodes: List[Dict]) -> List[Dict]:
        """
        Creates all valid edges between a list of nodes
        """
        edges = []
        for source_node in nodes:
            valid_targets = self._find_valid_targets(source_node, nodes)
            for target_node in valid_targets:
                edge = self.create_edge(source_node, target_node)
                if edge:
                    edges.append(edge)
        return edges

    def _find_valid_targets(self, source_node: Dict, nodes: List[Dict]) -> List[Dict]:
        """
        Finds all valid target nodes for a given source node
        """
        valid_targets = []
        for target_node in nodes:
            # Skip if connection is not valid
            if not self._is_valid_connection(source_node, target_node):
                continue

            # Check node positioning for logical flow
            if self._is_valid_position(source_node, target_node):
                valid_targets.append(target_node)

        return valid_targets

    def _is_valid_position(self, source_node: Dict, target_node: Dict) -> bool:
        """
        Determines if the positional relationship between nodes is valid
        """
        # Get node positions
        source_pos = source_node.get("position", {"y": 0})
        target_pos = target_node.get("position", {"y": 0})

        # Nodes should generally flow downward (target should be below source)
        if target_pos["y"] <= source_pos["y"]:
            return False

        # Special case for global nodes
        if source_node["data"].get("isGlobal"):
            return target_node["type"] == NodeType.TRANSFER_CALL.value

        return True 