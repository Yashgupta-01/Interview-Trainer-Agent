import os
import json
import chromadb
from chromadb.utils import embedding_functions

# Initialize ChromaDB client (local persistent storage)
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'chroma_db')
os.makedirs(DB_PATH, exist_ok=True)

chroma_client = chromadb.PersistentClient(path=DB_PATH)

# We use the default ONNX MiniLM embedding function (lightweight & fast)
sentence_transformer_ef = embedding_functions.DefaultEmbeddingFunction()

def get_or_create_collection():
    return chroma_client.get_or_create_collection(
        name="interview_questions", 
        embedding_function=sentence_transformer_ef
    )

def populate_database():
    collection = get_or_create_collection()
    
    # Check if already populated
    if collection.count() > 0:
        print(f"ChromaDB already populated with {collection.count()} questions.")
        return
        
    dataset_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'processed', 'questions.jsonl')
    
    if not os.path.exists(dataset_path):
        print(f"Dataset not found at {dataset_path}")
        return
        
    documents = []
    metadatas = []
    ids = []
    
    print("Loading questions into Vector Database...")
    with open(dataset_path, 'r', encoding='utf-8') as f:
        for i, line in enumerate(f):
            if not line.strip(): continue
            try:
                q = json.loads(line)
                
                # The document to embed is the question itself plus the role/experience context
                # This helps the RAG match the resume text to the question content
                doc_text = f"Role: {q.get('role', '')}. Type: {q.get('type', 'Technical')}. Question: {q.get('question', '')}"
                
                documents.append(doc_text)
                metadatas.append({
                    "role": q.get('role', ''),
                    "question": q.get('question', ''),
                    "model_answer": q.get('model_answer', ''),
                    "type": q.get('type', 'Technical')
                })
                ids.append(f"q_{i}")
                
            except json.JSONDecodeError:
                pass
                
    # Add to Chroma in batches
    batch_size = 100
    for i in range(0, len(documents), batch_size):
        collection.add(
            documents=documents[i:i+batch_size],
            metadatas=metadatas[i:i+batch_size],
            ids=ids[i:i+batch_size]
        )
        print(f"Inserted batch {i//batch_size + 1}")
        
    print(f"Successfully populated Vector DB with {len(documents)} questions.")

def retrieve_questions(role: str, resume_text: str, k: int = 5):
    collection = get_or_create_collection()
    
    # Clamp k to however many items exist for this role so ChromaDB doesn't raise
    total = collection.count()
    k = min(k, max(1, total))
    
    # Query string combines the user's role and resume to find matching questions
    query_text = f"Interview questions for a {role}. Candidate background: {resume_text}"
    
    # We filter by role to ensure they only get questions for the job they applied for
    results = collection.query(
        query_texts=[query_text],
        n_results=k,
        where={"role": role}
    )
    
    # Extract metadata
    if results and results['metadatas'] and len(results['metadatas']) > 0:
        return results['metadatas'][0]
    return []

if __name__ == "__main__":
    populate_database()
