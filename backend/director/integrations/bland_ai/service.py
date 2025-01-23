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
            f"{self.base_api_url}/pathways",
            headers=self.headers
        )
        
        if response.status_code == 200:
            return response.json().get("pathways", [])
        else:
            self._handle_error_response(response)

    def get_pathway(self, pathway_id: str) -> Dict:
        """Get details for a specific pathway
        
        Args:
            pathway_id: ID of the pathway to retrieve
            
        Returns:
            Pathway details including nodes and edges
        """
        response = requests.get(
            f"{self.base_api_url}/pathways/{pathway_id}",
            headers=self.headers
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            self._handle_error_response(response)

    def create_pathway(self, name: str, description: str, nodes: Optional[Dict] = None, edges: Optional[Dict] = None) -> Dict:
        """Create a new pathway
        
        Args:
            name: Name of the pathway
            description: Description of the pathway
            nodes: Optional dictionary of nodes (will create default if not provided)
            edges: Optional dictionary of edges (will create default if not provided)
            
        Returns:
            Created pathway data
        """
        try:
            if nodes is None or edges is None:
                # Create default nodes
                nodes = {
                    "start": {
                        "name": "Start",
                        "type": "Default",
                        "isStart": True,
                        "prompt": f"Hello! This is the {name} pathway. How can I help you today?"
                    },
                    "end": {
                        "name": "End Call",
                        "type": "End Call",
                        "prompt": "Thank you for your time. Have a great day!"
                    }
                }
                
                # Create default edge
                edges = {
                    "start_to_end": {
                        "source": "start",
                        "target": "end",
                        "label": "Default Flow"
                    }
                }

            # Create pathway
            url = f"{self.base_api_url}/pathways"
            payload = {
                "name": name,
                "description": description,
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
                
        except Exception as e:
            raise DirectorException(f"Failed to create pathway: {str(e)}")

    def update_pathway(self, pathway_id: str, updates: Dict) -> Dict:
        """Update an existing pathway
        
        Args:
            pathway_id: ID of the pathway to update
            updates: Dictionary containing updates (name, description, nodes, edges)
            
        Returns:
            Updated pathway data
        """
        try:
            # Validate updates
            if "nodes" in updates or "edges" in updates:
                self._validate_pathway_data(
                    updates.get("nodes", {}),
                    updates.get("edges", {})
                )
            
            url = f"{self.base_api_url}/pathways/{pathway_id}"
            
            response = requests.patch(
                url,
                headers=self.headers,
                json=updates
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                self._handle_error_response(response)
                
        except Exception as e:
            raise DirectorException(f"Failed to update pathway: {str(e)}")

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
        """Create a new vector knowledge base with content from sales analysis
        
        Args:
            name: Name of the knowledge base
            description: Description of the knowledge base
            content: Dictionary containing sales techniques, objection handling, etc.
            
        Returns:
            Response from Bland AI API containing knowledge base ID
        """
        try:
            url = f"{self.base_api_url}/knowledgebases"
            
            # Format content into a single text document for vectorization
            text_content = []
            
            # Add summary
            if content.get("summary"):
                text_content.append(f"Summary:\n{content['summary']}\n")
            
            # Add sales techniques
            if content.get("sales_techniques"):
                text_content.append("\nSales Techniques:")
                for technique in content["sales_techniques"]:
                    text_content.append(f"\n- {technique.get('name', '')}")
                    text_content.append(f"  Description: {technique.get('description', '')}")
                    if technique.get('examples'):
                        text_content.append("  Examples:")
                        for example in technique['examples']:
                            text_content.append(f"    * {example}")
                    if technique.get('effectiveness'):
                        text_content.append(f"  Effectiveness: {technique['effectiveness']}")
            
            # Add objection handling
            if content.get("objection_handling"):
                text_content.append("\nObjection Handling:")
                for obj in content["objection_handling"]:
                    text_content.append(f"\n- Objection: {obj.get('objection', '')}")
                    text_content.append(f"  Response: {obj.get('response', '')}")
                    if obj.get('examples'):
                        text_content.append("  Examples:")
                        for example in obj['examples']:
                            text_content.append(f"    * {example}")
            
            # Add training examples
            if content.get("training_pairs"):
                text_content.append("\nTraining Examples:")
                for pair in content["training_pairs"]:
                    text_content.append(f"\nInput: {pair.get('input', '')}")
                    text_content.append(f"Output: {pair.get('output', '')}")
                    if pair.get('context'):
                        text_content.append(f"Context: {pair['context']}")
            
            payload = {
                "name": name,
                "description": description,
                "text": "\n".join(text_content)
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

    def update_knowledge_base(self, kb_id: str, name: str, description: str, content: Dict) -> Dict:
        """Update an existing knowledge base
        
        Args:
            kb_id: ID of the knowledge base to update
            name: New name for the knowledge base
            description: New description for the knowledge base
            content: New content for the knowledge base
            
        Returns:
            Updated knowledge base metadata
        """
        try:
            url = f"{self.base_api_url}/knowledgebases/{kb_id}"
            
            # Format content into text same as create
            text_content = []
            
            if content.get("summary"):
                text_content.append(f"Summary:\n{content['summary']}\n")
            
            if content.get("sales_techniques"):
                text_content.append("\nSales Techniques:")
                for technique in content["sales_techniques"]:
                    text_content.append(f"\n- {technique.get('name', '')}")
                    text_content.append(f"  Description: {technique.get('description', '')}")
                    if technique.get('examples'):
                        text_content.append("  Examples:")
                        for example in technique['examples']:
                            text_content.append(f"    * {example}")
                    if technique.get('effectiveness'):
                        text_content.append(f"  Effectiveness: {technique['effectiveness']}")
            
            if content.get("objection_handling"):
                text_content.append("\nObjection Handling:")
                for obj in content["objection_handling"]:
                    text_content.append(f"\n- Objection: {obj.get('objection', '')}")
                    text_content.append(f"  Response: {obj.get('response', '')}")
                    if obj.get('examples'):
                        text_content.append("  Examples:")
                        for example in obj['examples']:
                            text_content.append(f"    * {example}")
            
            if content.get("training_pairs"):
                text_content.append("\nTraining Examples:")
                for pair in content["training_pairs"]:
                    text_content.append(f"\nInput: {pair.get('input', '')}")
                    text_content.append(f"Output: {pair.get('output', '')}")
                    if pair.get('context'):
                        text_content.append(f"Context: {pair['context']}")
            
            payload = {
                "name": name,
                "description": description,
                "text": "\n".join(text_content)
            }
            
            response = requests.patch(
                url,
                headers=self.headers,
                json=payload
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                self._handle_error_response(response)
                
        except Exception as e:
            raise DirectorException(f"Failed to update knowledge base: {str(e)}")

    def query_knowledge_base(self, kb_id: str, query: str, top_k: int = 5) -> List[Dict]:
        """Query a knowledge base using vector similarity search
        
        Args:
            kb_id: ID of the knowledge base to query
            query: Query text to search for
            top_k: Number of results to return (default 5)
            
        Returns:
            List of matching knowledge base entries
        """
        try:
            url = f"{self.base_api_url}/vectors/query"
            
            payload = {
                "kb_id": kb_id,
                "query": query,
                "top_k": top_k
            }
            
            response = requests.post(
                url,
                headers=self.headers,
                json=payload
            )
            
            if response.status_code == 200:
                return response.json().get("results", [])
            else:
                self._handle_error_response(response)
                
        except Exception as e:
            raise DirectorException(f"Failed to query knowledge base: {str(e)}")

    def list_knowledge_bases(self, include_text: bool = False) -> List[Dict]:
        """List all knowledge bases in the account
        
        Args:
            include_text: Whether to include the full text content (default False)
            
        Returns:
            List of knowledge base metadata
        """
        try:
            url = f"{self.base_api_url}/knowledgebases"
            if include_text:
                url += "?include_text=true"
                
            response = requests.get(
                url,
                headers=self.headers
            )
            
            if response.status_code == 200:
                return response.json().get("vectors", [])
            else:
                self._handle_error_response(response)
                
        except Exception as e:
            raise DirectorException(f"Failed to list knowledge bases: {str(e)}")
            
    def get_knowledge_base(self, kb_id: str, include_text: bool = False) -> Dict:
        """Get details for a specific knowledge base
        
        Args:
            kb_id: ID of the knowledge base
            include_text: Whether to include the full text content (default False)
            
        Returns:
            Knowledge base metadata and optionally content
        """
        try:
            url = f"{self.base_api_url}/knowledgebases/{kb_id}"
            if include_text:
                url += "?include_text=true"
                
            response = requests.get(
                url,
                headers=self.headers
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                self._handle_error_response(response)
                
        except Exception as e:
            raise DirectorException(f"Failed to get knowledge base details: {str(e)}")
            
    def upload_knowledge_base_file(self, file_path: str, name: Optional[str] = None, description: Optional[str] = None) -> Dict:
        """Upload a text file as a new knowledge base
        
        Args:
            file_path: Path to the text file (.pdf, .txt, .doc, or .docx)
            name: Optional name for the knowledge base
            description: Optional description for the knowledge base
            
        Returns:
            Created knowledge base metadata
        """
        try:
            url = f"{self.base_api_url}/knowledgebases/upload"
            
            files = {
                'file': open(file_path, 'rb')
            }
            
            data = {}
            if name:
                data['name'] = name
            if description:
                data['description'] = description
                
            response = requests.post(
                url,
                headers=self.headers,
                files=files,
                data=data
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                self._handle_error_response(response)
                
        except Exception as e:
            raise DirectorException(f"Failed to upload knowledge base file: {str(e)}") 