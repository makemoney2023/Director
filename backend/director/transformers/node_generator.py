from typing import Dict, List, Optional, Union
import uuid
import logging
import json
from enum import Enum
from dataclasses import dataclass
from openai import OpenAI
import os

logger = logging.getLogger(__name__)

class NodeType(Enum):
    DEFAULT = "Default"
    END_CALL = "End Call"
    TRANSFER_CALL = "Transfer Call"
    KNOWLEDGE_BASE = "Knowledge Base"
    WEBHOOK = "Webhook"
    GLOBAL = "Global"

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

class NodeGenerator:
    """Handles the generation and management of conversation nodes"""

    def __init__(self):
        self.node_width = 320
        self.node_height = 127

    def create_node(self, prompt_text: str, node_type: NodeType = NodeType.DEFAULT, 
                   position: Dict[str, int] = None, is_global: bool = False) -> Dict:
        """
        Creates a new conversation node with all necessary attributes
        """
        try:
            # Generate semantic name for the node
            node_name = self._generate_node_name(prompt_text)

            # Create node data structure
            node_data = {
                "name": node_name,
                "active": False,
                "prompt": prompt_text,
                "intent": self._generate_intent(node_name, prompt_text),
                "success_condition": self._generate_success_condition(node_name),
                "failure_condition": self._generate_failure_condition(node_name),
                "expected_outcomes": self._generate_outcomes(node_name),
                "transition_triggers": self._generate_triggers(node_name),
                "globalPrompt": self._get_global_prompt(),
                "modelOptions": ModelOptions().to_dict()
            }

            if is_global:
                node_data["isGlobal"] = True

            # Create complete node structure
            node = {
                "id": str(uuid.uuid4()),
                "type": node_type.value,
                "data": node_data,
                "width": self.node_width,
                "height": self.node_height,
                "position": position or {"x": 0, "y": 0},
                "dragging": False,
                "selected": False,
                "positionAbsolute": position or {"x": 0, "y": 0}
            }

            return node

        except Exception as e:
            logger.error(f"Error creating node: {str(e)}")
            raise

    def create_start_node(self, prompt_text: Optional[str] = None) -> Dict:
        """Creates the initial start node"""
        default_prompt = "Introduce yourself and establish the purpose of the call. Ask if they have a moment to talk."
        
        node_data = {
            "name": "Start",
            "active": False,
            "prompt": prompt_text or default_prompt,
            "isStart": True,
            "condition": "Condition fails if the user immediately refuses to talk",
            "globalPrompt": self._get_global_prompt(),
            "modelOptions": ModelOptions().to_dict()
        }

        return {
            "id": "start",
            "type": NodeType.DEFAULT.value,
            "data": node_data,
            "width": self.node_width,
            "height": self.node_height,
            "position": {"x": 0, "y": 0},
            "dragging": False,
            "selected": False,
            "positionAbsolute": {"x": 0, "y": 0}
        }

    def create_end_node(self, node_type: str, position: Dict[str, int]) -> Dict:
        """Creates an end node of the specified type"""
        if node_type == "success":
            return self._create_success_end_node(position)
        elif node_type == "rejection":
            return self._create_rejection_end_node(position)
        elif node_type == "transfer":
            return self._create_transfer_end_node(position)
        else:
            raise ValueError(f"Unknown end node type: {node_type}")

    def _create_success_end_node(self, position: Dict[str, int]) -> Dict:
        """Creates a successful completion end node"""
        return self.create_node(
            prompt_text="Thank you for your time. We've successfully completed our conversation.",
            node_type=NodeType.END_CALL,
            position=position
        )

    def _create_rejection_end_node(self, position: Dict[str, int]) -> Dict:
        """Creates a polite rejection end node"""
        return self.create_node(
            prompt_text="I understand this isn't what you're looking for. Thank you for your time.",
            node_type=NodeType.END_CALL,
            position=position
        )

    def _create_transfer_end_node(self, position: Dict[str, int]) -> Dict:
        """Creates a transfer to human end node"""
        node = self.create_node(
            prompt_text="I'll transfer you to a human assistant who can better help with your needs.",
            node_type=NodeType.TRANSFER_CALL,
            position=position
        )
        node["data"]["transferNumber"] = "+1234567890"  # Default transfer number
        return node

    def _generate_node_name(self, prompt_text: str) -> str:
        """Generates a semantic name for a node using GPT-4"""
        try:
            prompt = f"""
            Generate a concise and descriptive name (2-4 words) for this node that reflects:
            1. The primary intent (e.g., Inquiry Handling, Objection Resolution)
            2. The phase of the conversation (e.g., Introduction, Deep Dive)
            3. The expected outcome (e.g., Agreement, Information Gathering)

            Example transformations:
            - "How are you doing today?" -> "Initial Rapport Building"
            - "Let me tell you about our pricing" -> "Value Proposition Introduction"
            - "Would you like to proceed?" -> "Commitment Decision Point"
            
            Prompt to name: {prompt_text}
            Generate only the name, no explanation.
            """
            
            response = self._call_gpt4(prompt)
            name = response.strip().replace('"', '').replace("'", "")
            
            if not name:
                raise ValueError("Empty name generated")
            
            return name

        except Exception as e:
            logger.error(f"Error generating node name: {str(e)}")
            return "Conversation Node"

    def _call_gpt4(self, prompt: str) -> str:
        """Calls GPT-4 with a prompt and returns the response"""
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

    def _get_global_prompt(self) -> str:
        """Returns the global prompt for all nodes"""
        return "Maintain a professional and helpful demeanor throughout the conversation."

    def _generate_intent(self, node_name: str, prompt_text: str) -> str:
        """Generates the primary conversational intent for the node"""
        name_lower = node_name.lower()
        
        if "rapport" in name_lower:
            return "Build initial connection and establish trust with the user"
        elif "discovery" in name_lower:
            return "Understand user needs and gather relevant information"
        elif "value" in name_lower:
            return "Present and explain the value proposition"
        elif "objection" in name_lower:
            return "Address user concerns and provide clarification"
        elif "commitment" in name_lower:
            return "Secure user agreement and determine next steps"
        else:
            return "Progress the conversation effectively"

    def _generate_success_condition(self, node_name: str) -> str:
        """Generates success condition based on node name"""
        name_lower = node_name.lower()
        
        if "discovery" in name_lower:
            return "User provides clear information about their needs"
        elif "value" in name_lower:
            return "User shows interest in the proposed value"
        elif "objection" in name_lower:
            return "User's concerns are successfully addressed"
        elif "commitment" in name_lower:
            return "User agrees to proceed or take next steps"
        else:
            return "User engages positively and conversation progresses"

    def _generate_failure_condition(self, node_name: str) -> str:
        """Generates failure condition based on node name"""
        name_lower = node_name.lower()
        
        if "discovery" in name_lower:
            return "User refuses to share information"
        elif "value" in name_lower:
            return "User explicitly rejects the proposed value"
        elif "objection" in name_lower:
            return "User's objection intensifies"
        elif "commitment" in name_lower:
            return "User declines to proceed"
        else:
            return "User shows clear disengagement"

    def _generate_outcomes(self, node_name: str) -> List[str]:
        """Generates list of possible outcomes based on node name"""
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

    def _generate_triggers(self, node_name: str) -> List[str]:
        """Generates list of transition triggers based on node name"""
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