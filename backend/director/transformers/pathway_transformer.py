from typing import List, Dict, Optional, Tuple, Union
from datetime import datetime
import uuid
import logging
from enum import Enum
from dataclasses import dataclass
import json
from openai import OpenAI  # Updated import
import os

from .node_generator import NodeGenerator, NodeType
from .edge_manager import EdgeManager
from .position_manager import PositionManager, LayoutConfig
from .pathway_validator import PathwayValidator, ValidationError

logger = logging.getLogger(__name__)

@dataclass
class Position:
    x: int
    y: int

@dataclass
class ModelOptions:
    model_type: str = "smart"
    temperature: float = 0.2
    skip_user_response: bool = False
    block_interruptions: bool = False

    def to_dict(self) -> dict:
        return {
            "modelType": self.model_type,
            "temperature": self.temperature,
            "skipUserResponse": self.skip_user_response,
            "block_interruptions": self.block_interruptions
        }

@dataclass
class TransformationResult:
    """Result of pathway transformation"""
    nodes: Dict[str, Dict]
    edges: Dict[str, Dict]
    errors: List[ValidationError]
    warnings: List[str]

class PathwayTransformer:
    """
    Main transformer class that orchestrates the conversion of outputs into
    a structured conversation pathway using specialized components
    """

    def __init__(self, layout_config: Optional[LayoutConfig] = None):
        self.node_generator = NodeGenerator()
        self.edge_manager = EdgeManager()
        self.position_manager = PositionManager(layout_config)
        self.validator = PathwayValidator()

    def transform_from_outputs(self, outputs: List[Dict]) -> TransformationResult:
        """
        Main transformation method to convert outputs to pathway structure
        
        Args:
            outputs: List of generated outputs from database
            
        Returns:
            TransformationResult containing nodes, edges, and any validation issues
        """
        try:
            logger.info(f"Starting transformation of {len(outputs)} outputs")
            
            # Initialize result containers
            nodes = {}
            edges = {}
            warnings = []
            
            # 1. Process and group outputs
            grouped_outputs = self._group_outputs(outputs)
            
            # 2. Generate nodes
            node_list = self._generate_nodes(grouped_outputs)
            
            # 3. Position nodes
            positioned_nodes = self.position_manager.layout_nodes(node_list)
            
            # 4. Create edges
            edge_list = self.edge_manager.create_edges_for_nodes(positioned_nodes)
            
            # 5. Validate pathway
            validation_errors = self.validator.validate_pathway(positioned_nodes, edge_list)
            
            # 6. Convert to final format
            for node in positioned_nodes:
                nodes[node["id"]] = node
            
            for edge in edge_list:
                edges[edge["id"]] = edge
            
            # Log completion
            logger.info(f"Successfully created pathway with {len(nodes)} nodes and {len(edges)} edges")
            
            return TransformationResult(
                nodes=nodes,
                edges=edges,
                errors=validation_errors,
                warnings=warnings
            )
            
        except Exception as e:
            logger.error(f"Failed to transform outputs: {str(e)}")
            raise
            
    def _group_outputs(self, outputs: List[Dict]) -> Dict:
        """Group outputs by type and analyze their relationships"""
        grouped = {
            "voice_prompts": [],
            "global_handlers": [],
            "end_nodes": []
        }
        
        for output in outputs:
            content = output.get("content")
            output_id = output.get("id")
            
            if not content:
                logger.warning(f"Skipping output without content: {output}")
                continue
                
            try:
                # Parse content
                parsed_content = self._parse_content(content)
                parsed_content["output_id"] = output_id
                
                # Categorize output
                if parsed_content.get("isGlobal"):
                    grouped["global_handlers"].append(parsed_content)
                elif parsed_content.get("type") in [NodeType.END_CALL.value, NodeType.TRANSFER_CALL.value]:
                    grouped["end_nodes"].append(parsed_content)
                else:
                    grouped["voice_prompts"].append(parsed_content)
                    
            except Exception as e:
                logger.warning(f"Failed to parse content for output {output_id}: {str(e)}")
                continue
                
        return grouped
        
    def _parse_content(self, content: Union[str, Dict]) -> Dict:
        """Parse content into a standardized format"""
        if isinstance(content, str):
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                return {
                    "prompt": content,
                    "type": NodeType.DEFAULT.value
                }
        return dict(content)

    def _generate_nodes(self, grouped_outputs: Dict) -> List[Dict]:
        """Generate all nodes for the pathway"""
        nodes = []
        
        # 1. Create start node
        start_prompt = (grouped_outputs["voice_prompts"][0]["prompt"] 
                       if grouped_outputs["voice_prompts"] else None)
        nodes.append(self.node_generator.create_start_node(start_prompt))
        
        # 2. Create main conversation nodes
        for prompt in grouped_outputs["voice_prompts"][1:]:  # Skip first prompt (used in start)
            node = self.node_generator.create_node(
                prompt_text=prompt["prompt"],
                node_type=NodeType(prompt.get("type", NodeType.DEFAULT.value))
            )
            nodes.append(node)
        
        # 3. Create global handler nodes
        for handler in grouped_outputs["global_handlers"]:
            node = self.node_generator.create_node(
                prompt_text=handler["prompt"],
                node_type=NodeType.DEFAULT,
                is_global=True
            )
            nodes.append(node)
        
        # 4. Create end nodes
        end_types = ["success", "rejection", "transfer"]
        for end_type in end_types:
            node = self.node_generator.create_end_node(
                node_type=end_type,
                position={"x": 0, "y": 0}  # Position will be set by PositionManager
            )
            nodes.append(node)
        
        return nodes
        
    def update_node(self, node_id: str, updates: Dict) -> Optional[Dict]:
        """
        Update an existing node with new data
        Returns the updated node if successful, None if validation fails
        """
        try:
            # Get existing node data
            if node_id not in self.nodes:
                logger.error(f"Node {node_id} not found")
                return None
            
            node = self.nodes[node_id].copy()
            
            # Apply updates
            if "data" in updates:
                node["data"].update(updates["data"])
            if "position" in updates:
                node["position"].update(updates["position"])
                node["positionAbsolute"].update(updates["position"])
            
            # Validate updated node
            errors = self.validator._validate_basic_structure([node], [])
            if errors:
                logger.error(f"Invalid node update: {errors}")
                return None
            
            # Update storage
            self.nodes[node_id] = node
            return node
            
        except Exception as e:
            logger.error(f"Failed to update node: {str(e)}")
            return None

    def delete_node(self, node_id: str) -> bool:
        """
        Delete a node and its connected edges
        Returns True if successful, False otherwise
        """
        try:
            # Remove node
            if node_id not in self.nodes:
                return False
            
            del self.nodes[node_id]
            
            # Remove connected edges
            edges_to_remove = []
            for edge_id, edge in self.edges.items():
                if edge["source"] == node_id or edge["target"] == node_id:
                    edges_to_remove.append(edge_id)
            
            for edge_id in edges_to_remove:
                del self.edges[edge_id]
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete node: {str(e)}")
            return False

    def add_edge(self, source_id: str, target_id: str) -> Optional[Dict]:
        """
        Add a new edge between nodes
        Returns the created edge if successful, None if validation fails
        """
        try:
            # Validate nodes exist
            if source_id not in self.nodes or target_id not in self.nodes:
                return None
            
            source_node = self.nodes[source_id]
            target_node = self.nodes[target_id]
            
            # Create edge
            edge = self.edge_manager.create_edge(source_node, target_node)
            if not edge:
                return None
            
            # Validate new edge
            errors = self.validator._validate_node_connections(
                list(self.nodes.values()),
                list(self.edges.values()) + [edge]
            )
            if errors:
                return None
            
            # Add to storage
            self.edges[edge["id"]] = edge
            return edge
            
        except Exception as e:
            logger.error(f"Failed to add edge: {str(e)}")
            return None

    def delete_edge(self, edge_id: str) -> bool:
        """
        Delete an edge
        Returns True if successful, False otherwise
        """
        try:
            if edge_id not in self.edges:
                return False
            
            del self.edges[edge_id]
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete edge: {str(e)}")
            return False

    def _call_gpt4(self, prompt: str) -> str:
        """Call GPT-4 with a prompt and return the response"""
        try:
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEY environment variable not set")
            
            client = OpenAI(api_key=api_key)
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are an expert conversation designer for AI voice agents."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,
                max_tokens=50
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"Error calling GPT-4: {str(e)}")
            raise

    def _generate_node_name_from_prompt(self, prompt_text: str) -> str:
        """Generate a semantic name for a node based on its prompt text"""
        try:
            # Enhanced prompt for semantic name generation
            prompt = f"""
            Generate a concise and descriptive name (2-4 words) for this node that reflects:
            1. The primary intent (e.g., Inquiry Handling, Objection Resolution)
            2. The phase of the conversation (e.g., Introduction, Deep Dive)
            3. The expected outcome (e.g., Agreement, Information Gathering)

            The name should be professional and clearly indicate the node's role in the conversation.
            
            Example transformations:
            - "How are you doing today?" -> "Initial Rapport Building"
            - "Let me tell you about our pricing" -> "Value Proposition Introduction"
            - "Would you like to proceed?" -> "Commitment Decision Point"
            - "I understand your concern about the cost" -> "Budget Objection Resolution"
            
            Prompt to name: {prompt_text}
            
            Generate only the name, no explanation.
            """
            
            # Call GPT-4 with the enhanced prompt
            response = self._call_gpt4(prompt)
            
            # Clean and validate the response
            name = response.strip().replace('"', '').replace("'", "")
            if not name:
                raise ValueError("Empty name generated")
            
            logger.info(f"Generated node name: {name} for prompt: {prompt_text[:50]}...")
            return name
        
        except Exception as e:
            logger.error(f"Error generating node name: {str(e)}")
            return "Conversation Node"  # Fallback name

    def _generate_structured_pathway(self, outputs: List[Dict]) -> Dict:
        try:
            logger.info("Starting structured pathway generation")
            
            if not outputs:
                logger.error("No outputs provided to generate pathway")
                raise ValueError("No outputs provided to generate pathway")
            
            # Group outputs and generate nodes with names first
            nodes = []
            for output in outputs:
                if not isinstance(output, dict):
                    logger.warning(f"Skipping invalid output format: {type(output)}")
                    continue
                    
                content = output.get("content")
                if content is None:
                    logger.warning(f"Skipping output with no content: {output.get('id')}")
                    continue
                
                # Parse content if it's a string that might be JSON
                if isinstance(content, str):
                    try:
                        parsed_content = json.loads(content)
                        if isinstance(parsed_content, dict):
                            content = parsed_content
                        else:
                            content = {"text": content}
                    except json.JSONDecodeError:
                        content = {"text": content}
                elif not isinstance(content, dict):
                    content = {"text": str(content)}
                elif output.get("output_type") == "voice_prompt":
                    # Extract prompt text safely
                    prompt_text = content.get("text")
                    if not prompt_text and isinstance(content, dict):
                        prompt_text = str(content)
                    elif not prompt_text:
                        prompt_text = "Default prompt text"
                    
                    # Generate descriptive name using GPT-4-mini
                    try:
                        node_name = self._generate_node_name_from_prompt(prompt_text)
                    except Exception as e:
                        logger.error(f"Error generating node name: {str(e)}")
                        node_name = f"Node {len(nodes) + 1}"
                    
                    # Create default model options
                    model_options = {
                        "modelType": "smart",
                        "temperature": 0.2,
                        "skipUserResponse": False,
                        "blockInterruptions": False
                    }
                    
                    # Update with any provided options
                    if isinstance(content.get("modelOptions"), dict):
                        model_options.update(content["modelOptions"])
                    
                    node = {
                        "name": node_name,
                        "type": content.get("type", "Default"),
                        "prompt": prompt_text,
                        "condition": content.get("condition", "Proceed based on user's response"),
                        "modelOptions": model_options,
                        "promptId": output.get("id")
                    }
                    nodes.append(node)
            
            if not nodes:
                logger.error("No valid nodes could be generated from outputs")
                raise ValueError("No valid nodes could be generated from outputs")
            
            # Create a simple sequential structure
            structured_data = {
                "nodes": nodes,
                "edges": []
            }
            
            # Create edges connecting nodes sequentially
            for i in range(len(nodes) - 1):
                edge = {
                    "source": nodes[i]["name"],
                    "target": nodes[i + 1]["name"],
                    "condition": "Continue",
                    "data": {
                        "label": "Continue",
                        "description": "Continue with the conversation flow"
                    }
                }
                structured_data["edges"].append(edge)
            
            return structured_data
                
        except Exception as e:
            logger.error(f"Error generating structured pathway: {str(e)}")
            raise

    def _create_end_nodes(self) -> List[Dict]:
        """Create standard end nodes for different scenarios"""
        end_nodes = []
        
        # Successful completion end node
        success_node = {
            "id": "end_success",
            "type": NodeType.END_CALL.value,
            "data": {
                "name": "Successful Completion",
                "active": False,
                "prompt": "Thank you for your time and participation. We've successfully completed our conversation. Have a great day!",
                "condition": "Use when conversation reaches successful conclusion",
                "globalPrompt": self._get_global_prompt(),
                "modelOptions": ModelOptions().to_dict()
            },
            "position": self._calculate_position(self.current_level + 1, 0),
            "width": self.node_width,
            "height": self.node_height,
            "dragging": False,
            "selected": False
        }
        end_nodes.append(success_node)
        
        # Polite ending for rejections
        rejection_node = {
            "id": "end_rejection",
            "type": NodeType.END_CALL.value,
            "data": {
                "name": "Polite Ending",
                "active": False,
                "prompt": "I understand this isn't what you're looking for right now. Thank you for your time, and have a great day!",
                "condition": "Use when user clearly indicates they're not interested",
                "globalPrompt": self._get_global_prompt(),
                "modelOptions": ModelOptions().to_dict()
            },
            "position": self._calculate_position(self.current_level + 1, 1),
            "width": self.node_width,
            "height": self.node_height,
            "dragging": False,
            "selected": False
        }
        end_nodes.append(rejection_node)
        
        # Transfer to human end node
        transfer_node = {
            "id": "end_transfer",
            "type": NodeType.TRANSFER_CALL.value,
            "data": {
                "name": "Transfer to Human",
                "active": False,
                "prompt": "I'll transfer you to a human assistant who can better help with your needs. Please hold while I connect you.",
                "condition": "Use when issue requires human intervention",
                "globalPrompt": self._get_global_prompt(),
                "modelOptions": ModelOptions().to_dict(),
                "transferNumber": "+1234567890"  # Should be configured per implementation
            },
            "position": self._calculate_position(self.current_level + 1, 2),
            "width": self.node_width,
            "height": self.node_height,
            "dragging": False,
            "selected": False
        }
        end_nodes.append(transfer_node)
        
        return end_nodes

    def _should_connect_to_end_node(self, source_node: Dict, end_node: Dict) -> bool:
        """Determine if source node should connect to given end node"""
        source_type = source_node.get("type")
        end_type = end_node.get("type")
        
        # All nodes can potentially end in transfer
        if end_type == NodeType.TRANSFER_CALL.value:
            return True
            
        # Only certain nodes should connect to success/rejection ends
        if end_type == NodeType.END_CALL.value:
            # Connect if source is a decision point or final node
            if "final" in source_node["data"].get("name", "").lower():
                return True
            if "decision" in source_node["data"].get("name", "").lower():
                return True
            if "booking" in source_node["data"].get("name", "").lower():
                return True
                
        return False

    def _generate_node_intent(self, node_name: str, prompt_text: str) -> str:
        """Generate primary conversational intent for the node"""
        try:
            prompt = f"""
            Based on the node name '{node_name}' and prompt text '{prompt_text}',
            generate a clear, one-sentence statement of this node's primary conversational intent.
            Focus on what the AI agent aims to achieve in this step.
            """
            return self._call_gpt4(prompt).strip()
        except Exception as e:
            logger.error(f"Error generating node intent: {str(e)}")
            return "Progress the conversation effectively"

    def _generate_success_condition(self, node_name: str) -> str:
        """Generate success condition based on node name"""
        name_lower = node_name.lower()
        
        if "discovery" in name_lower:
            return "User provides clear information about their needs or situation"
        elif "value" in name_lower:
            return "User shows interest in the proposed value or benefits"
        elif "objection" in name_lower:
            return "User's concerns are successfully addressed"
        elif "commitment" in name_lower:
            return "User agrees to proceed or take next steps"
        else:
            return "User engages positively and conversation progresses naturally"

    def _generate_failure_condition(self, node_name: str) -> str:
        """Generate failure condition based on node name"""
        name_lower = node_name.lower()
        
        if "discovery" in name_lower:
            return "User refuses to share information or shows strong disinterest"
        elif "value" in name_lower:
            return "User explicitly rejects the proposed value or shows clear disinterest"
        elif "objection" in name_lower:
            return "User's objection intensifies or new serious objections arise"
        elif "commitment" in name_lower:
            return "User explicitly declines to proceed or requests to end conversation"
        else:
            return "User shows clear signs of disengagement or resistance"

    def _generate_expected_outcomes(self, node_name: str) -> List[str]:
        """Generate list of possible outcomes based on node name"""
        name_lower = node_name.lower()
        
        base_outcomes = ["positive_progression", "needs_clarification", "resistance_detected"]
        
        if "discovery" in name_lower:
            return base_outcomes + ["information_gathered", "deeper_exploration_needed"]
        elif "value" in name_lower:
            return base_outcomes + ["value_accepted", "objection_raised"]
        elif "objection" in name_lower:
            return base_outcomes + ["objection_resolved", "escalation_needed"]
        elif "commitment" in name_lower:
            return base_outcomes + ["commitment_secured", "further_discussion_needed"]
        else:
            return base_outcomes

    def _generate_transition_triggers(self, node_name: str) -> List[str]:
        """Generate list of transition triggers based on node name"""
        name_lower = node_name.lower()
        
        base_triggers = [
            "explicit_agreement",
            "explicit_disagreement",
            "confusion_expressed",
            "more_information_requested"
        ]
        
        if "discovery" in name_lower:
            return base_triggers + ["need_expressed", "resistance_to_sharing"]
        elif "value" in name_lower:
            return base_triggers + ["benefit_interest", "value_objection"]
        elif "objection" in name_lower:
            return base_triggers + ["satisfaction_expressed", "escalation_requested"]
        elif "commitment" in name_lower:
            return base_triggers + ["ready_to_proceed", "need_more_time"]
        else:
            return base_triggers