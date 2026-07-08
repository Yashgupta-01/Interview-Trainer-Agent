import json
import os
import random

DATASET_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'processed', 'questions.jsonl')

roles = ["Machine Learning Engineer", "Data Scientist", "Data Analyst", "AI Engineer"]
experience_levels = ["Junior", "Mid", "Senior"]

# Core behavioral themes based on HR guidelines
themes = [
    ("Conflict Resolution", "Tell me about a time you disagreed with a colleague or manager on a technical approach. How did you handle it?"),
    ("Adaptability", "Describe a situation where project requirements changed drastically at the last minute. What did you do?"),
    ("Leadership", "Can you share an example of a time you had to take the lead on a difficult project without formal authority?"),
    ("Communication", "Explain how you would communicate a complex technical concept or model result to a non-technical stakeholder."),
    ("Failure", "Tell me about a time a project you worked on failed or a model underperformed in production. What did you learn?"),
    ("Time Management", "How do you prioritize your work when you have multiple tight deadlines? Provide a specific example."),
    ("Continuous Learning", "The AI/Data field moves incredibly fast. How do you stay updated, and can you give an example of applying a newly learned concept?"),
    ("Ethics", "If you discovered bias in a dataset you were using for a critical model, how would you address it with your team?"),
    ("Teamwork", "Describe your role in a successful cross-functional team project. What was the most challenging part of collaborating?"),
    ("Problem Solving", "Tell me about the most complex technical problem you've faced and the steps you took to solve it.")
]

def generate_soft_skill_questions():
    questions = []
    for _ in range(150):
        theme, base_question = random.choice(themes)
        role = random.choice(roles)
        exp = random.choice(experience_levels)
        
        # Tailor the question slightly based on role and experience
        tailored_q = f"[{theme} - {exp} {role}] {base_question}"
        
        # Generate a model answer strategy
        model_answer = (
            f"Use the STAR method (Situation, Task, Action, Result). "
            f"Focus on showing soft skills relevant to a {exp}-level {role}. "
            f"Emphasize collaboration, empathy, clear communication, and taking ownership of outcomes."
        )
        
        questions.append({
            "role": role,
            "type": "Behavioral",
            "experience": exp,
            "question": tailored_q,
            "model_answer": model_answer,
            "answer_strategy": "STAR method"
        })
    return questions

if __name__ == "__main__":
    new_questions = generate_soft_skill_questions()
    
    with open(DATASET_PATH, 'a', encoding='utf-8') as f:
        for q in new_questions:
            f.write(json.dumps(q) + '\n')
            
    print(f"Successfully appended {len(new_questions)} HR/Behavioral questions to {DATASET_PATH}.")
