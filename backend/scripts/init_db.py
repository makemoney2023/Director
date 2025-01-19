"""Initialize the database with required tables and functions."""

SQL_COMMANDS = """
-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Create videos table
CREATE TABLE IF NOT EXISTS videos (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    video_id TEXT NOT NULL,
    collection_id TEXT NOT NULL,
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(video_id, collection_id)
);

-- Create transcripts table
CREATE TABLE IF NOT EXISTS transcripts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    video_id UUID REFERENCES videos(id),
    full_text TEXT NOT NULL,
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create transcript_chunks table with vector support
CREATE TABLE IF NOT EXISTS transcript_chunks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    transcript_id UUID REFERENCES transcripts(id),
    chunk_text TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    embedding vector(1536),
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create generated_outputs table
CREATE TABLE IF NOT EXISTS generated_outputs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    video_id UUID REFERENCES videos(id),
    output_type TEXT NOT NULL,
    content TEXT NOT NULL,
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create index for similarity search
CREATE INDEX IF NOT EXISTS transcript_chunks_embedding_idx 
ON transcript_chunks 
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- Create function for similarity search
CREATE OR REPLACE FUNCTION match_chunks(
    query_embedding vector(1536),
    match_count int DEFAULT 5
)
RETURNS TABLE (
    id UUID,
    chunk_text TEXT,
    transcript_id UUID,
    similarity float
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        transcript_chunks.id,
        transcript_chunks.chunk_text,
        transcript_chunks.transcript_id,
        1 - (transcript_chunks.embedding <=> query_embedding) as similarity
    FROM transcript_chunks
    ORDER BY transcript_chunks.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;
"""

def main():
    """Print the SQL commands needed to initialize the database."""
    print("Please execute the following SQL commands in the Supabase SQL editor:")
    print(SQL_COMMANDS)

if __name__ == "__main__":
    main() 