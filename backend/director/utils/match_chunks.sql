create or replace function match_chunks (
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