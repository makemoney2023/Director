"""
BlandAI Agent for managing conversation pathways through chat interface
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
import logging
import json
import requests

from director.core.session import Session, MsgStatus, TextContent, OutputMessage, MsgType
from director.agents.base import BaseAgent, AgentResponse, AgentStatus
from director.integrations.bland_ai.handler import BlandAIIntegrationHandler
from director.integrations.bland_ai.transformer import SalesPathwayTransformer
from director.transformers.pathway_transformer import PathwayStructureTransformer
from director.core.config import Config
from director.db import load_db
from director.constants import DBType
from director.integrations.bland_ai.service import BlandAIService
from director.integrations.bland_ai.tools.knowledge_base import KnowledgeBaseTool
from director.utils.supabase import SupabaseVectorStore
from director.exceptions import DirectorException
from director.llm import get_default_llm
from director.llm.base import LLMResponseStatus

logger = logging.getLogger(__name__)

class BlandAI_Agent(BaseAgent):
    """Agent for managing Bland AI pathways through chat"""
    
    def __init__(self, session: Session, **kwargs):
        self.agent_name = "bland_ai"
        self.description = "Manages Bland AI conversation pathways, including configuration, updates, and statistics"
        self.parameters = self.get_parameters()
        super().__init__(session=session, **kwargs)
        
        self.config = Config()
        self.bland_ai_service = BlandAIService(self.config)
        self.transformer = SalesPathwayTransformer()
        self.pathway_transformer = PathwayStructureTransformer()
        self.kb_tool = KnowledgeBaseTool(self.config)
        self.db = load_db(DBType.SQLITE)
        self.vector_store = SupabaseVectorStore()
        self.collection_id = "c-07af6c2f-73f8-4033-9d77-bbd9b21d3111"
        self.llm = get_default_llm()
        
    @property
    def name(self) -> str:
        return self.agent_name
        
    def get_parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "enum": [
                        "list",
                        "get",
                        "create",
                        "create_empty",
                        "update",
                        "preview",
                        "add_kb",
                        "remove_kb",
                        "create_kb",
                        "store_prompts",
                        "update_with_kb",
                        "analyze_and_create"
                    ],
                    "description": "Command to execute"
                },
                "name": {
                    "type": "string",
                    "description": "Name for the pathway or knowledge base. For example: 'Mark Wilsons Sales Pathway'"
                },
                "description": {
                    "type": "string",
                    "description": "Description for the pathway or knowledge base"
                },
                "analysis_id": {
                    "type": "string",
                    "description": "ID of the analysis to use. If not provided, will use the most recent analysis."
                },
                "pathway_id": {
                    "type": "string",
                    "description": "ID of the pathway to update/get. For example: '749b4302-92be-4dd0-9c07-591929dac8a6'"
                },
                "kb_id": {
                    "type": "string",
                    "description": "ID of the knowledge base to link/unlink"
                },
                "prompt_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of prompt IDs to use in pathway. If not provided, will use the most recent prompts."
                }
            },
            "required": ["command"],
            "description": "Manages Bland AI conversation pathways. Common uses:\n- List pathways: command='list'\n- Save prompts: command='store_prompts' name='Mark Wilsons'\n- Create knowledge base: command='create_kb' name='Sales KB'\n- Update pathway: command='update_with_kb' pathway_id='...'"
        }

    def _get_analysis_data(self, analysis_id: str) -> str:
        """Get analysis data from Supabase"""
        try:
            # Get analysis data from Supabase
            analysis = self.vector_store.get_latest_generated_output(output_type="analysis")
            if not analysis:
                raise ValueError(f"No analysis data found")
                
            # Clean and validate the text
            analysis_text = str(analysis.get("content", ""))
            if analysis_text.lower() == 'none' or not analysis_text.strip():
                raise ValueError("Empty or invalid analysis text")
                
            return analysis_text
            
        except Exception as e:
            logger.error(f"Failed to get analysis data: {str(e)}")
            raise

    def _get_latest_prompts(self) -> List[str]:
        """Get the most recently stored voice prompts"""
        try:
            # Get latest prompts using Supabase
            prompts = self.vector_store.list_generated_outputs(output_type="voice_prompt", limit=10)
            if not prompts:
                raise ValueError("No recent prompts found")
                
            return [p["id"] for p in prompts if p.get("id")]
            
        except Exception as e:
            logger.error(f"Failed to get latest prompts: {str(e)}")
            raise

    def _parse_natural_language(self, text: str) -> tuple[str, dict]:
        """Parse natural language into command and parameters using LLM"""
        prompt = f"""You are a command parser for a Bland AI agent. Convert the following natural language command into a structured command and parameters.

