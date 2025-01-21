import logging
import json
from typing import Dict, List, Optional
from datetime import datetime
from pydantic import BaseModel
from openai import OpenAI

logger = logging.getLogger(__name__)

class AnalysisResult(BaseModel):
    """Model for storing analysis results"""
    raw_analysis: str
    structured_data: Dict
    voice_prompt: str
    metadata: Dict = {}

class SalesAnalysisTool:
    """Comprehensive tool for sales conversation analysis"""
    
    def __init__(self, api_key: str):
        self.client = OpenAI(api_key=api_key)
        self.model = "gpt-4-1106-preview"
        
    def generate_analysis(self, transcript: str) -> Optional[str]:
        """Generate markdown analysis of sales conversation"""
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": """You are an expert sales analyst. Generate a detailed markdown analysis of the sales conversation.
                        
Focus on:
1. Key sales techniques used
2. Communication strategies
3. Objection handling approaches
4. Voice agent guidelines

Format your response in clean markdown with clear sections and examples."""
                    },
                    {
                        "role": "user",
                        "content": f"Analyze this sales conversation transcript:\n\n{transcript}"
                    }
                ],
                temperature=0.7,
                max_tokens=4000
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Error generating analysis: {str(e)}")
            return None

    def generate_structured_data(self, analysis_text: str) -> Dict:
        """Extract structured data from analysis"""
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": """Extract structured data from the sales analysis. Return a JSON object with:
1. sales_techniques: List of techniques with examples and effectiveness
2. communication_strategies: Key communication approaches
3. objection_handling: List of objections and responses
4. key_metrics: Engagement, clarity, and effectiveness scores"""
                    },
                    {
                        "role": "user",
                        "content": f"Extract structured data from this analysis:\n\n{analysis_text}"
                    }
                ],
                temperature=0.3,
                max_tokens=2000,
                response_format={"type": "json_object"}
            )
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            logger.error(f"Error generating structured data: {str(e)}")
            return {}

    def generate_voice_prompt(self, analysis_text: str, structured_data: Dict) -> str:
        """Generate voice prompt from analysis"""
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": """Generate a concise, actionable voice prompt that starts with 'Hello!' and guides an AI agent.
Include:
1. Key approaches to use
2. Response patterns for common situations
3. Communication style guidelines
4. Specific examples of effective phrases"""
                    },
                    {
                        "role": "user",
                        "content": f"Generate a voice prompt based on this analysis and data:\n\nAnalysis:\n{analysis_text}\n\nStructured Data:\n{json.dumps(structured_data, indent=2)}"
                    }
                ],
                temperature=0.7,
                max_tokens=1000
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Error generating voice prompt: {str(e)}")
            return ""

    def analyze_conversation(self, transcript: str) -> Optional[AnalysisResult]:
        """Complete analysis pipeline"""
        try:
            # Generate raw analysis
            analysis_text = self.generate_analysis(transcript)
            if not analysis_text:
                return None

            # Extract structured data
            structured_data = self.generate_structured_data(analysis_text)
            
            # Generate voice prompt
            voice_prompt = self.generate_voice_prompt(analysis_text, structured_data)

            return AnalysisResult(
                raw_analysis=analysis_text,
                structured_data=structured_data,
                voice_prompt=voice_prompt,
                metadata={
                    "timestamp": datetime.now().isoformat(),
                    "model": self.model
                }
            )
        except Exception as e:
            logger.error(f"Error in analysis pipeline: {str(e)}")
            return None 