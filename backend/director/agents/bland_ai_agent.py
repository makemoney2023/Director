"""
BlandAI Agent for managing conversation pathways through chat interface
"""

from typing import Dict, Any, Optional, List
from datetime import datetime
import logging

from director.core.session import Session, MsgStatus, TextContent, OutputMessage, MsgType
from director.agents.base import BaseAgent, AgentResponse, AgentStatus
from director.integrations.bland_ai.handler import BlandAIIntegrationHandler
from director.integrations.bland_ai.transformer import SalesPathwayTransformer
from director.core.config import Config
from director.db import load_db
from director.constants import DBType
from director.integrations.bland_ai.service import BlandAIService
from director.integrations.bland_ai.tools.knowledge_base import KnowledgeBaseTool

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
                        "remove_kb"
                    ],
                    "description": "Command to execute"
                },
                "name": {
                    "type": "string",
                    "description": "Name for the pathway"
                },
                "description": {
                    "type": "string",
                    "description": "Description for the pathway"
                },
                "analysis_id": {
                    "type": "string",
                    "description": "ID of the analysis to use for pathway creation/update"
                },
                "pathway_id": {
                    "type": "string",
                    "description": "ID of the pathway to update/get"
                },
                "kb_id": {
                    "type": "string",
                    "description": "ID of the knowledge base to link/unlink"
                }
            },
            "required": ["command"],
            "description": "Manages Bland AI conversation pathways"
        }

    def run(self, command: str, **kwargs) -> AgentResponse:
        """Run the Bland AI agent"""
        logger.info(f"BlandAI_Agent received command: {command}")
        
        # Create initial text content for output
        text_content = TextContent(
            agent_name=self.agent_name,
            status=MsgStatus.progress,
            status_message="Processing command...",
            text="Processing your request..."
        )
        self.output_message.content = [text_content]
        self.output_message.status = MsgStatus.progress
        logger.info("Publishing initial progress message")
        self.output_message.publish()
        
        try:
            # If no command or just whitespace or just @bland_ai, return help message
            if not command or command.isspace() or command.strip() == "@bland_ai":
                logger.info("Sending help message")
                help_text = """Welcome to the Bland AI Agent! Here are the available commands:

- create_empty name="Name" description="Description": Create a new empty pathway
- create name="Name" description="Description" analysis_id="ID": Create pathway from analysis
- update pathway_id="ID" [name="Name"] [description="Description"]: Update pathway
- get pathway_id="ID": Get pathway details
- list: List all available pathways
- add_kb pathway_id="ID" kb_id="ID": Add knowledge base to pathway
- remove_kb pathway_id="ID" kb_id="ID": Remove knowledge base from pathway

Example: @bland_ai list"""

                text_content.status = MsgStatus.success
                text_content.status_message = "Help Information"
                text_content.text = help_text
                
                self.output_message.content = [text_content]
                self.output_message.status = MsgStatus.success
                logger.info("Publishing help message")
                self.output_message.publish()
                
                return AgentResponse(
                    status=AgentStatus.SUCCESS,
                    message="Help information provided"
                )

            # Get parameters from kwargs
            name = kwargs.get('name')
            description = kwargs.get('description')
            analysis_id = kwargs.get('analysis_id')
            pathway_id = kwargs.get('pathway_id')
            kb_id = kwargs.get('kb_id')
            
            if command == "list":
                try:
                    pathways = self.bland_ai_service.list_pathways()
                    
                    if not pathways:
                        text_content.text = "No pathways found."
                    else:
                        pathway_list = []
                        for p in pathways:
                            kbs = self.kb_tool.get_pathway_knowledge_bases(p.get("id"))
                            kb_count = len(kbs)
                            pathway_list.append(
                                f"- {p.get('name')} (ID: {p.get('id')})"
                                f"\n  Description: {p.get('description')}"
                                f"\n  Knowledge Bases: {kb_count}"
                            )
                        
                        text_content.text = "Available pathways:\n\n" + "\n\n".join(pathway_list)
                    
                    text_content.status = MsgStatus.success
                    text_content.status_message = "Retrieved pathways"
                    self.output_message.publish()
                    
                    return AgentResponse(
                        status=AgentStatus.SUCCESS,
                        message="Retrieved pathways successfully",
                        data=pathways
                    )
                    
                except Exception as e:
                    text_content.status = MsgStatus.error
                    text_content.status_message = f"Failed to list pathways: {str(e)}"
                    self.output_message.publish()
                    return AgentResponse(
                        status=AgentStatus.ERROR,
                        message=f"Failed to list pathways: {str(e)}"
                    )
                    
            elif command == "get":
                if not pathway_id:
                    text_content.status = MsgStatus.error
                    text_content.status_message = "Pathway ID is required"
                    self.output_message.publish()
                    return AgentResponse(
                        status=AgentStatus.ERROR,
                        message="Pathway ID is required"
                    )
                    
                try:
                    pathway = self.bland_ai_service.get_pathway(pathway_id)
                    kbs = self.kb_tool.get_pathway_knowledge_bases(pathway_id)
                    
                    # Format pathway details
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
                    
                    text_content.text = "\n".join(details)
                    text_content.status = MsgStatus.success
                    text_content.status_message = "Retrieved pathway details"
                    self.output_message.publish()
                    
                    return AgentResponse(
                        status=AgentStatus.SUCCESS,
                        message="Retrieved pathway details successfully",
                        data=pathway
                    )
                    
                except Exception as e:
                    text_content.status = MsgStatus.error
                    text_content.status_message = f"Failed to get pathway: {str(e)}"
                    self.output_message.publish()
                    return AgentResponse(
                        status=AgentStatus.ERROR,
                        message=f"Failed to get pathway: {str(e)}"
                    )
            
            elif command == "create_empty":
                if not name or not description:
                    text_content.status = MsgStatus.error
                    text_content.status_message = "Name and description are required"
                    self.output_message.publish()
                    return AgentResponse(
                        status=AgentStatus.ERROR,
                        message="Name and description are required"
                    )
                    
                try:
                    result = self.bland_ai_service.create_pathway(
                        name=name,
                        description=description
                    )
                    text_content.status = MsgStatus.success
                    text_content.status_message = f"Created pathway '{name}' successfully"
                    text_content.text = (
                        f"Created new pathway:\n"
                        f"Name: {name}\n"
                        f"Description: {description}\n"
                        f"ID: {result.get('id')}"
                    )
                    self.output_message.publish()
                    return AgentResponse(
                        status=AgentStatus.SUCCESS,
                        message=f"Created pathway '{name}' successfully",
                        data=result
                    )
                except Exception as e:
                    text_content.status = MsgStatus.error
                    text_content.status_message = f"Failed to create pathway: {str(e)}"
                    self.output_message.publish()
                    return AgentResponse(
                        status=AgentStatus.ERROR,
                        message=f"Failed to create pathway: {str(e)}"
                    )
                    
            elif command == "create":
                if not name or not description or not analysis_id:
                    text_content.status = MsgStatus.error
                    text_content.status_message = "Name, description, and analysis_id are required"
                    self.output_message.publish()
                    return AgentResponse(
                        status=AgentStatus.ERROR,
                        message="Name, description, and analysis_id are required"
                    )
                    
                try:
                    # Get analysis data
                    analysis_data = self._get_analysis_data(analysis_id)
                    if not analysis_data:
                        text_content.status = MsgStatus.error
                        text_content.status_message = f"Analysis data not found for ID {analysis_id}"
                        self.output_message.publish()
                        return AgentResponse(
                            status=AgentStatus.ERROR,
                            message=f"Analysis data not found for ID {analysis_id}"
                        )
                    
                    # Create knowledge base
                    kb_name = f"Sales Analysis KB - {name}"
                    kb_result = self.kb_tool.create_from_analysis(
                        analysis_data=analysis_data,
                        name=kb_name
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
                    
                    text_content.status = MsgStatus.success
                    text_content.status_message = f"Created pathway '{name}' with knowledge base"
                    text_content.text = (
                        f"Created new pathway with knowledge base:\n"
                        f"Name: {name}\n"
                        f"Description: {description}\n"
                        f"ID: {pathway_result.get('id')}\n"
                        f"Knowledge Base ID: {kb_result.get('vector_id')}\n"
                        f"Nodes: {len(nodes)}\n"
                        f"Edges: {len(edges)}"
                    )
                    self.output_message.publish()
                    
                    return AgentResponse(
                        status=AgentStatus.SUCCESS,
                        message=f"Created pathway '{name}' successfully",
                        data={
                            "pathway": pathway_result,
                            "knowledge_base": kb_result
                        }
                    )
                    
                except Exception as e:
                    text_content.status = MsgStatus.error
                    text_content.status_message = f"Failed to create pathway: {str(e)}"
                    self.output_message.publish()
                    return AgentResponse(
                        status=AgentStatus.ERROR,
                        message=f"Failed to create pathway: {str(e)}"
                    )
                    
            elif command == "update":
                if not pathway_id:
                    text_content.status = MsgStatus.error
                    text_content.status_message = "Pathway ID is required"
                    self.output_message.publish()
                    return AgentResponse(
                        status=AgentStatus.ERROR,
                        message="Pathway ID is required"
                    )
                    
                try:
                    # Get current pathway
                    current = self.bland_ai_service.get_pathway(pathway_id)
                    
                    # Build updates
                    updates = {}
                    if name:
                        updates["name"] = name
                    if description:
                        updates["description"] = description
                        
                    # If analysis_id provided, update nodes
                    if analysis_id:
                        analysis_data = self._get_analysis_data(analysis_id)
                        if not analysis_data:
                            text_content.status = MsgStatus.error
                            text_content.status_message = f"Analysis data not found for ID {analysis_id}"
                            self.output_message.publish()
                            return AgentResponse(
                                status=AgentStatus.ERROR,
                                message=f"Analysis data not found for ID {analysis_id}"
                            )
                            
                        # Create new KB
                        kb_name = f"Sales Analysis KB - Update {datetime.now().strftime('%Y%m%d_%H%M%S')}"
                        kb_result = self.kb_tool.create_from_analysis(
                            analysis_data=analysis_data,
                            name=kb_name
                        )
                        
                        # Create new nodes using KB
                        updates["nodes"] = self.transformer.create_nodes_from_analysis(
                            analysis_data=analysis_data,
                            kb_id=kb_result.get("vector_id")
                        )
                        updates["edges"] = self.transformer.create_edges(updates["nodes"])
                        
                        # Link new KB
                        self.kb_tool.link_to_pathway(
                            kb_id=kb_result.get("vector_id"),
                            pathway_id=pathway_id
                        )
                    
                    # Update pathway
                    result = self.bland_ai_service.update_pathway(
                        pathway_id=pathway_id,
                        updates=updates
                    )
                    
                    text_content.status = MsgStatus.success
                    text_content.status_message = f"Updated pathway successfully"
                    text_content.text = f"Updated pathway {pathway_id}"
                    if analysis_id:
                        text_content.text += f"\nAdded new knowledge base: {kb_result.get('vector_id')}"
                    self.output_message.publish()
                    
                    return AgentResponse(
                        status=AgentStatus.SUCCESS,
                        message="Updated pathway successfully",
                        data=result
                    )
                    
                except Exception as e:
                    text_content.status = MsgStatus.error
                    text_content.status_message = f"Failed to update pathway: {str(e)}"
                    self.output_message.publish()
                    return AgentResponse(
                        status=AgentStatus.ERROR,
                        message=f"Failed to update pathway: {str(e)}"
                    )
                    
            elif command == "add_kb":
                if not pathway_id or not kb_id:
                    text_content.status = MsgStatus.error
                    text_content.status_message = "Pathway ID and KB ID are required"
                    self.output_message.publish()
                    return AgentResponse(
                        status=AgentStatus.ERROR,
                        message="Pathway ID and KB ID are required"
                    )
                    
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
                    
                    text_content.status = MsgStatus.success
                    text_content.status_message = "Added knowledge base to pathway"
                    text_content.text = f"Added knowledge base {kb_id} to pathway {pathway_id}"
                    self.output_message.publish()
                    
                    return AgentResponse(
                        status=AgentStatus.SUCCESS,
                        message="Added knowledge base to pathway",
                        data=result
                    )
                    
                except Exception as e:
                    text_content.status = MsgStatus.error
                    text_content.status_message = f"Failed to add knowledge base: {str(e)}"
                    self.output_message.publish()
                    return AgentResponse(
                        status=AgentStatus.ERROR,
                        message=f"Failed to add knowledge base: {str(e)}"
                    )
                    
            elif command == "remove_kb":
                if not pathway_id or not kb_id:
                    text_content.status = MsgStatus.error
                    text_content.status_message = "Pathway ID and KB ID are required"
                    self.output_message.publish()
                    return AgentResponse(
                        status=AgentStatus.ERROR,
                        message="Pathway ID and KB ID are required"
                    )
                    
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
                    
                    text_content.status = MsgStatus.success
                    text_content.status_message = "Removed knowledge base from pathway"
                    text_content.text = f"Removed knowledge base {kb_id} from pathway {pathway_id}"
                    self.output_message.publish()
                    
                    return AgentResponse(
                        status=AgentStatus.SUCCESS,
                        message="Removed knowledge base from pathway",
                        data=result
                    )
                    
                except Exception as e:
                    text_content.status = MsgStatus.error
                    text_content.status_message = f"Failed to remove knowledge base: {str(e)}"
                    self.output_message.publish()
                    return AgentResponse(
                        status=AgentStatus.ERROR,
                        message=f"Failed to remove knowledge base: {str(e)}"
                    )
            
            else:
                text_content.status = MsgStatus.error
                text_content.status_message = f"Unknown command: {command}"
                self.output_message.publish()
                return AgentResponse(
                    status=AgentStatus.ERROR,
                    message=f"Unknown command: {command}"
                )
                
        except Exception as e:
            text_content.status = MsgStatus.error
            text_content.status_message = f"Error: {str(e)}"
            self.output_message.publish()
            return AgentResponse(
                status=AgentStatus.ERROR,
                message=f"Error: {str(e)}"
            )
            
    def _get_analysis_data(self, analysis_id: str) -> Optional[Dict]:
        """Get analysis data from database"""
        try:
            query = "SELECT data FROM sales_analyses WHERE id = ?"
            result = self.db.fetch_one(query, (analysis_id,))
            return result.get("data") if result else None
        except Exception as e:
            logger.error(f"Error getting analysis data: {str(e)}")
            return None 