"""
BlandAI Agent for managing conversation pathways through chat interface
"""

from typing import Dict, Any, Optional, List
from datetime import datetime
import logging

from director.core.session import Session, MsgStatus, TextContent
from director.agents.base import BaseAgent, AgentResponse, AgentStatus
from director.integrations.bland_ai.handler import BlandAIIntegrationHandler
from director.integrations.bland_ai.transformer import SalesPathwayTransformer
from director.core.config import Config
from director.db import load_db
from director.constants import DBType
from director.integrations.bland_ai.service import BlandAIService

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
                    "enum": ["list", "stats", "create", "create_empty", "update", "preview"],
                    "description": "Command to execute"
                },
                "name": {
                    "type": "string",
                    "description": "Name for the new pathway (required for create_empty)"
                },
                "description": {
                    "type": "string",
                    "description": "Description for the new pathway (required for create_empty)"
                },
                "analysis_id": {
                    "type": "string",
                    "description": "ID of the analysis to use for pathway creation/update"
                },
                "pathway_id": {
                    "type": "string",
                    "description": "ID of the pathway to update/get stats for"
                }
            },
            "required": ["command"],
            "description": "Manages Bland AI conversation pathways"
        }
        
    def _get_latest_analysis_id(self) -> Optional[str]:
        """Get the latest analysis ID from the current session"""
        try:
            # Get messages from the current conversation
            messages = self.session.get_messages()
            if not messages:
                logger.info("No messages found in current session")
                return None
                
            # Look for the most recent sales prompt extractor response
            for msg in reversed(messages):
                if msg.msg_type == "output":
                    # Check each content item
                    for content in msg.content:
                        if content.get("agent_name") == "sales_prompt_extractor":
                            # Try different ways the analysis ID might be stored
                            analysis_data = content.get("analysis_data", {})
                            analysis_id = (
                                analysis_data.get("analysis_id") or  # Direct access
                                content.get("analysis_id") or        # Top level
                                content.get("result", {}).get("analysis_id")  # In result
                            )
                            if analysis_id:
                                logger.info(f"Found latest analysis ID: {analysis_id}")
                                return analysis_id
                            
                            # Log the content for debugging
                            logger.info(f"Found sales_prompt_extractor content but no analysis_id: {content}")
                            
            logger.info("No analysis ID found in recent messages")
            return None
            
        except Exception as e:
            logger.error(f"Error getting latest analysis ID: {str(e)}", exc_info=True)
            return None
            
    def _get_pathway_by_name(self, name: str) -> Optional[str]:
        """Find pathway ID by name"""
        try:
            pathways = self.bland_ai_service.list_pathways()
            for pathway in pathways:
                if pathway.get("name", "").lower() == name.lower():
                    return pathway.get("id")
            return None
        except Exception as e:
            logger.error(f"Error finding pathway by name: {str(e)}")
            return None

    def run(self, command: str, **kwargs) -> AgentResponse:
        # If no command or just whitespace, return help message
        if not command or command.isspace():
            help_text = """Available commands:
- create_empty name="Name" description="Description": Create a new empty pathway
- update name="Name": Update pathway with latest analysis
- list: List all available pathways
- stats pathway_id=ID: Get statistics for a pathway"""
            
            text_content = TextContent(
                agent_name="bland_ai",
                status=MsgStatus.SUCCESS,
                status_message="Help Information",
                text=help_text
            )
            self.output_message.content.append(text_content)
            self.output_message.publish()
            return AgentResponse(status=MsgStatus.SUCCESS, message="Help information provided")

        try:
            # Create text content for output
            text_content = TextContent(
                agent_name=self.agent_name,
                status=MsgStatus.progress,
                status_message="Processing command..."
            )
            self.output_message.content.append(text_content)
            self.output_message.publish()
            
            # Get parameters from kwargs
            name = kwargs.get('name')
            description = kwargs.get('description')
            analysis_id = kwargs.get('analysis_id')
            pathway_id = kwargs.get('pathway_id')
            
            if command == "create_empty":
                if not name or not description:
                    text_content.status = MsgStatus.error
                    text_content.status_message = "Name and description are required for creating a pathway"
                    self.output_message.publish()
                    return AgentResponse(
                        status=AgentStatus.ERROR,
                        message="Name and description are required for creating a pathway"
                    )
                    
                try:
                    result = self.bland_ai_service.create_pathway(
                        name=name,
                        description=description
                    )
                    text_content.status = MsgStatus.success
                    text_content.status_message = f"Created new pathway '{name}' successfully"
                    text_content.text = f"Created new pathway:\nName: {name}\nDescription: {description}\nID: {result.get('pathway_id', 'Unknown')}"
                    self.output_message.publish()
                    return AgentResponse(
                        status=AgentStatus.SUCCESS,
                        message=f"Created new pathway '{name}' successfully",
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
                
            elif command == "update":
                # If no analysis_id provided, try to get the latest one
                if not analysis_id:
                    analysis_id = self._get_latest_analysis_id()
                    if not analysis_id:
                        text_content.status = MsgStatus.error
                        text_content.status_message = "No analysis found in current session"
                        text_content.text = (
                            "I couldn't find a recent analysis in this chat session. To update the pathway:\n\n"
                            "1. First run the sales prompt extractor by selecting it from the sidebar\n"
                            "2. Once the analysis is complete, run this command again:\n"
                            "   @bland_ai update name=\"Mark Wilson Used Cars\""
                        )
                        self.output_message.publish()
                        return AgentResponse(
                            status=AgentStatus.ERROR,
                            message="No analysis found in current session"
                        )
                
                # If name is provided but no pathway_id, try to find the pathway by name
                if name and not pathway_id:
                    pathway_id = self._get_pathway_by_name(name)
                    if not pathway_id:
                        text_content.status = MsgStatus.error
                        text_content.status_message = f"Could not find pathway with name '{name}'"
                        self.output_message.publish()
                        return AgentResponse(
                            status=AgentStatus.ERROR,
                            message=f"Could not find pathway with name '{name}'"
                        )
                
                if not pathway_id:
                    text_content.status = MsgStatus.error
                    text_content.status_message = "Please provide either a pathway ID or name to update"
                    self.output_message.publish()
                    return AgentResponse(
                        status=AgentStatus.ERROR,
                        message="Please provide either a pathway ID or name to update"
                    )
                
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
                
                # Transform analysis data to pathway format
                nodes, edges = self.transformer.transform_to_pathway(analysis_data)
                
                try:
                    # Update the pathway
                    result = self.bland_ai_service.update_pathway(
                        pathway_id=pathway_id,
                        nodes=nodes,
                        edges=edges
                    )
                    text_content.status = MsgStatus.success
                    text_content.status_message = f"Updated pathway successfully"
                    text_content.text = f"Updated pathway (ID: {pathway_id}) with analysis data (ID: {analysis_id})"
                    self.output_message.publish()
                    return AgentResponse(
                        status=AgentStatus.SUCCESS,
                        message=f"Updated pathway successfully",
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
                    
            elif command == "list":
                try:
                    pathways = self.bland_ai_service.list_pathways()
                    
                    if not pathways:
                        text_content.text = "No pathways found"
                        text_content.status = MsgStatus.success
                        text_content.status_message = "No pathways available"
                        self.output_message.publish()
                        return AgentResponse(
                            status=AgentStatus.SUCCESS,
                            message="No pathways found",
                            data={"pathways": []}
                        )
                    
                    # Format pathway information
                    pathway_text = []
                    for p in pathways:
                        pathway_info = {
                            "id": p.get("id", "Unknown"),
                            "name": p.get("name", "Unnamed Pathway"),
                            "description": p.get("description", "No description"),
                            "created_at": p.get("created_at", "Unknown"),
                            "updated_at": p.get("updated_at", "Unknown")
                        }
                        pathway_text.append(
                            f"- {pathway_info['name']}\n"
                            f"  ID: {pathway_info['id']}\n"
                            f"  Description: {pathway_info['description']}\n"
                            f"  Created: {pathway_info['created_at']}\n"
                            f"  Updated: {pathway_info['updated_at']}"
                        )
                    
                    text_content.text = f"Found {len(pathways)} pathways:\n\n" + "\n\n".join(pathway_text)
                    text_content.status = MsgStatus.success
                    text_content.status_message = "Retrieved available pathways"
                    self.output_message.publish()
                    
                    return AgentResponse(
                        status=AgentStatus.SUCCESS,
                        message="Retrieved available pathways",
                        data={"pathways": pathways}
                    )
                    
                except Exception as e:
                    text_content.status = MsgStatus.error
                    text_content.status_message = f"Failed to list pathways: {str(e)}"
                    self.output_message.publish()
                    return AgentResponse(
                        status=AgentStatus.ERROR,
                        message=f"Failed to list pathways: {str(e)}"
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
            logger.error(f"Error in BlandAI_Agent: {str(e)}", exc_info=True)
            text_content = TextContent(
                agent_name=self.name,
                status=MsgStatus.error,
                status_message=f"Error: {str(e)}"
            )
            self.output_message.content.append(text_content)
            self.output_message.publish()
            return AgentResponse(
                status=AgentStatus.ERROR,
                message=str(e)
            )
            
    def _get_analysis_data(self, analysis_id: str) -> Optional[Dict]:
        """Retrieve analysis data from the database"""
        try:
            # Get the analysis result from the database
            analysis = self.db.get_analysis_result(analysis_id)
            if not analysis:
                logger.error(f"No analysis found with ID: {analysis_id}")
                return None
                
            # Extract the relevant data
            return {
                "sales_techniques": analysis.get("sales_techniques", []),
                "objection_handling": analysis.get("objection_handling", []),
                "voice_prompts": analysis.get("voice_prompts", []),
                "training_pairs": analysis.get("training_pairs", []),
                "summary": analysis.get("summary", ""),
                "analysis_id": analysis_id,
                "timestamp": datetime.now().isoformat(),
                "meta_data": analysis.get("metadata", {}),  # Note: field name is 'metadata' in DB
                "structured_data": analysis.get("structured_data", {})
            }
            
        except Exception as e:
            logger.error(f"Error retrieving analysis data: {str(e)}", exc_info=True)
            return None 