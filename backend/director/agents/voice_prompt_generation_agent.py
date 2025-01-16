import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from pydantic import BaseModel
import json
import re

from director.agents.base import BaseAgent, AgentResponse, AgentStatus
from director.core.session import TextContent, MsgStatus, OutputMessage, Session
from director.tools.anthropic_tool import AnthropicTool
from director.llm.base import LLMResponseStatus

logger = logging.getLogger(__name__)

class VoicePromptContent(TextContent):
    """Content type for dynamic voice prompt results"""
    prompt_data: Dict = {}
    context_metadata: Dict = {}
    adaptation_rules: Dict = {}
    
    def __init__(
        self, 
        prompt_data: Dict = None, 
        context_metadata: Dict = None,
        adaptation_rules: Dict = None, 
        **kwargs
    ):
        super().__init__(**kwargs)
        self.prompt_data = prompt_data if prompt_data is not None else {}
        self.context_metadata = context_metadata if context_metadata is not None else {}
        self.adaptation_rules = adaptation_rules if adaptation_rules is not None else {}

    def to_dict(self) -> Dict:
        base_dict = super().to_dict()
        base_dict.update({
            "prompt_data": self.prompt_data,
            "context_metadata": self.context_metadata,
            "adaptation_rules": self.adaptation_rules
        })
        return base_dict

