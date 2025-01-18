"""
Handler for coordinating between Sales Prompt Extractor and Bland AI
"""

import logging
from typing import Dict, Optional, List
from datetime import datetime

from director.core.config import Config
from director.utils.exceptions import DirectorException
from director.agents.sales_prompt_extractor import SalesPromptExtractorAgent
from director.integrations.bland_ai.service import BlandAIService
from director.integrations.bland_ai.transformer import SalesPathwayTransformer

logger = logging.getLogger(__name__)

class BlandAIIntegrationHandler:
    """Handler for coordinating between Sales Prompt Extractor and Bland AI"""
    
    def __init__(self, config: Config):
        """Initialize the handler
        
        Args:
            config: Application configuration
            
        Raises:
            DirectorException: If required configuration is missing
        """
        self.config = config
        self.service = BlandAIService(config)
        self.transformer = SalesPathwayTransformer()
        
    async def process_sales_recording(self,
                                    recording_data: Dict,
                                    update_existing: bool = False,
                                    pathway_id: Optional[str] = None) -> Dict:
        """Process a sales recording and create/update a Bland AI pathway
        
        Args:
            recording_data: The recording data to process
            update_existing: Whether to update an existing pathway
            pathway_id: ID of the pathway to update (required if update_existing is True)
            
        Returns:
            Dict containing the created/updated pathway information
            
        Raises:
            DirectorException: If there is an error processing the recording
        """
        try:
            # Validate input
            if update_existing and not pathway_id:
                raise DirectorException("pathway_id is required when updating an existing pathway")
                
            # Transform the recording data into a pathway
            nodes, edges = self.transformer.transform_to_pathway(recording_data)
            metadata = self.transformer.generate_pathway_metadata(recording_data)
            
            # Create or update the pathway
            if update_existing:
                result = await self.service.update_pathway(
                    pathway_id=pathway_id,
                    nodes=nodes,
                    edges=edges,
                    metadata=metadata
                )
            else:
                result = await self.service.create_pathway(
                    nodes=nodes,
                    edges=edges,
                    metadata=metadata
                )
                
            return result
            
        except Exception as e:
            logger.error(f"Error processing sales recording: {str(e)}")
            raise DirectorException(f"Failed to process sales recording: {str(e)}")
            
    async def list_available_pathways(self) -> List[Dict]:
        """List all available pathways
        
        Returns:
            List of pathway information dictionaries
            
        Raises:
            DirectorException: If there is an error retrieving pathways
        """
        try:
            return await self.service.list_pathways()
        except Exception as e:
            logger.error(f"Error listing pathways: {str(e)}")
            raise DirectorException(f"Failed to list pathways: {str(e)}")
            
    async def get_pathway_stats(self, pathway_id: str) -> Dict:
        """Get statistics for a specific pathway
        
        Args:
            pathway_id: ID of the pathway to get stats for
            
        Returns:
            Dict containing pathway statistics
            
        Raises:
            DirectorException: If there is an error retrieving pathway stats
        """
        try:
            pathway = await self.service.get_pathway(pathway_id)
            
            return {
                "node_count": len(pathway.get("nodes", [])),
                "edge_count": len(pathway.get("edges", [])),
                "created_at": pathway.get("created_at", ""),
                "updated_at": pathway.get("updated_at", ""),
                "complexity_score": self._calculate_complexity_score(pathway)
            }
            
        except Exception as e:
            logger.error(f"Error getting pathway stats: {str(e)}")
            raise DirectorException(f"Failed to get pathway stats: {str(e)}")
            
    def _calculate_complexity_score(self, pathway: Dict) -> float:
        """Calculate a complexity score for the pathway based on nodes and edges
        
        Args:
            pathway: The pathway to calculate complexity for
            
        Returns:
            Float representing the complexity score
        """
        nodes = pathway.get("nodes", [])
        edges = pathway.get("edges", [])
        
        if not nodes:
            return 0.0
            
        # Calculate based on:
        # 1. Number of nodes and edges
        # 2. Average connections per node
        # 3. Maximum path depth
        
        connections_per_node = len(edges) / len(nodes)
        max_depth = self._calculate_max_depth(nodes, edges)
        
        # Normalize and combine factors
        score = (
            0.4 * min(1.0, len(nodes) / 100) +  # Node count factor
            0.3 * min(1.0, connections_per_node / 5) +  # Connectivity factor
            0.3 * min(1.0, max_depth / 10)  # Depth factor
        )
        
        return round(score, 2)
        
    def _calculate_max_depth(self, nodes: List[Dict], edges: List[Dict]) -> int:
        """Calculate the maximum path depth in the pathway
        
        Args:
            nodes: List of pathway nodes
            edges: List of pathway edges
            
        Returns:
            Integer representing the maximum path depth
        """
        # Find start node
        start_node = next(
            (n["id"] for n in nodes if n.get("isStart")),
            None
        )
        if not start_node:
            return 0
            
        # Build adjacency list
        adjacency = {}
        for edge in edges:
            source = edge.get("source")
            target = edge.get("target")
            if source and target:
                if source not in adjacency:
                    adjacency[source] = []
                adjacency[source].append(target)
                
        # Find max depth with DFS
        visited = set()
        def dfs(node: str, depth: int) -> int:
            if node in visited:
                return depth
            visited.add(node)
            
            max_child_depth = depth
            for child in adjacency.get(node, []):
                child_depth = dfs(child, depth + 1)
                max_child_depth = max(max_child_depth, child_depth)
                
            return max_child_depth
            
        return dfs(start_node, 0) 