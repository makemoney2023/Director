import sqlite3
import os

# SQL to create the sessions table
CREATE_SESSIONS_TABLE = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    video_id TEXT,
    collection_id TEXT,
    created_at INTEGER,
    updated_at INTEGER,
    metadata JSON
)
"""

# SQL to create the conversations table
CREATE_CONVERSATIONS_TABLE = """
CREATE TABLE IF NOT EXISTS conversations (
    session_id TEXT,
    conv_id TEXT,
    msg_id TEXT PRIMARY KEY,
    msg_type TEXT,
    agents JSON,
    actions JSON,
    content JSON,
    status TEXT,
    created_at INTEGER,
    updated_at INTEGER,
    metadata JSON,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
)
"""

# SQL to create the context_messages table
CREATE_CONTEXT_MESSAGES_TABLE = """
CREATE TABLE IF NOT EXISTS context_messages (
    session_id TEXT PRIMARY KEY,
    context_data JSON,
    created_at INTEGER,
    updated_at INTEGER,
    metadata JSON,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
)
"""

# SQL to create the analysis_results table
CREATE_ANALYSIS_RESULTS_TABLE = """
CREATE TABLE IF NOT EXISTS analysis_results (
    analysis_id TEXT PRIMARY KEY,
    session_id TEXT,
    video_id TEXT,
    analysis_type TEXT,
    sales_techniques JSON,
    objection_handling JSON,
    voice_prompts JSON,
    training_pairs JSON,
    summary TEXT,
    created_at INTEGER,
    updated_at INTEGER,
    metadata JSON,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
)
"""

# SQL to create the videos table
CREATE_VIDEOS_TABLE = """
CREATE TABLE IF NOT EXISTS videos (
    id TEXT PRIMARY KEY,
    video_id TEXT NOT NULL,
    collection_id TEXT NOT NULL,
    metadata JSON,
    created_at INTEGER,
    UNIQUE(video_id, collection_id)
)
"""

# SQL to create the transcripts table
CREATE_TRANSCRIPTS_TABLE = """
CREATE TABLE IF NOT EXISTS transcripts (
    id TEXT PRIMARY KEY,
    video_id TEXT REFERENCES videos(id),
    full_text TEXT NOT NULL,
    metadata JSON,
    created_at INTEGER
)
"""

# SQL to create the transcript_chunks table
CREATE_TRANSCRIPT_CHUNKS_TABLE = """
CREATE TABLE IF NOT EXISTS transcript_chunks (
    id TEXT PRIMARY KEY,
    transcript_id TEXT REFERENCES transcripts(id),
    chunk_text TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    embedding JSON,
    metadata JSON,
    created_at INTEGER
)
"""

# SQL to create the generated_outputs table
CREATE_GENERATED_OUTPUTS_TABLE = """
CREATE TABLE IF NOT EXISTS generated_outputs (
    id TEXT PRIMARY KEY,
    video_id TEXT REFERENCES videos(id),
    output_type TEXT NOT NULL,
    content TEXT NOT NULL,
    metadata JSON,
    created_at INTEGER
)
"""

# SQL to create the pathway_knowledge_bases table
CREATE_PATHWAY_KB_TABLE = """
CREATE TABLE IF NOT EXISTS pathway_knowledge_bases (
    id TEXT PRIMARY KEY,
    pathway_id TEXT NOT NULL,
    kb_id TEXT NOT NULL,
    name TEXT,
    description TEXT,
    metadata JSON,
    created_at INTEGER,
    UNIQUE(pathway_id, kb_id)
)
"""

# SQL to create the knowledge_bases table
CREATE_KB_TABLE = """
CREATE TABLE IF NOT EXISTS knowledge_bases (
    id TEXT PRIMARY KEY,
    kb_id TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    metadata JSON,
    created_at INTEGER,
    UNIQUE(kb_id)
)
"""

def initialize_sqlite(db_name="director.db"):
    """Initialize the SQLite database by creating the necessary tables."""
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()

    cursor.execute(CREATE_SESSIONS_TABLE)
    cursor.execute(CREATE_CONVERSATIONS_TABLE)
    cursor.execute(CREATE_CONTEXT_MESSAGES_TABLE)
    cursor.execute(CREATE_ANALYSIS_RESULTS_TABLE)
    cursor.execute(CREATE_VIDEOS_TABLE)
    cursor.execute(CREATE_TRANSCRIPTS_TABLE)
    cursor.execute(CREATE_TRANSCRIPT_CHUNKS_TABLE)
    cursor.execute(CREATE_GENERATED_OUTPUTS_TABLE)
    cursor.execute(CREATE_PATHWAY_KB_TABLE)
    cursor.execute(CREATE_KB_TABLE)

    conn.commit()
    conn.close()


if __name__ == "__main__":
    db_path = os.getenv("SQLITE_DB_PATH", "director.db")
    initialize_sqlite(db_path)
