import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from pydantic import BaseModel

from director.agents.base import BaseAgent, AgentResponse, AgentStatus
from director.core.session import TextContent, MsgStatus, OutputMessage, Session
from director.tools.anthropic_tool import AnthropicTool
from director.llm.base import LLMResponseStatus

logger = logging.getLogger(__name__)

class AnalysisContent(TextContent):
    """Content type for sales analysis results"""
    analysis_data: Dict = {}
    raw_analysis: str = ""
    
    def __init__(self, analysis_data: Dict = None, raw_analysis: str = "", **kwargs):
        super().__init__(**kwargs)
        self.analysis_data = analysis_data if analysis_data is not None else {}
        self.raw_analysis = raw_analysis

    def to_dict(self) -> Dict:
        base_dict = super().to_dict()
        base_dict.update({
            "analysis_data": self.analysis_data,
            "raw_analysis": self.raw_analysis
        })
        return base_dict

class SalesAnalysisAgent(BaseAgent):
    """Agent for performing detailed sales conversation analysis"""
    
    def __init__(self, session: Session, **kwargs):
        self.agent_name = "sales_analysis"
        self.description = "Performs detailed analysis of sales conversations"
        self.parameters = self.get_parameters()
        super().__init__(session=session, **kwargs)
        
        # Initialize Anthropic
        self.analysis_llm = kwargs.get('analysis_llm') or AnthropicTool()

    def get_parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "transcript": {
                    "type": "string",
                    "description": "The conversation transcript to analyze"
                },
                "analysis_type": {
                    "type": "string",
                    "enum": ["sales_techniques", "communication", "full"],
                    "default": "full",
                    "description": "Type of analysis to perform"
                }
            },
            "required": ["transcript"],
            "description": "Analyzes sales conversations in detail"
        }

    def _get_analysis_prompt(self, transcript: str, analysis_type: str) -> List[Dict[str, str]]:
        """Generate appropriate prompt for Anthropic analysis"""
        system_prompt = """You are an expert sales conversation analyst. Your task is to provide a detailed, insightful analysis of sales conversations that can be used to train AI voice agents.

Your analysis should be in markdown format and cover:

1. OVERVIEW
- Brief summary of the conversation
- Key objectives identified
- Overall effectiveness assessment

2. SALES TECHNIQUES
- Specific techniques used
- Effectiveness of each technique
- Real examples from the transcript
- Suggested improvements

3. COMMUNICATION PATTERNS
- Tone and style analysis
- Pacing and timing
- Question techniques
- Active listening examples

4. CUSTOMER INTERACTION
- Response patterns
- Pain points identified
- Engagement levels
- Trust-building moments

5. OBJECTION HANDLING
- Types of objections raised
- Response effectiveness
- Alternative approaches
- Recovery strategies

6. CLOSING TECHNIQUES
- Approach used
- Timing and execution
- Success factors
- Improvement areas

FORMAT YOUR RESPONSE IN CLEAN MARKDOWN WITH CLEAR SECTIONS AND EXAMPLES.
USE EXACT QUOTES FROM THE TRANSCRIPT WHEN PROVIDING EXAMPLES.
INCLUDE SPECIFIC, ACTIONABLE INSIGHTS FOR EACH SECTION."""

        user_prompt = f"""Analyze this sales conversation transcript with particular attention to {analysis_type} aspects.

For each insight:
1. Provide specific examples from the transcript
2. Explain why it was effective or not
3. Suggest concrete improvements
4. Note any patterns or recurring elements

Transcript:
{transcript}

Remember to:
- Use markdown formatting
- Include exact quotes as examples
- Provide actionable insights
- Focus on patterns and effectiveness"""

        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

    def _find_similar_analyses(self, transcript: str) -> List[Dict]:
        """Find similar analyses in the codebase"""
        try:
            # Simplified implementation without using removed tools
            return []
        except Exception as e:
            logger.warning(f"Error finding similar analyses: {str(e)}")
            return []

    def _process_transcript(self, transcript: str) -> str:
        """Process the transcript for analysis"""
        try:
            # Basic transcript cleaning
            return transcript.strip()
        except Exception as e:
            logger.warning(f"Error processing transcript: {str(e)}")
            return transcript

    def run(
        self,
        transcript: str,
        analysis_type: str = "full",
        *args,
        **kwargs
    ) -> AgentResponse:
        """Run the sales analysis"""
        try:
            if not transcript:
                raise ValueError("Transcript is required for analysis")

            # Initialize content
            text_content = AnalysisContent(
                analysis_data={},
                raw_analysis="",
                agent_name=self.agent_name,
                status=MsgStatus.progress,
                status_message="Starting analysis...",
                text="Processing transcript..."
            )
            self.output_message.add_content(text_content)
            self.output_message.actions.append("Beginning analysis...")
            self.output_message.push_update()

            # Find similar analyses for context
            similar_analyses = self._find_similar_analyses(transcript)
            
            # Process transcript
            processed_transcript = self._process_transcript(transcript)

            # Generate analysis prompt
            messages = self._get_analysis_prompt(processed_transcript, analysis_type)
            
            logger.info("Requesting analysis from Anthropic")
            response = self.analysis_llm.chat_completions(
                messages=messages,
                temperature=0.7,
                max_tokens=4096
            )
            
            if response.status == LLMResponseStatus.ERROR:
                raise Exception(f"Anthropic analysis failed: {response.message}")

            # Store results
            text_content.raw_analysis = response.content
            text_content.text = response.content
            text_content.analysis_data = {
                "similar_analyses": similar_analyses,
                "processed_transcript": processed_transcript
            }
            text_content.status = MsgStatus.success
            text_content.status_message = "Analysis completed"
            
            self.output_message.actions.append("Analysis completed")
            self.output_message.push_update()
            
            logger.info("Sales analysis completed successfully")
            return AgentResponse(
                status=AgentStatus.SUCCESS,
                message="Analysis completed successfully",
                data={
                    "raw_analysis": response.content,
                    "analysis_type": analysis_type,
                    "similar_analyses": similar_analyses
                }
            )
            
        except Exception as e:
            logger.error(f"Error in sales analysis: {str(e)}", exc_info=True)
            if 'text_content' in locals():
                text_content.status = MsgStatus.error
                text_content.status_message = f"Analysis failed: {str(e)}"
                self.output_message.push_update()
            return AgentResponse(
                status=AgentStatus.ERROR,
                message=str(e),
                data={"error": str(e)}
            ) 