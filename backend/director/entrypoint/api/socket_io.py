import os
from datetime import datetime
import logging
import time
from typing import Dict, Optional

from flask import current_app, request
from flask_socketio import Namespace, emit
from flask_socketio import disconnect

from director.db import load_db
from director.handler import ChatHandler
from director.core.session import Session, MsgStatus

logger = logging.getLogger(__name__)

class ChatNamespace(Namespace):
    """Chat namespace for socket.io"""
    
    def __init__(self, namespace=None):
        super().__init__(namespace)
        # Initialize without db, will be set when needed
        self.db = None
        self.retry_attempts = 3
        self.retry_delay = 2  # seconds
        self.operation_timeout = 300  # 5 minutes timeout for long operations
        
    def _ensure_db(self):
        """Ensure database is initialized within application context"""
        if self.db is None:
            with current_app.app_context():
                self.db = load_db(os.getenv("SERVER_DB_TYPE", current_app.config["DB_TYPE"]))
        return self.db

    def _get_last_response(self, session_id: str, conv_id: str) -> dict:
        """Get the last response from database for recovery"""
        try:
            # Ensure db is initialized
            self._ensure_db()
            
            # Get conversations for the session
            conversations = self.db.get_conversations(session_id)
            if not conversations:
                return None
                
            # Find the last response for this conversation
            for conv in reversed(conversations):
                if conv.get("conv_id") == conv_id and conv.get("msg_type") == "output":
                    return conv
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting last response: {str(e)}")
            return None

    def on_connect(self):
        """Handle client connection"""
        logger.info("Client connected")

    def on_disconnect(self, sid=None, reason=None):
        """Handle client disconnection"""
        logger.info(f"Client disconnected. SID: {sid}, Reason: {reason}")

    def on_reconnect(self, data):
        """Handle client reconnection and recovery"""
        try:
            session_id = data.get("session_id")
            conv_id = data.get("conv_id")
            
            if not session_id or not conv_id:
                logger.warning("Missing session_id or conv_id in reconnect")
                return
                
            # Try to get last response
            last_response = self._get_last_response(session_id, conv_id)
            if last_response:
                # Check if it contains an Anthropic response
                for content in last_response.get("content", []):
                    if content.get("anthropic_response"):
                        logger.info("Found stored Anthropic response, resending...")
                        self.emit("chat", last_response)
                        return
                        
            logger.info("No stored response found for recovery")
            
        except Exception as e:
            logger.error(f"Error in reconnect handler: {str(e)}")

    def on_chat(self, message):
        """Handle chat messages"""
        logger.info(f"Received chat message: {message}")
        # Ensure db is initialized
        self._ensure_db()
        chat_handler = ChatHandler(db=self.db)
        
        try:
            # Create a new session if one doesn't exist
            if not message.get("session_id"):
                session = Session(db=chat_handler.db)
                session.create()
                message["session_id"] = session.id
                logger.info(f"Created new session: {session.id}")
            
            # Try to get existing response first (in case of reconnection)
            existing_response = None
            if message.get("is_retry"):
                existing_response = self._get_last_response(
                    message["session_id"], 
                    message["conv_id"]
                )
                if existing_response:
                    logger.info("Found existing response, returning from database")
                    self.emit("chat", existing_response, room=request.sid)
                    return
            
            # Run the chat handler and get the response
            response = chat_handler.chat(message)
            
            # Ensure we have a valid response
            if not response:
                logger.warning("No response from chat handler")
                response = {
                    "status": "error",
                    "message": "No response from chat handler",
                    "session_id": message.get("session_id"),
                    "content": []
                }
            
            # Ensure session_id is in the response
            if not response.get("session_id"):
                response["session_id"] = message.get("session_id")
            
            # Ensure content is present
            if not response.get("content"):
                response["content"] = []
                
            # Add any missing required fields
            response.update({
                "conv_id": message.get("conv_id"),
                "msg_type": "output",
                "actions": response.get("actions", []),
                "agents": response.get("agents", []),
                "metadata": {
                    **(response.get("metadata") or {}),
                    "timestamp": datetime.now().isoformat()
                }
            })
            
            # Attempt to emit with retry logic
            retry_count = 0
            while retry_count < self.retry_attempts:
                try:
                    logger.info(f"Emitting response (attempt {retry_count + 1})")
                    self.emit("chat", response, room=request.sid)
                    break
                except Exception as e:
                    retry_count += 1
                    if retry_count < self.retry_attempts:
                        logger.warning(f"Emit failed, retrying in {self.retry_delay} seconds")
                        time.sleep(self.retry_delay)
                    else:
                        logger.error("Max retries reached for emit")
                        raise
            
        except Exception as e:
            logger.error(f"Error in chat handler: {str(e)}")
            # Handle any errors and ensure we always emit a response
            error_response = {
                "status": "error",
                "message": f"Error in chat handler: {str(e)}",
                "session_id": message.get("session_id"),
                "conv_id": message.get("conv_id"),
                "msg_type": "output",
                "content": [],
                "actions": [],
                "agents": [],
                "metadata": {
                    "timestamp": datetime.now().isoformat(),
                    "error_type": type(e).__name__
                }
            }
            self.emit("chat", error_response, room=request.sid)

    def emit_progress(self, session_id: str, conv_id: str, stage: str, progress: float):
        """Emit progress update for long-running operations"""
        progress_msg = {
            "status": "progress",
            "session_id": session_id,
            "conv_id": conv_id,
            "msg_type": "output",
            "content": [{
                "type": "progress",
                "stage": stage,
                "progress": progress
            }],
            "metadata": {
                "timestamp": datetime.now().isoformat()
            }
        }
        self.emit("chat", progress_msg, room=request.sid)

    def emit_timeout_error(self, session_id: str, conv_id: str, operation: str):
        """Emit timeout error message"""
        error_msg = {
            "status": "error",
            "session_id": session_id,
            "conv_id": conv_id,
            "msg_type": "output",
            "content": [{
                "type": "error",
                "text": f"Operation {operation} timed out after {self.operation_timeout} seconds"
            }],
            "metadata": {
                "timestamp": datetime.now().isoformat(),
                "error_type": "OperationTimeout"
            }
        }
        self.emit("chat", error_msg, room=request.sid)

    def cleanup_failed_operation(self, session_id: str, video_id: str = None):
        """Clean up resources after a failed operation"""
        try:
            # Ensure db is initialized
            self._ensure_db()
            
            # Delete any partial analysis results
            if video_id:
                self.db.delete_video(video_id)
            
            # Delete any partial session data
            self.db.delete_session(session_id)
            
            logger.info(f"Cleaned up failed operation for session {session_id}")
            
        except Exception as e:
            logger.error(f"Error during cleanup: {str(e)}")

    async def _get_agent_response(self, message: Dict) -> Optional[Dict]:
        """Get response from appropriate agent based on message"""
        
        try:
            # Get the first agent from the list
            agent_name = message.get("agents", [])[0] if message.get("agents") else None
            session_id = message.get("session_id")
            conv_id = message.get("conv_id")
            video_id = message.get("video_id")
            
            # Handle special cases that bypass the reasoning engine
            if agent_name in ["sales_prompt_extractor", "bland_ai"]:
                # Start timeout timer
                start_time = time.time()
                
                # For video analysis, emit progress updates
                if agent_name == "sales_prompt_extractor":
                    try:
                        self.emit_progress(session_id, conv_id, "Initializing analysis", 0.0)
                        
                        # Check timeout between operations
                        if time.time() - start_time > self.operation_timeout:
                            self.emit_timeout_error(session_id, conv_id, "video analysis")
                            self.cleanup_failed_operation(session_id, video_id)
                            return None
                            
                        self.emit_progress(session_id, conv_id, "Processing transcript", 0.25)
                        
                        if time.time() - start_time > self.operation_timeout:
                            self.emit_timeout_error(session_id, conv_id, "transcript processing")
                            self.cleanup_failed_operation(session_id, video_id)
                            return None
                            
                        self.emit_progress(session_id, conv_id, "Generating embeddings", 0.5)
                        
                        if time.time() - start_time > self.operation_timeout:
                            self.emit_timeout_error(session_id, conv_id, "embedding generation")
                            self.cleanup_failed_operation(session_id, video_id)
                            return None
                            
                        self.emit_progress(session_id, conv_id, "Analyzing sales techniques", 0.75)
                        
                        if time.time() - start_time > self.operation_timeout:
                            self.emit_timeout_error(session_id, conv_id, "sales analysis")
                            self.cleanup_failed_operation(session_id, video_id)
                            return None
                            
                        self.emit_progress(session_id, conv_id, "Generating voice prompts", 0.9)
                        
                    except Exception as e:
                        logger.error(f"Error during video analysis: {str(e)}")
                        self.cleanup_failed_operation(session_id, video_id)
                        return None
                
                # Get the command from the text content
                text = message.get("content", [{}])[0].get("text", "")
                
                # For sales prompt extractor, always use "analyze"
                if agent_name == "sales_prompt_extractor":
                    command = "analyze"
                else:
                    # For bland_ai, parse the command after @bland_ai
                    command = text.replace("@bland_ai", "").strip()
                
                # Create agent instance
                agent = self.chat_handler.get_agent(
                    agent_name,
                    session=self.session,
                    input_message=message
                )
                
                if not agent:
                    return None
                    
                # Run the agent with the command
                return agent.run(command)

        except Exception as e:
            logger.error(f"Error in agent response: {str(e)}")
            return None
