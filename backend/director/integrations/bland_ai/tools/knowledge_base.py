"""
Knowledge Base Tool for managing Bland AI vector knowledge bases
"""

from typing import Dict, List, Optional, Any
import logging
from datetime import datetime
import os

from director.core.config import Config
from director.integrations.bland_ai.service import BlandAIService
from director.db import load_db
from director.constants import DBType

logger = logging.getLogger(__name__)

class KnowledgeBaseTool:
    """Tool for managing Bland AI vector knowledge bases"""
    
    def __init__(self, config: Config):
        """Initialize the knowledge base tool
        
        Args:
            config: Director configuration object
        """
        self.config = config
        self.bland_ai_service = BlandAIService(config)
        self.db = load_db(DBType.SQLITE)
        
    def create_from_analysis(self, analysis_data: Dict[str, Any], name: Optional[str] = None) -> Dict[str, Any]:
        """Create a new knowledge base from sales analysis data
        
        Args:
            analysis_data: Dictionary containing sales analysis data
            name: Optional name for the knowledge base. If not provided, will generate one
            
        Returns:
            Dictionary containing knowledge base metadata including ID
        """
        try:
            # Generate name if not provided
            if not name:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                name = f"Sales Analysis KB - {timestamp}"
                
            # Create description from analysis summary
            description = f"Knowledge base created from sales analysis: {analysis_data.get('summary', 'No summary available')}"
            
            # Create knowledge base through service
            kb_result = self.bland_ai_service.create_knowledge_base(
                name=name,
                description=description,
                content=analysis_data
            )
            
            # Store metadata in local DB
            self._store_kb_metadata(kb_result, analysis_data.get("analysis_id"))
            
            return kb_result
            
        except Exception as e:
            logger.error(f"Failed to create knowledge base from analysis: {str(e)}", exc_info=True)
            raise
            
    def create_from_file(self, file_path: str, name: Optional[str] = None, description: Optional[str] = None) -> Dict[str, Any]:
        """Create a new knowledge base from a file
        
        Args:
            file_path: Path to the file (.pdf, .txt, .doc, or .docx)
            name: Optional name for the knowledge base
            description: Optional description for the knowledge base
            
        Returns:
            Dictionary containing knowledge base metadata
        """
        try:
            if not os.path.exists(file_path):
                raise ValueError(f"File not found: {file_path}")
                
            # Generate name if not provided
            if not name:
                file_name = os.path.basename(file_path)
                name = f"KB from {file_name}"
                
            # Create knowledge base through service
            kb_result = self.bland_ai_service.upload_knowledge_base_file(
                file_path=file_path,
                name=name,
                description=description
            )
            
            # Store metadata in local DB
            self._store_kb_metadata(kb_result)
            
            return kb_result
            
        except Exception as e:
            logger.error(f"Failed to create knowledge base from file: {str(e)}", exc_info=True)
            raise
            
    def _store_kb_metadata(self, kb_data: Dict[str, Any], analysis_id: Optional[str] = None) -> None:
        """Store knowledge base metadata in local database
        
        Args:
            kb_data: Knowledge base data from Bland AI API
            analysis_id: Optional ID of associated sales analysis
        """
        try:
            kb_id = kb_data.get("vector_id")  # Updated to use vector_id from API
            if not kb_id:
                logger.error("No vector_id in response data")
                return
                
            # Store in knowledge_bases table
            query = """
                INSERT INTO knowledge_bases (
                    kb_id, name, description, analysis_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, datetime('now'), datetime('now'))
            """
            
            self.db.execute(
                query,
                (
                    kb_id,
                    kb_data.get("name"),
                    kb_data.get("description"),
                    analysis_id
                )
            )
            
        except Exception as e:
            logger.error(f"Failed to store knowledge base metadata: {str(e)}", exc_info=True)
            
    def link_to_pathway(self, kb_id: str, pathway_id: str) -> None:
        """Link a knowledge base to a conversation pathway
        
        Args:
            kb_id: ID of the knowledge base
            pathway_id: ID of the pathway to link to
        """
        try:
            # Store in pathway_knowledge_bases table
            query = """
                INSERT INTO pathway_knowledge_bases (
                    pathway_id, kb_id, created_at
                ) VALUES (?, ?, datetime('now'))
            """
            
            self.db.execute(query, (pathway_id, kb_id))
            
        except Exception as e:
            logger.error(f"Failed to link knowledge base to pathway: {str(e)}", exc_info=True)
            
    def get_pathway_knowledge_bases(self, pathway_id: str) -> List[Dict[str, Any]]:
        """Get all knowledge bases linked to a pathway
        
        Args:
            pathway_id: ID of the pathway
            
        Returns:
            List of knowledge base metadata dictionaries
        """
        try:
            query = """
                SELECT kb.* 
                FROM knowledge_bases kb
                JOIN pathway_knowledge_bases pkb ON kb.kb_id = pkb.kb_id
                WHERE pkb.pathway_id = ?
                ORDER BY kb.created_at DESC
            """
            
            return self.db.fetch_all(query, (pathway_id,))
            
        except Exception as e:
            logger.error(f"Failed to get pathway knowledge bases: {str(e)}", exc_info=True)
            return []
            
    def update_from_analysis(self, kb_id: str, analysis_data: Dict[str, Any], name: Optional[str] = None, description: Optional[str] = None) -> Dict[str, Any]:
        """Update an existing knowledge base with new analysis data
        
        Args:
            kb_id: ID of the knowledge base to update
            analysis_data: New analysis data
            name: Optional new name for the knowledge base
            description: Optional new description for the knowledge base
            
        Returns:
            Updated knowledge base metadata
        """
        try:
            # Get existing KB metadata
            existing_kb = self.get_knowledge_base(kb_id)
            if not existing_kb:
                raise ValueError(f"Knowledge base {kb_id} not found")
                
            # Use existing name/description if not provided
            name = name or existing_kb.get("name")
            description = description or existing_kb.get("description")
            
            # Update through service
            kb_result = self.bland_ai_service.update_knowledge_base(
                kb_id=kb_id,
                name=name,
                description=description,
                content=analysis_data
            )
            
            # Update metadata
            update_query = """
                UPDATE knowledge_bases
                SET name = ?, description = ?, updated_at = datetime('now')
                WHERE kb_id = ?
            """
            self.db.execute(update_query, (name, description, kb_id))
            
            return kb_result
            
        except Exception as e:
            logger.error(f"Failed to update knowledge base: {str(e)}", exc_info=True)
            raise
            
    def get_knowledge_base(self, kb_id: str, include_text: bool = False) -> Optional[Dict[str, Any]]:
        """Get details for a specific knowledge base
        
        Args:
            kb_id: ID of the knowledge base
            include_text: Whether to include the full text content
            
        Returns:
            Knowledge base metadata and optionally content, or None if not found
        """
        try:
            return self.bland_ai_service.get_knowledge_base(kb_id, include_text)
        except Exception as e:
            logger.error(f"Failed to get knowledge base details: {str(e)}", exc_info=True)
            return None
            
    def list_knowledge_bases(self, include_text: bool = False) -> List[Dict[str, Any]]:
        """List all knowledge bases
        
        Args:
            include_text: Whether to include the full text content
            
        Returns:
            List of knowledge base metadata
        """
        try:
            return self.bland_ai_service.list_knowledge_bases(include_text)
        except Exception as e:
            logger.error(f"Failed to list knowledge bases: {str(e)}", exc_info=True)
            return []
            
    def query(self, kb_id: str, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Query a knowledge base using vector similarity search
        
        Args:
            kb_id: ID of the knowledge base to query
            query: Query text to search for
            top_k: Number of results to return
            
        Returns:
            List of matching knowledge base entries
        """
        try:
            return self.bland_ai_service.query_knowledge_base(kb_id, query, top_k)
        except Exception as e:
            logger.error(f"Failed to query knowledge base: {str(e)}", exc_info=True)
            return [] 