import os
import logging
from typing import Dict, List, Optional, Any

import anthropic
from anthropic import Anthropic

logger = logging.getLogger(__name__)

class AnthropicTool:
    """Tool for interacting with Anthropic's Claude API"""
    
    def __init__(self):
        self.api_key = os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable is not set")
        self.client = Anthropic(api_key=self.api_key)
        self.model = "claude-3-opus-20240229"  # Using the latest Claude model

    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs: Any
    ) -> Dict:
        """
        Send a chat completion request to Anthropic's Claude
        
        Args:
            messages: List of message dictionaries with 'role' and 'content'
            temperature: Controls randomness in responses
            max_tokens: Maximum tokens to generate
            **kwargs: Additional arguments to pass to the API
            
        Returns:
            Dict containing the response
        """
        try:
            # Convert messages to Anthropic format
            system_message = next((msg["content"] for msg in messages if msg["role"] == "system"), None)
            
            # Build messages in Anthropic format
            message_content = []
            for msg in messages:
                if msg["role"] != "system":  # System message handled separately
                    message_content.append({
                        "role": "assistant" if msg["role"] == "assistant" else "user",
                        "content": msg["content"]
                    })

            # Make the API call
            response = self.client.messages.create(
                model=self.model,
                messages=message_content,
                system=system_message,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs
            )

            return {
                "content": response.content[0].text,
                "model": response.model,
                "usage": {
                    "prompt_tokens": response.usage.input_tokens,
                    "completion_tokens": response.usage.output_tokens,
                    "total_tokens": response.usage.input_tokens + response.usage.output_tokens
                }
            }

        except Exception as e:
            logger.error(f"Error in Anthropic chat completion: {str(e)}")
            raise 