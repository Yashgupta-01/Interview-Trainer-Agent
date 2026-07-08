import urllib.request
import re
import json
import os
import html

def get_questions_from_url(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req) as response:
            content = response.read().decode('utf-8')
        # Find headings containing questions, e.g. <h3>1. How do you...</h3>
        headings = re.findall(r'<h[23][^>]*>(.*?)</h[23]>', content)
        questions = []
        for h in headings:
            clean_q = re.sub(r'<[^<]+?>', '', h) # Strip HTML tags
            clean_q = html.unescape(clean_q)
            # Remove leading numbers like "1. ", "100. "
            clean_q = re.sub(r'^\d+\.\s*', '', clean_q).strip()
            if clean_q and any(clean_q.lower().startswith(w) for w in ['how', 'what', 'explain', 'why', 'when', 'difference', 'can', 'define', 'is', 'compare', 'describe']):
                questions.append(clean_q)
        return list(set(questions))
    except Exception as e:
        print(f"Error scraping {url}: {e}")
        return []

def main():
    urls = [
        "https://devinterview.io/questions/machine-learning-and-data-science/python-ml-interview-questions/",
        "https://devinterview.io/questions/machine-learning-and-data-science/machine-learning-interview-questions/",
        "https://devinterview.io/questions/machine-learning-and-data-science/data-science-interview-questions/"
    ]
    
    scraped_questions = []
    for url in urls:
        print(f"Scraping {url}...")
        qs = get_questions_from_url(url)
        print(f"Found {len(qs)} questions.")
        scraped_questions.extend(qs)
        
    scraped_questions = list(set(scraped_questions))
    print(f"Total unique scraped questions: {len(scraped_questions)}")
    
    # Save the scraped list to raw data
    raw_path = "D:\\interview_trainer_agent\\data\\raw\\scraped_questions.json"
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump(scraped_questions, f, indent=4)
        
if __name__ == "__main__":
    main()
