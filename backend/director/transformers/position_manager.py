from typing import Dict, List, Optional, Tuple
import logging
from dataclasses import dataclass
from .node_generator import NodeType

logger = logging.getLogger(__name__)

@dataclass
class LayoutConfig:
    """Configuration for layout spacing and dimensions"""
    node_width: int = 320
    node_height: int = 127
    horizontal_spacing: int = 400
    vertical_spacing: int = 200
    start_x: int = 400
    start_y: int = 100
    max_nodes_per_row: int = 3

class PositionManager:
    """Manages the positioning and layout of nodes in the conversation flow"""

    def __init__(self, config: Optional[LayoutConfig] = None):
        self.config = config or LayoutConfig()
        self.level_counts: Dict[int, int] = {}  # Tracks number of nodes at each level
        self.occupied_positions: List[Tuple[int, int]] = []  # Tracks used positions

    def calculate_position(self, node: Dict, level: int) -> Dict[str, int]:
        """
        Calculates the position for a node based on its level and existing nodes
        """
        try:
            # Initialize level count if not exists
            if level not in self.level_counts:
                self.level_counts[level] = 0

            # Calculate base position
            x = self._calculate_x_position(level)
            y = self._calculate_y_position(level)

            # Adjust for node type
            position = self._adjust_position_for_type(node, x, y)
            
            # Update tracking
            self.level_counts[level] += 1
            self.occupied_positions.append((position["x"], position["y"]))

            return position

        except Exception as e:
            logger.error(f"Error calculating position: {str(e)}")
            return {"x": 0, "y": 0}

    def _calculate_x_position(self, level: int) -> int:
        """
        Calculates the x-coordinate based on level and number of nodes
        """
        current_count = self.level_counts.get(level, 0)
        base_x = self.config.start_x
        
        # Calculate horizontal position within row
        column = current_count % self.config.max_nodes_per_row
        x = base_x + (column * (self.config.node_width + self.config.horizontal_spacing))
        
        return x

    def _calculate_y_position(self, level: int) -> int:
        """
        Calculates the y-coordinate based on level
        """
        return self.config.start_y + (level * (self.config.node_height + self.config.vertical_spacing))

    def _adjust_position_for_type(self, node: Dict, x: int, y: int) -> Dict[str, int]:
        """
        Adjusts position based on node type and special conditions
        """
        node_type = node.get("type")
        
        # Start node positioning
        if node["data"].get("isStart"):
            return {"x": self.config.start_x, "y": self.config.start_y}
        
        # Global node positioning (placed on the left side)
        if node["data"].get("isGlobal"):
            return {
                "x": self.config.start_x // 2,
                "y": y + self.config.vertical_spacing
            }
        
        # End/Transfer node positioning (placed on the right side)
        if node_type in [NodeType.END_CALL.value, NodeType.TRANSFER_CALL.value]:
            return {
                "x": x + self.config.horizontal_spacing,
                "y": y
            }
        
        return {"x": x, "y": y}

    def layout_nodes(self, nodes: List[Dict]) -> List[Dict]:
        """
        Applies layout positioning to a list of nodes
        """
        # Reset tracking
        self.level_counts = {}
        self.occupied_positions = []
        
        # Sort nodes by type to ensure proper ordering
        sorted_nodes = self._sort_nodes_by_type(nodes)
        
        # Apply positions
        positioned_nodes = []
        current_level = 0
        
        for node in sorted_nodes:
            # Calculate position
            position = self.calculate_position(node, current_level)
            
            # Update node with position
            node["position"] = position
            node["positionAbsolute"] = position
            
            positioned_nodes.append(node)
            
            # Increment level if max nodes per row reached
            if self.level_counts.get(current_level, 0) >= self.config.max_nodes_per_row:
                current_level += 1
        
        return positioned_nodes

    def _sort_nodes_by_type(self, nodes: List[Dict]) -> List[Dict]:
        """
        Sorts nodes to ensure proper layout order
        Order: Start -> Main -> Global -> End/Transfer
        """
        start_nodes = []
        main_nodes = []
        global_nodes = []
        end_nodes = []
        
        for node in nodes:
            if node["data"].get("isStart"):
                start_nodes.append(node)
            elif node["data"].get("isGlobal"):
                global_nodes.append(node)
            elif node["type"] in [NodeType.END_CALL.value, NodeType.TRANSFER_CALL.value]:
                end_nodes.append(node)
            else:
                main_nodes.append(node)
        
        return start_nodes + main_nodes + global_nodes + end_nodes

    def check_position_overlap(self, position: Dict[str, int]) -> bool:
        """
        Checks if a position overlaps with any existing nodes
        """
        x, y = position["x"], position["y"]
        
        # Check against all occupied positions
        for occupied_x, occupied_y in self.occupied_positions:
            # Calculate if boxes overlap
            x_overlap = abs(x - occupied_x) < self.config.node_width
            y_overlap = abs(y - occupied_y) < self.config.node_height
            
            if x_overlap and y_overlap:
                return True
        
        return False

    def adjust_for_overlap(self, position: Dict[str, int]) -> Dict[str, int]:
        """
        Adjusts position if overlap is detected
        """
        original_x = position["x"]
        original_y = position["y"]
        
        # Try moving right
        position["x"] += self.config.horizontal_spacing
        if not self.check_position_overlap(position):
            return position
        
        # Try moving down
        position["x"] = original_x
        position["y"] += self.config.vertical_spacing
        if not self.check_position_overlap(position):
            return position
        
        # If still overlapping, find next free position
        while self.check_position_overlap(position):
            position["x"] += self.config.horizontal_spacing
            if position["x"] > original_x + (self.config.horizontal_spacing * 3):
                position["x"] = original_x
                position["y"] += self.config.vertical_spacing
        
        return position 