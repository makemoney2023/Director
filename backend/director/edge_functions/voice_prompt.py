"""Edge Function for generating voice prompts from structured sales data."""

from typing import Any, Dict, List
import json

from .base import BaseEdgeFunction
from director.utils.anthropic import Claude

class VoicePromptFunction(BaseEdgeFunction):
    """Edge Function for generating voice prompts from structured sales data."""

    def __init__(self, session):
        super().__init__(session)
        self.claude = Claude()

    def validate_input(self, input_data: Dict[str, Any]) -> bool:
        """Validate the input data.
        
        Args:
            input_data: Input data containing structured analysis and metadata
            
        Returns:
            True if valid, False otherwise
        """
        required_fields = ['video_id', 'structured_data']
        if not all(field in input_data for field in required_fields):
            return False
            
        required_structured_fields = [
            'sales_techniques',
            'communication_strategies',
            'objection_handling',
            'voice_agent_guidelines'
        ]
        return all(field in input_data['structured_data'] for field in required_structured_fields)

    async def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the voice prompt generation.
        
        Args:
            input_data: Dict containing:
                - video_id: ID of the video being processed
                - structured_data: Structured analysis data
                
        Returns:
            Dict containing voice prompt data
        """
        if not self.validate_input(input_data):
            raise ValueError("Invalid input data")

        try:
            # Generate voice prompt using Claude
            prompt_data = await self._generate_voice_prompt(input_data['structured_data'])

            # Store result
            result_id = self.store_result(
                video_id=input_data['video_id'],
                result=prompt_data,
                output_type='voice_prompt'
            )

            if result_id:
                prompt_data['id'] = result_id
                return prompt_data
            else:
                raise Exception("Failed to store voice prompt")

        except Exception as e:
            self.session.logger.error(f"Error in voice prompt generation: {str(e)}")
            raise

    async def _generate_voice_prompt(self, structured_data: Dict[str, Any]) -> Dict[str, Any]:
        """Generate voice prompt using Claude.
        
        Args:
            structured_data: Structured analysis data
            
        Returns:
            Dict containing voice prompt data
        """
        prompt = self._generate_prompt_template(structured_data)
        
        response = await self.claude.complete(
            prompt=prompt,
            max_tokens=2000,
            temperature=0.7
        )

        try:
            return json.loads(response)
        except json.JSONDecodeError:
            self.session.logger.error("Failed to parse Claude response as JSON")
            return {
                "error": "Failed to generate voice prompt",
                "raw_response": response
            }

    def _generate_prompt_template(self, structured_data: Dict[str, Any]) -> str:
        """Generate the prompt template.
        
        Args:
            structured_data: Structured analysis data
            
        Returns:
            Formatted prompt string
        """
        # Extract key components
        techniques = structured_data.get('sales_techniques', [])
        strategies = structured_data.get('communication_strategies', [])
        objections = structured_data.get('objection_handling', [])
        guidelines = structured_data.get('voice_agent_guidelines', [])

        prompt = """Based on the following sales conversation analysis, generate a comprehensive voice prompt for an AI agent. 
The prompt should include specific instructions for voice characteristics, conversation flow, and response patterns.

Format the response as a JSON object with these components:

{
    "voice_characteristics": {
        "tone": string,
        "pace": string,
        "style": string
    },
    "conversation_framework": {
        "opening": {
            "approach": string,
            "key_elements": [string]
        },
        "discovery": {
            "techniques": [string],
            "adaptations": {
                "positive_signals": [string],
                "negative_signals": [string]
            }
        },
        "closing": {
            "strategies": [string],
            "transitions": {
                "success_indicators": [string],
                "fallback_options": [string]
            }
        }
    },
    "response_patterns": {
        "key_phrases": [string],
        "objection_responses": [{
            "trigger": string,
            "response": string,
            "context": string
        }],
        "engagement_cues": [{
            "cue": string,
            "action": string
        }]
    }
}

Analysis Data:

Sales Techniques:
"""
        for technique in techniques[:3]:
            prompt += f"\n- {technique.get('name')}: {technique.get('description')}"
            if technique.get('examples'):
                prompt += f"\n  Example: {technique['examples'][0]}"

        prompt += "\n\nCommunication Strategies:"
        for strategy in strategies[:3]:
            prompt += f"\n- {strategy.get('type')}: {strategy.get('description')}"
            if strategy.get('examples'):
                prompt += f"\n  Example: {strategy['examples'][0]}"

        prompt += "\n\nObjection Handling:"
        for objection in objections[:3]:
            prompt += f"\n- When hearing: {objection.get('objection')}"
            prompt += f"\n  Respond with: {objection.get('response')}"

        prompt += "\n\nVoice Guidelines:"
        for guideline in guidelines:
            prompt += f"\n- {'Do' if guideline.get('type') == 'do' else 'Don\'t'}: {guideline.get('description')}"
            if guideline.get('context'):
                prompt += f"\n  Context: {guideline['context']}"

        return prompt 