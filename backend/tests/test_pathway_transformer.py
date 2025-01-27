import unittest
from unittest.mock import Mock, patch
import json
from datetime import datetime

from director.transformers.pathway_transformer import (
    PathwayStructureTransformer,
    NodeType,
    ModelOptions,
    Position
)

class TestPathwayStructureTransformer(unittest.TestCase):
    def setUp(self):
        self.transformer = PathwayStructureTransformer()
        self.sample_outputs = [
            {
                "id": "1",
                "video_id": "test_video",
                "output_type": "analysis",
                "content": json.dumps({
                    "conversation_type": "sales",
                    "key_points": ["greeting", "pitch", "close"],
                    "sentiment": "positive"
                }),
                "created_at": datetime.now().isoformat()
            },
            {
                "id": "2",
                "video_id": "test_video",
                "output_type": "conversation",
                "content": json.dumps({
                    "type": "greeting",
                    "text": "Hello, this is a sales call",
                    "next_actions": ["pitch_product", "handle_objection"]
                }),
                "created_at": datetime.now().isoformat()
            },
            {
                "id": "3",
                "video_id": "test_video",
                "output_type": "error_handling",
                "content": json.dumps({
                    "type": "objection",
                    "text": "I need to speak with a manager",
                    "action": "transfer"
                }),
                "created_at": datetime.now().isoformat()
            }
        ]

    def test_transform_from_outputs_creates_valid_structure(self):
        """Test that transformation creates valid pathway structure"""
        result = self.transformer.transform_from_outputs(self.sample_outputs)
        
        # Check basic structure
        self.assertIn("nodes", result)
        self.assertIn("edges", result)
        self.assertTrue(isinstance(result["nodes"], list))
        self.assertTrue(isinstance(result["edges"], list))
        
        # Verify start node exists
        start_nodes = [n for n in result["nodes"] if n["data"].get("isStart")]
        self.assertEqual(len(start_nodes), 1, "Should have exactly one start node")
        
        # Verify node structure
        for node in result["nodes"]:
            self._verify_node_structure(node)
            
        # Verify edge structure
        for edge in result["edges"]:
            self._verify_edge_structure(edge)
            
    def test_node_positioning(self):
        """Test that nodes are positioned correctly"""
        result = self.transformer.transform_from_outputs(self.sample_outputs)
        
        positions = [n["position"] for n in result["nodes"]]
        
        # Check no overlapping positions
        position_strings = [f"{p['x']},{p['y']}" for p in positions]
        self.assertEqual(
            len(position_strings),
            len(set(position_strings)),
            "Nodes should not overlap"
        )
        
        # Check proper spacing
        for i in range(len(positions) - 1):
            pos1 = positions[i]
            pos2 = positions[i + 1]
            
            # Verify minimum spacing
            if pos1["y"] == pos2["y"]:  # Same level
                self.assertGreaterEqual(
                    abs(pos2["x"] - pos1["x"]),
                    self.transformer.horizontal_spacing
                )
                
    def test_error_handling_nodes(self):
        """Test creation of error handling nodes"""
        result = self.transformer.transform_from_outputs(self.sample_outputs)
        
        # Find error handling nodes
        error_nodes = [
            n for n in result["nodes"]
            if "error" in n["data"].get("name", "").lower()
            or n["type"] == NodeType.TRANSFER_CALL.value
        ]
        
        self.assertGreater(len(error_nodes), 0, "Should create error handling nodes")
        
        # Verify transfer nodes have transfer numbers
        transfer_nodes = [
            n for n in error_nodes
            if n["type"] == NodeType.TRANSFER_CALL.value
        ]
        for node in transfer_nodes:
            self.assertIn("transferNumber", node["data"])
            
    def test_edge_creation(self):
        """Test that edges are created correctly"""
        result = self.transformer.transform_from_outputs(self.sample_outputs)
        
        # Get node IDs
        node_ids = {n["id"] for n in result["nodes"]}
        
        # Verify edges connect existing nodes
        for edge in result["edges"]:
            self.assertIn(edge["source"], node_ids)
            self.assertIn(edge["target"], node_ids)
            
            # Verify edge data
            self.assertIn("label", edge["data"])
            self.assertIn("description", edge["data"])
            
    def test_model_options(self):
        """Test that model options are properly set"""
        result = self.transformer.transform_from_outputs(self.sample_outputs)
        
        for node in result["nodes"]:
            model_options = node["data"]["modelOptions"]
            self.assertIn("modelType", model_options)
            self.assertIn("temperature", model_options)
            self.assertIn("skipUserResponse", model_options)
            self.assertIn("block_interruptions", model_options)
            
            # Verify types
            self.assertIsInstance(model_options["temperature"], float)
            self.assertIsInstance(model_options["skipUserResponse"], bool)
            self.assertIsInstance(model_options["block_interruptions"], bool)
            
    def test_global_nodes(self):
        """Test that global nodes are properly created"""
        result = self.transformer.transform_from_outputs(self.sample_outputs)
        
        # Find global nodes
        global_nodes = [
            n for n in result["nodes"]
            if n["data"].get("isGlobal", False)
        ]
        
        self.assertGreater(len(global_nodes), 0, "Should create global nodes")
        
        for node in global_nodes:
            self.assertIn("globalLabel", node["data"])
            self.assertIn("globalDescription", node["data"])
            
    def _verify_node_structure(self, node):
        """Helper to verify node structure"""
        required_fields = {"id", "type", "data", "position", "width", "height"}
        self.assertTrue(all(field in node for field in required_fields))
        
        required_data_fields = {"name", "prompt", "modelOptions"}
        self.assertTrue(all(field in node["data"] for field in required_data_fields))
        
        # Verify model options
        model_options = node["data"]["modelOptions"]
        self.assertIn("modelType", model_options)
        self.assertIn("temperature", model_options)
        self.assertIn("skipUserResponse", model_options)
        self.assertIn("block_interruptions", model_options)
        
    def _verify_edge_structure(self, edge):
        """Helper to verify edge structure"""
        required_fields = {"id", "source", "target", "type", "data"}
        self.assertTrue(all(field in edge for field in required_fields))
        
        self.assertEqual(edge["type"], "custom")
        self.assertTrue(isinstance(edge["animated"], bool))
        
if __name__ == '__main__':
    unittest.main() 