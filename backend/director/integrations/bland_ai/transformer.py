"""
Transformer for converting sales analysis data to Bland AI pathway format
"""

import uuid
from typing import Dict, List, Tuple, Any, Optional
from datetime import datetime

class SalesPathwayTransformer:
    """Transforms sales analysis data into Bland AI pathway format"""
    
    def __init__(self):
        self.node_counter = 0
        self.edge_counter = 0
        
    def _generate_node_id(self) -> str:
        """Generate a unique node ID"""
        self.node_counter += 1
        return f"node_{self.node_counter}_{int(datetime.now().timestamp())}"
        
    def _generate_edge_id(self) -> str:
        """Generate a unique edge ID"""
        self.edge_counter += 1
        return f"edge_{self.edge_counter}_{int(datetime.now().timestamp())}"
        
    def transform_to_pathway(self, analysis_data: Dict, kb_id: Optional[str] = None, prompt_ids: Optional[List[str]] = None) -> Tuple[Dict[str, Dict], Dict[str, Dict]]:
        """Transform sales analysis data into pathway nodes and edges
        
        Args:
            analysis_data: Analysis data from sales prompt extractor
            kb_id: Optional knowledge base ID to link to nodes
            prompt_ids: Optional list of prompt IDs to use for nodes
            
        Returns:
            Tuple of (nodes dict, edges dict)
        """
        nodes = {}
        edges = {}
        
        # Create start node
        nodes["start"] = {
            "id": "start",
            "type": "Default",
            "data": {
                "name": "Start",
                "isStart": True
            }
        }
        
        # Add greeting prompt if available
        if prompt_ids and len(prompt_ids) > 0:
            nodes["start"]["data"]["prompt_id"] = prompt_ids[0]
        
        # Create knowledge base nodes for sales techniques
        for idx, technique in enumerate(analysis_data.get("knowledge_base", {}).get("sales_techniques", [])):
            node_id = f"technique_{idx}"
            nodes[node_id] = {
                "id": node_id,
                "type": "Knowledge Base",
                "data": {
                    "name": technique.get("name", "Sales Technique"),
                    "kb_id": kb_id,
                    "kb_section": "sales_techniques",
                    "kb_item_index": idx
                }
            }
            
            # Link to previous node
            prev_id = "start" if idx == 0 else f"technique_{idx-1}"
            edge_id = f"{prev_id}_to_{node_id}"
            edges[edge_id] = {
                "id": edge_id,
                "source": prev_id,
                "target": node_id,
                "data": {
                    "name": "Next Technique"
                }
            }
        
        # Create objection handling nodes
        objection_start_idx = len(nodes) - 1  # Start after technique nodes
        for idx, objection in enumerate(analysis_data.get("knowledge_base", {}).get("objection_handling", [])):
            node_id = f"objection_{idx}"
            nodes[node_id] = {
                "id": node_id,
                "type": "Knowledge Base",
                "data": {
                    "name": f"Handle {objection.get('objection', 'Objection')}",
                    "kb_id": kb_id,
                    "kb_section": "objection_handling",
                    "kb_item_index": idx
                }
            }
            
            # Link from each technique node to this objection handler
            for tech_idx in range(len(analysis_data.get("knowledge_base", {}).get("sales_techniques", []))):
                tech_id = f"technique_{tech_idx}"
                edge_id = f"{tech_id}_to_{node_id}"
                edges[edge_id] = {
                    "id": edge_id,
                    "source": tech_id,
                    "target": node_id,
                    "data": {
                        "name": "Handle Objection"
                    }
                }
        
        # Create end node
        nodes["end"] = {
            "id": "end",
            "type": "End Call",
            "data": {
                "name": "End Call"
            }
        }
        
        # Add closing prompt if available
        if prompt_ids and len(prompt_ids) > 1:
            nodes["end"]["data"]["prompt_id"] = prompt_ids[-1]
        
        # Link all nodes to end
        for node_id in nodes.keys():
            if node_id != "end":
                edge_id = f"{node_id}_to_end"
                edges[edge_id] = {
                    "id": edge_id,
                    "source": node_id,
                    "target": "end",
                    "data": {
                        "name": "End Call"
                    }
                }
        
        return nodes, edges
        
    def _get_greeting_text(self, sales_analysis: Dict) -> str:
        """Extract appropriate greeting text from analysis"""
        voice_prompts = sales_analysis.get("voice_prompts", [])
        if voice_prompts:
            return voice_prompts[0]
        return "Hello, this is an AI assistant calling. How are you today?"
        
    def _get_greeting_examples(self, sales_analysis: Dict) -> List[List[str]]:
        """Get training examples for greeting"""
        training_pairs = sales_analysis.get("training_pairs", [])
        return [
            [pair["input"], pair["output"]]
            for pair in training_pairs
            if pair.get("context") == "opening" and pair.get("quality_score", 0) > 0.7
        ]
        
    def _transform_techniques(self, sales_analysis: Dict) -> Dict:
        """Transform sales techniques into nodes with voice prompts"""
        nodes = {}
        techniques = sales_analysis.get("sales_techniques", [])
        voice_prompts = sales_analysis.get("voice_prompts", [])
        
        for i, technique in enumerate(techniques):
            node_id = self._generate_node_id()
            # Get corresponding voice prompt if available
            voice_prompt = voice_prompts[i + 1] if i + 1 < len(voice_prompts) else None
            
            nodes[node_id] = {
                "name": technique["name"],
                "type": "Default",
                "text": voice_prompt if voice_prompt else technique["examples"][0] if technique["examples"] else "",
                "prompt": technique["description"],
                "dialogueExamples": [
                    ["customer_response", example]
                    for example in technique["examples"]
                ],
                "modelOptions": {
                    "interruptionThreshold": 0.8,
                    "temperature": 0.7
                }
            }
            
        return nodes
        
    def _transform_objection_handlers(self, sales_analysis: Dict) -> Dict:
        """Transform objection handlers into nodes with voice prompts"""
        nodes = {}
        objections = sales_analysis.get("objection_handling", [])
        voice_prompts = sales_analysis.get("voice_prompts", [])
        
        for i, objection in enumerate(objections):
            node_id = self._generate_node_id()
            # Get corresponding voice prompt if available
            voice_prompt = voice_prompts[i + len(sales_analysis.get("sales_techniques", [])) + 1] if i + len(sales_analysis.get("sales_techniques", [])) + 1 < len(voice_prompts) else None
            
            nodes[node_id] = {
                "name": f"Handle {objection['name']}",
                "type": "Default",
                "text": voice_prompt if voice_prompt else objection["examples"][0] if objection["examples"] else "",
                "prompt": objection["description"],
                "dialogueExamples": [
                    ["objection", example]
                    for example in objection["examples"]
                ],
                "modelOptions": {
                    "interruptionThreshold": 0.9,  # Higher for objection handling
                    "temperature": 0.6   # Lower for more focused responses
                }
            }
            
        return nodes
        
    def _create_node_connections(self,
                               start_node_id: str,
                               technique_nodes: Dict,
                               objection_nodes: Dict) -> Dict:
        """Create edges connecting all nodes"""
        edges = {}
        
        # Connect start node to first technique
        if technique_nodes:
            first_technique_id = list(technique_nodes.keys())[0]
            edges[self._generate_edge_id()] = {
                "source": start_node_id,
                "target": first_technique_id,
                "label": "Begin Sales Process"
            }
            
        # Connect techniques in sequence
        technique_ids = list(technique_nodes.keys())
        for i in range(len(technique_ids) - 1):
            edges[self._generate_edge_id()] = {
                "source": technique_ids[i],
                "target": technique_ids[i + 1],
                "label": "Continue"
            }
            
        # Connect each technique to objection handlers
        for technique_id in technique_nodes:
            for objection_id in objection_nodes:
                edges[self._generate_edge_id()] = {
                    "source": technique_id,
                    "target": objection_id,
                    "label": "Handle Objection"
                }
                # Add return edge
                edges[self._generate_edge_id()] = {
                    "source": objection_id,
                    "target": technique_id,
                    "label": "Resume"
                }
                
        return edges
        
    def generate_pathway_metadata(self, sales_analysis: Dict) -> Dict:
        """Generate metadata for the pathway"""
        return {
            "name": f"Sales Pathway - {datetime.now().strftime('%Y-%m-%d')}",
            "description": sales_analysis.get("summary", "Automated sales conversation pathway"),
            "created_at": datetime.now().isoformat(),
            "source_analysis_id": sales_analysis.get("analysis_id"),
            "confidence_score": self._calculate_confidence_score(sales_analysis)
        }
        
    def _calculate_confidence_score(self, sales_analysis: Dict) -> float:
        """Calculate a confidence score for the pathway based on analysis quality"""
        scores = []
        
        # Check training pair quality
        training_pairs = sales_analysis.get("training_pairs", [])
        if training_pairs:
            avg_quality = sum(p.get("quality_score", 0) for p in training_pairs) / len(training_pairs)
            scores.append(avg_quality)
            
        # Check technique coverage
        techniques = sales_analysis.get("sales_techniques", [])
        if techniques:
            technique_score = min(len(techniques) / 5, 1.0)  # Normalize to max of 5 techniques
            scores.append(technique_score)
            
        # Check objection handler coverage
        objections = sales_analysis.get("objection_handling", [])
        if objections:
            objection_score = min(len(objections) / 3, 1.0)  # Normalize to max of 3 objections
            scores.append(objection_score)
            
        return sum(scores) / len(scores) if scores else 0.5  # Default to 0.5 if no scores 