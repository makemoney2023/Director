import os
import logging
import time
from typing import Dict, List, Optional, Any
from anthropic import Anthropic, APITimeoutError, APIError, APIConnectionError
from tenacity import retry, stop_after_attempt, wait_exponential
from director.llm.base import LLMResponse, LLMResponseStatus

logger = logging.getLogger(__name__)

class AnthropicTool:
    """Tool for interacting with Anthropic's Claude API"""
    
    def __init__(self):
        self.api_key = os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable is not set")
        self.client = Anthropic(api_key=self.api_key)
        self.model = "claude-3-5-sonnet-20241022"  # Using Claude 3.5 Sonnet
        self.timeout = 120  # 120 seconds timeout

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        reraise=True
    )
    def chat_completions(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs: Any
    ) -> LLMResponse:
        """
        Send a chat completion request to Anthropic's Claude
        
        Args:
            messages: List of message dictionaries with 'role' and 'content'
            temperature: Controls randomness in responses
            max_tokens: Maximum tokens to generate
            **kwargs: Additional arguments to pass to the API
            
        Returns:
            LLMResponse object containing the response
        """
        try:
            logger.info("=== Starting Anthropic Chat Completion ===")
            logger.info(f"Input messages: {messages}")
            logger.info(f"Temperature: {temperature}")
            logger.info(f"Max tokens: {max_tokens}")
            
            # Extract system message if present
            system_message = None
            formatted_messages = []
            
            for msg in messages:
                if msg["role"] == "system":
                    system_message = msg["content"]
                else:
                    formatted_messages.append({
                        "role": msg["role"],
                        "content": msg["content"]
                    })
            
            logger.info(f"System message: {system_message}")
            logger.info(f"Formatted messages: {formatted_messages}")
            
            # Make the API call with timeout
            logger.info("Making API call to Anthropic...")
            start_time = time.time()
            
            try:
                params = {
                    "model": self.model,
                    "messages": formatted_messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens if max_tokens else 8192,  # Sonnet max output tokens is 8192
                }
                
                if system_message:
                    params["system"] = system_message
                
                logger.info(f"API parameters: {params}")
                response = self.client.messages.create(**params)
                
                elapsed_time = time.time() - start_time
                logger.info(f"API call completed in {elapsed_time:.2f} seconds")
                logger.info(f"Response: {response}")
                
                return LLMResponse(
                    content=response.content[0].text,
                    send_tokens=response.usage.input_tokens,
                    recv_tokens=response.usage.output_tokens,
                    total_tokens=response.usage.input_tokens + response.usage.output_tokens,
                    finish_reason=response.stop_reason or "stop",
                    status=LLMResponseStatus.SUCCESS
                )
                
            except APITimeoutError:
                logger.error(f"API call timed out after {self.timeout} seconds")
                return LLMResponse(
                    content=f"Analysis timed out after {self.timeout} seconds. Please try with a shorter video or contact support.",
                    status=LLMResponseStatus.ERROR,
                    finish_reason="timeout"
                )
            except APIConnectionError as e:
                logger.error(f"Connection error: {str(e)}")
                return LLMResponse(
                    content="Failed to connect to the analysis service. Please try again later.",
                    status=LLMResponseStatus.ERROR,
                    finish_reason="connection_error"
                )
            except APIError as e:
                logger.error(f"API error: {str(e)}")
                return LLMResponse(
                    content=f"Analysis service error: {str(e)}",
                    status=LLMResponseStatus.ERROR,
                    finish_reason="api_error"
                )
            
        except Exception as e:
            logger.error("=== Anthropic API Error ===")
            logger.error(f"Error type: {type(e)}")
            logger.error(f"Error message: {str(e)}")
            logger.error(f"Messages attempted: {messages}")
            logger.error(f"System message attempted: {system_message}")
            return LLMResponse(
                content=f"An unexpected error occurred: {str(e)}",
                status=LLMResponseStatus.ERROR,
                finish_reason="error"
            )

    # Alias for backward compatibility
    chat_completion = chat_completions