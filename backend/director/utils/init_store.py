from director.utils.supabase import SupabaseVectorStore

def main():
    """Initialize the vector store tables and functions"""
    store = SupabaseVectorStore()
    store.create_tables()

if __name__ == "__main__":
    main() 