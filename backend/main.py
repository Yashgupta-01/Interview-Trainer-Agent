import os
import json
import random
import re
import requests
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional
from dotenv import load_dotenv

import backend.rag_utils as rag_utils

# Load environment variables from .env file
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'))

# Configuration (In production, these come from environment variables)
COS_API_KEY = os.getenv("COS_API_KEY", "")
COS_INSTANCE_CRN = os.getenv("COS_INSTANCE_CRN", "")
WATSONX_API_KEY = os.getenv("WATSONX_API_KEY", "")
WATSONX_PROJECT_ID = os.getenv("WATSONX_PROJECT_ID", "")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize and populate the RAG Vector Database on startup
    rag_utils.populate_database()
    yield  # application runs here

app = FastAPI(title="Interview Trainer API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class SessionRequest(BaseModel):
    role: str
    experience: str
    resume: str

class EvaluationRequest(BaseModel):
    question: str
    model_answer: str
    user_answer: str

class FrameAnswerRequest(BaseModel):
    question: str
    key_points: List[str]
    role: str
    experience: str

app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), '..', 'frontend')), name="static")

@app.get("/")
def read_root():
    return FileResponse(os.path.join(os.path.dirname(__file__), '..', 'frontend', 'index.html'))


@app.get("/api/health")
def health_check():
    return {"status": "ok", "rag_ready": True}

def _parse_watsonx_output(text: str):
    """
    Extract the first real QUESTION / MODEL_ANSWER pair from Watsonx output.
    Skips any placeholder blocks like 'QUESTION: [your question here]'.
    Returns (question, answer) or (None, None).
    """
    # Find all occurrences of QUESTION: ... MODEL_ANSWER: ... blocks (case-insensitive)
    pattern = re.compile(
        r'QUESTION:\s*(.*?)\s*MODEL_ANSWER:\s*(.*?)(?=\nQUESTION:|\Z)',
        re.IGNORECASE | re.DOTALL
    )
    for match in pattern.finditer(text):
        q = match.group(1).strip()
        a = match.group(2).strip()
        # Skip placeholder / template lines that the model echoes back
        if q.startswith('[') or not q or len(q) < 10:
            continue
        if a.startswith('[') or not a or len(a) < 10:
            continue
        return q, a
    return None, None


def call_watsonx(prompt: str, max_tokens: int = 100, temperature: float = 0.5) -> Optional[str]:
    if not WATSONX_API_KEY or not WATSONX_PROJECT_ID:
        return None
        
    token_url = "https://iam.cloud.ibm.com/identity/token"
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    data = f"grant_type=urn:ibm:params:oauth:grant-type:apikey&apikey={WATSONX_API_KEY}"
    
    try:
        token_resp = requests.post(token_url, headers=headers, data=data)
        if token_resp.status_code != 200:
            print(f"Failed to authenticate with IBM Cloud. Status: {token_resp.status_code}, Body: {token_resp.text}")
            return None
        
        access_token = token_resp.json().get("access_token")
        
        # au-syd is the region where this project lives
        ml_url = "https://au-syd.ml.cloud.ibm.com/ml/v1/text/generation?version=2023-05-29"
        ml_headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        # Use 'sample' decoding when temperature > 0 so the model is creative;
        # 'greedy' ignores temperature entirely.
        decoding = "sample" if temperature > 0 else "greedy"
        payload = {
            "input": prompt,
            "parameters": {
                "decoding_method": decoding,
                "max_new_tokens": max_tokens,
                "temperature": temperature,
            },
            # granite-13b-chat-v2 is deprecated on au-syd; use llama-3-3-70b-instruct
            "model_id": "meta-llama/llama-3-3-70b-instruct",
            "project_id": WATSONX_PROJECT_ID
        }
        
        resp = requests.post(ml_url, headers=ml_headers, json=payload)
        if resp.status_code == 200:
            result = resp.json()
            return result['results'][0]['generated_text'].strip()
        else:
            print(f"Error calling Watsonx REST API: {resp.status_code} {resp.text}")
            return None
            
    except Exception as e:
        print(f"Error communicating with Watsonx: {str(e)}")
        return None

