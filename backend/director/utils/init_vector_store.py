import os
from dotenv import load_dotenv
from director.utils.supabase import SupabaseVectorStore

def init_vector_store():
    """Initialize the vector store with proper environment variables"""
    # Load environment variables from .env file
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), '.env')
    load_dotenv(env_path)
    
    # Initialize and create tables
    store = SupabaseVectorStore()
    success = store.create_tables()
    
    if success:
        print("Successfully initialized vector store")
    else:
        print("Failed to initialize vector store")

if __name__ == "__main__":
    init_vector_store() 