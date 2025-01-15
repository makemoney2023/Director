import json
import logging
import re
from datetime import datetime
from typing import Dict

from director.core.session import Session
from director.core.base_agent import BaseAgent
from director.core.content import TextContent
from director.core.types import MsgStatus, AgentStatus, AgentResponse
from director.llm.openai import OpenAI, OpenaiConfig, OpenAIChatModel
from director.llm.utils import get_default_llm
from director.llm.response import LLMResponseStatus
from director.tools.anthropic_tool import AnthropicTool
from director.agents.transcription_agent import TranscriptionAgent
from director.agents.summarize_video_agent import SummarizeVideoAgent

logger = logging.getLogger(__name__)

class SalesAnalysisContent(TextContent):
    """Content type for sales analysis results"""
    analysis_data: Dict = {}  # Add field definition
    
    def __init__(self, analysis_data: Dict = None, **kwargs):
        super().__init__(**kwargs)
        self.analysis_data = analysis_data if analysis_data is not None else {}

    def to_dict(self) -> Dict:
        base_dict = super().to_dict()
        base_dict.update({
            "analysis_data": self.analysis_data
        })
        return base_dict

class SalesPromptExtractorAgent(BaseAgent):
    """Agent for extracting sales concepts and generating AI voice agent prompts"""
    
    def __init__(self, session: Session, **kwargs):
        logger.info("Initializing SalesPromptExtractorAgent")
        self.agent_name = "sales_prompt_extractor"
        self.description = "Analyzes sales techniques and generates AI voice agent prompts"
        self.parameters = self.get_parameters()
        self.llm = get_default_llm()  # For system operations
        
        # Initialize OpenAI for conversation generation with structured outputs
        openai_config = kwargs.get('openai_config') or OpenaiConfig(
            chat_model=OpenAIChatModel.GPT4o,  # Using GPT-4o for better structured output handling
            max_tokens=8192
        )
        self.conversation_llm = kwargs.get('conversation_llm') or OpenAI(config=openai_config)
        
        super().__init__(session=session, **kwargs)
        
        # Initialize dependent agents
        self.transcription_agent = TranscriptionAgent(session)
        self.summarize_agent = SummarizeVideoAgent(session)
        
        # Initialize analysis LLM after super().__init__ to allow for mocking in tests
        self.analysis_llm = kwargs.get('analysis_llm') or AnthropicTool()

    def _analyze_content(self, transcript: str, analysis_type: str) -> dict:
        """Analyze the transcript content and extract sales insights."""
        try:
            # Format messages for analysis
            messages = self._get_analysis_prompt(transcript, analysis_type)
            
            # Make API call with error handling
            response = self.analysis_llm.chat_completions(
                messages=messages,
                temperature=0.7,
                max_tokens=8192
            )
            
            if not response or not response.content:
                raise Exception("No response received from analysis LLM")
            
            if response.status == LLMResponseStatus.ERROR:
                raise Exception(f"Analysis error: {response.content}")
            
            # Format and store the analysis
            formatted_output = self._format_output(response.content)
            if not formatted_output:
                raise Exception("Failed to format analysis output")
            
            # Initialize analysis data
            analysis_data = {
                "sales_techniques": [],
                "communication_strategies": [],
                "objection_handling": [],
                "voice_agent_guidelines": []
            }
            
            # Process the formatted output
            current_section = None
            for line in formatted_output.split('\n'):
                line = line.strip()
                if not line:
                    continue
                
                # Check section headers
                if "1. Sales Techniques" in line:
                    current_section = "sales_techniques"
                    continue
                elif "2. Communication Strategies" in line:
                    current_section = "communication_strategies"
                    continue
                elif "3. Objection Handling" in line:
                    current_section = "objection_handling"
                    continue
                elif "4. Voice Agent Guidelines" in line:
                    current_section = "voice_agent_guidelines"
                    continue
                
                # Add points to current section
                if current_section and (line.startswith('•') or line.startswith('-')):
                    point = line.lstrip('•- ').strip()
                    if point:
                        if current_section in ["communication_strategies", "objection_handling"]:
                            if ":" in point:
                                type_part, desc_part = point.split(":", 1)
                                analysis_data[current_section].append({
                                    "type": type_part.strip(),
                                    "description": desc_part.strip()
                                })
                            else:
                                analysis_data[current_section].append({
                                    "type": "General",
                                    "description": point
                                })
                        else:
                            analysis_data[current_section].append({
                                "description": point
                            })
            
            return {
                "raw_analysis": formatted_output,
                "structured_data": analysis_data,
                "metadata": {
                    "sections_found": list(analysis_data.keys()),
                    "total_techniques": sum(len(section) for section in analysis_data.values())
                }
            }
            
        except Exception as e:
            logger.error(f"Error in content analysis: {str(e)}", exc_info=True)
            raise

    def _generate_prompt(self, analysis_data: dict) -> dict:
        """Generate prompts for the AI voice agent based on analysis."""
        try:
            # Generate system prompt
            system_prompt = self._get_system_prompt(analysis_data.get("structured_data", {}))
            
            # Generate example conversations
            conversation_prompt = self._get_conversation_prompt(analysis_data.get("structured_data", {}))
            
            # Make API call for example conversations
            response = self.analysis_llm.chat_completions(
                messages=[{
                    "role": "system",
                    "content": conversation_prompt
                }],
                temperature=0.7,
                max_tokens=4096
            )
            
            if not response or not response.content:
                raise Exception("No response received for conversation generation")
            
            try:
                conversations = json.loads(response.content)
                if not isinstance(conversations, dict) or "conversations" not in conversations:
                    raise ValueError("Invalid conversation format")
            except (json.JSONDecodeError, ValueError):
                # Fallback to default conversations if parsing fails
                conversations = self._get_fallback_conversations()
            
            return {
                "system_prompt": system_prompt,
                "first_message": "Hi! I'm here to help you find the perfect solution for your needs. What brings you here today?",
                "example_conversations": conversations.get("conversations", []),
                "metadata": {
                    "generated_at": datetime.utcnow().isoformat(),
                    "source_analysis": analysis_data.get("metadata", {})
                }
            }
            
        except Exception as e:
            logger.error(f"Error in prompt generation: {str(e)}", exc_info=True)
            raise 

    def run(
        self,
        video_id: str = None,
        *args,
        **kwargs,
    ) -> AgentResponse:
        """Run the sales prompt extractor agent."""
        try:
            # Initialize content holder
            text_content = SalesAnalysisContent()
            text_content.status = MsgStatus.processing
            text_content.status_message = "Starting analysis..."
            
            # Get transcript
            self.output_message.actions.append("Getting transcript...")
            self.output_message.push_update(progress=0.1)
            
            transcript = self.transcription_agent.get_transcript(video_id)
            if not transcript:
                raise Exception("Failed to get transcript")
            
            self.output_message.actions.append("Analyzing sales content...")
            self.output_message.push_update(progress=0.3)
            
            # Get analysis with proper error handling
            try:
                # Format messages for Claude 3.5
                messages = self._get_analysis_prompt(transcript, "full")
                
                logger.info("=== Starting Anthropic API Request ===")
                logger.info("Sending analysis request...")
                self.output_message.actions.append("Processing analysis...")
                self.output_message.push_update(progress=0.4)
                
                # Make API call with error handling
                response = self.analysis_llm.chat_completions(
                    messages=messages,
                    temperature=0.7,
                    max_tokens=8192
                )
                
                logger.info("=== Anthropic API Response Received ===")
                if not response or not response.content:
                    raise Exception("No response received from Anthropic API")
                
                logger.info(f"Response status: {response.status}")
                logger.info(f"Response content length: {len(response.content) if response.content else 0}")
                logger.info(f"Response content: {response.content[:500]}...")  # Log first 500 chars
                
                if response.status == LLMResponseStatus.ERROR:
                    raise Exception(f"AI analysis error: {response.content}")
                
                # Format and store the analysis
                formatted_output = self._format_output(response.content)
                if not formatted_output:
                    raise Exception("Failed to format analysis output")
                
                logger.info("Formatted output successfully")
                
                # Initialize analysis data
                analysis_data = {
                    "sales_techniques": [],
                    "communication_strategies": [],
                    "objection_handling": [],
                    "voice_agent_guidelines": []
                }
                
                # Process the formatted output
                current_section = None
                for line in formatted_output.split('\n'):
                    line = line.strip()
                    if not line:
                        continue
                    
                    # Check section headers
                    if "1. Sales Techniques" in line:
                        current_section = "sales_techniques"
                        continue
                    elif "2. Communication Strategies" in line:
                        current_section = "communication_strategies"
                        continue
                    elif "3. Objection Handling" in line:
                        current_section = "objection_handling"
                        continue
                    elif "4. Voice Agent Guidelines" in line:
                        current_section = "voice_agent_guidelines"
                        continue
                    
                    # Add points to current section
                    if current_section and (line.startswith('•') or line.startswith('-')):
                        point = line.lstrip('•- ').strip()
                        if point:
                            if current_section == "communication_strategies":
                                # Split point into type and description if possible
                                if ":" in point:
                                    type_part, desc_part = point.split(":", 1)
                                    analysis_data[current_section].append({
                                        "type": type_part.strip(),
                                        "description": desc_part.strip()
                                    })
                                else:
                                    analysis_data[current_section].append({
                                        "type": "General",
                                        "description": point
                                    })
                            else:
                                analysis_data[current_section].append({
                                    "description": point
                                })
                
                logger.info(f"Processed sections: {list(analysis_data.keys())}")
                logger.info(f"Total techniques found: {sum(len(section) for section in analysis_data.values())}")
                
                # Store results
                text_content.text = formatted_output
                text_content.analysis_data = {
                    "raw_analysis": formatted_output,
                    "structured_analysis": analysis_data,
                    "voice_prompts": self._get_system_prompt(analysis_data),
                    "example_conversations": self._get_fallback_conversations()
                }
                
                # Only update status after successful processing
                text_content.status = MsgStatus.success
                text_content.status_message = "Analysis complete"
                self.output_message.actions.append("Analysis complete")
                self.output_message.push_update(progress=1.0)
                
                return AgentResponse(
                    status=AgentStatus.SUCCESS,
                    message="Analysis complete",
                    data=text_content.analysis_data
                )
                
            except Exception as e:
                logger.error(f"Analysis error: {str(e)}", exc_info=True)
                text_content.status = MsgStatus.error
                text_content.status_message = f"Failed to analyze content: {str(e)}"
                self.output_message.push_update(progress=1.0)
                return AgentResponse(
                    status=AgentStatus.ERROR,
                    message=str(e),
                    data={"error": str(e), "error_type": "analysis_error"}
                )
                
        except Exception as e:
            logger.error(f"Agent execution error: {str(e)}", exc_info=True)
            return AgentResponse(
                status=AgentStatus.ERROR,
                message=str(e),
                data={"error": str(e), "error_type": "execution_error"}
            ) 

    def _get_fallback_conversations(self) -> list:
        """Return default fallback conversations if generation fails."""
        return [
            {
                "title": "Basic Product Inquiry",
                "scenario": "Customer inquiring about product features and pricing",
                "techniques_used": ["Active Listening", "Feature-Benefit Selling", "Consultative Approach"],
                "conversation": [
                    {
                        "role": "user",
                        "content": "I'm interested in learning more about your product."
                    },
                    {
                        "role": "assistant",
                        "content": "I'd be happy to help you learn more. To ensure I provide the most relevant information, could you tell me what specific needs or challenges you're looking to address?"
                    },
                    {
                        "role": "user",
                        "content": "Well, I'm mainly concerned about the cost and whether it's worth the investment."
                    },
                    {
                        "role": "assistant",
                        "content": "I understand cost is an important factor. Let's look at how our solution can provide value for your specific situation. Could you share more about your current process and what improvements you're hoping to achieve?"
                    }
                ]
            }
        ] 