@app.post("/api/start")
def get_question(req: SessionRequest):
    # Retrieve a larger candidate pool so we can randomise and avoid
    # always returning the same top-k embedding neighbours.
    retrieved = rag_utils.retrieve_questions(req.role, req.resume, k=20)
    
    if not retrieved:
        raise HTTPException(status_code=404, detail="No questions found for this role in the database.")
    
    # Shuffle to add variety even before hitting Watsonx
    random.shuffle(retrieved)

    # Attempt to dynamically generate a question via IBM Watsonx (Generative RAG)
    if WATSONX_API_KEY:
        # Pick 5 diverse reference questions from the shuffled pool
        ref_questions = "\n".join([f"- {q['question']}" for q in retrieved[:5]])
        prompt = (
            f"You are an expert technical interviewer.\n"
            f"Candidate Role: {req.experience} {req.role}\n"
            f"Candidate Resume/Background: {req.resume}\n\n"
            f"Reference Topics:\n{ref_questions}\n\n"
            f"Based ONLY on the candidate's exact background, generate a highly customized, specific interview question for them. "
            f"Do not ask generic questions. If they mention specific tools (like pandas or PyTorch) or zero experience, tailor the question to that.\n"
            f"Also provide a concise model answer for the generated question.\n\n"
            f"Output strictly in this exact format and nothing else:\n"
            f"QUESTION: [your question here]\n"
            f"MODEL_ANSWER: [your answer here]"
        )
        
        generated_text = call_watsonx(prompt, max_tokens=400, temperature=0.7)
        if generated_text:
            try:
                question, answer = _parse_watsonx_output(generated_text)
                if question and answer:
                    return {"question": question, "model_answer": answer, "source": "ibm-watsonx"}
                print(f"Watsonx parse failed, raw output: {generated_text[:300]}")
            except Exception as e:
                print(f"Watsonx parse error: {e}, raw: {generated_text[:300]}")
                
    # Fallback to static RAG if Watsonx fails or keys are missing
    question_data = retrieved[0]
    return {
        "question": question_data['question'],
        "model_answer": question_data['model_answer'],
        "source": "static-rag"
    }

@app.post("/api/frame_answer")
def frame_answer(req: FrameAnswerRequest):
    """Turn user's bullet key-points into a STAR-framed interview answer."""
    points_text = "\n".join(f"- {p}" for p in req.key_points)
    if not WATSONX_API_KEY:
        return {"framed_answer": points_text}

    prompt = (
        f"You are a career coach helping a {req.experience} {req.role} answer an interview question.\n"
        f"Question: {req.question}\n\n"
        f"The candidate's key points:\n{points_text}\n\n"
        f"Using ONLY these key points, write a concise, well-structured answer (3-5 sentences) "
        f"using the STAR method where applicable. Do not invent facts not in the key points.\n\n"
        f"Answer:"
    )
    result = call_watsonx(prompt, max_tokens=300, temperature=0.4)
    if result:
        # Strip any echo of the prompt prefix
        for prefix in ["Answer:", "answer:"]:
            if result.lower().startswith(prefix.lower()):
                result = result[len(prefix):].strip()
        # Strip stray code tails
        result = re.sub(r'\n```[\s\S]*$', '', result, flags=re.MULTILINE).strip()
        return {"framed_answer": result}
    return {"framed_answer": points_text}


@app.post("/api/evaluate")
def evaluate_answer(req: EvaluationRequest):
    if WATSONX_API_KEY and WATSONX_PROJECT_ID:
        prompt = (
            f"You are an expert technical interviewer evaluating a candidate's response.\n"
            f"Question: {req.question}\n"
            f"Model Answer: {req.model_answer}\n"
            f"Candidate's Answer: {req.user_answer}\n\n"
            f"Evaluate the candidate using ONLY this exact format. "
            f"Output nothing before SCORE and nothing after IMPROVED_ANSWER. No code, no notes.\n\n"
            f"SCORE: [number]/10\n"
            f"SUMMARY: [one or two sentence overall assessment]\n"
            f"STRENGTHS:\n"
            f"- [strength 1]\n"
            f"- [strength 2]\n"
            f"WEAKNESSES:\n"
            f"- [weakness 1]\n"
            f"- [weakness 2]\n"
            f"IMPROVEMENT_TIPS:\n"
            f"- [specific tip 1]\n"
            f"- [specific tip 2]\n"
            f"- [specific tip 3]\n"
            f"IMPROVED_ANSWER: [rewrite the candidate's answer in a better, structured way — "
            f"keep their correct points but fix gaps, add missing depth, and frame it professionally]\n"
            f"END"
        )

        feedback = call_watsonx(prompt, max_tokens=600, temperature=0.2)
        if feedback:
            return {"feedback": feedback, "source": "ibm-watsonx"}
        else:
            raise HTTPException(
                status_code=502,
                detail="IBM Watsonx API call failed. Check server logs for details."
            )
    else:
        return {
            "feedback": "IBM Watsonx credentials are not configured. Set WATSONX_API_KEY and WATSONX_PROJECT_ID in your .env file.",
            "source": "mock"
        }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
