"""Edge Function for generating structured data from sales conversation analysis."""

from typing import Any, Dict, List
import json

from .base import BaseEdgeFunction
from director.utils.openai import OpenAI

class StructuredDataFunction(BaseEdgeFunction):
    """Edge Function for generating structured data from sales conversation analysis."""

    def __init__(self, session):
        super().__init__(session)
        self.openai = OpenAI()

    def validate_input(self, input_data: Dict[str, Any]) -> bool:
        """Validate the input data.
        
        Args:
            input_data: Input data containing transcript chunks and metadata
            
        Returns:
            True if valid, False otherwise
        """
        required_fields = ['video_id', 'transcript_chunks']
        return all(field in input_data for field in required_fields)

    async def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the structured data generation.
        
        Args:
            input_data: Dict containing:
                - video_id: ID of the video being processed
                - transcript_chunks: List of transcript chunks
                
        Returns:
            Dict containing structured analysis data
        """
        if not self.validate_input(input_data):
            raise ValueError("Invalid input data")

        try:
            # Combine transcript chunks
            transcript_text = " ".join([chunk['chunk_text'] for chunk in input_data['transcript_chunks']])

            # Generate structured analysis using OpenAI
            analysis = await self._analyze_transcript(transcript_text)

            # Store result
            result_id = self.store_result(
                video_id=input_data['video_id'],
                result=analysis,
                output_type='structured_data'
            )

            if result_id:
                analysis['id'] = result_id
                return analysis
            else:
                raise Exception("Failed to store analysis result")

        except Exception as e:
            self.session.logger.error(f"Error in structured data generation: {str(e)}")
            raise

    async def _analyze_transcript(self, transcript: str) -> Dict[str, Any]:
        """Analyze transcript using OpenAI.
        
        Args:
            transcript: Complete transcript text
            
        Returns:
            Dict containing structured analysis
        """
        prompt = self._generate_analysis_prompt(transcript)
        
        response = await self.openai.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are an expert sales conversation analyzer."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=2000
        )

        try:
            return json.loads(response.choices[0].message.content)
        except json.JSONDecodeError:
            self.session.logger.error("Failed to parse OpenAI response as JSON")
            return {
                "error": "Failed to generate structured data",
                "raw_response": response.choices[0].message.content
            }

    def _generate_analysis_prompt(self, transcript: str) -> str:
        """Generate the analysis prompt.
        
        Args:
            transcript: Complete transcript text
            
        Returns:
            Formatted prompt string
        """
        return f"""Analyze this sales conversation transcript and provide a structured JSON response with the following components:

1. Sales Techniques Used:
   - Name of technique
   - Description
   - Examples from transcript
   - Effectiveness assessment

2. Communication Strategies:
   - Type of strategy
   - Description
   - Examples from transcript
   - Effectiveness assessment

3. Objection Handling:
   - Objection raised
   - Response used
   - Examples from transcript
   - Effectiveness assessment

4. Voice Agent Guidelines:
   - Do's and Don'ts
   - Context for each guideline
   - Priority level

Transcript:
{transcript}

Format your response as a JSON object with these exact keys:
{{
    "sales_techniques": [{{
        "name": string,
        "description": string,
        "examples": [string],
        "effectiveness": string
    }}],
    "communication_strategies": [{{
        "type": string,
        "description": string,
        "examples": [string],
        "effectiveness": string
    }}],
    "objection_handling": [{{
        "objection": string,
        "response": string,
        "examples": [string],
        "effectiveness": string
    }}],
    "voice_agent_guidelines": [{{
        "type": "do"|"dont",
        "description": string,
        "context": string
    }}]
}}""" 