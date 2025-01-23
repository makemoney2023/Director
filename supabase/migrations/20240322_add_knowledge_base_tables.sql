-- Create knowledge_bases table
CREATE TABLE IF NOT EXISTS knowledge_bases (
    kb_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    analysis_id TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (analysis_id) REFERENCES sales_analyses(id) ON DELETE SET NULL
);

-- Create pathway_knowledge_bases table for linking KBs to pathways
CREATE TABLE IF NOT EXISTS pathway_knowledge_bases (
    pathway_id TEXT NOT NULL,
    kb_id TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (pathway_id, kb_id),
    FOREIGN KEY (kb_id) REFERENCES knowledge_bases(kb_id) ON DELETE CASCADE
);

-- Create index for faster lookups
CREATE INDEX IF NOT EXISTS idx_kb_analysis ON knowledge_bases(analysis_id);
CREATE INDEX IF NOT EXISTS idx_kb_pathway ON pathway_knowledge_bases(pathway_id); 