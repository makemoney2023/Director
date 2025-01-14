import logging
from typing import Dict, List, Optional
import json
import re
from datetime import datetime

from director.agents.base import BaseAgent, AgentResponse, AgentStatus
from director.agents.transcription import TranscriptionAgent
from director.agents.summarize_video import SummarizeVideoAgent
from director.core.session import (
    Session,
    TextContent,
    MsgStatus,
    ContextMessage,
    RoleTypes,
)
from director.llm import get_default_llm

logger = logging.getLogger(__name__)

SALES_PROMPT_PARAMETERS = {
    "type": "object",
    "properties": {
        "video_id": {
            "type": "string",
            "description": "The ID of the video to analyze",
        },
        "analysis_type": {
            "type": "string",
            "enum": ["sales_techniques", "communication", "full"],
            "default": "full",
            "description": "Type of analysis to perform",
        },
        "output_format": {
            "type": "string",
            "enum": ["structured", "text", "both"],
            "default": "both",
            "description": "Format of the analysis output",
        }
    },
    "required": ["video_id"]
}

class SalesAnalysisContent(TextContent):
    """Content type for sales analysis results"""
    def __init__(self, analysis_data: Dict, **kwargs):
        super().__init__(**kwargs)
        self.analysis_data = analysis_data

    def to_dict(self) -> Dict:
        base_dict = super().to_dict()
        base_dict.update({
            "analysis_data": self.analysis_data
        })
        return base_dict

