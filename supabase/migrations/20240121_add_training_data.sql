-- Add training_data column to generated_outputs table
ALTER TABLE generated_outputs
ADD COLUMN training_data JSONB DEFAULT NULL;

-- Add index for faster querying
CREATE INDEX idx_generated_outputs_training_data ON generated_outputs USING GIN (training_data);

-- Add comment for documentation
COMMENT ON COLUMN generated_outputs.training_data IS 'Structured training data examples extracted from transcripts for LLM fine-tuning'; 