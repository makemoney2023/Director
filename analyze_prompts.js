const { createClient } = require('@supabase/supabase-js');

const supabase = createClient(
  'https://pzzxahvrgvwmrfbxqsxg.supabase.co',
  'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InB6enhhaHZyZ3Z3bXJmYnhxc3hnIiwicm9sZSI6ImFub24iLCJpYXQiOjE3MDg2NDQ3OTUsImV4cCI6MjAyNDIyMDc5NX0.YkPd8178xKiR0XCQjZ-LJh0PhPLR0DvHGCf0gqvBHvM'
);

const phases = {
  discovery: ['discovery', 'initial', 'introduction', 'greeting'],
  rapport_building: ['rapport', 'relationship', 'trust', 'connection'],
  value_proposition: ['value', 'benefit', 'advantage', 'solution'],
  objection_handling: ['objection', 'concern', 'hesitation', 'doubt'],
  closing: ['close', 'closing', 'commitment', 'decision'],
  follow_up: ['follow', 'next steps', 'future', 'schedule']
};

function detectPhases(text) {
  if (!text) return new Set();
  text = text.toLowerCase();
  const detected = new Set();
  
  for (const [phase, keywords] of Object.entries(phases)) {
    if (keywords.some(keyword => text.includes(keyword))) {
      detected.add(phase);
    }
  }
  return detected;
}

async function analyzePrompt(promptData) {
  try {
    const content = JSON.parse(promptData.content);
    const mainPrompt = content.prompt || '';
    const examples = content.few_shot_examples || [];

    // Analyze main prompt
    const promptPhases = detectPhases(mainPrompt);

    // Analyze examples
    const examplePhases = new Set();
    const exampleAnalysis = examples.map(ex => {
      const context = ex.context || '';
      const input = ex.input || '';
      const response = ex.response || '';

      const detected = new Set([
        ...detectPhases(context),
        ...detectPhases(input),
        ...detectPhases(response)
      ]);

      detected.forEach(phase => examplePhases.add(phase));

      return {
        context: context.length > 100 ? context.slice(0, 100) + '...' : context,
        phases: Array.from(detected)
      };
    });

    const combinedPhases = new Set([...promptPhases, ...examplePhases]);

    return {
      id: promptData.id,
      main_prompt_phases: Array.from(promptPhases),
      example_phases: Array.from(examplePhases),
      combined_phases: Array.from(combinedPhases),
      examples_analysis: exampleAnalysis,
      created_at: promptData.created_at,
      full_content: content
    };
  } catch (error) {
    console.error(`Error analyzing prompt ${promptData.id}:`, error);
    throw error;
  }
}

async function analyzeAllPrompts() {
  try {
    console.log('Fetching voice prompts...');
    const { data: prompts, error } = await supabase
      .from('generated_outputs')
      .select('*')
      .eq('output_type', 'voice_prompt')
      .order('created_at', { ascending: false });

    if (error) throw error;
    
    console.log(`\nAnalyzing ${prompts.length} voice prompts...`);
    
    const analyzedPrompts = [];
    for (let i = 0; i < prompts.length; i++) {
      const prompt = prompts[i];
      console.log(`\nAnalyzing prompt ${i + 1}/${prompts.length} (ID: ${prompt.id})...`);
      
      const analysis = await analyzePrompt(prompt);
      analyzedPrompts.push(analysis);
      
      console.log(`Main prompt phases: ${analysis.main_prompt_phases.join(', ')}`);
      console.log(`Example phases: ${analysis.example_phases.join(', ')}`);
      console.log('Example analysis:');
      analysis.examples_analysis.forEach(ex => {
        console.log(`- Context: ${ex.context}`);
        console.log(`  Phases: ${ex.phases.join(', ')}`);
      });
      console.log('-'.repeat(50));
    }

    // Organize prompts by phase
    const promptsByPhase = {};
    for (const phase of Object.keys(phases)) {
      promptsByPhase[phase] = analyzedPrompts.filter(p => 
        p.combined_phases.includes(phase)
      );
      
      console.log(`\n${phase.toUpperCase()} phase prompts: ${promptsByPhase[phase].length}`);
      promptsByPhase[phase].forEach(p => {
        console.log(`- Prompt ${p.id}`);
      });
    }

    // Save analysis results
    const fs = require('fs');
    fs.writeFileSync('prompt_analysis.json', JSON.stringify({
      analyzed_prompts: analyzedPrompts,
      prompts_by_phase: Object.fromEntries(
        Object.entries(promptsByPhase).map(([phase, prompts]) => [
          phase,
          prompts.map(p => p.id)
        ])
      )
    }, null, 2));
    
    console.log('\nAnalysis results saved to prompt_analysis.json');
    return promptsByPhase;
  } catch (error) {
    console.error('Error analyzing prompts:', error);
    throw error;
  }
}

analyzeAllPrompts(); 