import os
from supabase import Client, create_client
from pathlib import Path

def init_vector_db():
    """Initialize Supabase with required tables and functions for vector search"""
    # Get Supabase credentials from environment
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY")
    
    if not supabase_url or not supabase_key:
        raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in environment variables")
    
    # Initialize Supabase client
    supabase: Client = create_client(supabase_url, supabase_key)
    
    # Read SQL initialization file
    sql_path = Path(__file__).parent / "vector_db_init.sql"
    with open(sql_path, "r") as f:
        sql = f.read()
    
    # Execute SQL statements
    try:
        result = supabase.query(sql).execute()
        print("Successfully initialized Supabase tables and functions")
        return True
    except Exception as e:
        print(f"Error initializing Supabase: {str(e)}")
        return False

if __name__ == "__main__":
    init_vector_db() 