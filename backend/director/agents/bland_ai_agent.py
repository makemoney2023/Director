"""
BlandAI Agent for managing conversation pathways through chat interface
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
import logging
import json

from director.core.session import Session, MsgStatus, TextContent, OutputMessage, MsgType
from director.agents.base import BaseAgent, AgentResponse, AgentStatus
from director.integrations.bland_ai.handler import BlandAIIntegrationHandler
from director.integrations.bland_ai.transformer import SalesPathwayTransformer
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
        self.kb_tool = KnowledgeBaseTool(self.config)
        self.db = load_db(DBType.SQLITE)
        self.vector_store = SupabaseVectorStore()
        self.collection_id = "c-07af6c2f-73f8-4033-9d77-bbd9b21d3111"
        self.llm = get_default_llm()  # Add LLM initialization
        
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
                        "update_with_kb"
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

    def _get_latest_analysis(self) -> tuple[str, str]:
        """Get the most recent analysis ID and data from Supabase"""
        try:
            # Query latest analysis from generated_outputs
            query = """
                SELECT video_id, content, created_at 
                FROM generated_outputs 
                WHERE output_type = 'analysis'
                ORDER BY created_at DESC 
                LIMIT 1
            """
            result = self.vector_store.execute_query(query)
            if not result:
                raise ValueError("No recent analysis found")
                
            video_id = result[0]['video_id']
            analysis_id = f"analysis_{video_id}"
            return analysis_id, str(result[0]['content'])
            
        except Exception as e:
            logger.error(f"Failed to get latest analysis: {str(e)}")
            raise

    def _get_latest_prompts(self) -> List[str]:
        """Get the most recently stored voice prompts"""
        try:
            # Query latest prompts from bland_ai_prompts
            query = """
                SELECT prompt_id 
                FROM bland_ai_prompts
                ORDER BY created_at DESC 
                LIMIT 10
            """
            result = self.vector_store.execute_query(query)
            if not result:
                raise ValueError("No recent prompts found")
                
            return [r['prompt_id'] for r in result]
            
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
            if command in ["create_kb", "store_prompts"] and "analysis_id" not in kwargs:
                latest_output = self.vector_store.get_latest_generated_output(output_type="analysis")
                if latest_output:
                    kwargs["analysis_id"] = latest_output["id"]
                    
            if command == "update_with_kb" and "prompt_ids" not in kwargs:
                latest_prompts = self.vector_store.list_generated_outputs(output_type="voice_prompt", limit=5)
                if latest_prompts:
                    kwargs["prompt_ids"] = [p["id"] for p in latest_prompts]
                    
            # Handle commands
            if command == "list":
                try:
                    pathways = self.bland_ai_service.list_pathways()
                    pathways_text = self._list_pathways()
                    
                    text_content = TextContent(
                        text=pathways_text,
                        status=MsgStatus.success,
                        status_message="Here are the available pathways",
                        agent_name=self.agent_name,
                        structured_data={
                            "pathways": pathways,
                            "metadata": {
                                "count": len(pathways),
                                "timestamp": str(datetime.now().isoformat())
                            }
                        }
                    )
                    
                    self.output_message.add_content(text_content)
                    self.output_message.push_update()
                    
                    return AgentResponse(
                        status=AgentStatus.SUCCESS,
                        message="Successfully retrieved pathways",
                        content=[text_content.to_dict()],
                        data={
                            "pathways": pathways,
                            "formatted_text": pathways_text
                        }
                    )
                except Exception as e:
                    logger.error(f"Error listing pathways: {str(e)}")
                    return AgentResponse(
                        status=AgentStatus.ERROR,
                        message=f"Error listing pathways: {str(e)}"
                    )
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

    def _get_analysis_data(self, analysis_id: str) -> str:
        """Get analysis data from Supabase"""
        try:
            # Extract video ID from analysis ID - handle both prefixed and unprefixed cases
            video_id = analysis_id
            if video_id.startswith('analysis_'):
                video_id = video_id[len('analysis_'):]  # Remove 'analysis_' prefix if present
            
            logger.info(f"Retrieving analysis data for video ID: {video_id}")
            
            # Get analysis data from Supabase
            analysis_data = self.vector_store.get_generated_output(video_id, self.collection_id, "analysis")
            
            if not analysis_data:
                # List all generated outputs for debugging
                logger.info("Listing all generated outputs for debugging:")
                outputs = self.vector_store.list_generated_outputs(video_id, self.collection_id)
                for output in outputs:
                    logger.info(f"Found output: type={output['output_type']}, created_at={output['created_at']}")
                raise ValueError(f"No analysis data found for video ID {video_id}")
                
            # Clean and validate the text
            analysis_text = str(analysis_data)
            if analysis_text.lower() == 'none' or not analysis_text.strip():
                raise ValueError(f"Empty or invalid analysis text for video ID {video_id}")
                
            return analysis_text
            
        except Exception as e:
            logger.error(f"Failed to get analysis data: {str(e)}")
            raise

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