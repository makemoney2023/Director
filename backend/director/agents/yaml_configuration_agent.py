import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
import yaml
from pydantic import BaseModel
import json
import time

from director.agents.base import BaseAgent, AgentResponse, AgentStatus
from director.core.session import TextContent, MsgStatus, OutputMessage, Session
from director.tools.anthropic_tool import AnthropicTool
from director.llm.base import LLMResponseStatus
from director.utils.supabase import SupabaseVectorStore
from director.llm.openai import OpenAI

logger = logging.getLogger(__name__)

class YAMLContent(TextContent):
    """Content type for YAML configuration results"""
    yaml_data: Dict = {}
    config_metadata: Dict = {}
    
    def __init__(self, yaml_data: Dict = None, config_metadata: Dict = None, **kwargs):
        super().__init__(**kwargs)
        self.yaml_data = yaml_data if yaml_data is not None else {}
        self.config_metadata = config_metadata if config_metadata is not None else {}

    def to_dict(self) -> Dict:
        base_dict = super().to_dict()
        base_dict.update({
            "yaml_data": self.yaml_data,
            "config_metadata": self.config_metadata
        })
        return base_dict

class YAMLConfigurationAgent(BaseAgent):
    """Agent for generating YAML configurations from analysis and structured data"""
    
    def __init__(self, session: Session, **kwargs):
        self.agent_name = "yaml_configuration"
        self.description = "Generates YAML configurations from analysis"
        self.parameters = self.get_parameters()
        super().__init__(session=session, **kwargs)
        
        # Initialize OpenAI and Vector Store
        self.config_llm = kwargs.get('config_llm') or OpenAI()
        self.vector_store = SupabaseVectorStore()

    def get_parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "analysis": {
                    "type": "string",
                    "description": "The sales analysis to configure"
                },
                "structured_data": {
                    "type": "object",
                    "description": "The structured data to configure"
                },
                "config_type": {
                    "type": "string",
                    "enum": ["voice", "system", "training", "complete"],
                    "default": "complete",
                    "description": "The type of configuration to generate"
                }
            },
            "required": ["analysis", "structured_data"],
            "description": "Generates YAML configurations from analysis and structured data"
        }

    def _get_config_prompt(self, analysis: str, structured_data: Dict, config_type: str) -> List[Dict[str, str]]:
        """Generate appropriate prompt for YAML configuration generation"""
        system_prompt = """You are an expert in creating YAML configurations for AI voice agents. Your task is to generate clear, well-organized YAML configurations that capture all necessary settings and parameters.

Your output must be valid YAML and should include:

1. METADATA
- Version information
- Generation timestamp
- Model configurations
- Usage guidelines

2. VOICE SETTINGS
- Base characteristics
  * Tone parameters
  * Pacing controls
  * Expression settings
- Adaptation rules
  * Context-based adjustments
  * Emotional responses
  * Energy level modulation

3. CONVERSATION FRAMEWORK
- Opening strategies
- Discovery techniques
- Solution presentation
- Objection handling
- Closing approaches

4. COMMUNICATION PATTERNS
- Response templates
- Key phrases
- Transition strategies
- Recovery patterns

5. BEHAVIORAL GUIDELINES
- Core principles
- Ethical boundaries
- Professional standards
- Adaptation rules

FORMAT REQUIREMENTS:
1. Use clear, hierarchical structure
2. Include descriptive comments
3. Group related settings
4. Use consistent indentation
5. Follow YAML best practices

The output should be immediately usable for voice agent configuration."""

        user_prompt = f"""Convert this analysis and structured data into a {config_type} YAML configuration for an AI voice agent.

The configuration should:
1. Capture all voice and conversation parameters
2. Include behavioral guidelines
3. Define adaptation rules
4. Specify communication patterns
5. Set quality thresholds

Analysis:
{analysis}

Structured Data:
{json.dumps(structured_data, indent=2)}

Required sections:
1. metadata
2. voice_settings
3. conversation_framework
4. communication_patterns
5. behavioral_guidelines
6. quality_thresholds

Remember to:
- Use descriptive comments
- Include all techniques from the analysis
- Define clear adaptation rules
- Specify response patterns
- Set appropriate thresholds"""

        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

    def _find_similar_configs(self, config_type: str) -> List[Dict]:
        """Find similar YAML configurations in the codebase"""
        try:
            # For now, return empty list until we implement proper config search
            return []
        except Exception as e:
            logger.warning(f"Error finding similar configs: {str(e)}")
            return []

    def _save_config(self, config: Dict, config_type: str) -> str:
        """Save the YAML configuration to a file"""
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"config/{config_type}_config_{timestamp}.yaml"
            
            # Add header comments
            header_comment = f"""# AI Voice Agent Configuration
# Type: {config_type}
# Generated: {datetime.now().isoformat()}
# 
# This configuration file defines the behavior and characteristics
# of an AI voice agent for sales conversations. It includes:
# - Voice characteristics and adaptation rules
# - Conversation framework and patterns
# - Communication strategies and guidelines
# - Quality thresholds and monitoring parameters
#
"""
            
            # Convert to YAML with comments preserved
            yaml_content = yaml.dump(
                config,
                default_flow_style=False,
                sort_keys=False,
                allow_unicode=True,
                width=80,
                indent=2
            )
            
            # Combine header and content
            full_content = header_comment + yaml_content
            
            # Ensure config directory exists
            import os
            os.makedirs("config", exist_ok=True)
            
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(full_content)
            
            return filename
        except Exception as e:
            logger.warning(f"Error saving configuration: {str(e)}")
            return None

    def _validate_yaml(self, content: str) -> Dict:
        """Validate and clean YAML content"""
        try:
            # First try to parse as is
            yaml_data = yaml.safe_load(content)
            
            # Validate required sections
            required_sections = [
                "metadata",
                "voice_settings",
                "conversation_framework",
                "communication_patterns",
                "behavioral_guidelines",
                "quality_thresholds"
            ]
            
            missing_sections = [section for section in required_sections if section not in yaml_data]
            if missing_sections:
                raise ValueError(f"Missing required sections: {', '.join(missing_sections)}")
            
            # Validate voice settings
            if "voice_settings" in yaml_data:
                required_voice_settings = {
                    "tone": ["base_tone", "variations", "adaptations"],
                    "pacing": ["base_speed", "dynamic_range", "situational_adjustments"],
                    "expression": ["emphasis_patterns", "emotional_markers", "pause_points"],
                    "adaptation": ["customer_matching", "context_sensitivity", "emotional_mirroring", "response_calibration"]
                }
                
                for setting, required_fields in required_voice_settings.items():
                    if setting not in yaml_data["voice_settings"]:
                        raise ValueError(f"Missing required voice setting: {setting}")
                    
                    missing_fields = [field for field in required_fields 
                                    if field not in yaml_data["voice_settings"][setting]]
                    if missing_fields:
                        raise ValueError(f"Missing required fields in {setting}: {', '.join(missing_fields)}")
            
            # Validate conversation framework
            required_framework_sections = {
                "opening": ["approach", "key_elements", "timing"],
                "discovery": ["question_types", "focus_areas", "techniques"],
                "presentation": ["structure", "emphasis", "techniques"],
                "objection_handling": ["approach", "key_principles", "responses"],
                "closing": ["style", "techniques", "timing_triggers"]
            }
            
            for section, required_fields in required_framework_sections.items():
                if section not in yaml_data["conversation_framework"]:
                    raise ValueError(f"Missing required conversation framework section: {section}")
                
                missing_fields = [field for field in required_fields 
                                if field not in yaml_data["conversation_framework"][section]]
                if missing_fields:
                    raise ValueError(f"Missing required fields in {section}: {', '.join(missing_fields)}")
            
            # Validate communication patterns
            required_pattern_fields = ["power_phrases", "transition_phrases", "emphasis_patterns", "response_templates"]
            missing_pattern_fields = [field for field in required_pattern_fields 
                                    if field not in yaml_data["communication_patterns"]]
            if missing_pattern_fields:
                raise ValueError(f"Missing required communication pattern fields: {', '.join(missing_pattern_fields)}")
            
            # Validate behavioral guidelines
            required_guideline_fields = ["core_principles", "do", "dont", "adaptations"]
            missing_guideline_fields = [field for field in required_guideline_fields 
                                      if field not in yaml_data["behavioral_guidelines"]]
            if missing_guideline_fields:
                raise ValueError(f"Missing required behavioral guideline fields: {', '.join(missing_guideline_fields)}")
            
            # Validate quality thresholds
            required_threshold_sections = {
                "response_time": ["standard", "max_pause", "min_pause"],
                "speech_metrics": ["clarity", "pace", "tone_consistency"],
                "interaction_quality": ["turn_taking", "engagement", "effectiveness"]
            }
            
            for section, required_fields in required_threshold_sections.items():
                if section not in yaml_data["quality_thresholds"]:
                    raise ValueError(f"Missing required quality threshold section: {section}")
                
                missing_fields = [field for field in required_fields 
                                if field not in yaml_data["quality_thresholds"][section]]
                if missing_fields:
                    raise ValueError(f"Missing required fields in {section}: {', '.join(missing_fields)}")
            
            # Ensure non-empty values in critical sections
            if not yaml_data["behavioral_guidelines"]["core_principles"]:
                yaml_data["behavioral_guidelines"]["core_principles"] = ["Focus on customer needs", "Build trust through authenticity", "Practice active listening"]
            
            if not yaml_data["behavioral_guidelines"]["do"]:
                yaml_data["behavioral_guidelines"]["do"] = ["Maintain professional tone", "Show genuine interest", "Follow conversation framework"]
            
            if not yaml_data["behavioral_guidelines"]["dont"]:
                yaml_data["behavioral_guidelines"]["dont"] = ["Interrupt customer", "Use aggressive language", "Rush through discovery phase"]
            
            if not yaml_data["communication_patterns"]["power_phrases"]:
                yaml_data["communication_patterns"]["power_phrases"] = ["I understand your perspective", "Let me show you how", "What are your thoughts on"]
            
            return yaml_data
            
        except yaml.YAMLError:
            # If fails, try to extract YAML from markdown
            try:
                # Look for YAML code blocks
                if "```yaml" in content:
                    yaml_content = content.split("```yaml")[1].split("```")[0]
                    return self._validate_yaml(yaml_content)
                # Look for YAML content
                elif "---" in content:
                    return self._validate_yaml(content)
                else:
                    raise ValueError("Could not extract valid YAML from content")
            except Exception as e:
                raise ValueError(f"YAML validation failed: {str(e)}")
        except Exception as e:
            raise ValueError(f"YAML validation failed: {str(e)}")

    def _generate_yaml_config(self, analysis: str, structured_data: Dict) -> str:
        """Generate YAML configuration from analysis and structured data using OpenAI's function calling"""
        try:
            # Define the function schema for OpenAI
            function_schema = {
                "name": "generate_voice_agent_config",
                "description": "Generate a complete YAML configuration for an AI voice sales agent",
                "parameters": {
                    "type": "object",
                    "required": ["metadata", "voice_settings", "conversation_framework", "communication_patterns", "behavioral_guidelines", "quality_thresholds"],
                    "properties": {
                        "metadata": {
                            "type": "object",
                            "required": ["version", "type", "description", "last_updated"],
                            "properties": {
                                "version": { "type": "string" },
                                "type": { "type": "string" },
                                "description": { "type": "string" },
                                "last_updated": { "type": "string" }
                            }
                        },
                        "voice_settings": {
                            "type": "object",
                            "required": ["tone", "pacing", "expression", "adaptation"],
                            "properties": {
                                "tone": {
                                    "type": "object",
                                    "properties": {
                                        "base_tone": { "type": "string" },
                                        "variations": { "type": "array", "items": { "type": "string" }},
                                        "adaptations": {
                                            "type": "object",
                                            "properties": {
                                                "objection_handling": { "type": "string" },
                                                "value_presentation": { "type": "string" },
                                                "closing": { "type": "string" }
                                            }
                                        }
                                    }
                                },
                                "pacing": {
                                    "type": "object",
                                    "properties": {
                                        "base_speed": { "type": "string" },
                                        "dynamic_range": { "type": "array", "items": { "type": "string" }},
                                        "situational_adjustments": { "type": "object" }
                                    }
                                },
                                "expression": {
                                    "type": "object",
                                    "properties": {
                                        "emphasis_patterns": { "type": "array", "items": { "type": "string" }},
                                        "emotional_markers": { "type": "array", "items": { "type": "string" }},
                                        "pause_points": { "type": "array", "items": { "type": "string" }}
                                    }
                                },
                                "adaptation": {
                                    "type": "object",
                                    "properties": {
                                        "customer_matching": { "type": "boolean" },
                                        "context_sensitivity": { "type": "boolean" },
                                        "emotional_mirroring": { "type": "boolean" },
                                        "response_calibration": { "type": "object" }
                                    }
                                }
                            }
                        },
                        "conversation_framework": {
                            "type": "object",
                            "required": ["opening", "discovery", "presentation", "objection_handling", "closing"],
                            "properties": {
                                "opening": {
                                    "type": "object",
                                    "properties": {
                                        "approach": { "type": "string" },
                                        "key_elements": { "type": "array", "items": { "type": "string" }},
                                        "timing": { "type": "string" }
                                    }
                                },
                                "discovery": {
                                    "type": "object",
                                    "properties": {
                                        "question_types": { "type": "array", "items": { "type": "string" }},
                                        "focus_areas": { "type": "array", "items": { "type": "string" }},
                                        "techniques": { "type": "array", "items": { "type": "object" }}
                                    }
                                },
                                "presentation": {
                                    "type": "object",
                                    "properties": {
                                        "structure": { "type": "array", "items": { "type": "string" }},
                                        "emphasis": { "type": "string" },
                                        "techniques": { "type": "array", "items": { "type": "object" }}
                                    }
                                },
                                "objection_handling": {
                                    "type": "object",
                                    "properties": {
                                        "approach": { "type": "string" },
                                        "key_principles": { "type": "array", "items": { "type": "string" }},
                                        "responses": { "type": "object" }
                                    }
                                },
                                "closing": {
                                    "type": "object",
                                    "properties": {
                                        "style": { "type": "string" },
                                        "techniques": { "type": "array", "items": { "type": "object" }},
                                        "timing_triggers": { "type": "array", "items": { "type": "string" }}
                                    }
                                }
                            }
                        },
                        "communication_patterns": {
                            "type": "object",
                            "required": ["power_phrases", "transition_phrases", "emphasis_patterns", "response_templates"],
                            "properties": {
                                "power_phrases": { "type": "array", "items": { "type": "string" }},
                                "transition_phrases": { "type": "array", "items": { "type": "string" }},
                                "emphasis_patterns": { "type": "array", "items": { "type": "object" }},
                                "response_templates": { "type": "object" }
                            }
                        },
                        "behavioral_guidelines": {
                            "type": "object",
                            "required": ["core_principles", "do", "dont", "adaptations"],
                            "properties": {
                                "core_principles": { "type": "array", "items": { "type": "string" }},
                                "do": { "type": "array", "items": { "type": "string" }},
                                "dont": { "type": "array", "items": { "type": "string" }},
                                "adaptations": {
                                    "type": "object",
                                    "properties": {
                                        "to_customer_style": { "type": "boolean" },
                                        "to_conversation_stage": { "type": "boolean" },
                                        "to_emotional_state": { "type": "boolean" }
                                    }
                                }
                            }
                        },
                        "quality_thresholds": {
                            "type": "object",
                            "required": ["response_time", "speech_metrics", "interaction_quality"],
                            "properties": {
                                "response_time": {
                                    "type": "object",
                                    "properties": {
                                        "standard": { "type": "string" },
                                        "max_pause": { "type": "string" },
                                        "min_pause": { "type": "string" }
                                    }
                                },
                                "speech_metrics": {
                                    "type": "object",
                                    "properties": {
                                        "clarity": { "type": "object" },
                                        "pace": { "type": "object" },
                                        "tone_consistency": { "type": "object" }
                                    }
                                },
                                "interaction_quality": {
                                    "type": "object",
                                    "properties": {
                                        "turn_taking": { "type": "object" },
                                        "engagement": { "type": "object" },
                                        "effectiveness": { "type": "object" }
                                    }
                                }
                            }
                        }
                    }
                }
            }

            # Create prompt for OpenAI
            messages = [
                {"role": "system", "content": "You are an expert in creating YAML configurations for AI voice agents. Generate a complete configuration based on the provided analysis and structured data."},
                {"role": "user", "content": f"""Generate a complete YAML configuration for an AI voice sales agent based on this analysis and structured data.

Analysis:
{analysis}

Structured Data:
{json.dumps(structured_data, indent=2)}"""}
            ]

            # Call OpenAI with function calling
            response = self.config_llm.chat_completions(
                messages=messages,
                tools=[function_schema],
                temperature=0.7
            )

            if response.status == LLMResponseStatus.ERROR:
                raise Exception(f"Configuration generation failed: {response.message}")

            # Extract the YAML data from the function call
            if response.tool_calls and response.tool_calls[0]["tool"]["name"] == "generate_voice_agent_config":
                yaml_data = json.loads(response.tool_calls[0]["tool"]["arguments"])
            else:
                raise Exception("No valid configuration generated")

            # Convert to YAML string with proper formatting
            yaml_str = """# AI Voice Sales Agent Configuration
# Generated: {timestamp}
# Purpose: Define voice characteristics, conversation patterns, and behavioral guidelines
# Version: 1.0

{yaml_content}""".format(
                timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                yaml_content=yaml.dump(yaml_data, default_flow_style=False, sort_keys=False, allow_unicode=True)
            )

            # Validate the configuration before returning
            self._validate_yaml(yaml_str)

            return yaml_str

        except Exception as e:
            logger.error(f"Error generating YAML config: {str(e)}", exc_info=True)
            raise Exception(f"YAML configuration generation failed: {str(e)}")

    def _process_long_analysis(self, analysis: str) -> str:
        """Process long analysis text using vector search"""
        # Store the analysis in chunks
        transcript_id = self.vector_store.store_transcript(
            analysis,
            metadata={"type": "sales_analysis"}
        )
        
        # Search for relevant chunks based on key aspects
        key_aspects = [
            "sales techniques",
            "communication patterns",
            "objection handling",
            "voice characteristics",
            "behavioral guidelines"
        ]
        
        relevant_chunks = []
        for aspect in key_aspects:
            chunks = self.vector_store.search_similar_chunks(
                f"Find information about {aspect}",
                limit=2
            )
            relevant_chunks.extend(chunks)
        
        # Combine relevant chunks
        processed_analysis = "\n\n".join([
            f"# {chunk['similarity']:.2f} relevance:\n{chunk['chunk_text']}"
            for chunk in relevant_chunks
        ])
        
        return processed_analysis

    def run(
        self,
        analysis: str,
        structured_data: Dict,
        config_type: str = "complete",
        *args,
        **kwargs
    ) -> AgentResponse:
        """Generate YAML configuration from analysis and structured data"""
        try:
            if not analysis or not structured_data:
                raise ValueError("Both analysis and structured data are required")

            # Initialize content
            text_content = YAMLContent(
                yaml_data={},
                config_metadata={},
                agent_name=self.agent_name,
                status=MsgStatus.progress,
                status_message="Starting configuration generation...",
                text="Processing inputs..."
            )
            self.output_message.add_content(text_content)
            self.output_message.actions.append("Beginning configuration generation...")
            self.output_message.push_update()

            # Process long analysis using vector search
            processed_analysis = self._process_long_analysis(analysis)
            
            # Generate YAML configuration using OpenAI's function calling
            yaml_str = self._generate_yaml_config(processed_analysis, structured_data)
            
            # Validate and clean YAML
            yaml_data = self._validate_yaml(yaml_str)

            # Add metadata
            config_metadata = {
                "version": "1.0",
                "generated_at": datetime.now().isoformat(),
                "config_type": config_type,
                "source": {
                    "analysis": True,
                    "structured_data": True
                },
                "model": {
                    "name": "openai-gpt4",
                    "temperature": 0.7
                }
            }
            
            # Update metadata section
            if "metadata" not in yaml_data:
                yaml_data["metadata"] = {}
            yaml_data["metadata"].update(config_metadata)

            # Save the configuration
            config_file = self._save_config(yaml_data, config_type)

            # Store results
            text_content.yaml_data = yaml_data
            text_content.config_metadata = config_metadata
            text_content.text = f"""# YAML Configuration:
```yaml
{yaml_str}
```

# Voice Prompt:

You are an advanced AI voice sales agent, trained in high-performance sales techniques and emotional intelligence. Your goal is to engage in natural, persuasive sales conversations while maintaining unwavering professionalism.

## Context & Objectives:
This is a sales training focused on building confidence, handling objections, and mastering closing techniques. The emphasis is on transforming sales professionals into confident closers through proven psychological techniques.

### Key Techniques:
- Identity Shifting: Creating a confident sales persona
- Value Anchoring: Connecting price to long-term value
- Emotional Connection: Speaking to desires rather than logic
- Hypothetical Questioning: Bypassing initial resistance

### Identity & Persona:
- Embody a confident, professional sales identity
- Project unwavering confidence while maintaining authenticity
- Adapt tone and pace to match customer while staying authoritative
- Demonstrate deep product knowledge and genuine desire to help
- Maintain strong eye contact and assured presence

### Conversation Framework:
1. Opening (first 30 seconds):
   - Create a strong first impression with confident presence
   - Establish immediate familiarity
   - Create urgency while using permission-based language
   - Frame questions for positive responses
   - Tell stories to illustrate points"""
            text_content.status = MsgStatus.success
            text_content.status_message = "Configuration generated successfully"
            
            self.output_message.push_update()
            
            logger.info("YAML configuration generated successfully")
            return AgentResponse(
                status=AgentStatus.SUCCESS,
                message="Configuration generated successfully",
                data={
                    "yaml_config": yaml_data,
                    "config_type": config_type,
                    "config_file": config_file
                }
            )
            
        except Exception as e:
            logger.error(f"Error in configuration generation: {str(e)}", exc_info=True)
            if 'text_content' in locals():
                text_content.status = MsgStatus.error
                text_content.status_message = f"Configuration generation failed: {str(e)}"
                self.output_message.push_update()
            return AgentResponse(
                status=AgentStatus.ERROR,
                message=str(e),
                data={"error": str(e)}
            ) 