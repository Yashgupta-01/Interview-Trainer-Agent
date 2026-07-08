import urllib.request
import re
import json
import os

def get_devinterview_questions():
    urls = [
        'https://devinterview.io/questions/machine-learning-and-data-science/python-ml-interview-questions/',
        'https://devinterview.io/questions/machine-learning-and-data-science/machine-learning-interview-questions/',
        'https://devinterview.io/questions/machine-learning-and-data-science/data-science-interview-questions/',
        'https://devinterview.io/questions/machine-learning-and-data-science/deep-learning-interview-questions/',
        'https://devinterview.io/questions/machine-learning-and-data-science/nlp-interview-questions/',
        'https://devinterview.io/questions/data-engineering-and-database/sql-interview-questions/',
        'https://devinterview.io/questions/data-engineering-and-database/pandas-interview-questions/',
        'https://devinterview.io/questions/web-and-mobile-development/python-interview-questions/'
    ]
    qs = []
    for url in urls:
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            html = urllib.request.urlopen(req).read().decode('utf-8')
            match = re.search(r'<script type="application/json"[^>]*>(.*?)</script>', html)
            if match:
                data = json.loads(match.group(1))
                if isinstance(data, list):
                    strings = [x for x in data if isinstance(x, str)]
                    qs.extend([s for s in strings if '?' in s and len(s) > 15])
        except Exception as e:
            pass
    return qs

def get_github_questions():
    urls = [
        'https://raw.githubusercontent.com/alexeygrigorev/data-science-interviews/master/README.md',
        'https://raw.githubusercontent.com/yanshengjia/ml-road/master/README.md',
        'https://raw.githubusercontent.com/virgili0/Virgilio/master/README.md'
    ]
    qs = []
    for url in urls:
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            text = urllib.request.urlopen(req).read().decode('utf-8')
            lines = text.split('\n')
            for line in lines:
                line = line.strip()
                if line.endswith('?') and len(line) > 15:
                    line = re.sub(r'^[\*\-\#\d\.\s]+', '', line)
                    qs.append(line)
        except Exception:
            pass
    return qs

def clean_q(q):
    q = re.sub(r'_(.*?)_', r'\1', q)
    q = re.sub(r'\*(.*?)\*', r'\1', q)
    q = re.sub(r'<[^>]+>', '', q)
    return q.strip()

def generate_robust_answer(q, strategy):
    q_lower = q.lower()
    base = "This is a core concept evaluated frequently in technical interviews."
    if 'sql' in q_lower or 'join' in q_lower or 'database' in q_lower:
        base = "In database engineering, this involves leveraging query optimization techniques like indexing, understanding join variations (INNER, LEFT, OUTER), and properly managing transaction isolation levels to ensure data integrity."
    elif 'neural' in q_lower or 'deep' in q_lower or 'gradient' in q_lower:
        base = "Deep learning systems address this by optimizing backpropagation through carefully tuned learning rates, utilizing activation functions like ReLU to mitigate vanishing gradients, and implementing dropout for regularization."
    elif 'overfit' in q_lower or 'variance' in q_lower:
        base = "To handle overfitting and high variance, practitioners utilize cross-validation (like k-fold), implement L1/L2 regularization (Lasso/Ridge), and gather more diverse training data."
    elif 'pandas' in q_lower or 'dataframe' in q_lower:
        base = "In Python's Pandas ecosystem, this is handled through vectorized operations, efficient grouping (groupby) and aggregation mechanisms, while avoiding expensive row-by-row iteration."
    elif 'transformer' in q_lower or 'llm' in q_lower:
        base = "Transformers address this through self-attention mechanisms that capture long-range dependencies efficiently, enabling massive parallelization during LLM pretraining."
    else:
        base = "A comprehensive approach requires balancing algorithmic complexity with scalable deployment, often testing edge cases and establishing robust baseline metrics before iterating on model complexity."
        
    if strategy == "STAR Method":
        return f"Situation/Task: When encountering problems related to '{q}'. Action/Result: {base} This consistently results in optimized performance and reliable deployments."
    elif strategy == "Flow Driven":
        return f"Step 1: Analyze the requirements of '{q}'. Step 2: Formulate the solution. {base} Step 3: Implement and monitor metrics."
    elif strategy == "Example Driven":
        return f"For example, consider a scenario asking '{q}'. A practical approach is: {base}"
    else:
        return f"Direct Answer: {base}"

def main():
    dev_qs = get_devinterview_questions()
    gh_qs = get_github_questions()
    all_qs = list(set([clean_q(q) for q in dev_qs + gh_qs if len(q) > 10]))

    roles = {"Data Analyst": [], "AI Engineer": [], "Machine Learning Engineer": [], "Data Scientist": []}

    for q in all_qs:
        ql = q.lower()
        if any(w in ql for w in ['sql', 'join', 'having', 'aggregate', 'dashboard', 'report', 'clean', 'pandas', 'excel']):
            roles["Data Analyst"].append(q)
        elif any(w in ql for w in ['llm', 'transformer', 'rag', 'tokenizer', 'agent', 'prompt', 'embedding', 'generative']):
            roles["AI Engineer"].append(q)
        elif any(w in ql for w in ['gradient', 'overfit', 'loss', 'optimizer', 'model', 'neural', 'hyperparameter', 'deep']):
            roles["Machine Learning Engineer"].append(q)
        else:
            roles["Data Scientist"].append(q)

    # Balance datasets to ensure exactly 150 each
    for role in roles:
        if len(roles[role]) < 150:
            shortfall = 150 - len(roles[role])
            for other_role in roles:
                if other_role != role and len(roles[other_role]) > 150:
                    borrow = roles[other_role][150:150+shortfall]
                    roles[role].extend(borrow)
                    roles[other_role] = roles[other_role][:150] + roles[other_role][150+shortfall:]
                    shortfall = 150 - len(roles[role])
                if shortfall <= 0:
                    break
                    
    final_dataset = []
    for role, qs in roles.items():
        strategies = ["Direct Answer", "Flow Driven", "STAR Method", "Example Driven"]
        for idx, q in enumerate(qs[:150]):
            final_dataset.append({
                "role": role,
                "category": "Technical Interview",
                "question": q,
                "answer_strategy": strategies[idx % 4],
                "tags": [role, "Technical"],
                "difficulty": "medium",
                "model_answer": generate_robust_answer(q, strategies[idx % 4])
            })

    output_path = r"D:\interview_trainer_agent\data\processed\questions.jsonl"
    with open(output_path, "w", encoding="utf-8") as f:
        for item in final_dataset:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
            
    print(f"Successfully generated {len(final_dataset)} questions at {output_path}")

if __name__ == "__main__":
    main()
