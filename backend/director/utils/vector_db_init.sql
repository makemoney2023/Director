-- Enable the pgvector extension to work with embeddings
create extension if not exists vector;

-- Create a table for storing full transcripts
create table if not exists transcripts (
    id uuid default gen_random_uuid() primary key,
    full_text text not null,
    metadata jsonb default '{}'::jsonb,
    created_at timestamp with time zone default timezone('utc'::text, now()) not null
);

-- Create a table for storing transcript chunks with embeddings
create table if not exists transcript_chunks (
    id uuid default gen_random_uuid() primary key,
    transcript_id uuid references transcripts(id) on delete cascade,
    chunk_text text not null,
    chunk_index integer not null,
    embedding vector(1536),  -- OpenAI embeddings are 1536 dimensions
    metadata jsonb default '{}'::jsonb,
    created_at timestamp with time zone default timezone('utc'::text, now()) not null
);

-- Create an index for faster similarity searches
create index if not exists transcript_chunks_embedding_idx 
    on transcript_chunks 
    using ivfflat (embedding vector_cosine_ops)
    with (lists = 100);

-- Function to match similar chunks
create or replace function match_chunks(
    query_embedding vector(1536),
    match_count int
)
returns table (
    id uuid,
    chunk_text text,
    transcript_id uuid,
    similarity float
)
language plpgsql
as $$
begin
    return query
    select
        tc.id,
        tc.chunk_text,
        tc.transcript_id,
        1 - (tc.embedding <=> query_embedding) as similarity
    from transcript_chunks tc
    order by tc.embedding <=> query_embedding
    limit match_count;
end;
$$; 