Available commands and their mappings:
- "show pathways" or "list pathways" -> command: "list"
- "create knowledge base" -> command: "create_kb"
- "save prompt to [pathway name]" or "store prompt to [pathway name]" -> command: "store_prompts"
- "update [pathway name]" -> command: "update_with_kb"

Input: {text}

Output format:
{{
    "command": "command_name",
    "parameters": {{
        "param1": "value1",
        ...
    }}
}}

Only return valid JSON, no other text."""

        try:
            response = self.llm.chat_completions(
                messages=[{
                    "role": "system",
                    "content": "You are a command parser that converts natural language into structured commands."
                }, {
                    "role": "user",
                    "content": prompt
                }]
            )
            
            if response.status == LLMResponseStatus.ERROR:
                logger.error(f"LLM error: {response.error}")
                return None, {}
                
            # Parse JSON response
            result = json.loads(response.content)
            command = result.get("command")
            params = result.get("parameters", {})
            
            # Add latest analysis/prompts if needed
            if command in ["create_kb", "store_prompts"]:
                try:
                    analysis_id, _ = self._get_latest_analysis()
                    params["analysis_id"] = analysis_id
                    params["name"] = "Latest Analysis"  # Default name
                except Exception as e:
                    logger.error(f"Failed to get latest analysis: {str(e)}")
                    
            if command in ["store_prompts", "update_with_kb"]:
                try:
                    prompt_ids = self._get_latest_prompts()
                    if prompt_ids:
                        params["prompt_ids"] = prompt_ids
                except Exception as e:
                    logger.error(f"Failed to get latest prompts: {str(e)}")
                    
            # Look up pathway ID if name provided
            if "pathway_name" in params:
                try:
                    pathways = self.bland_ai_service.list_pathways()
                    for p in pathways:
                        if params["pathway_name"].lower() in p.get("name", "").lower():
                            params["pathway_id"] = p.get("id")
                            break
                except Exception as e:
                    logger.error(f"Failed to look up pathway ID: {str(e)}")
                    
            logger.info(f"Parsed natural language command: {command} with params: {params}")
            return command, params
            
        except Exception as e:
            logger.error(f"Error parsing command: {str(e)}")
            return None, {}

    def run(self, **kwargs) -> AgentResponse:
        try:
            command = kwargs.get("command", "")
            text = kwargs.get("text", "")
            
            # Handle natural language commands
            if text and not command:
                command, parsed_kwargs = self._parse_natural_language(text)
                if command:
                    kwargs.update(parsed_kwargs)
                else:
                    return AgentResponse(
                        status=AgentStatus.ERROR,
                        message="Could not parse natural language command"
                    )
            
            if not command:
                return AgentResponse(
                    status=AgentStatus.SUCCESS,
                    message=self.get_help()
                )
                
            # Get latest analysis and prompts if not provided
            if command in ["create_kb", "store_prompts", "analyze_and_create"] and "analysis_id" not in kwargs:
                latest_output = self.vector_store.get_latest_generated_output(output_type="analysis")
                if latest_output:
                    kwargs["analysis_id"] = latest_output["id"]
                    
            if command == "update_with_kb" and "prompt_ids" not in kwargs:
                latest_prompts = self.vector_store.list_generated_outputs(output_type="voice_prompt", limit=5)
                if latest_prompts:
                    kwargs["prompt_ids"] = [p["id"] for p in latest_prompts]
                    
            # Handle commands
            if command == "analyze_and_create":
                result = self._analyze_and_create_pathway(
                    name=kwargs.get("name", "Generated Pathway"),
                    description=kwargs.get("description", "Automatically generated from analysis")
                )
            elif command == "list":
                result = self._list_pathways()
            elif command == "get":
                result = self._get_pathway(kwargs.get("pathway_id"))
            elif command == "create_empty":
                result = self._create_empty_pathway(kwargs.get("name"), kwargs.get("description"))
            elif command == "create":
                result = self._create_pathway(kwargs.get("name"), kwargs.get("description"), kwargs.get("analysis_id"))
            elif command == "update":
                result = self._update_pathway(kwargs.get("pathway_id"), kwargs.get("name"), kwargs.get("description"))
            elif command == "preview":
                result = self._preview_pathway(kwargs.get("analysis_id"))
            elif command == "add_kb":
                result = self._add_knowledge_base(kwargs.get("pathway_id"), kwargs.get("kb_id"))
            elif command == "remove_kb":
                result = self._remove_knowledge_base(kwargs.get("pathway_id"), kwargs.get("kb_id"))
            elif command == "create_kb":
                result = self._create_knowledge_base(kwargs.get("name"), kwargs.get("description"), kwargs.get("analysis_id"))
            elif command == "store_prompts":
                result = self._store_prompts(kwargs.get("name"), kwargs.get("analysis_id"))
            elif command == "update_with_kb":
                result = self._update_pathway_with_kb(kwargs.get("pathway_id"), kwargs.get("prompt_ids"))
            else:
                return AgentResponse(
                    status=AgentStatus.ERROR,
                    message=f"Unknown command: {command}"
                )
                
            return AgentResponse(
                status=AgentStatus.SUCCESS,
                message=result
            )
            
        except Exception as e:
            logger.error(f"Error in BlandAI_Agent.run: {str(e)}")
            return AgentResponse(
                status=AgentStatus.ERROR,
                message=f"Error executing command: {str(e)}"
            )

    def _list_pathways(self) -> str:
        try:
            pathways = self.bland_ai_service.list_pathways()
            if not pathways:
                return "No pathways found."
                
            pathway_list = []
            for p in pathways:
                name = p.get('name', 'Unnamed')
                pathway_id = p.get('id', 'No ID')
                description = p.get('description', 'No description')
                
                pathway_list.append(
                    f"- {name} (ID: {pathway_id})\n"
                    f"  Description: {description}"
                )
            
            result = "Available pathways:\n\n" + "\n\n".join(pathway_list)
            logger.info(f"Found {len(pathways)} pathways: {[p.get('name') for p in pathways]}")
            return result
        except Exception as e:
            logger.error(f"Failed to list pathways: {str(e)}")
            return f"Failed to list pathways: {str(e)}"
            
    def _get_pathway(self, pathway_id: str) -> str:
        if not pathway_id:
            return "Pathway ID is required"
            
        try:
            pathway = self.bland_ai_service.get_pathway(pathway_id)
            kbs = self.kb_tool.get_pathway_knowledge_bases(pathway_id)
            
            details = [
                f"Name: {pathway.get('name')}",
                f"Description: {pathway.get('description')}",
                f"ID: {pathway.get('id')}",
                f"\nKnowledge Bases ({len(kbs)}):"
            ]
            
            for kb in kbs:
                details.append(f"- {kb.get('name')} (ID: {kb.get('kb_id')})")
                
            details.append("\nNodes:")
            for node_id, node in pathway.get('nodes', {}).items():
                details.append(
                    f"- {node.get('name')} ({node_id})"
                    f"\n  Type: {node.get('type')}"
                    f"\n  Tools: {', '.join(node.get('tools', []))}"
                )
            
            return "\n".join(details)
        except Exception as e:
            return f"Failed to get pathway: {str(e)}"
            
    def _create_empty_pathway(self, name: str, description: str) -> str:
        if not name or not description:
            return "Name and description are required"
            
        try:
            result = self.bland_ai_service.create_pathway(
                name=name,
                description=description
            )
            return (
                f"Created new pathway:\n"
                f"Name: {name}\n"
                f"Description: {description}\n"
                f"ID: {result.get('id')}"
            )
        except Exception as e:
            return f"Failed to create pathway: {str(e)}"
            
    def _create_pathway(self, name: str, description: str, analysis_id: str) -> str:
        if not name or not description or not analysis_id:
            return "Name, description, and analysis_id are required"
            
        try:
            # Get analysis data
            analysis_data = self._get_analysis_data(analysis_id)
            if not analysis_data:
                return f"Analysis data not found for ID {analysis_id}"
            
            # Create knowledge base
            kb_name = f"Sales Analysis KB - {name}"
            kb_result = self.kb_tool.create_from_analysis(
                analysis_data=analysis_data,
                name=kb_name,
                analysis_id=analysis_id,
                video_id=analysis_id.split('_')[1]
            )
            
            # Create pathway with nodes using KB
            nodes = self.transformer.create_nodes_from_analysis(
                analysis_data=analysis_data,
                kb_id=kb_result.get("vector_id")
            )
            edges = self.transformer.create_edges(nodes)
            
            # Create pathway
            pathway_result = self.bland_ai_service.create_pathway(
                name=name,
                description=description,
                nodes=nodes,
                edges=edges
            )
            
            # Link KB to pathway
            self.kb_tool.link_to_pathway(
                kb_id=kb_result.get("vector_id"),
                pathway_id=pathway_result.get("id")
            )
            
            return (
                f"Created new pathway with knowledge base:\n"
                f"Name: {name}\n"
                f"Description: {description}\n"
                f"ID: {pathway_result.get('id')}\n"
                f"Knowledge Base ID: {kb_result.get('vector_id')}\n"
                f"Nodes: {len(nodes)}\n"
                f"Edges: {len(edges)}"
            )
        except Exception as e:
            return f"Failed to create pathway: {str(e)}"
            
    def _update_pathway(self, pathway_id: str, name: str = None, description: str = None) -> str:
        if not pathway_id:
            return "Pathway ID is required"
            
        try:
            # Get current pathway
            current = self.bland_ai_service.get_pathway(pathway_id)
            
            # Build updates
            updates = {}
            if name:
                updates["name"] = name
            if description:
                updates["description"] = description
                
            # Update pathway
            result = self.bland_ai_service.update_pathway(
                pathway_id=pathway_id,
                updates=updates
            )
            
            return f"Updated pathway {pathway_id}"
        except Exception as e:
            return f"Failed to update pathway: {str(e)}"
            
    def _preview_pathway(self, analysis_id: str) -> str:
        if not analysis_id:
            return "Analysis ID is required"
            
        try:
            # Get analysis data
            analysis_data = self._get_analysis_data(analysis_id)
            if not analysis_data:
                return f"Analysis data not found for ID {analysis_id}"
            
            # Create nodes and edges
            nodes = self.transformer.create_nodes_from_analysis(
                analysis_data=analysis_data,
                kb_id="preview"
            )
            edges = self.transformer.create_edges(nodes)
            
            # Format preview
            preview = [
                "Pathway Preview:",
                f"Nodes: {len(nodes)}",
                f"Edges: {len(edges)}",
                "\nNodes:"
            ]
            
            for node_id, node in nodes.items():
                preview.append(
                    f"- {node.get('name')} ({node_id})"
                    f"\n  Type: {node.get('type')}"
                    f"\n  Tools: {', '.join(node.get('tools', []))}"
                )
                
            return "\n".join(preview)
        except Exception as e:
            return f"Failed to preview pathway: {str(e)}"
            
    def _add_knowledge_base(self, pathway_id: str, kb_id: str) -> str:
        if not pathway_id or not kb_id:
            return "Pathway ID and KB ID are required"
            
        try:
            # Link KB to pathway
            self.kb_tool.link_to_pathway(kb_id=kb_id, pathway_id=pathway_id)
            
            # Get pathway and update nodes to use KB
            pathway = self.bland_ai_service.get_pathway(pathway_id)
            nodes = pathway.get("nodes", {})
            
            # Add KB to tools for each node
            for node_id, node in nodes.items():
                tools = node.get("tools", [])
                if kb_id not in tools:
                    tools.append(kb_id)
                    node["tools"] = tools
            
            # Update pathway
            result = self.bland_ai_service.update_pathway(
                pathway_id=pathway_id,
                updates={"nodes": nodes}
            )
            
            return f"Added knowledge base {kb_id} to pathway {pathway_id}"
        except Exception as e:
            return f"Failed to add knowledge base: {str(e)}"
            
    def _remove_knowledge_base(self, pathway_id: str, kb_id: str) -> str:
        if not pathway_id or not kb_id:
            return "Pathway ID and KB ID are required"
            
        try:
            # Get pathway
            pathway = self.bland_ai_service.get_pathway(pathway_id)
            nodes = pathway.get("nodes", {})
            
            # Remove KB from tools for each node
            for node_id, node in nodes.items():
                tools = node.get("tools", [])
                if kb_id in tools:
                    tools.remove(kb_id)
                    node["tools"] = tools
            
            # Update pathway
            result = self.bland_ai_service.update_pathway(
                pathway_id=pathway_id,
                updates={"nodes": nodes}
            )
            
            # Remove KB link
            query = """
                DELETE FROM pathway_knowledge_bases
                WHERE pathway_id = ? AND kb_id = ?
            """
            self.db.execute(query, (pathway_id, kb_id))
            
            return f"Removed knowledge base {kb_id} from pathway {pathway_id}"
        except Exception as e:
            return f"Failed to remove knowledge base: {str(e)}"
            
    def _create_knowledge_base(self, name: str, description: str, analysis_id: str) -> str:
        if not name or not description or not analysis_id:
            return "Name, description, and analysis_id are required"
            
        try:
            # Get analysis data
            analysis_data = self._get_analysis_data(analysis_id)
            if not analysis_data:
                return f"Analysis data not found for ID {analysis_id}"
            
            # Create knowledge base
            kb_name = f"Sales Analysis KB - {name}"
            kb_result = self.kb_tool.create_from_analysis(
                analysis_data=analysis_data,
                name=kb_name,
                analysis_id=analysis_id,
                video_id=analysis_id.split('_')[1]
            )
            
            return (
                f"Created new knowledge base:\n"
                f"Name: {name}\n"
                f"Description: {description}\n"
                f"ID: {kb_result.get('vector_id')}"
            )
        except Exception as e:
            return f"Failed to create knowledge base: {str(e)}"
            
    def _store_prompts(self, name: str, analysis_id: str) -> str:
        if not name or not analysis_id:
            return "Name and analysis_id are required"
            
        try:
            # Get analysis data
            analysis_data = self._get_analysis_data(analysis_id)
            if not analysis_data:
                return f"Analysis data not found for ID {analysis_id}"
            
            # Store voice prompts
            prompts = self.bland_ai_service.store_prompts(
                name=name,
                analysis_data=analysis_data
            )
            
            return f"Stored {len(prompts)} voice prompts"
        except Exception as e:
            return f"Failed to store voice prompts: {str(e)}"
            
    def _update_pathway_with_kb(self, pathway_id: str, prompt_ids: List[str]) -> str:
        if not pathway_id or not prompt_ids:
            return "Pathway ID and prompt_ids are required"
            
        try:
            # Get pathway
            pathway = self.bland_ai_service.get_pathway(pathway_id)
            
            # Update pathway with existing KB and prompts
            result = self.bland_ai_service.update_pathway_with_kb(
                pathway_id=pathway_id,
                prompt_ids=prompt_ids
            )
            
            return f"Updated pathway {pathway_id} with prompts"
        except Exception as e:
            return f"Failed to update pathway with prompts: {str(e)}"

    def _analyze_and_create_pathway(self, name: str, description: str) -> str:
        """
        Create a pathway structure from voice prompts in generated outputs
        """
        try:
            logger.info("Starting pathway creation from voice prompts")
            
            # Get all voice prompts directly
            query = self.vector_store.supabase.from_('generated_outputs')\
                .select('*')\
                .eq('output_type', 'voice_prompt')\
                .order('created_at', desc=True)\
                .limit(50)
                
            result = query.execute()
            outputs = result.data
            
            if not outputs:
                logger.error("No voice prompts found in the database")
                raise ValueError("No voice prompts found in the database")
                
            logger.info(f"Found {len(outputs)} voice prompts")
            
            # Transform voice prompts into pathway structure
            pathway_structure = self.pathway_transformer.transform_from_outputs(outputs)
            
            # Convert nodes and edges to lists if they're dictionaries
            nodes = list(pathway_structure["nodes"].values()) if isinstance(pathway_structure["nodes"], dict) else pathway_structure["nodes"]
            edges = list(pathway_structure["edges"].values()) if isinstance(pathway_structure["edges"], dict) else pathway_structure["edges"]
            
            # Ensure each node has required fields
            for node in nodes:
                if "data" not in node:
                    node["data"] = {}
                if "name" not in node["data"]:
                    node["data"]["name"] = "Default Node"
                if "type" not in node:
                    node["type"] = "Default"
                
            # Ensure each edge has required fields
            for edge in edges:
                if "data" not in edge:
                    edge["data"] = {}
                if "name" not in edge["data"]:
                    edge["data"]["name"] = "Default Edge"
            
            # Step 1: Create empty pathway first
            pathway = self.bland_ai_service.create_pathway(
                name=name,
                description=description
            )
            
            pathway_id = pathway.get('pathway_id')
            if not pathway_id:
                raise ValueError(f"No pathway_id in create response: {pathway}")
                
            # Step 2: Update pathway with nodes and edges
            update_url = f"{self.bland_ai_service.base_api_url}/pathway/{pathway_id}"
            update_payload = {
                "name": name,
                "description": description,
                "nodes": nodes,
                "edges": edges
            }
            
            logger.info(f"Updating pathway {pathway_id} with structure")
            logger.info(f"Update payload nodes: {json.dumps(nodes[:2], indent=2)}")  # Log first 2 nodes as example
            logger.info(f"Update payload edges: {json.dumps(edges[:2], indent=2)}")  # Log first 2 edges as example
            
            update_response = requests.post(
                update_url,
                headers=self.bland_ai_service.headers,
                json=update_payload
            )
            
            if not update_response.ok:
                logger.error(f"Update failed with status {update_response.status_code}: {update_response.text}")
                update_response.raise_for_status()
            
            logger.info(f"Bland AI update pathway response: {update_response.text}")
            
            # Store mapping between pathway and outputs
            try:
                self._store_pathway_output_mapping(pathway_id, outputs)
            except Exception as e:
                logger.error(f"Failed to store pathway output mapping: {str(e)}")
                # Don't raise - this is not critical to pathway creation
                
            # Return formatted string response
            return (
                f"Successfully created pathway:\n"
                f"Name: {name}\n"
                f"Description: {description}\n"
                f"Pathway ID: {pathway_id}\n"
                f"Nodes: {len(nodes)}\n"
                f"Edges: {len(edges)}"
            )
            
        except Exception as e:
            logger.error(f"Failed to analyze and create pathway: {str(e)}")
            raise
            
    def _store_pathway_output_mapping(self, pathway_id: str, outputs: List[Dict]):
        """Store mapping between pathway and the outputs used to create it"""
        try:
            # Extract output IDs
            output_ids = []
            for output in outputs:
                output_id = output.get("id")
                if output_id:
                    # Remove any prefix if present
                    if "_" in output_id:
                        output_id = output_id.split("_")[-1]
                    output_ids.append(output_id)
            
            if not output_ids:
                logger.warning("No valid output IDs found for mapping")
                return
                
            # Store mapping in database
            self.vector_store.store_pathway_output_mapping(
                pathway_id=pathway_id,
                output_ids=output_ids
            )
            
            logger.info(f"Stored mapping between pathway {pathway_id} and {len(output_ids)} outputs")
            
        except Exception as e:
            logger.error(f"Failed to store pathway output mapping: {str(e)}")
            # Don't raise - this is not critical to pathway creation
            pass