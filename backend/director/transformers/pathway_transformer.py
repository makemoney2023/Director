from typing import List, Dict, Optional, Tuple, Union
from datetime import datetime
import uuid
import logging
from enum import Enum
from dataclasses import dataclass
import json
from openai import OpenAI  # Updated import

logger = logging.getLogger(__name__)

class NodeType(Enum):
    DEFAULT = "Default"
    END_CALL = "End Call"
    TRANSFER_CALL = "Transfer Call"
    KNOWLEDGE_BASE = "Knowledge Base"
    WEBHOOK = "Webhook"
    GLOBAL = "Global"

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

class PathwayStructureTransformer:
    """Transforms generated outputs into Bland AI pathway structure"""
    
    def __init__(self):
        self.node_width = 320
        self.node_height = 127
        self.horizontal_spacing = 400
        self.vertical_spacing = 200
        self.current_level = 0
        self.nodes_by_level: Dict[int, List[dict]] = {}
        
    def transform_from_outputs(self, outputs: List[Dict]) -> Dict:
        """
        Main transformation method to convert outputs to pathway structure
        
        Args:
            outputs: List of generated outputs from database
            
        Returns:
            Dict containing nodes and edges in Bland AI format
        """
        try:
            logger.info(f"Starting transformation of {len(outputs)} outputs")
            
            # Generate structured pathway using GPT-4
            structured_data = self._generate_structured_pathway(outputs)
            
            # Convert structured data to Bland AI format
            nodes = {}
            edges = {}
            
            # Process nodes first and store their IDs
            node_ids = []
            for idx, node in enumerate(structured_data["nodes"]):
                position = self._calculate_position(idx // 3, idx % 3)  # Arrange nodes in a grid
                
                node_data = {
                    "name": node["name"],
                    "active": False,
                    "prompt": node["prompt"],
                    "condition": node["condition"],
                    "globalPrompt": self._get_global_prompt(),
                    "modelOptions": node["modelOptions"]
                }
                
                node_id = node.get("id") or str(uuid.uuid4())
                node_ids.append(node_id)
                nodes[node_id] = {
                    "id": node_id,
                    "type": node["type"],
                    "data": node_data,
                    "width": self.node_width,
                    "height": self.node_height,
                    "position": position,
                    "dragging": False,
                    "selected": False,
                    "positionAbsolute": position
                }
            
            # Process edges using the stored node IDs
            for edge in structured_data.get("edges", []):
                source_idx = edge.get("source")
                target_idx = edge.get("target")
                
                if isinstance(source_idx, int) and isinstance(target_idx, int):
                    if 0 <= source_idx < len(node_ids) and 0 <= target_idx < len(node_ids):
                        source_id = node_ids[source_idx]
                        target_id = node_ids[target_idx]
                        
                        edge_id = f"reactflow__edge-{source_id}-{target_id}"
                        edges[edge_id] = {
                            "id": edge_id,
                            "source": source_id,
                            "target": target_id,
                            "type": "custom",
                            "animated": True,
                            "data": {
                                "label": edge.get("label", "Continue"),
                                "description": edge.get("description", "Continue with the conversation flow")
                            },
                            "selected": False,
                            "sourceHandle": None,
                            "targetHandle": None
                        }
            
            # Add global nodes
            global_nodes = self._create_global_nodes()
            for node in global_nodes:
                node_id = node["id"]
                nodes[node_id] = node
                
                # Connect global nodes to transfer nodes
                if node["data"].get("isGlobal"):
                    transfer_nodes = [n for n in nodes.values() if n["type"] == NodeType.TRANSFER_CALL.value]
                    for target in transfer_nodes:
                        edge_id = f"reactflow__edge-{node_id}-{target['id']}"
                        edges[edge_id] = {
                            "id": edge_id,
                            "source": node_id,
                            "target": target["id"],
                            "type": "custom",
                            "animated": True,
                            "data": {
                                "label": "Transfer to human",
                                "description": "Transfer the call to a human assistant."
                            },
                            "selected": False,
                            "sourceHandle": None,
                            "targetHandle": None
                        }
            
            # Validate final structure
            self._validate_pathway_structure(list(nodes.values()), list(edges.values()))
            
            logger.info(f"Successfully created pathway with {len(nodes)} nodes and {len(edges)} edges")
            
            return {
                "nodes": nodes,
                "edges": edges
            }
            
        except Exception as e:
            logger.error(f"Failed to transform outputs: {str(e)}")
            raise
            
    def _group_and_analyze_outputs(self, outputs: List[Dict]) -> Dict:
        """Group outputs by type and analyze their relationships"""
        grouped = {
            "voice_prompts": []
        }
        
        for output in outputs:
            content = output.get("content")
            output_id = output.get("id")
            
            if not content:
                logger.warning(f"Skipping output without content: {output}")
                continue
                
            try:
                # Create a new dictionary for the parsed content
                parsed_content = {}
                
                # Handle both JSON and plain text content
                if isinstance(content, str):
                    try:
                        # Try to parse as JSON first
                        parsed_content = json.loads(content)
                    except json.JSONDecodeError:
                        # If not JSON, treat as plain text
                        parsed_content = {
                            "prompt": content,
                            "type": "voice_prompt"
                        }
                else:
                    parsed_content = dict(content)  # Create a copy of the content
                    
                # Add output ID to content
                parsed_content["output_id"] = output_id
                grouped["voice_prompts"].append(parsed_content)
                    
            except Exception as e:
                logger.warning(f"Failed to parse content for output {output_id}: {str(e)}")
                continue
                
        return grouped
        
    def _create_all_nodes(self, grouped_outputs: Dict, prompt_ids: List[str] = None) -> List[Dict]:
        """Create all nodes with proper structure and positioning"""
        nodes = []
        
        # Start with greeting node using first voice prompt if available
        voice_prompts = grouped_outputs["voice_prompts"]
        start_prompt = voice_prompts[0] if voice_prompts else None
        start_node = self._create_start_node(
            prompt_id=start_prompt.get("output_id") if start_prompt else None,
            prompt_text=start_prompt.get("prompt") if start_prompt else None
        )
        nodes.append(start_node)
        self.current_level += 1
        
        # Create nodes for remaining voice prompts
        if len(voice_prompts) > 1:
            prompt_nodes = self._create_prompt_nodes(voice_prompts[1:])
            nodes.extend(prompt_nodes)
        
        return nodes
        
    def _create_start_node(self, prompt_id: str = None, prompt_text: str = None) -> Dict:
        """Create the initial greeting node with full data structure"""
        position = self._calculate_position(0, 0)
        
        node_data = {
            "name": "Start",
            "active": False,
            "prompt": prompt_text or "Introduce yourself and establish the purpose of the call. Ask if they have a moment to talk.",
            "isStart": True,
            "condition": "Condition fails if the user immediately refuses to talk or asks to be removed from the call list.",
            "globalPrompt": self._get_global_prompt(),
            "modelOptions": ModelOptions().to_dict()
        }
        
        if prompt_id:
            node_data["promptId"] = prompt_id
        
        return {
            "id": "1",
            "type": NodeType.DEFAULT.value,
            "data": node_data,
            "width": self.node_width,
            "height": self.node_height,
            "position": position,
            "dragging": False,
            "selected": False,
            "positionAbsolute": position
        }
        
    def _create_prompt_nodes(self, prompts: List[Dict]) -> List[Dict]:
        """Create nodes from voice prompts with full data structure"""
        nodes = []
        
        for idx, prompt in enumerate(prompts):
            position = self._calculate_position(self.current_level, idx)
            
            # Handle string content
            if isinstance(prompt, str):
                prompt_text = prompt
                prompt_data = {"prompt": prompt_text}
            else:
                prompt_text = prompt.get("prompt", "")
                prompt_data = prompt
            
            node_data = {
                "name": self._generate_node_name(prompt_data),
                "active": False,
                "prompt": prompt_text,
                "condition": self._extract_condition(prompt_data),
                "globalPrompt": self._get_global_prompt(),
                "modelOptions": self._get_model_options(prompt_data)
            }
            
            # Add prompt ID if available
            if isinstance(prompt, dict) and prompt.get("output_id"):
                node_data["promptId"] = prompt["output_id"]
            
            # Determine if this is a special node type
            node_type = self._determine_node_type(prompt_data)
            
            # Add transfer number for transfer nodes
            if node_type == NodeType.TRANSFER_CALL:
                node_data["transferNumber"] = self._extract_transfer_number(prompt_data)
            
            node = {
                "id": str(uuid.uuid4()),
                "type": node_type.value,
                "data": node_data,
                "width": self.node_width,
                "height": self.node_height,
                "position": position,
                "dragging": False,
                "selected": False,
                "positionAbsolute": position
            }
            
            nodes.append(node)
            
        self.current_level += 1
        return nodes
        
    def _create_edges(self, nodes: List[Dict]) -> List[Dict]:
        """Create edges between nodes in sequence with proper data structure"""
        edges = []
        
        # Connect nodes in sequence
        for i in range(len(nodes) - 1):
            source_node = nodes[i]
            target_node = nodes[i+1]
            
            edge = {
                "id": f"reactflow__edge-{source_node['id']}-{target_node['id']}",
                "source": source_node["id"],
                "target": target_node["id"],
                "type": "custom",
                "animated": True,
                "data": {
                    "label": self._generate_edge_label(source_node, target_node),
                    "description": self._generate_edge_description(source_node, target_node)
                },
                "selected": False,
                "sourceHandle": None,
                "targetHandle": None
            }
            edges.append(edge)
            
        return edges
        
    def _calculate_position(self, level: int, index: int) -> Dict[str, int]:
        """Calculate node position based on level and index with proper spacing"""
        x = index * (self.horizontal_spacing + self.node_width) + self.horizontal_spacing
        y = level * (self.vertical_spacing + self.node_height) + self.vertical_spacing
        return {
            "x": x,
            "y": y
        }
        
    def _determine_node_type(self, content: Dict) -> NodeType:
        """Determine the appropriate node type based on content"""
        # Handle string content
        if isinstance(content, str):
            content_str = content.lower()
            content_dict = {}
        else:
            content_str = str(content).lower()
            content_dict = content
        
        # Check for global nodes first
        if content_dict.get("isGlobal", False):
            return NodeType.GLOBAL
        
        # Check for transfer nodes
        if "transfer" in content_str or content_dict.get("transferNumber"):
            return NodeType.TRANSFER_CALL
        
        # Check for end nodes
        if "end" in content_str or content_dict.get("isEnd", False):
            return NodeType.END_CALL
        
        # Check for knowledge base nodes
        if "knowledge" in content_str or content_dict.get("kb_id"):
            return NodeType.KNOWLEDGE_BASE
        
        # Check for webhook nodes
        if "webhook" in content_str or content_dict.get("webhook_url"):
            return NodeType.WEBHOOK
        
        return NodeType.DEFAULT
        
    def _is_error_handling(self, content: Dict) -> bool:
        """Determine if content represents error handling"""
        error_keywords = ["error", "exception", "fail", "frustration", "complaint"]
        content_str = str(content).lower()
        return any(keyword in content_str for keyword in error_keywords)
        
    def _generate_greeting_prompt(self) -> str:
        """Generate initial greeting prompt"""
        return "Introduce yourself and establish the purpose of the call. Ask if they have a moment to talk."
        
    def _get_global_prompt(self) -> str:
        """Get global prompt for all nodes"""
        return "Maintain a professional and helpful demeanor throughout the conversation. Be ready to transfer to a human assistant if needed. Listen actively and adapt your responses based on the user's engagement level."
        
    def _generate_node_name(self, content: Union[Dict, str]) -> str:
        """Generate descriptive node name based on content"""
        if isinstance(content, str):
            # Generate name from first few words of string
            words = content.split()[:3]
            return " ".join(words) + "..."
        elif "name" in content:
            return content["name"]
        elif "type" in content:
            return content["type"].title()
        elif "prompt" in content:
            # Generate name from first few words of prompt
            words = content["prompt"].split()[:3]
            return " ".join(words) + "..."
        else:
            return "Conversation Node"
            
    def _extract_prompt(self, content: Dict) -> str:
        """Extract or generate prompt from content"""
        if "prompt" in content:
            return content["prompt"]
        elif "text" in content:
            return content["text"]
        else:
            return "Continue the conversation based on the user's response."
            
    def _extract_condition(self, content: Union[Dict, str]) -> str:
        """Extract or generate condition from content"""
        if isinstance(content, str):
            return "Proceed based on user's response and engagement level."
        elif "condition" in content:
            return content["condition"]
        else:
            return "Proceed based on user's response and engagement level."
            
    def _get_model_options(self, content: Optional[Union[Dict, str]] = None) -> Dict:
        """Get model options, potentially customized based on content"""
        options = ModelOptions()
        if isinstance(content, dict) and "model_options" in content:
            # Update options based on content
            content_options = content["model_options"]
            options.temperature = content_options.get("temperature", options.temperature)
            options.skip_user_response = content_options.get("skip_user_response", options.skip_user_response)
            options.block_interruptions = content_options.get("block_interruptions", options.block_interruptions)
        return options.to_dict()
        
    def _extract_transfer_number(self, content: Union[Dict, str]) -> str:
        """Extract transfer number from content"""
        if isinstance(content, dict) and "transfer_number" in content:
            return content["transfer_number"]
        return "+1234567890"  # Default transfer number
        
    def _generate_error_prompt(self, error: Dict) -> str:
        """Generate prompt for error handling"""
        error_type = error.get("type", "issue")
        return f"I apologize for any {error_type}. Let me help address your concerns or connect you with someone who can assist further."
        
    def _generate_error_condition(self, error: Dict) -> str:
        """Generate condition for error handling"""
        return f"Triggered when user expresses {error.get('type', 'dissatisfaction')} or requests escalation."
        
    def _find_target_nodes(self, source_node: Dict, nodes: List[Dict]) -> List[Dict]:
        """Find appropriate target nodes for edges"""
        # Skip global nodes as targets unless specifically connected
        potential_targets = [
            n for n in nodes 
            if n["id"] != source_node["id"]
            and not n["data"].get("isGlobal", False)
        ]
        
        # Logic to determine valid targets based on node types and positions
        valid_targets = []
        source_level = source_node["position"]["y"] // self.vertical_spacing
        
        for target in potential_targets:
            target_level = target["position"]["y"] // self.vertical_spacing
            
            # Only connect to nodes in the next level or error handling nodes
            if (target_level == source_level + 1 or 
                target["type"] == NodeType.TRANSFER_CALL.value):
                valid_targets.append(target)
                
        return valid_targets
        
    def _generate_edge_label(self, source_node: Dict, target_node: Dict) -> str:
        """Generate appropriate label for edge"""
        if target_node["type"] == NodeType.TRANSFER_CALL.value:
            return "Transfer needed"
        elif target_node["type"] == NodeType.END_CALL.value:
            return "End conversation"
        else:
            return "Continue"
            
    def _generate_edge_description(self, source_node: Dict, target_node: Dict) -> str:
        """Generate detailed description for edge transition"""
        if target_node["type"] == NodeType.TRANSFER_CALL.value:
            return "User needs to be transferred to a human agent"
        elif target_node["type"] == NodeType.END_CALL.value:
            return "Conversation can be concluded"
        else:
            return "Continue with the next step in the conversation flow"
            
    def _validate_pathway_structure(self, nodes: List[Dict], edges: List[Dict]) -> None:
        """Validate the pathway structure meets Bland AI requirements"""
        # Check for required node fields
        required_node_fields = {"id", "type", "data", "position"}
        required_data_fields = {"name", "prompt"}
        
        for node in nodes:
            missing_fields = required_node_fields - set(node.keys())
            if missing_fields:
                raise ValueError(f"Node missing required fields: {missing_fields}")
                
            missing_data = required_data_fields - set(node["data"].keys())
            if missing_data:
                raise ValueError(f"Node data missing required fields: {missing_data}")
                
        # Validate edges
        required_edge_fields = {"id", "source", "target", "type"}
        node_ids = {node["id"] for node in nodes}
        
        for edge in edges:
            missing_fields = required_edge_fields - set(edge.keys())
            if missing_fields:
                raise ValueError(f"Edge missing required fields: {missing_fields}")
                
            # Validate edge connections
            if edge["source"] not in node_ids:
                raise ValueError(f"Edge references non-existent source node: {edge['source']}")
            if edge["target"] not in node_ids:
                raise ValueError(f"Edge references non-existent target node: {edge['target']}")
        
    def _create_global_nodes(self) -> List[Dict]:
        """Create global nodes for error handling and frustration"""
        nodes = []
        
        # Create global frustration handler
        frustration_node = {
            "id": str(uuid.uuid4()),
            "type": NodeType.DEFAULT.value,
            "data": {
                "name": "Global Frustration Handler",
                "active": False,
                "prompt": "Apologize for any frustration caused. Offer to transfer the call to a human assistant who can better address their concerns.",
                "isGlobal": True,
                "globalLabel": "User expresses frustration",
                "globalPrompt": self._get_global_prompt(),
                "modelOptions": ModelOptions().to_dict(),
                "globalDescription": "This node is triggered if at any point the user expresses frustration or explicitly asks to speak to a human."
            },
            "width": self.node_width,
            "height": self.node_height,
            "position": self._calculate_position(self.current_level + 1, 0),
            "dragging": False,
            "selected": False
        }
        nodes.append(frustration_node)
        
        return nodes

    def _generate_node_name_from_prompt(self, prompt_text: str) -> str:
        """Generate a descriptive node name from the prompt text using GPT-4-mini"""
        try:
            client = OpenAI()
            response = client.chat.completions.create(
                model="gpt-4-0125-preview",
                messages=[
                    {"role": "system", "content": "Generate a short, descriptive name (2-4 words) for a conversation node based on its prompt. The name should capture the main intent or action of the prompt."},
                    {"role": "user", "content": f"Prompt: {prompt_text}"}
                ],
                temperature=0.2,
                max_tokens=20
            )
            node_name = response.choices[0].message.content.strip().strip('"')
            logger.info(f"Generated node name: {node_name} for prompt: {prompt_text[:50]}...")
            return node_name
        except Exception as e:
            logger.error(f"Failed to generate node name: {str(e)}")
            return "Conversation Node"

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
                
                if output.get("output_type") == "voice_prompt":
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