class SalesPromptExtractorAgent(BaseAgent):
    """Agent for extracting sales concepts and generating AI voice agent prompts"""
    
    def __init__(self, session: Session, **kwargs):
        self.agent_name = "sales_prompt_extractor"
        self.description = "Analyzes video content to extract sales techniques and generate AI voice agent prompts"
        self.parameters = SALES_PROMPT_PARAMETERS
        self.llm = get_default_llm()
        super().__init__(session=session, **kwargs)
        
        # Initialize dependent agents
        self.transcription_agent = TranscriptionAgent(session)
        self.summarize_agent = SummarizeVideoAgent(session)

    def _get_transcript(self, video_id: str) -> str:
        """Get transcript using existing transcription agent"""
        response = self.transcription_agent.run(
            video_id=video_id,
            collection_id=self.session.collection_id
        )
        if response.status != AgentStatus.SUCCESS:
            raise Exception(f"Failed to get transcript: {response.message}")
        return response.data.get("transcript", "")

    def _analyze_content(self, transcript: str, analysis_type: str) -> Dict:
        """Analyze transcript for sales concepts"""
        # Prepare prompt for sales-specific analysis
        analysis_prompt = self._get_analysis_prompt(transcript, analysis_type)
        
        # Get analysis from LLM
        analysis_response = self.llm.chat_completions(
            messages=[{
                "role": "system",
                "content": analysis_prompt
            }]
        )
        
        # Process and structure the response
        return self._structure_analysis(analysis_response.content)

    def _get_analysis_prompt(self, transcript: str, analysis_type: str) -> str:
        """Generate appropriate prompt based on analysis type"""
        base_prompt = """You are an expert sales analyst. Analyze the following transcript for sales techniques and concepts.
        Focus on extracting actionable insights that can be used to train an AI sales assistant.
        
        Provide your analysis in the following JSON format:
        {
            "sales_techniques": [
                {
                    "name": "technique name",
                    "description": "detailed description of how the technique works",
                    "examples": ["specific example from transcript"],
                    "context": "detailed explanation of when and how to use this technique"
                }
            ],
            "communication_strategies": [
                {
                    "type": "strategy type",
                    "description": "detailed explanation of the communication strategy",
                    "application": "specific guidance on how and when to apply this strategy"
                }
            ],
            "objection_handling": [
                {
                    "objection_type": "specific type of objection",
                    "recommended_response": "detailed response strategy",
                    "examples": ["specific example from transcript"],
                    "psychology": "explanation of the customer psychology behind this objection"
                }
            ],
            "closing_techniques": [
                {
                    "name": "technique name",
                    "description": "detailed explanation of how the technique works",
                    "effectiveness": "specific scenarios where this technique is most effective",
                    "psychology": "explanation of why this technique works psychologically"
                }
            ]
        }
        
        Guidelines for analysis:
        1. Extract techniques that are both explicitly mentioned and implicitly demonstrated
        2. Focus on modern, ethical sales approaches that build trust
        3. Include psychological insights where relevant
        4. Provide specific, actionable examples from the transcript
        5. Ensure all descriptions are detailed enough to be implemented by an AI
        
        Remember to maintain the exact JSON structure in your response."""

        if analysis_type == "sales_techniques":
            base_prompt += "\nFocus specifically on concrete sales techniques and their application, including both explicit and implicit techniques used in the transcript."
        elif analysis_type == "communication":
            base_prompt += "\nFocus specifically on communication strategies, emotional intelligence, and customer interaction patterns demonstrated in the transcript."
            
        return f"{base_prompt}\n\nTranscript:\n{transcript}"

    def _structure_analysis(self, analysis_text: str) -> Dict:
        """Structure the analysis response into a standardized format"""
        try:
            # Try to extract JSON from the response using a more robust pattern
            json_pattern = r'(\{[\s\S]*\})'
            json_matches = re.finditer(json_pattern, analysis_text)
            
            # Try each potential JSON match
            for match in json_matches:
                try:
                    structured_data = json.loads(match.group(0))
                    # Validate the structure
                    required_keys = ["sales_techniques", "communication_strategies", 
                                   "objection_handling", "closing_techniques"]
                    if all(key in structured_data for key in required_keys):
                        return {
                            "structured_data": structured_data,
                            "raw_analysis": analysis_text
                        }
                except json.JSONDecodeError:
                    continue
            
            # If no valid JSON found, create basic structure
            logger.warning("No valid JSON found in analysis response, using fallback structure")
            structured_data = {
                "sales_techniques": [],
                "communication_strategies": [],
                "objection_handling": [],
                "closing_techniques": []
            }
            
            return {
                "structured_data": structured_data,
                "raw_analysis": analysis_text
            }
        except Exception as e:
            logger.error(f"Error structuring analysis: {str(e)}")
            raise Exception(f"Failed to structure analysis: {str(e)}")

    def _generate_prompt(self, analysis_data: Dict) -> Dict:
        """Generate AI voice agent prompt from analysis"""
        try:
            structured_data = analysis_data.get("structured_data", {})
            
            # Generate system prompt
            system_prompt = self._generate_system_prompt(structured_data)
            
            # Generate example conversations
            example_conversations = self._generate_example_conversations(structured_data)
            
            # Generate first message
            first_message = "Hello! I'm here to help you today. How can I assist you?"
            
            return {
                "system_prompt": system_prompt,
                "first_message": first_message,
                "example_conversations": example_conversations,
                "metadata": {
                    "techniques_used": len(structured_data.get("sales_techniques", [])),
                    "strategies_used": len(structured_data.get("communication_strategies", [])),
                    "timestamp": datetime.now().isoformat()
                }
            }
        except Exception as e:
            logger.error(f"Error generating prompt: {str(e)}")
            raise Exception(f"Failed to generate prompt: {str(e)}")

    def _generate_system_prompt(self, structured_data: Dict) -> str:
        """Generate the system prompt from structured analysis"""
        prompt_parts = [
            "You are an AI sales assistant trained to engage with customers effectively and ethically. Your responses should be natural, empathetic, and focused on building genuine value for the customer.",
            "\nCore Capabilities:",
            "- Understand and adapt to customer needs and communication styles",
            "- Build trust through transparency and ethical sales practices",
            "- Provide relevant information and solutions",
            "- Handle objections professionally and empathetically",
            "\nYour approach is based on the following sales techniques and strategies:"
        ]

        # Add sales techniques with enhanced context
        if structured_data.get("sales_techniques"):
            prompt_parts.append("\n### Sales Techniques")
            for technique in structured_data["sales_techniques"]:
                prompt_parts.extend([
                    f"\n#### {technique['name']}",
                    f"- **Purpose**: {technique['description']}",
                    f"- **When to Use**: {technique['context']}"
                ])

        # Add communication strategies with practical guidelines
        if structured_data.get("communication_strategies"):
            prompt_parts.append("\n### Communication Guidelines")
            for strategy in structured_data["communication_strategies"]:
                prompt_parts.extend([
                    f"\n#### {strategy['type']}",
                    f"- **Approach**: {strategy['description']}",
                    f"- **Implementation**: {strategy['application']}"
                ])

        # Add objection handling with psychological insights
        if structured_data.get("objection_handling"):
            prompt_parts.append("\n### Objection Handling Framework")
            for objection in structured_data["objection_handling"]:
                prompt_parts.extend([
                    f"\n#### When customer expresses: {objection['objection_type']}",
                    f"- **Response Strategy**: {objection['recommended_response']}",
                    f"- **Psychology**: {objection.get('psychology', 'Address underlying concerns with empathy')}"
                ])

        # Add closing techniques with effectiveness criteria
        if structured_data.get("closing_techniques"):
            prompt_parts.append("\n### Conversion Strategies")
            for technique in structured_data["closing_techniques"]:
                prompt_parts.extend([
                    f"\n#### {technique['name']}",
                    f"- **Method**: {technique['description']}",
                    f"- **Best Used When**: {technique['effectiveness']}",
                    f"- **Psychological Impact**: {technique.get('psychology', 'Creates natural progression to decision')}"
                ])

        # Add core principles
        prompt_parts.extend([
            "\n### Core Principles:",
            "1. Always prioritize customer value over immediate sales",
            "2. Be transparent about capabilities and limitations",
            "3. Use active listening and thoughtful responses",
            "4. Maintain professional and friendly tone",
            "5. Respect customer time and decisions",
            "6. Focus on building long-term relationships",
            "\n### Response Guidelines:",
            "- Keep responses clear and concise",
            "- Use natural, conversational language",
            "- Adapt tone to customer's style",
            "- Provide specific, relevant information",
            "- Ask clarifying questions when needed"
        ])

        return "\n".join(prompt_parts)

    def _generate_example_conversations(self, structured_data: Dict) -> List[Dict]:
        """Generate example conversations from the analysis"""
        examples = []
        
        # Generate examples based on objection handling
        for objection in structured_data.get("objection_handling", []):
            if objection.get("examples"):
                example = {
                    "title": f"Handling {objection['objection_type']}",
                    "conversation": [
                        {"role": "user", "content": objection["examples"][0]},
                        {"role": "assistant", "content": objection["recommended_response"]}
                    ]
                }
                examples.append(example)

        # Generate examples based on sales techniques
        for technique in structured_data.get("sales_techniques", []):
            if technique.get("examples"):
                example = {
                    "title": f"Using {technique['name']}",
                    "conversation": [
                        {"role": "assistant", "content": technique["examples"][0]},
                        {"role": "user", "content": "Tell me more about that."},
                        {"role": "assistant", "content": technique["description"]}
                    ]
                }
                examples.append(example)

        # Add a general conversation flow example
        examples.append({
            "title": "Complete Sales Interaction",
            "conversation": [
                {"role": "user", "content": "I'm interested in learning more about your product."},
                {"role": "assistant", "content": "I'd be happy to help you learn more. What specific aspects are you most interested in?"},
                {"role": "user", "content": "I'm concerned about the price."},
                {"role": "assistant", "content": "I understand price is an important factor. Let me explain the value you'll receive..."},
                {"role": "user", "content": "That makes sense, but I need to think about it."},
                {"role": "assistant", "content": "Of course, take your time. Would it be helpful if I summarized the key benefits we discussed?"}
            ]
        })

        return examples[:5]  # Limit to 5 examples to keep the prompt focused

    def _format_output(self, analysis: Dict) -> str:
        """Format the analysis output in a readable way"""
        formatted = "# Sales Analysis Summary\n\n"
        
        # Sales Techniques
        formatted += "## 🎯 Sales Techniques\n\n"
        for technique in analysis["structured_data"].get("sales_techniques", []):
            formatted += f"### {technique['name']}\n"
            formatted += f"- **Description**: {technique['description']}\n"
            if technique.get("examples"):
                formatted += f"- **Example**: _{technique['examples'][0]}_\n"
            if technique.get("context"):
                formatted += f"- **Best Used**: {technique['context']}\n"
            formatted += "\n"

        # Communication Strategies
        formatted += "## 🗣️ Communication Strategies\n\n"
        for strategy in analysis["structured_data"].get("communication_strategies", []):
            formatted += f"### {strategy['type']}\n"
            formatted += f"- **Description**: {strategy['description']}\n"
            if strategy.get("application"):
                formatted += f"- **Application**: {strategy['application']}\n"
            formatted += "\n"

        # Objection Handling
        formatted += "## 🛡️ Objection Handling\n\n"
        for objection in analysis["structured_data"].get("objection_handling", []):
            formatted += f"### When Customer Says: \"{objection['objection_type']}\"\n"
            formatted += f"- **Recommended Response**: {objection['recommended_response']}\n"
            if objection.get("examples"):
                formatted += f"- **Example**: _{objection['examples'][0]}_\n"
            formatted += "\n"

        # Closing Techniques
        formatted += "## 🎯 Closing Techniques\n\n"
        for technique in analysis["structured_data"].get("closing_techniques", []):
            formatted += f"### {technique['name']}\n"
            formatted += f"- **How it Works**: {technique['description']}\n"
            if technique.get("effectiveness"):
                formatted += f"- **Most Effective**: {technique['effectiveness']}\n"
            formatted += "\n"

        # Generate and add AI Voice Agent Prompt
        prompt_data = self._generate_prompt(analysis)
        formatted += "## 🤖 AI Voice Agent Configuration\n\n"
        formatted += "### System Prompt\n"
        formatted += f"```\n{prompt_data['system_prompt']}\n```\n\n"
        
        formatted += "### Example Conversations\n"
        for example in prompt_data['example_conversations']:
            formatted += f"\n#### {example['title']}\n"
            for msg in example['conversation']:
                role_emoji = "👤" if msg['role'] == "user" else "🤖"
                formatted += f"{role_emoji} **{msg['role'].title()}**: {msg['content']}\n"
            formatted += "\n"

        return formatted

    def run(
        self,
        video_id: str,
        analysis_type: str = "full",
        output_format: str = "both",
        *args,
        **kwargs,
    ) -> AgentResponse:
        """Run the sales prompt extractor agent."""
        try:
            # Create initial text content for frontend updates
            text_content = TextContent(
                agent_name=self.agent_name,
                status=MsgStatus.progress,
                status_message="Analyzing sales content...",
            )
            self.output_message.content.append(text_content)
            self.output_message.push_update()

            # Get transcript and analyze content
            transcript = self._get_transcript(video_id)
            analysis = self._analyze_content(transcript, analysis_type)
            
            # Generate AI voice agent prompt
            prompt_data = self._generate_prompt(analysis)
            
            # Prepare structured data without transcript
            structured_data = {
                "sales_techniques": analysis["structured_data"]["sales_techniques"],
                "communication_strategies": analysis["structured_data"]["communication_strategies"],
                "objection_handling": analysis["structured_data"]["objection_handling"],
                "closing_techniques": analysis["structured_data"]["closing_techniques"]
            }
            
            # Format output based on preference
            if output_format == "structured":
                output = {
                    "analysis": structured_data,
                    "voice_agent": prompt_data
                }
                formatted_output = self._format_output({"structured_data": structured_data})
            elif output_format == "text":
                formatted_output = self._format_output({"structured_data": structured_data})
                output = formatted_output
            else:  # both
                output = {
                    "analysis": structured_data,
                    "voice_agent": prompt_data,
                    "formatted": self._format_output({"structured_data": structured_data}),
                    "timestamp": datetime.now().isoformat()
                }
                formatted_output = output["formatted"]

            # Update frontend with results
            text_content.text = formatted_output
            text_content.status = MsgStatus.success
            text_content.status_message = "Sales analysis completed successfully"
            self.output_message.publish()
                
            return AgentResponse(
                status=AgentStatus.SUCCESS,
                message="Sales analysis completed successfully",
                data=output
            )
            
        except Exception as e:
            logger.error(f"Error in sales analysis: {str(e)}")
            if 'text_content' in locals():
                text_content.status = MsgStatus.error
                text_content.status_message = f"Error in sales analysis: {str(e)}"
                self.output_message.publish()
            return AgentResponse(
                status=AgentStatus.ERROR,
                message=f"Error in sales analysis: {str(e)}",
                data={
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "stage": "sales_analysis"
                }
            ) 