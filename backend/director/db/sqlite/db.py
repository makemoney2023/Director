import json
import sqlite3
import time
import logging
import os

from typing import List, Optional

from director.constants import DBType
from director.db.base import BaseDB
from director.db.sqlite.initialize import initialize_sqlite

logger = logging.getLogger(__name__)


class SQLiteDB(BaseDB):
    def __init__(self, db_path: str = None):
        """
        :param db_path: Path to the SQLite database file.
        """
        self.db_type = DBType.SQLITE
        if db_path is None:
            self.db_path = os.getenv("SQLITE_DB_PATH", "director.db")
        else:
            self.db_path = db_path
        
        # Configure SQLite for multi-threaded access
        self.conn = sqlite3.connect(
            self.db_path,
            check_same_thread=False,  # Allow multi-threaded access
            timeout=30.0,  # Increase timeout for busy connections
            isolation_level='IMMEDIATE'  # Use immediate transaction isolation
        )
        self.conn.row_factory = sqlite3.Row
        
        # Enable WAL mode for better concurrency
        self.conn.execute('PRAGMA journal_mode=WAL')
        self.conn.execute('PRAGMA busy_timeout=30000')  # 30 second timeout
        
        self.cursor = self.conn.cursor()
        logger.info("Connected to SQLite DB with multi-threading support...")

    def create_session(
        self,
        session_id: str,
        video_id: str,
        collection_id: str,
        created_at: int = None,
        updated_at: int = None,
        metadata: dict = {},
        **kwargs,
    ) -> None:
        """Create a new session.

        :param session_id: Unique session ID.
        :param video_id: ID of the video associated with the session.
        :param collection_id: ID of the collection associated with the session.
        :param created_at: Timestamp when the session was created.
        :param updated_at: Timestamp when the session was last updated.
        :param metadata: Additional metadata for the session.
        """
        created_at = created_at or int(time.time())
        updated_at = updated_at or int(time.time())

        self.cursor.execute(
            """
        INSERT OR IGNORE INTO sessions (session_id, video_id, collection_id, created_at, updated_at, metadata)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
            (
                session_id,
                video_id,
                collection_id,
                created_at,
                updated_at,
                json.dumps(metadata),
            ),
        )
        self.conn.commit()

    def get_session(self, session_id: str) -> dict:
        """Get a session by session_id.

        :param session_id: Unique session ID.
        :return: Session data as a dictionary.
        :rtype: dict
        """
        self.cursor.execute(
            "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
        )
        row = self.cursor.fetchone()
        if row is not None:
            session = dict(row)  # Convert sqlite3.Row to dictionary
            session["metadata"] = json.loads(session["metadata"])
            return session

        else:
            return {}  # Return an empty dictionary if no data found

    def get_sessions(self) -> list:
        """Get all sessions.

        :return: List of all sessions.
        :rtype: list
        """
        self.cursor.execute("SELECT * FROM sessions ORDER BY updated_at DESC")
        row = self.cursor.fetchall()
        sessions = [dict(r) for r in row]
        for s in sessions:
            s["metadata"] = json.loads(s["metadata"])
        return sessions

    def add_or_update_msg_to_conv(
        self,
        session_id: str,
        conv_id: str,
        msg_id: str,
        msg_type: str,
        agents: List[str],
        actions: List[str],
        content: List[dict],
        status: str = None,
        created_at: int = None,
        updated_at: int = None,
        metadata: dict = {},
        **kwargs,
    ) -> None:
        """Add a new message (input or output) to the conversation.

        :param str session_id: Unique session ID.
        :param str conv_id: Unique conversation ID.
        :param str msg_id: Unique message ID.
        :param str msg_type: Type of message (input or output).
        :param list agents: List of agents involved in the conversation.
        :param list actions: List of actions taken by the agents.
        :param list content: List of message content.
        :param str status: Status of the message.
        :param int created_at: Timestamp when the message was created.
        :param int updated_at: Timestamp when the message was last updated.
        :param dict metadata: Additional metadata for the message.
        """
        created_at = created_at or int(time.time())
        updated_at = updated_at or int(time.time())

        self.cursor.execute(
            """
        INSERT OR REPLACE INTO conversations (session_id, conv_id, msg_id, msg_type, agents, actions, content, status, created_at, updated_at, metadata)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                session_id,
                conv_id,
                msg_id,
                msg_type,
                json.dumps(agents),
                json.dumps(actions),
                json.dumps(content),
                status,
                created_at,
                updated_at,
                json.dumps(metadata),
            ),
        )
        self.conn.commit()

    def get_conversations(self, session_id: str) -> list:
        self.cursor.execute(
            "SELECT * FROM conversations WHERE session_id = ?", (session_id,)
        )
        rows = self.cursor.fetchall()
        conversations = []
        for row in rows:
            if row is not None:
                conv_dict = dict(row)
                conv_dict["agents"] = json.loads(conv_dict["agents"])
                conv_dict["actions"] = json.loads(conv_dict["actions"])
                conv_dict["content"] = json.loads(conv_dict["content"])
                conv_dict["metadata"] = json.loads(conv_dict["metadata"])
                conversations.append(conv_dict)
        return conversations

    def get_context_messages(self, session_id: str) -> list:
        """Get context messages for a session.

        :param str session_id: Unique session ID.
        :return: List of context messages.
        :rtype: list
        """
        self.cursor.execute(
            "SELECT context_data FROM context_messages WHERE session_id = ?",
            (session_id,),
        )
        result = self.cursor.fetchone()
        return json.loads(result[0]) if result else {}

    def add_or_update_context_msg(
        self,
        session_id: str,
        context_messages: list,
        created_at: int = None,
        updated_at: int = None,
        metadata: dict = {},
        **kwargs,
    ) -> None:
        """Update context messages for a session.

        :param str session_id: Unique session ID.
        :param List context_messages: List of context messages.
        :param int created_at: Timestamp when the context messages were created.
        :param int updated_at: Timestamp when the context messages were last updated.
        :param dict metadata: Additional metadata for the context messages.
        """
        created_at = created_at or int(time.time())
        updated_at = updated_at or int(time.time())

        self.cursor.execute(
            """
        INSERT OR REPLACE INTO context_messages (context_data, session_id, created_at, updated_at, metadata)
        VALUES (?, ?, ?, ?, ?)
        """,
            (
                json.dumps(context_messages),
                session_id,
                created_at,
                updated_at,
                json.dumps(metadata),
            ),
        )
        self.conn.commit()

    def delete_conversation(self, session_id: str) -> bool:
        """Delete all conversations for a given session.

        :param str session_id: Unique session ID.
        :return: True if conversations were deleted, False otherwise.
        """
        self.cursor.execute(
            "DELETE FROM conversations WHERE session_id = ?", (session_id,)
        )
        self.conn.commit()
        return self.cursor.rowcount > 0

    def delete_context(self, session_id: str) -> bool:
        """Delete context messages for a given session.

        :param str session_id: Unique session ID.
        :return: True if context messages were deleted, False otherwise.
        """
        self.cursor.execute(
            "DELETE FROM context_messages WHERE session_id = ?", (session_id,)
        )
        self.conn.commit()
        return self.cursor.rowcount > 0

    def delete_session(self, session_id: str) -> bool:
        """Delete a session and all its associated data.

        :param str session_id: Unique session ID.
        :return: True if the session was deleted, False otherwise.
        """
        failed_components = []
        
        # Delete conversations
        if not self.delete_conversation(session_id):
            failed_components.append("conversation")
            
        # Delete context messages
        if not self.delete_context(session_id):
            failed_components.append("context")
            
        # Delete analysis results
        self.cursor.execute(
            "DELETE FROM analysis_results WHERE session_id = ?",
            (session_id,)
        )
        if not self.cursor.rowcount > 0:
            failed_components.append("analysis_results")
            
        # Delete session
        self.cursor.execute(
            "DELETE FROM sessions WHERE session_id = ?",
            (session_id,)
        )
        self.conn.commit()
        if not self.cursor.rowcount > 0:
            failed_components.append("session")
            
        success = len(failed_components) < 4
        return success, failed_components

    def health_check(self) -> bool:
        """Check if the SQLite database is healthy and the necessary tables exist. If not, create them."""
        try:
            query = """
                SELECT COUNT(name)
                FROM sqlite_master
                WHERE type='table'
                AND name IN ('sessions', 'conversations', 'context_messages');
            """
            self.cursor.execute(query)
            table_count = self.cursor.fetchone()[0]
            if table_count < 3:
                logger.info("Tables not found. Initializing SQLite DB...")
                initialize_sqlite(self.db_path)
            return True

        except Exception as e:
            logger.exception(f"SQLite health check failed: {e}")
            return False

    def add_analysis_result(
        self,
        analysis_id: str,
        session_id: str,
        video_id: str,
        analysis_type: str,
        sales_techniques: List[dict],
        objection_handling: List[dict],
        voice_prompts: List[str],
        training_pairs: List[dict],
        summary: str,
        created_at: int = None,
        updated_at: int = None,
        metadata: dict = {},
    ) -> None:
        """Add or update an analysis result.
        
        Args:
            analysis_id: Unique ID for the analysis
            session_id: ID of the session
            video_id: ID of the video analyzed
            analysis_type: Type of analysis performed
            sales_techniques: List of extracted sales techniques
            objection_handling: List of objection handling strategies
            voice_prompts: List of voice prompts
            training_pairs: List of training pairs
            summary: Summary of the analysis
            created_at: Creation timestamp
            updated_at: Update timestamp
            metadata: Additional metadata
        """
        created_at = created_at or int(time.time())
        updated_at = updated_at or int(time.time())

        self.cursor.execute(
            """
            INSERT OR REPLACE INTO analysis_results 
            (analysis_id, session_id, video_id, analysis_type, sales_techniques, 
             objection_handling, voice_prompts, training_pairs, summary, 
             created_at, updated_at, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                analysis_id,
                session_id,
                video_id,
                analysis_type,
                json.dumps(sales_techniques),
                json.dumps(objection_handling),
                json.dumps(voice_prompts),
                json.dumps(training_pairs),
                summary,
                created_at,
                updated_at,
                json.dumps(metadata),
            ),
        )
        self.conn.commit()

    def get_analysis_result(self, analysis_id: str) -> Optional[dict]:
        """Get an analysis result by ID.
        
        Args:
            analysis_id: ID of the analysis to retrieve
            
        Returns:
            Dict containing the analysis data or None if not found
        """
        self.cursor.execute(
            "SELECT * FROM analysis_results WHERE analysis_id = ?",
            (analysis_id,)
        )
        row = self.cursor.fetchone()
        
        if row is not None:
            result = dict(row)
            # Parse JSON fields
            result["sales_techniques"] = json.loads(result["sales_techniques"])
            result["objection_handling"] = json.loads(result["objection_handling"])
            result["voice_prompts"] = json.loads(result["voice_prompts"])
            result["training_pairs"] = json.loads(result["training_pairs"])
            result["metadata"] = json.loads(result["metadata"])
            return result
            
        return None

    def get_session_analysis_results(self, session_id: str) -> List[dict]:
        """Get all analysis results for a session.
        
        Args:
            session_id: ID of the session
            
        Returns:
            List of analysis results
        """
        self.cursor.execute(
            "SELECT * FROM analysis_results WHERE session_id = ? ORDER BY created_at DESC",
            (session_id,)
        )
        rows = self.cursor.fetchall()
        
        results = []
        for row in rows:
            result = dict(row)
            # Parse JSON fields
            result["sales_techniques"] = json.loads(result["sales_techniques"])
            result["objection_handling"] = json.loads(result["objection_handling"])
            result["voice_prompts"] = json.loads(result["voice_prompts"])
            result["training_pairs"] = json.loads(result["training_pairs"])
            result["metadata"] = json.loads(result["metadata"])
            results.append(result)
            
        return results

    def delete_analysis_result(self, analysis_id: str) -> bool:
        """Delete an analysis result.
        
        Args:
            analysis_id: ID of the analysis to delete
            
        Returns:
            True if deleted, False if not found
        """
        self.cursor.execute(
            "DELETE FROM analysis_results WHERE analysis_id = ?",
            (analysis_id,)
        )
        self.conn.commit()
        return self.cursor.rowcount > 0

    def add_video(self, id: str, video_id: str, collection_id: str, metadata: dict = {}, created_at: int = None) -> None:
        """Add a new video record.
        
        Args:
            id: Unique ID for the video
            video_id: External video ID
            collection_id: Collection ID
            metadata: Additional metadata
            created_at: Creation timestamp
        """
        created_at = created_at or int(time.time())
        
        self.cursor.execute(
            """
            INSERT OR REPLACE INTO videos (id, video_id, collection_id, metadata, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (id, video_id, collection_id, json.dumps(metadata), created_at)
        )
        self.conn.commit()

    def add_transcript(self, id: str, video_id: str, full_text: str, metadata: dict = {}, created_at: int = None) -> None:
        """Add a transcript for a video.
        
        Args:
            id: Unique ID for the transcript
            video_id: ID of the associated video
            full_text: Complete transcript text
            metadata: Additional metadata
            created_at: Creation timestamp
        """
        created_at = created_at or int(time.time())
        
        self.cursor.execute(
            """
            INSERT OR REPLACE INTO transcripts (id, video_id, full_text, metadata, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (id, video_id, full_text, json.dumps(metadata), created_at)
        )
        self.conn.commit()

    def add_transcript_chunk(self, id: str, transcript_id: str, chunk_text: str, chunk_index: int, 
                           embedding: list = None, metadata: dict = {}, created_at: int = None) -> None:
        """Add a transcript chunk with embedding.
        
        Args:
            id: Unique ID for the chunk
            transcript_id: ID of the associated transcript
            chunk_text: Text content of the chunk
            chunk_index: Index of the chunk in sequence
            embedding: Vector embedding of the chunk
            metadata: Additional metadata
            created_at: Creation timestamp
        """
        created_at = created_at or int(time.time())
        
        self.cursor.execute(
            """
            INSERT OR REPLACE INTO transcript_chunks 
            (id, transcript_id, chunk_text, chunk_index, embedding, metadata, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (id, transcript_id, chunk_text, chunk_index, 
             json.dumps(embedding) if embedding else None,
             json.dumps(metadata), created_at)
        )
        self.conn.commit()

    def add_generated_output(self, id: str, video_id: str, output_type: str, content: str,
                           metadata: dict = {}, created_at: int = None) -> None:
        """Add a generated output.
        
        Args:
            id: Unique ID for the output
            video_id: ID of the associated video
            output_type: Type of output (e.g., 'structured_data', 'voice_prompt')
            content: Output content
            metadata: Additional metadata
            created_at: Creation timestamp
        """
        created_at = created_at or int(time.time())
        
        self.cursor.execute(
            """
            INSERT OR REPLACE INTO generated_outputs 
            (id, video_id, output_type, content, metadata, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (id, video_id, output_type, content, json.dumps(metadata), created_at)
        )
        self.conn.commit()

    def get_video(self, id: str) -> Optional[dict]:
        """Get a video by ID."""
        self.cursor.execute("SELECT * FROM videos WHERE id = ?", (id,))
        row = self.cursor.fetchone()
        if row:
            result = dict(row)
            result["metadata"] = json.loads(result["metadata"])
            return result
        return None

    def get_transcript(self, video_id: str) -> Optional[dict]:
        """Get a transcript by video ID."""
        self.cursor.execute("SELECT * FROM transcripts WHERE video_id = ?", (video_id,))
        row = self.cursor.fetchone()
        if row:
            result = dict(row)
            result["metadata"] = json.loads(result["metadata"])
            return result
        return None

    def get_transcript_chunks(self, transcript_id: str) -> List[dict]:
        """Get all chunks for a transcript."""
        self.cursor.execute(
            "SELECT * FROM transcript_chunks WHERE transcript_id = ? ORDER BY chunk_index",
            (transcript_id,)
        )
        rows = self.cursor.fetchall()
        results = []
        for row in rows:
            result = dict(row)
            result["metadata"] = json.loads(result["metadata"])
            if result["embedding"]:
                result["embedding"] = json.loads(result["embedding"])
            results.append(result)
        return results

    def get_generated_outputs(self, video_id: str, output_type: str = None) -> List[dict]:
        """Get generated outputs for a video."""
        if output_type:
            self.cursor.execute(
                "SELECT * FROM generated_outputs WHERE video_id = ? AND output_type = ?",
                (video_id, output_type)
            )
        else:
            self.cursor.execute(
                "SELECT * FROM generated_outputs WHERE video_id = ?",
                (video_id,)
            )
        rows = self.cursor.fetchall()
        results = []
        for row in rows:
            result = dict(row)
            result["metadata"] = json.loads(result["metadata"])
            results.append(result)
        return results

    def delete_video(self, id: str) -> bool:
        """Delete a video and all associated data."""
        try:
            # Get transcript IDs for the video
            self.cursor.execute("SELECT id FROM transcripts WHERE video_id = ?", (id,))
            transcript_ids = [row[0] for row in self.cursor.fetchall()]
            
            # Delete transcript chunks
            for transcript_id in transcript_ids:
                self.cursor.execute(
                    "DELETE FROM transcript_chunks WHERE transcript_id = ?",
                    (transcript_id,)
                )
            
            # Delete transcripts
            self.cursor.execute("DELETE FROM transcripts WHERE video_id = ?", (id,))
            
            # Delete generated outputs
            self.cursor.execute("DELETE FROM generated_outputs WHERE video_id = ?", (id,))
            
            # Delete video
            self.cursor.execute("DELETE FROM videos WHERE id = ?", (id,))
            
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error deleting video: {str(e)}")
            return False

    def __del__(self):
        self.conn.close()
