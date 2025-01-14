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
        base_prompt = """Analyze the following transcript for sales techniques and concepts.
        Provide your analysis in the following JSON format:
        {
            "sales_techniques": [
                {
                    "name": "technique name",
                    "description": "detailed description",
                    "examples": ["example from transcript"],
                    "context": "when/how to use"
                }
            ],
            "communication_strategies": [
                {
                    "type": "strategy type",
                    "description": "strategy description",
                    "application": "how to apply"
                }
            ],
            "objection_handling": [
                {
                    "objection_type": "type of objection",
                    "recommended_response": "how to handle",
                    "examples": ["example from transcript"]
                }
            ],
            "closing_techniques": [
                {
                    "name": "technique name",
                    "description": "how it works",
                    "effectiveness": "when it's most effective"
                }
            ]
        }
        
        Focus on extracting:
        1. Key sales techniques used
        2. Communication strategies demonstrated
        3. Objection handling approaches shown
        4. Closing techniques employed"""
        
        if analysis_type == "sales_techniques":
            base_prompt += "\nFocus specifically on concrete sales techniques and their application."
        elif analysis_type == "communication":
            base_prompt += "\nFocus specifically on communication strategies and customer interaction."
            
        return f"{base_prompt}\n\nTranscript:\n{transcript}"

    def _structure_analysis(self, analysis_text: str) -> Dict:
        """Structure the analysis response into a standardized format"""
        try:
            # Try to extract JSON from the response
            json_match = re.search(r'\{[\s\S]*\}', analysis_text)
            if json_match:
                structured_data = json.loads(json_match.group(0))
            else:
                # If no JSON found, create basic structure
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
            "You are an AI sales assistant trained to engage with customers effectively.",
            "\nYour approach is based on the following sales techniques and strategies:"
        ]

        # Add sales techniques
        if structured_data.get("sales_techniques"):
            prompt_parts.append("\nKey Sales Techniques:")
            for technique in structured_data["sales_techniques"]:
                prompt_parts.append(f"- {technique['name']}: {technique['description']}")
                if technique.get("context"):
                    prompt_parts.append(f"  Use when: {technique['context']}")

        # Add communication strategies
        if structured_data.get("communication_strategies"):
            prompt_parts.append("\nCommunication Strategies:")
            for strategy in structured_data["communication_strategies"]:
                prompt_parts.append(f"- {strategy['type']}: {strategy['description']}")
                if strategy.get("application"):
                    prompt_parts.append(f"  Application: {strategy['application']}")

        # Add objection handling
        if structured_data.get("objection_handling"):
            prompt_parts.append("\nWhen handling objections:")
            for objection in structured_data["objection_handling"]:
                prompt_parts.append(f"- If customer mentions {objection['objection_type']}:")
                prompt_parts.append(f"  Response: {objection['recommended_response']}")

        # Add closing techniques
        if structured_data.get("closing_techniques"):
            prompt_parts.append("\nClosing Techniques:")
            for technique in structured_data["closing_techniques"]:
                prompt_parts.append(f"- {technique['name']}: {technique['description']}")
                if technique.get("effectiveness"):
                    prompt_parts.append(f"  Most effective: {technique['effectiveness']}")

        # Add general guidelines
        prompt_parts.extend([
            "\nGeneral Guidelines:",
            "- Always maintain a professional and helpful tone",
            "- Listen actively and acknowledge customer concerns",
            "- Use appropriate techniques based on the conversation context",
            "- Be transparent and honest in all interactions",
            "- Focus on providing value to the customer"
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