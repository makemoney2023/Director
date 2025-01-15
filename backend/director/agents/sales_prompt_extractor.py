import logging
import sys
import codecs
from typing import Dict, List, Optional, Any, Literal
import json
import re
from datetime import datetime
from pydantic import BaseModel
import time
import os

from director.agents.base import BaseAgent, AgentResponse, AgentStatus
from director.agents.transcription import TranscriptionAgent
from director.agents.summarize_video import SummarizeVideoAgent
from director.agents.sales_voice_prompt_agent import SalesVoicePromptAgent
from director.agents.sales_conversation_agent import SalesConversationAgent
from director.core.session import (
    Session,
    TextContent,
    MsgStatus,
    ContextMessage,
    RoleTypes,
    OutputMessage,
)
from director.llm import get_default_llm
from director.tools.anthropic_tool import AnthropicTool
from director.llm.openai import OpenAI, OpenaiConfig, OpenAIChatModel
from director.llm.base import LLMResponseStatus

# Configure UTF-8 encoding for stdout
if sys.stdout.encoding != 'utf-8':
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# Configure logging with UTF-8 encoding and file output
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('sales_prompt_extractor.log', encoding='utf-8'),
        logging.StreamHandler(codecs.getwriter('utf-8')(sys.stdout.buffer) if hasattr(sys.stdout, 'buffer') else sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

def _clean_text_for_logging(text: str) -> str:
    """Clean text for logging by replacing problematic Unicode characters"""
    return (text.replace('→', '->') 
            .replace('←', '<-')
            .replace('⇒', '=>')
            .replace('⇐', '<=')
            .encode('ascii', 'replace')
            .decode('ascii'))

SALES_PROMPT_PARAMETERS = {
    "type": "object",
    "properties": {
        "video_id": {
            "type": "string",
            "description": "The ID of the video to analyze"
        },
        "collection_id": {
            "type": "string", 
            "description": "The ID of the collection containing the video"
        },
        "analysis_type": {
            "type": "string",
            "enum": ["sales_techniques", "communication", "full"],
            "default": "full",
            "description": "Type of analysis to perform"
        },
        "output_format": {
            "type": "string",
            "enum": ["structured", "text", "both"],
            "default": "both",
            "description": "Format of the analysis output"
        }
    },
    "required": ["video_id", "collection_id"],
    "description": "Analyzes sales techniques and generates AI voice agent prompts",
    "bypass_reasoning": True,
    "example_queries": [
        "@sales_prompt_extractor analyze video_id=123 collection_id=456",
        "@sales_prompt_extractor"
    ]
}

class AnthropicResponse(BaseModel):
    """Model for storing Anthropic responses"""
    content: str
    timestamp: datetime
    status: str
    metadata: Dict = {}

class SalesAnalysisContent(TextContent):
    """Content type for sales analysis results"""
    analysis_data: Dict = {}
    anthropic_response: Optional[AnthropicResponse] = None
    voice_prompt: Optional[str] = None
    
    def __init__(self, analysis_data: Dict = None, anthropic_response: Dict = None, voice_prompt: str = None, **kwargs):
        super().__init__(**kwargs)
        self.analysis_data = analysis_data if analysis_data is not None else {}
        self.anthropic_response = AnthropicResponse(**anthropic_response) if anthropic_response else None
        self.voice_prompt = voice_prompt

    def to_dict(self) -> Dict:
        base_dict = super().to_dict()
        base_dict.update({
            "analysis_data": self.analysis_data,
            "anthropic_response": self.anthropic_response.dict() if self.anthropic_response else None,
            "voice_prompt": self.voice_prompt
        })
        return base_dict

    def store_anthropic_response(self, content: str, status: str = "success", metadata: Dict = None):
        """Store Anthropic response with metadata"""
        self.anthropic_response = AnthropicResponse(
            content=content,
            timestamp=datetime.now(),
            status=status,
            metadata=metadata or {}
        )

class ConversationMessage(BaseModel):
    """A single message in a conversation"""
    role: Literal["user", "assistant"]
    content: str

class Conversation(BaseModel):
    """A complete conversation example"""
    title: str
    scenario: str
    techniques_used: List[str]
    conversation: List[ConversationMessage]

class ConversationResponse(BaseModel):
    """The complete response structure for conversation generation"""
    explanation: str
    conversations: List[Conversation]

class SalesPromptExtractorAgent(BaseAgent):
    """Agent for extracting sales concepts and generating AI voice agent prompts"""
    
    def __init__(self, session: Session, **kwargs):
        self.agent_name = "sales_prompt_extractor"
        self.description = "Analyzes sales techniques and generates AI voice agent prompts"
        self.parameters = SALES_PROMPT_PARAMETERS
        super().__init__(session=session, **kwargs)
        
        # Initialize dependent agents
        self.transcription_agent = TranscriptionAgent(session)
        self.summarize_agent = SummarizeVideoAgent(session)
        
        # Initialize LLMs
        self.llm = get_default_llm()
        self.analysis_llm = kwargs.get('analysis_llm') or AnthropicTool()
        self.max_retries = 3
        self.retry_delay = 2  # seconds

    def _get_analysis_prompt(self, transcript: str, analysis_type: str) -> List[Dict[str, str]]:
        """Generate appropriate prompt based on analysis type"""
        try:
            logger.info("=== Generating Analysis Prompt ===")
            messages = [
                {
                    "role": "system",
                    "content": """You are an expert sales analyst. Your task is to analyze sales conversations and provide clear, actionable insights.
Your analysis must include specific examples and detailed descriptions for:
1. Sales techniques used (with examples from the transcript)
2. Communication strategies employed (with specific phrases used)
3. Objection handling approaches demonstrated
4. Voice agent guidelines based on successful patterns

Format your response with clear sections, bullet points, and specific examples from the transcript."""
                },
                {
                    "role": "user",
                    "content": f"""Analyze this sales conversation transcript and provide detailed insights in these specific areas:

1. Sales Techniques Used
• List each specific technique identified
• Include exact quotes or examples from the transcript
• Explain when and why each technique was effective
• Note the context and timing of each technique

2. Communication Strategies
• Document specific phrases and approaches used
• Include exact quotes showing each strategy
• Analyze tone, pacing, and style choices
• Note which strategies were most effective and why

3. Objection Handling
• List each objection encountered
• Document exactly how each was addressed
• Include specific phrases and responses used
• Analyze why the handling was effective or not

4. Voice Agent Guidelines
• Provide specific phrases to use or avoid
• Include exact response templates from successful exchanges
• Document tone and style recommendations
• List specific do's and don'ts with examples

Transcript to analyze:
{transcript}

For each section, include:
- Specific techniques/strategies by name
- Exact quotes and examples from the transcript
- When and why each approach works best
- Clear guidelines for implementation"""
                }
            ]
            logger.info("Analysis prompt generated successfully")
            return messages
        except Exception as e:
            logger.error(f"Error generating analysis prompt: {str(e)}", exc_info=True)
            raise

    def _store_analysis_response(self, content: str, status: str = "success", metadata: Dict = None, 
                               structured_data: Dict = None, voice_prompt: str = None) -> None:
        """Store analysis response and related data in the database"""
        try:
            # Get the current content or create new if doesn't exist
            if not self.output_message.content:
                text_content = SalesAnalysisContent(
                    agent_name=self.agent_name,
                    status=MsgStatus.progress,
                    status_message="Storing analysis..."
                )
                self.output_message.content.append(text_content)
            else:
                # Ensure we're working with a SalesAnalysisContent object
                text_content = self.output_message.content[-1]
                if not isinstance(text_content, SalesAnalysisContent):
                    text_content = SalesAnalysisContent(
                        agent_name=self.agent_name,
                        status=MsgStatus.progress,
                        status_message="Storing analysis..."
                    )
                    self.output_message.content[-1] = text_content

            # Store all the data
            text_content.anthropic_response = AnthropicResponse(
                content=content,
                timestamp=datetime.now(),
                status=status,
                metadata=metadata or {}
            )
            
            if structured_data:
                text_content.analysis_data = structured_data
                
            if voice_prompt:
                text_content.voice_prompt = voice_prompt
            
            # Update message status
            text_content.status = MsgStatus.success if status == "success" else MsgStatus.error
            text_content.status_message = "Analysis stored successfully" if status == "success" else "Error storing analysis"
            text_content.text = content  # Set the text content for display
            
            # Push update to database
            self.output_message.push_update()
            logger.info(f"Analysis response and related data stored with status: {status}")
            
        except Exception as e:
            logger.error(f"Error storing analysis response: {str(e)}", exc_info=True)
            raise

    def _save_markdown_analysis(self, analysis_content: str, structured_data: Dict, voice_prompt: str, video_id: str) -> str:
        """Save the analysis as a markdown file."""
        try:
            # Create analysis directory if it doesn't exist
            analysis_dir = os.path.join(os.getcwd(), 'analysis')
            os.makedirs(analysis_dir, exist_ok=True)
            
            # Create filename with timestamp
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f'analysis_{video_id}_{timestamp}.md'
            filepath = os.path.join(analysis_dir, filename)
            
            # Format content
            markdown_content = f"""# Sales Conversation Analysis

## Raw Analysis
{analysis_content}

## Voice Agent Prompt
```
{voice_prompt}
```

## Structured Data
```json
{json.dumps(structured_data, indent=2)}
```
"""
            
            # Write to file
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(markdown_content)
                
            logger.info(f"Analysis saved to markdown file: {filepath}")
            return filepath
            
        except Exception as e:
            logger.error(f"Error saving markdown analysis: {str(e)}", exc_info=True)
            return None

    def run(
        self,
        video_id: str = None,
        collection_id: str = None,
        analysis_type: str = "full",
        bypass_reasoning: bool = True,
        *args,
        **kwargs,
    ) -> AgentResponse:
        """Run the sales prompt extractor agent."""
        try:
            # Initialize content holder
            text_content = SalesAnalysisContent(
                agent_name=self.agent_name,
                status=MsgStatus.progress,
                status_message="Starting analysis..."
            )
            self.output_message.content.append(text_content)
            
            # Get transcript
            self.output_message.actions.append("Getting transcript...")
            self.output_message.push_update(progress=0.1)
            
            if not collection_id:
                raise Exception("collection_id is required to get transcript")
            
            transcript_response = self.transcription_agent.run(
                collection_id=collection_id,
                video_id=video_id
            )
            
            if transcript_response.status != AgentStatus.SUCCESS:
                raise Exception(f"Failed to get transcript: {transcript_response.message}")
            
            transcript = transcript_response.data.get("transcript")
            if not transcript:
                raise Exception("No transcript found in response")
            
            self.output_message.actions.append("Analyzing sales content...")
            self.output_message.push_update(progress=0.3)
            
            # Get analysis with proper error handling and retries
            retry_count = 0
            last_error = None
            
            while retry_count < self.max_retries:
                try:
                    # Format messages for analysis
                    messages = self._get_analysis_prompt(transcript, analysis_type)
                    
                    logger.info("=== Starting Anthropic API Request ===")
                    logger.info("Sending analysis request...")
                    self.output_message.actions.append("Processing analysis...")
                    self.output_message.push_update(progress=0.4)
                    
                    # Make API call directly to Anthropic
                    response = self.analysis_llm.chat_completions(
                        messages=messages,
                        temperature=0.7,
                        max_tokens=8192
                    )
                    
                    if not response or not response.content:
                        raise Exception("No response received from Anthropic API")
                    
                    # Store the raw analysis response
                    raw_analysis = response.content
                    
                    # Generate voice prompt first
                    self.output_message.actions.append("Generating voice agent prompt...")
                    self.output_message.push_update(progress=0.6)
                    
                    # Create initial data structure with raw analysis
                    initial_data = {
                        "raw_analysis": raw_analysis,
                        "sales_techniques": [],
                        "communication_strategies": [],
                        "objection_handling": [],
                        "voice_agent_guidelines": []
                    }
                    
                    voice_prompt = self._generate_voice_prompt(initial_data)
                    
                    # Now generate structured output using both raw analysis and voice prompt
                    self.output_message.actions.append("Generating structured output...")
                    self.output_message.push_update(progress=0.8)
                    
                    structured_data = self._generate_structured_output(raw_analysis, voice_prompt)
                    structured_data["raw_analysis"] = raw_analysis
                    
                    # Save analysis to markdown file
                    markdown_file = self._save_markdown_analysis(
                        analysis_content=raw_analysis,
                        structured_data=structured_data,
                        voice_prompt=voice_prompt,
                        video_id=video_id
                    )

                    # Format final response
                    final_response = f"""## Raw Analysis
```
{raw_analysis}
```

## Voice Agent Prompt
```
{voice_prompt}
```

## Structured Data
```json
{json.dumps(structured_data, indent=2)}
```

Analysis has been saved to: {markdown_file if markdown_file else 'Error saving markdown file'}
"""
                    
                    # Store all the data
                    self._store_analysis_response(
                        content=final_response,
                        status="success",
                        metadata={
                            "attempt": retry_count + 1,
                            "timestamp": datetime.now().isoformat(),
                            "bypass_reasoning": bypass_reasoning
                        },
                        structured_data=structured_data,
                        voice_prompt=voice_prompt
                    )
                    
                    return AgentResponse(
                        status=AgentStatus.SUCCESS,
                        message="Analysis completed successfully",
                        data={
                            "analysis": raw_analysis,
                            "voice_prompt": voice_prompt,
                            "structured_data": structured_data,
                            "markdown_file": markdown_file
                        }
                    )
                    
                except Exception as e:
                    last_error = str(e)
                    logger.error(f"Attempt {retry_count + 1} failed: {last_error}", exc_info=True)
                    retry_count += 1
                    if retry_count < self.max_retries:
                        time.sleep(self.retry_delay * retry_count)
                    
                    # Store failed attempt
                    self._store_analysis_response(
                        content="",
                        status="error",
                        metadata={
                            "error": last_error,
                            "attempt": retry_count,
                            "timestamp": datetime.now().isoformat(),
                            "bypass_reasoning": bypass_reasoning
                        }
                    )
            
            # If we get here, all retries failed
            raise Exception(f"Failed after {self.max_retries} attempts. Last error: {last_error}")
            
        except Exception as e:
            logger.error(f"Error in sales prompt extractor: {str(e)}", exc_info=True)
            return AgentResponse(
                status=AgentStatus.ERROR,
                message=str(e),
                data=None
            )

    def _format_output(self, content: str) -> str:
        """Format the analysis output for better readability."""
        try:
            # Clean and normalize the content
            content = content.strip()
            content = re.sub(r'\n{3,}', '\n\n', content)  # Remove excessive newlines
            content = _clean_text_for_logging(content)
            return content
        except Exception as e:
            logger.error(f"Error formatting output: {str(e)}", exc_info=True)
            return content

    def _get_system_prompt(self, analysis_data: dict) -> str:
        """Generate system prompt for the AI voice agent."""
        prompt = """You are an AI sales agent trained to engage in natural, empathetic, and effective sales conversations. Your responses should be guided by the following framework:

ROLE AND PERSONA:
- You are a professional, friendly, and knowledgeable sales consultant
- You focus on understanding customer needs before proposing solutions
- You maintain a balanced approach between being helpful and goal-oriented

COMMUNICATION STYLE:
- Use clear, concise, and professional language
- Practice active listening and ask clarifying questions
- Mirror the customer's communication style while maintaining professionalism
- Show genuine interest in helping customers solve their problems

KEY OBJECTIVES:
1. Build trust and rapport with customers
2. Understand customer needs through effective questioning
3. Present relevant solutions based on customer requirements
4. Address concerns and objections professionally
5. Guide conversations toward positive outcomes

ETHICAL GUIDELINES:
1. Always be truthful and transparent
2. Never pressure customers into decisions
3. Respect customer privacy and confidentiality
4. Only make promises you can keep
5. Prioritize customer needs over immediate sales

AVAILABLE TECHNIQUES AND STRATEGIES:

Sales Techniques:
{techniques}

Communication Strategies:
{strategies}

Objection Handling:
{objections}

Voice Agent Guidelines:
{guidelines}

IMPLEMENTATION GUIDELINES:
1. Start conversations by building rapport and understanding needs
2. Use appropriate sales techniques based on the conversation context
3. Address objections using the provided strategies
4. Apply closing techniques naturally when customer shows interest
5. Maintain a helpful and consultative approach throughout

Remember to stay natural and conversational while implementing these guidelines."""

        # Format techniques section
        techniques = "\n".join([
            f"- {t.get('description', '')}"
            for t in analysis_data.get("sales_techniques", [])
        ])
        
        # Format strategies section
        strategies = "\n".join([
            f"- {s.get('type', 'Strategy')}: {s.get('description', '')}"
            for s in analysis_data.get("communication_strategies", [])
        ])
        
        # Format objections section
        objections = "\n".join([
            f"- {o.get('description', '')}"
            for o in analysis_data.get("objection_handling", [])
        ])
        
        # Format guidelines section
        guidelines = "\n".join([
            f"- {g.get('description', '')}"
            for g in analysis_data.get("voice_agent_guidelines", [])
        ])
        
        return prompt.format(
            techniques=techniques or "No specific techniques provided",
            strategies=strategies or "No specific strategies provided",
            objections=objections or "No specific objection handling provided",
            guidelines=guidelines or "No specific guidelines provided"
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

    def _generate_structured_output(self, analysis_text: str, voice_prompt: str) -> Dict:
        """Convert Anthropic analysis into structured data using OpenAI"""
        try:
            # Initialize structured data
            structured_data = {
                "sales_techniques": [],
                "communication_strategies": [],
                "objection_handling": [],
                "voice_agent_guidelines": []
            }
            
            # Split analysis into sections
            sections = analysis_text.split("\n\n")
            current_section = None
            current_item = None
            
            for section in sections:
                if "1. Sales Techniques Used" in section:
                    current_section = "sales_techniques"
                    continue
                elif "2. Communication Strategies" in section:
                    current_section = "communication_strategies"
                    continue
                elif "3. Objection Handling" in section:
                    current_section = "objection_handling"
                    continue
                elif "4. Voice Agent Guidelines" in section:
                    current_section = "voice_agent_guidelines"
                    continue
                
                if not current_section:
                    continue
                
                lines = section.split("\n")
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                        
                    if line.startswith("•"):
                        # Save previous item if exists
                        if current_item:
                            structured_data[current_section].append(current_item)
                        
                        # Start new item
                        if current_section == "sales_techniques":
                            current_item = {
                                "name": line.replace("•", "").strip(),
                                "description": "",
                                "examples": [],
                                "effectiveness": ""
                            }
                        elif current_section == "communication_strategies":
                            current_item = {
                                "type": line.replace("•", "").strip(),
                                "description": "",
                                "examples": [],
                                "effectiveness": ""
                            }
                        elif current_section == "objection_handling":
                            current_item = {
                                "name": line.replace("•", "").strip(),
                                "description": "",
                                "examples": [],
                                "effectiveness": ""
                            }
                        elif current_section == "voice_agent_guidelines":
                            if "Do's:" in section:
                                current_item = {
                                    "name": "Do",
                                    "description": line.replace("•", "").strip(),
                                    "examples": [],
                                    "context": "Best practice guideline"
                                }
                            elif "Don'ts:" in section:
                                current_item = {
                                    "name": "Don't",
                                    "description": line.replace("•", "").strip(),
                                    "examples": [],
                                    "context": "Practice to avoid"
                                }
                    elif line.startswith("- Quote:") or line.startswith("- Customer:"):
                        if current_item:
                            quote = line.split(":", 1)[1].strip().strip('"')
                            current_item["examples"].append(quote)
                    elif line.startswith("- Response:"):
                        if current_item:
                            response = line.split(":", 1)[1].strip().strip('"')
                            current_item["description"] = response
                    elif line.startswith("- "):
                        if current_item:
                            text = line.replace("-", "").strip()
                            if "when" in text.lower() or "use" in text.lower():
                                current_item["effectiveness"] = text
                            elif not current_item["description"]:
                                current_item["description"] = text
                
                # Add the last item of the section
                if current_item:
                    structured_data[current_section].append(current_item)
                    current_item = None
            
            # Add key phrases as examples to relevant guidelines
            if "Key Phrases" in analysis_text:
                key_phrases_section = analysis_text.split("Key Phrases")[1].split("\n\n")[0]
                phrases = [line.replace("•", "").strip().strip('"') 
                          for line in key_phrases_section.split("\n") 
                          if line.strip().startswith("•")]
                
                for phrase in phrases:
                    for guideline in structured_data["voice_agent_guidelines"]:
                        if any(keyword in phrase.lower() for keyword in guideline["description"].lower().split()):
                            guideline["examples"].append(phrase)
            
            return structured_data
            
        except Exception as e:
            logger.error(f"Error generating structured output: {str(e)}", exc_info=True)
            return {
                "sales_techniques": [],
                "communication_strategies": [],
                "objection_handling": [],
                "voice_agent_guidelines": [],
                "raw_analysis": analysis_text
            }

    def _generate_voice_prompt(self, analysis_data: Dict) -> str:
        """Generate a detailed voice agent prompt from the structured analysis data"""
        try:
            prompt = """You are an advanced AI voice sales agent. Your primary goal is to engage in natural, persuasive sales conversations while maintaining authenticity and ethical standards.

IDENTITY & PERSONA:
- You are a professional, empathetic sales consultant named [Agent Name]
- Your voice is warm, confident, and naturally engaging
- You adapt your tone and pace to match the customer while staying professional
- You demonstrate deep product knowledge and genuine desire to help

CONVERSATION FRAMEWORK:
1. OPENING (First 30 seconds):
   - Greet warmly and introduce yourself clearly
   - Build immediate rapport with genuine interest
   - Set a positive, professional tone

2. DISCOVERY (Next 2-3 minutes):
   - Ask strategic questions to understand needs
   - Listen actively and acknowledge responses
   - Show empathy and understanding

3. SOLUTION PRESENTATION (2-3 minutes):
   - Present tailored solutions based on discovery
   - Focus on value and benefits
   - Use relevant examples and social proof

4. HANDLING CONCERNS (As needed):
   - Address objections professionally
   - Maintain positive, solution-focused approach
   - Use proven objection handling techniques

5. CLOSING (When appropriate):
   - Recognize buying signals
   - Guide naturally to next steps
   - Maintain relationship even if no immediate sale

VOICE & LANGUAGE PATTERNS:

Tonality Guidelines:
- Maintain a warm, confident baseline tone
- Vary pitch and pace for engagement
- Use strategic pauses for emphasis
- Express genuine enthusiasm appropriately

Power Phrases & Techniques:
{techniques}

Communication Strategies:
{strategies}

Objection Response Templates:
{objections}

BEHAVIORAL GUIDELINES:

Do's:
{guidelines}

KEY CONVERSATION FLOWS:
{key_phrases}

META INSTRUCTIONS:
1. Always maintain natural conversation flow
2. Adapt responses based on customer's emotional state
3. Use silence strategically - allow customer to process
4. Mirror customer's speech pattern while staying professional
5. Break complex information into digestible segments
6. Use verbal nods and acknowledgments appropriately
7. Recover gracefully from any misunderstandings
8. Stay focused on customer's needs and goals

ETHICAL FRAMEWORK:
1. Always prioritize customer's best interests
2. Never make false or exaggerated claims
3. Respect privacy and confidentiality
4. Be transparent about limitations
5. Maintain professional boundaries

Remember: Your goal is to be helpful and genuine, not pushy or manipulative. Build trust through authenticity and expertise."""

            # Format sales techniques
            techniques_section = ""
            for technique in analysis_data.get("sales_techniques", []):
                techniques_section += f"• {technique.get('name', 'Technique').upper()}\n"
                if technique.get('description'):
                    techniques_section += f"  Description: {technique.get('description')}\n"
                if technique.get('examples'):
                    techniques_section += "  Examples:\n"
                    for example in technique.get('examples'):
                        techniques_section += f'    - "{example}"\n'
                if technique.get('effectiveness'):
                    techniques_section += f"  When to use: {technique.get('effectiveness')}\n"
                techniques_section += "\n"

            # Format communication strategies
            strategies_section = ""
            for strategy in analysis_data.get("communication_strategies", []):
                strategies_section += f"• {strategy.get('type', 'Strategy').upper()}\n"
                if strategy.get('description'):
                    strategies_section += f"  Description: {strategy.get('description')}\n"
                if strategy.get('examples'):
                    strategies_section += "  Examples:\n"
                    for example in strategy.get('examples'):
                        strategies_section += f'    - "{example}"\n'
                if strategy.get('effectiveness'):
                    strategies_section += f"  Best practice: {strategy.get('effectiveness')}\n"
                strategies_section += "\n"

            # Format objection handling
            objections_section = ""
            for objection in analysis_data.get("objection_handling", []):
                objections_section += f"• WHEN CUSTOMER SAYS: {objection.get('name', 'Objection')}\n"
                if objection.get('description'):
                    objections_section += f"  Response: {objection.get('description')}\n"
                if objection.get('examples'):
                    objections_section += "  Examples:\n"
                    for example in objection.get('examples'):
                        objections_section += f'    - "{example}"\n'
                if objection.get('effectiveness'):
                    objections_section += f"  Note: {objection.get('effectiveness')}\n"
                objections_section += "\n"

            # Format voice agent guidelines
            guidelines_section = "DO:\n"
            donts_section = "\nDON'T:\n"
            
            for guideline in analysis_data.get("voice_agent_guidelines", []):
                if guideline.get('name') == 'Do':
                    guidelines_section += f"• {guideline.get('description')}\n"
                    if guideline.get('examples'):
                        for example in guideline.get('examples'):
                            guidelines_section += f'  - "{example}"\n'
                elif guideline.get('name') == 'Don\'t':
                    donts_section += f"• {guideline.get('description')}\n"
                    if guideline.get('examples'):
                        for example in guideline.get('examples'):
                            donts_section += f'  - "{example}"\n'

            guidelines_section += donts_section

            # Extract key phrases from examples
            key_phrases_section = ""
            for section in [analysis_data.get("sales_techniques", []), 
                           analysis_data.get("communication_strategies", []),
                           analysis_data.get("voice_agent_guidelines", [])]:
                for item in section:
                    if item.get('examples'):
                        for example in item.get('examples'):
                            key_phrases_section += f"• \"{example}\"\n"

            # Format the final prompt
            formatted_prompt = prompt.format(
                techniques=techniques_section or "No specific techniques identified",
                strategies=strategies_section or "No specific strategies identified",
                objections=objections_section or "No specific objection handling identified",
                guidelines=guidelines_section or "No specific guidelines identified",
                key_phrases=key_phrases_section or "No specific key phrases identified"
            )
            
            return formatted_prompt
            
        except Exception as e:
            logger.error(f"Error generating voice prompt: {str(e)}", exc_info=True)
            return "Error generating voice prompt. Please check the logs for details."