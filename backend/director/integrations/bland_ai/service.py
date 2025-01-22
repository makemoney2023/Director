"""
Bland AI Integration Service
Handles all interactions with the Bland AI API for pathway management.
"""

import os
import json
import logging
from typing import Dict, List, Optional, Union
import requests
from datetime import datetime

from director.core.config import Config
from director.utils.exceptions import DirectorException

logger = logging.getLogger(__name__)

class BlandAIService:
    """Service class for interacting with Bland AI API"""
    
    def __init__(self, config: Config):
        """Initialize the Bland AI service
        
        Args:
            config: Application configuration
            
        Raises:
            DirectorException: If API key is not configured
        """
        self.config = config
        self.base_url = "https://api.bland.ai"
        self.version = "v1"
        
        if not config.bland_ai_api_key:
            raise DirectorException("Bland AI API key not configured. Please set BLAND_AI_API_KEY environment variable.")
            
        self.headers = {
            "authorization": config.bland_ai_api_key,
            "Content-Type": "application/json"
        }
        
    @property
    def base_api_url(self) -> str:
        """Get the base API URL with version"""
        return f"{self.base_url}/{self.version}"
        
    def _handle_error_response(self, response: requests.Response) -> None:
        """Handle error responses from the Bland AI API."""
        try:
            error_data = response.json()
            error_message = error_data.get('error', str(response.text))
        except:
            error_message = response.text
            
        raise DirectorException(
            f"Bland AI API error (status {response.status_code}): {error_message}"
        )
        
    def list_pathways(self) -> List[Dict]:
        """Get all available pathways"""
        response = requests.get(
            f"{self.base_api_url}/pathway",
            headers=self.headers
        )
        
        if response.status_code == 200:
            data = response.json()
            # Handle both list and dict responses
            if isinstance(data, dict):
                return data.get("pathways", [])
            elif isinstance(data, list):
                return data
            else:
                return []
        else:
            self._handle_error_response(response)

    def create_pathway(self, name: str, description: str) -> Dict:
        """Create a new pathway with default start and end nodes"""
        try:
            # Create default nodes
            start_node = {
                "id": "start",
                "type": "Default",
                "data": {
                    "name": "Start",
                    "text": f"Hello! This is the {name} pathway. How can I help you today?",
                    "isStart": True
                }
            }
            
            end_node = {
                "id": "end",
                "type": "End Call",
                "data": {
                    "name": "End Call",
                    "text": "Thank you for your time. Have a great day!"
                }
            }
            
            # Create default edge
            default_edge = {
                "id": "start_to_end",
                "source": "start",
                "target": "end",
                "data": {
                    "name": "Default Flow"
                }
            }

            # Store the greeting prompt
            greeting_prompt = self.store_prompt(start_node["data"]["text"])
            if greeting_prompt and "id" in greeting_prompt:
                start_node["data"]["prompt_id"] = greeting_prompt["id"]
                del start_node["data"]["text"]

            # Store the closing prompt
            closing_prompt = self.store_prompt(end_node["data"]["text"])
            if closing_prompt and "id" in closing_prompt:
                end_node["data"]["prompt_id"] = closing_prompt["id"]
                del end_node["data"]["text"]

            # Create pathway with default structure
            url = f"{self.base_api_url}/pathway/create"
            payload = {
                "name": name,
                "description": description,
                "nodes": [start_node, end_node],
                "edges": [default_edge]
            }
            
            response = requests.post(url, headers=self.headers, json=payload)
            
            if response.status_code == 200:
                return response.json()
            else:
                self._handle_error_response(response)
                
        except Exception as e:
            raise DirectorException(f"Failed to create pathway: {str(e)}")

    def update_pathway(self, pathway_id: str, nodes: Dict, edges: Dict) -> Dict:
        """Update an existing pathway with new nodes and edges"""
        # First store voice prompts for each node
        for node_id, node in nodes.items():
            if node.get("text"):
                try:
                    prompt_response = self.store_prompt(
                        prompt=node["text"],
                        name=f"{node['name']} - {pathway_id}"
                    )
                    # Update node with stored prompt reference
                    node["prompt_id"] = prompt_response.get("id")
                    # Remove the text field as we'll use the prompt_id
                    del node["text"]
                except Exception as e:
                    logger.warning(f"Failed to store prompt for node {node_id}: {str(e)}")
        
        url = f"{self.base_api_url}/pathway/{pathway_id}"
        payload = {
            "nodes": nodes,
            "edges": edges
        }
        
        response = requests.post(
            url,
            headers=self.headers,
            json=payload
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            self._handle_error_response(response)

    def _validate_pathway_data(self, nodes: Dict, edges: Dict) -> bool:
        """Validate pathway data before sending to API"""
        # Validate nodes
        for node_id, node in nodes.items():
            if not isinstance(node, dict):
                raise ValueError(f"Invalid node format for {node_id}")
            if "name" not in node:
                raise ValueError(f"Missing name for node {node_id}")
            if "type" not in node:
                raise ValueError(f"Missing type for node {node_id}")
                
        # Validate edges
        for edge_id, edge in edges.items():
            if not isinstance(edge, dict):
                raise ValueError(f"Invalid edge format for {edge_id}")
            if "source" not in edge or "target" not in edge:
                raise ValueError(f"Missing source or target for edge {edge_id}")
            if edge["source"] not in nodes or edge["target"] not in nodes:
                raise ValueError(f"Invalid source or target node in edge {edge_id}")
                
        return True 

    def store_prompt(self, prompt: str, name: Optional[str] = None) -> Dict:
        """
        Store a prompt for future use using the /v1/prompts endpoint
        Args:
            prompt: The prompt text to store
            name: Optional name for the prompt
        Returns:
            Response from Bland AI API
        """
        url = f"{self.base_api_url}/prompts"
        
        payload = {
            "prompt": prompt
        }
        if name:
            payload["name"] = name
            
        response = requests.post(
            url,
            headers=self.headers,
            json=payload
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            self._handle_error_response(response) 

    def create_knowledge_base(self, name: str, description: str, content: Dict) -> Dict:
        """Create a new knowledge base with content from sales analysis
        
        Args:
            name: Name of the knowledge base
            description: Description of the knowledge base
            content: Dictionary containing sales techniques, objection handling, etc.
            
        Returns:
            Response from Bland AI API containing knowledge base ID
        """
        try:
            url = f"{self.base_api_url}/knowledge"
            
            # Format content for knowledge base
            formatted_content = {
                "sales_techniques": [
                    {
                        "title": technique.get("name", ""),
                        "description": technique.get("description", ""),
                        "examples": technique.get("examples", []),
                        "effectiveness": technique.get("effectiveness", "")
                    }
                    for technique in content.get("sales_techniques", [])
                ],
                "objection_handling": [
                    {
                        "objection": obj.get("objection", ""),
                        "response": obj.get("response", ""),
                        "examples": obj.get("examples", [])
                    }
                    for obj in content.get("objection_handling", [])
                ],
                "training_examples": content.get("training_pairs", []),
                "summary": content.get("summary", "")
            }
            
            payload = {
                "name": name,
                "description": description,
                "content": formatted_content,
                "type": "sales_analysis"
            }
            
            response = requests.post(
                url,
                headers=self.headers,
                json=payload
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                self._handle_error_response(response)
                
        except Exception as e:
            raise DirectorException(f"Failed to create knowledge base: {str(e)}") 