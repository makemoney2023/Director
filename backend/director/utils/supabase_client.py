"""
Supabase Edge Function client utility
"""

import os
import json
import logging
from typing import Dict, Any, Optional
import requests
from director.utils.exceptions import DirectorException

logger = logging.getLogger(__name__)

class SupabaseClient:
    """Client for interacting with Supabase Edge Functions"""
    
    def __init__(self):
        """Initialize the Supabase client"""
        self.project_ref = os.getenv("SUPABASE_PROJECT_REF")
        self.anon_key = os.getenv("SUPABASE_ANON_KEY")
        
        if not self.project_ref or not self.anon_key:
            raise DirectorException(
                "Supabase configuration missing. Please set SUPABASE_PROJECT_REF and SUPABASE_ANON_KEY environment variables."
            )
            
        self.base_url = f"https://{self.project_ref}.functions.supabase.co"
        
    def call_edge_function(self, function_name: str, payload: Dict) -> Dict:
        """Call a Supabase Edge Function
        
        Args:
            function_name: Name of the Edge Function to call
            payload: Data to send to the function
            
        Returns:
            Dict containing the function response
            
        Raises:
            DirectorException: If the function call fails
        """
        try:
            url = f"{self.base_url}/{function_name}"
            headers = {
                "Authorization": f"Bearer {self.anon_key}",
                "Content-Type": "application/json"
            }
            
            response = requests.post(url, json=payload, headers=headers)
            response.raise_for_status()
            
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error calling Edge Function {function_name}: {str(e)}")
            raise DirectorException(f"Failed to call Edge Function {function_name}: {str(e)}")
            
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding response from Edge Function {function_name}: {str(e)}")
            raise DirectorException(f"Failed to decode response from Edge Function {function_name}: {str(e)}")
            
        except Exception as e:
            logger.error(f"Unexpected error calling Edge Function {function_name}: {str(e)}")
            raise DirectorException(f"Unexpected error calling Edge Function {function_name}: {str(e)}") 