class VoicePromptGenerationAgent(BaseAgent):
    """Agent for generating flexible and context-aware voice prompts"""
    
    def __init__(self, session: Session, **kwargs):
        self.agent_name = "voice_prompt_generation"
        self.description = "Generates dynamic voice prompts with context adaptation"
        self.parameters = self.get_parameters()
        super().__init__(session=session, **kwargs)
        
        # Initialize Anthropic
        self.prompt_llm = kwargs.get('prompt_llm') or AnthropicTool()

    def get_parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "structured_data": {
                    "type": "object",
                    "description": "Structured data from analysis"
                },
                "yaml_config": {
                    "type": "object",
                    "description": "YAML configuration settings"
                },
                "context": {
                    "type": "object",
                    "description": "Current conversation context",
                    "default": {}
                },
                "style": {
                    "type": "string",
                    "enum": ["natural", "professional", "friendly", "dynamic"],
                    "default": "dynamic",
                    "description": "Voice prompt style"
                }
            },
            "required": ["structured_data", "yaml_config"],
            "description": "Generates dynamic voice prompts based on context and configuration"
        }

    def _get_prompt_template(self, style: str, context: Dict, structured_data: Dict, yaml_config: Dict) -> List[Dict[str, str]]:
        """Generate appropriate prompt template based on style, context, and analysis"""
        system_prompt = """You are an expert voice prompt architect specializing in dynamic AI conversations.
Your core competencies include:
1. Sales psychology and conversation dynamics
2. Voice modulation and emotional resonance
3. Natural language pattern recognition
4. Adaptive response strategy design

Your responsibility is to generate voice prompts that are:
- Contextually aware
- Emotionally intelligent
- Naturally adaptive
- Style-consistent

Your output must be in the following JSON format:
{
    "prompt": {
        "content": "The actual voice prompt content",
        "tone_guidance": {
            "pitch": "Specific pitch guidance",
            "rate": "Speech rate guidance",
            "energy": "Energy level guidance"
        },
        "adaptation_rules": {
            "context_triggers": ["List of specific situations that trigger adaptations"],
            "response_patterns": ["Patterns for different response types"],
            "transitions": ["Natural transition phrases"]
        }
    },
    "metadata": {
        "style": "Style used",
        "context_awareness": ["Specific context elements addressed"],
        "emotional_resonance": ["Emotional aspects considered"]
    }
}"""

        # Process structured data insights
        analysis_insights = self._extract_analysis_insights(structured_data)
        
        # Get style-specific configuration
        style_config = self._get_style_config(style, yaml_config)
        
        # Process context analysis
        context_analysis = self._analyze_context(context)
        
        user_prompt = f"""Generate a {style} voice prompt based on the following analysis and configuration:

ANALYSIS INSIGHTS:
{json.dumps(analysis_insights, indent=2)}

STYLE CONFIGURATION:
{json.dumps(style_config, indent=2)}

CONTEXT ANALYSIS:
{json.dumps(context_analysis, indent=2)}

Requirements:
1. Maintain {style} style characteristics
2. Incorporate analysis insights naturally
3. Follow tone and pacing guidelines
4. Include adaptation triggers
5. Enable flexible responses

The prompt should feel natural while maintaining professional standards and incorporating the analyzed patterns."""

        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

    def _extract_analysis_insights(self, structured_data: Dict) -> Dict:
        """Extract key insights from structured data"""
        insights = {
            "key_patterns": [],
            "communication_style": {},
            "effectiveness_indicators": [],
            "recommended_approaches": []
        }
        
        try:
            # Extract key patterns
            if "patterns" in structured_data:
                insights["key_patterns"] = structured_data["patterns"]
            
            # Extract communication style
            if "communication" in structured_data:
                insights["communication_style"] = structured_data["communication"]
            
            # Extract effectiveness indicators
            if "effectiveness" in structured_data:
                insights["effectiveness_indicators"] = structured_data["effectiveness"]
            
            # Extract recommended approaches
            if "recommendations" in structured_data:
                insights["recommended_approaches"] = structured_data["recommendations"]
                
        except Exception as e:
            logger.warning(f"Error extracting analysis insights: {str(e)}")
            
        return insights

    def _get_style_config(self, style: str, yaml_config: Dict) -> Dict:
        """Get style-specific configuration"""
        style_configs = {
            "professional": {
                "tone": {
                    "base": "measured",
                    "modulation": "minimal",
                    "formality": "high"
                },
                "pacing": {
                    "rate": "moderate",
                    "pauses": "structured",
                    "emphasis": "key-points"
                }
            },
            "natural": {
                "tone": {
                    "base": "conversational",
                    "modulation": "dynamic",
                    "formality": "moderate"
                },
                "pacing": {
                    "rate": "variable",
                    "pauses": "natural",
                    "emphasis": "contextual"
                }
            },
            "friendly": {
                "tone": {
                    "base": "warm",
                    "modulation": "expressive",
                    "formality": "low"
                },
                "pacing": {
                    "rate": "relaxed",
                    "pauses": "natural",
                    "emphasis": "emotional"
                }
            },
            "dynamic": {
                "tone": {
                    "base": "adaptive",
                    "modulation": "responsive",
                    "formality": "flexible"
                },
                "pacing": {
                    "rate": "adaptive",
                    "pauses": "contextual",
                    "emphasis": "dynamic"
                }
            }
        }
        
        # Get base style configuration
        config = style_configs.get(style, style_configs["dynamic"])
        
        # Override with YAML config if provided
        if yaml_config and "voice_settings" in yaml_config:
            voice_settings = yaml_config["voice_settings"]
            if "tone" in voice_settings:
                config["tone"].update(voice_settings["tone"])
            if "pacing" in voice_settings:
                config["pacing"].update(voice_settings["pacing"])
                
        return config

    def _analyze_context(self, context: Dict) -> Dict:
        """Analyze conversation context for adaptation"""
        try:
            # Extract key context elements
            current_state = context.get('current_state', {})
            history = context.get('history', [])
            user_preferences = context.get('user_preferences', {})
            
            # Analyze patterns and transitions
            analysis = {
                "state": current_state,
                "patterns": self._identify_patterns(history),
                "preferences": user_preferences,
                "adaptations": self._generate_adaptations(current_state, history)
            }
            
            return analysis
        except Exception as e:
            logger.warning(f"Error analyzing context: {str(e)}")
            return {}

    def _identify_patterns(self, history: List) -> Dict:
        """Identify conversation patterns from history"""
        try:
            patterns = {
                "response_types": {},
                "transitions": [],
                "common_flows": [],
                "user_behaviors": {}
            }
            
            # Analyze conversation history
            for interaction in history:
                # Extract and categorize patterns
                response_type = interaction.get('type')
                if response_type:
                    patterns['response_types'][response_type] = \
                        patterns['response_types'].get(response_type, 0) + 1
                
                # Track transitions
                if len(patterns['transitions']) < 10:  # Keep last 10 transitions
                    patterns['transitions'].append({
                        'from': interaction.get('from_state'),
                        'to': interaction.get('to_state')
                    })
            
            return patterns
        except Exception as e:
            logger.warning(f"Error identifying patterns: {str(e)}")
            return {}

    def _generate_adaptations(self, current_state: Dict, history: List) -> Dict:
        """Generate context-based adaptation rules"""
        try:
            adaptations = {
                "tone_adjustments": {},
                "pacing_rules": {},
                "response_triggers": [],
                "recovery_strategies": {}
            }
            
            # Generate adaptation rules based on state and history
            if current_state.get('emotion'):
                adaptations['tone_adjustments']['emotion'] = \
                    self._map_emotion_to_tone(current_state['emotion'])
            
            # Add recovery strategies for common scenarios
            adaptations['recovery_strategies'] = {
                "clarification": "Maintain current context while seeking clarity",
                "correction": "Acknowledge and smoothly redirect",
                "missing_info": "Naturally request additional details"
            }
            
            return adaptations
        except Exception as e:
            logger.warning(f"Error generating adaptations: {str(e)}")
            return {}

    def _map_emotion_to_tone(self, emotion: str) -> Dict:
        """Map emotional state to voice tone adjustments"""
        tone_mappings = {
            "positive": {
                "pitch": "medium-high",
                "rate": "moderate",
                "energy": "high"
            },
            "neutral": {
                "pitch": "medium",
                "rate": "moderate",
                "energy": "medium"
            },
            "negative": {
                "pitch": "medium-low",
                "rate": "slower",
                "energy": "low"
            }
        }
        return tone_mappings.get(emotion, tone_mappings["neutral"])

    def run(
        self,
        structured_data: Dict,
        yaml_config: Dict,
        context: Dict = None,
        style: str = "dynamic",
        *args,
        **kwargs
    ) -> AgentResponse:
        """Generate dynamic voice prompts based on context and configuration"""
        try:
            if not structured_data or not yaml_config:
                raise ValueError("Both structured data and YAML config are required")

            context = context or {}
            
            # Initialize content
            text_content = VoicePromptContent(
                prompt_data={},
                context_metadata={},
                adaptation_rules={},
                agent_name=self.agent_name,
                status=MsgStatus.progress,
                status_message="Starting voice prompt generation...",
                text="Processing inputs..."
            )
            self.output_message.add_content(text_content)
            self.output_message.actions.append("Beginning prompt generation...")
            self.output_message.push_update()

            # Analyze context
            context_analysis = self._analyze_context(context)
            
            # Generate prompt with enhanced template
            messages = self._get_prompt_template(
                style=style,
                context=context_analysis,
                structured_data=structured_data,
                yaml_config=yaml_config
            )
            
            logger.info("Requesting prompt generation from Anthropic")
            response = self.prompt_llm.chat_completions(
                messages=messages,
                temperature=0.7,
                max_tokens=2048
            )
            
            if response.status == LLMResponseStatus.ERROR:
                raise Exception(f"Anthropic prompt generation failed: {response.message}")

            # Parse and validate the response
            try:
                prompt_data = json.loads(response.content)
            except json.JSONDecodeError:
                logger.warning("Failed to parse JSON response, attempting extraction")
                # Try to extract JSON from markdown if present
                match = re.search(r"```json\n(.*?)\n```", response.content, re.DOTALL)
                if match:
                    prompt_data = json.loads(match.group(1))
                else:
                    raise ValueError("Could not parse prompt generation response")

            # Add metadata
            context_metadata = {
                "version": "1.0",
                "timestamp": datetime.now().isoformat(),
                "style": style,
                "context_analysis": context_analysis
            }

            # Store results
            text_content.prompt_data = prompt_data["prompt"]
            text_content.context_metadata = {**context_metadata, **prompt_data["metadata"]}
            text_content.adaptation_rules = prompt_data["prompt"]["adaptation_rules"]
            text_content.text = prompt_data["prompt"]["content"]
            text_content.status = MsgStatus.success
            text_content.status_message = "Voice prompt generated"
            
            self.output_message.actions.append("Prompt generation completed")
            self.output_message.push_update()
            
            logger.info("Voice prompt generated successfully")
            return AgentResponse(
                status=AgentStatus.SUCCESS,
                message="Voice prompt generated successfully",
                data={
                    "prompt_data": prompt_data["prompt"],
                    "context_metadata": context_metadata,
                    "adaptation_rules": prompt_data["prompt"]["adaptation_rules"]
                }
            )
            
        except Exception as e:
            logger.error(f"Error in prompt generation: {str(e)}", exc_info=True)
            if 'text_content' in locals():
                text_content.status = MsgStatus.error
                text_content.status_message = f"Prompt generation failed: {str(e)}"
                self.output_message.push_update()
            return AgentResponse(
                status=AgentStatus.ERROR,
                message=str(e),
                data={"error": str(e)}
            ) 