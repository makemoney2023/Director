import json
from typing import Dict, List, Set
import os
import time
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

class ConversationPhaseAnalyzer:
    def __init__(self):
        # Initialize REST client with retry logic
        self.base_url = "https://pzzxahvrgvwmrfbxqsxg.supabase.co/rest/v1"
        self.anon_key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InB6enhhaHZyZ3Z3bXJmYnhxc3hnIiwicm9sZSI6ImFub24iLCJpYXQiOjE3MDg2NDQ3OTUsImV4cCI6MjAyNDIyMDc5NX0.YkPd8178xKiR0XCQjZ-LJh0PhPLR0DvHGCf0gqvBHvM"
        
        # Configure retry strategy
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session = requests.Session()
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        self.session.headers.update({
            'apikey': self.anon_key,
            'Authorization': f'Bearer {self.anon_key}',
            'Content-Type': 'application/json',
            'Prefer': 'return=representation'
        })
        
        print("Successfully initialized REST client")

        self.phases = {
            'discovery': ['discovery', 'initial', 'introduction', 'greeting'],
            'rapport_building': ['rapport', 'relationship', 'trust', 'connection'],
            'value_proposition': ['value', 'benefit', 'advantage', 'solution'],
            'objection_handling': ['objection', 'concern', 'hesitation', 'doubt'],
            'closing': ['close', 'closing', 'commitment', 'decision'],
            'follow_up': ['follow', 'next steps', 'future', 'schedule']
        }

    def get_voice_prompts(self) -> List[Dict]:
        """Get all voice prompts from Supabase with retry logic"""
        max_retries = 3
        retry_delay = 2  # seconds
        
        for attempt in range(max_retries):
            try:
                print(f"Fetching voice prompts (attempt {attempt + 1}/{max_retries})...")
                response = self.session.get(
                    f"{self.base_url}/generated_outputs",
                    params={
                        'output_type': 'eq.voice_prompt',
                        'order': 'created_at.desc'
                    }
                )
                response.raise_for_status()
                data = response.json()
                print(f"Successfully fetched {len(data)} prompts")
                return data
            except Exception as e:
                print(f"Error fetching voice prompts (attempt {attempt + 1}): {str(e)}")
                if attempt < max_retries - 1:
                    print(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                else:
                    raise

    def detect_phases(self, text: str) -> Set[str]:
        """Detect conversation phases in a piece of text"""
        if not text:
            return set()
        text = text.lower()
        detected = set()
        for phase, keywords in self.phases.items():
            if any(keyword in text for keyword in keywords):
                detected.add(phase)
        return detected

    def analyze_prompt(self, prompt_data: Dict) -> Dict:
        """Analyze a single prompt and its examples"""
        try:
            content = json.loads(prompt_data['content'])
            main_prompt = content.get('prompt', '')
            examples = content.get('few_shot_examples', [])

            # Analyze main prompt
            phases = self.detect_phases(main_prompt)

            # Analyze examples
            example_phases = set()
            example_analysis = []
            for ex in examples:
                context = ex.get('context', '')
                input_text = ex.get('input', '')
                response = ex.get('response', '')
                
                # Detect phases in all parts
                detected = self.detect_phases(context)
                detected.update(self.detect_phases(input_text))
                detected.update(self.detect_phases(response))
                
                example_phases.update(detected)
                example_analysis.append({
                    'context': context[:100] + '...' if len(context) > 100 else context,
                    'phases': list(detected)
                })

            return {
                'id': prompt_data['id'],
                'main_prompt_phases': list(phases),
                'example_phases': list(example_phases),
                'combined_phases': list(phases.union(example_phases)),
                'examples_analysis': example_analysis,
                'created_at': prompt_data['created_at'],
                'full_content': content  # Keep the full content for later use
            }
        except Exception as e:
            print(f"Error analyzing prompt {prompt_data.get('id')}: {str(e)}")
            raise

    def analyze_all_prompts(self):
        """Analyze all voice prompts and organize by phase"""
        try:
            prompts = self.get_voice_prompts()
            if not prompts:
                print("No prompts found")
                return {}
                
            print(f"\nAnalyzing {len(prompts)} voice prompts...")
            
            # Analyze each prompt
            analyzed_prompts = []
            for i, prompt in enumerate(prompts, 1):
                try:
                    print(f"\nAnalyzing prompt {i}/{len(prompts)} (ID: {prompt['id']})...")
                    analysis = self.analyze_prompt(prompt)
                    analyzed_prompts.append(analysis)
                    
                    print(f"Main prompt phases: {analysis['main_prompt_phases']}")
                    print(f"Example phases: {analysis['example_phases']}")
                    print("Example analysis:")
                    for ex in analysis['examples_analysis']:
                        print(f"- Context: {ex['context']}")
                        print(f"  Phases: {ex['phases']}")
                    print("-" * 50)
                except Exception as e:
                    print(f"Error analyzing prompt {prompt.get('id')}: {str(e)}")
                    continue  # Skip failed prompts but continue with others

            # Organize prompts by phase
            prompts_by_phase = {}
            for phase in self.phases.keys():
                prompts_by_phase[phase] = [
                    p for p in analyzed_prompts 
                    if phase in p['combined_phases']
                ]
                print(f"\n{phase.upper()} phase prompts: {len(prompts_by_phase[phase])}")
                for p in prompts_by_phase[phase]:
                    print(f"- Prompt {p['id']}")

            # Save analysis results
            try:
                with open('prompt_analysis.json', 'w', encoding='utf-8') as f:
                    json.dump({
                        'analyzed_prompts': analyzed_prompts,
                        'prompts_by_phase': {
                            phase: [p['id'] for p in prompts]
                            for phase, prompts in prompts_by_phase.items()
                        }
                    }, f, indent=2, ensure_ascii=False)
                print("\nAnalysis results saved to prompt_analysis.json")
            except Exception as e:
                print(f"Error saving analysis results: {str(e)}")

            return prompts_by_phase
        except Exception as e:
            print(f"Error in analyze_all_prompts: {str(e)}")
            raise

if __name__ == "__main__":
    try:
        analyzer = ConversationPhaseAnalyzer()
        phase_analysis = analyzer.analyze_all_prompts()
    except Exception as e:
        print(f"Script failed: {str(e)}")
        raise 