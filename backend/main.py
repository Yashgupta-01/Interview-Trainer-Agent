import os
import json
import random
import re
import httpx
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional
from dotenv import load_dotenv

import backend.rag_utils as rag_utils
import backend.database as database

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# Document extraction
import PyPDF2
import docx
import io

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'))

WATSONX_API_KEY = os.getenv("WATSONX_API_KEY", "")
WATSONX_PROJECT_ID = os.getenv("WATSONX_PROJECT_ID", "")

limiter = Limiter(key_func=get_remote_address)

@asynccontextmanager
async def lifespan(app: FastAPI):
    rag_utils.populate_database()
    database.init_db()
    yield

app = FastAPI(title="Interview Trainer API", lifespan=lifespan)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000", "http://127.0.0.1:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class SessionRequest(BaseModel):
    session_id: str
    profile_name: str
    role: str
    experience: str
    resume: str
    question_type: str = "Technical"  # default to Technical

class EvaluationRequest(BaseModel):
    session_id: str
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

@app.post("/api/upload_resume")
@limiter.limit("5/minute")
async def upload_resume(request: Request, file: UploadFile = File(...)):
    content = await file.read()
    text = ""
    filename = file.filename.lower()
    try:
        if filename.endswith(".pdf"):
            reader = PyPDF2.PdfReader(io.BytesIO(content))
            for page in reader.pages:
                text += page.extract_text() + "\n"
        elif filename.endswith(".docx"):
            doc = docx.Document(io.BytesIO(content))
            for para in doc.paragraphs:
                text += para.text + "\n"
        else:
            raise HTTPException(status_code=400, detail="Only PDF or DOCX files are supported.")
        return {"resume_text": text.strip()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error parsing file: {str(e)}")

async def call_watsonx_async(prompt: str, max_tokens: int = 100, temperature: float = 0.5) -> Optional[str]:
    if not WATSONX_API_KEY or not WATSONX_PROJECT_ID:
        return None
        
    token_url = "https://iam.cloud.ibm.com/identity/token"
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    data = f"grant_type=urn:ibm:params:oauth:grant-type:apikey&apikey={WATSONX_API_KEY}"
    
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            token_resp = await client.post(token_url, headers=headers, data=data)
            if token_resp.status_code != 200:
                print(f"Failed to authenticate with IBM Cloud. Status: {token_resp.status_code}")
                return None
            
            access_token = token_resp.json().get("access_token")
            
            # Sydney (au-syd) region
            ml_url = "https://au-syd.ml.cloud.ibm.com/ml/v1/text/generation?version=2023-05-29"
            ml_headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
            decoding = "sample" if temperature > 0 else "greedy"
            payload = {
                "input": prompt,
                "parameters": {
                    "decoding_method": decoding,
                    "max_new_tokens": max_tokens,
                    "temperature": temperature,
                },
                "model_id": "meta-llama/llama-3-3-70b-instruct",
                "project_id": WATSONX_PROJECT_ID
            }
            
            resp = await client.post(ml_url, headers=ml_headers, json=payload)
            if resp.status_code == 200:
                result = resp.json()
                return result['results'][0]['generated_text'].strip()
            else:
                print(f"Error calling Watsonx REST API: {resp.status_code} {resp.text}")
                return None
                
        except Exception as e:
            print(f"Error communicating with Watsonx: {str(e)}")
            return None

@app.post("/api/strategy")
@limiter.limit("5/minute")
async def generate_strategy(request: Request, req: SessionRequest):
    if not WATSONX_API_KEY:
        return {"strategy": "IBM Watsonx API key is missing. Cannot generate strategy."}
        
    prompt = (
        f"You are an expert career coach.\n"
        f"Candidate Name: {req.profile_name}\n"
        f"Candidate Role: {req.experience} {req.role}\n"
        f"Candidate Background: {req.resume}\n\n"
        f"Based ONLY on their background, generate a short, personalized Preparation Strategy (3-4 bullet points) "
        f"for their upcoming interview. Highlight what they should focus on studying.\n"
        f"Output nothing but the bullet points."
    )
    
    result = await call_watsonx_async(prompt, max_tokens=250, temperature=0.6)
    if result:
        return {"strategy": result}
    return {"strategy": "Failed to generate strategy."}

@app.post("/api/start")
@limiter.limit("10/minute")
async def get_question(request: Request, req: SessionRequest):
    # Fetch adaptive difficulty from SQLite
    recent_scores = database.get_recent_scores(req.session_id, limit=3)
    avg_score = sum(recent_scores)/len(recent_scores) if recent_scores else 5.0
    
    difficulty_modifier = ""
    if avg_score < 5.0:
        difficulty_modifier = "The candidate has struggled recently. Please ask an EASIER, more fundamental question."
    elif avg_score >= 8.0:
        difficulty_modifier = "The candidate is doing great. Please ask a HARDER, more advanced question."

    # We pass req.role for the exact metadata match, but we can add question_type to the query text
    query_hint = f"{req.resume} Focus: {req.question_type}"
    retrieved = rag_utils.retrieve_questions(req.role, query_hint, k=20)
    
    if not retrieved:
        raise HTTPException(status_code=404, detail="No questions found for this role in the database.")
    
    random.shuffle(retrieved)

    if WATSONX_API_KEY:
        ref_questions = "\n".join([f"- {q['question']}" for q in retrieved[:5]])
        prompt = (
            f"You are an expert technical interviewer.\n"
            f"Candidate Name: {req.profile_name}\n"
            f"Candidate Role: {req.experience} {req.role}\n"
            f"Question Type Focus: {req.question_type}\n"
            f"Candidate Background: {req.resume}\n\n"
            f"Reference Topics:\n{ref_questions}\n\n"
            f"Based ONLY on the candidate's exact background and the Question Type Focus, generate a highly customized interview question for them. "
            f"{difficulty_modifier} "
            f"CRITICAL RULE: The candidate's experience level is {req.experience}. Do NOT ask questions that are too advanced for their level. "
            f"If they are 'Junior' or have 0 experience, focus heavily on fundamentals, basic definitions, and simple scenarios. "
            f"If they are 'Senior', focus on deep architecture, system design, and trade-offs. "
            f"Also provide a concise model answer for the generated question.\n\n"
            f"Output strictly in VALID JSON format with exact keys 'question' and 'model_answer'. Do not output any markdown formatting or extra text.\n"
            f"{{\n"
            f'  "question": "[your question here]",\n'
            f'  "model_answer": "[your answer here]"\n'
            f"}}"
        )
        
        generated_text = await call_watsonx_async(prompt, max_tokens=400, temperature=0.7)
        if generated_text:
            try:
                # Strip markdown JSON fences if they leaked in
                clean_json = re.sub(r'```json|```', '', generated_text).strip()
                parsed = json.loads(clean_json)
                q = parsed.get('question')
                a = parsed.get('model_answer')
                if q and a:
                    return {"question": q, "model_answer": a, "source": "ibm-watsonx"}
            except Exception as e:
                print(f"Watsonx JSON parse error: {e}, raw: {generated_text[:300]}")
                
    question_data = retrieved[0]
    return {
        "question": question_data['question'],
        "model_answer": question_data['model_answer'],
        "source": "static-rag"
    }

@app.post("/api/frame_answer")
@limiter.limit("10/minute")
async def frame_answer(request: Request, req: FrameAnswerRequest):
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
    result = await call_watsonx_async(prompt, max_tokens=300, temperature=0.4)
    if result:
        for prefix in ["Answer:", "answer:"]:
            if result.lower().startswith(prefix.lower()):
                result = result[len(prefix):].strip()
        result = re.sub(r'\n```[\s\S]*$', '', result, flags=re.MULTILINE).strip()
        return {"framed_answer": result}
    return {"framed_answer": points_text}

@app.post("/api/evaluate")
@limiter.limit("10/minute")
async def evaluate_answer(request: Request, req: EvaluationRequest):
    if WATSONX_API_KEY and WATSONX_PROJECT_ID:
        prompt = (
            f"You are an expert technical interviewer evaluating a candidate's response.\n"
            f"Question: {req.question}\n"
            f"Model Answer: {req.model_answer}\n"
            f"Candidate's Answer: {req.user_answer}\n\n"
            f"CRITICAL RULES:\n"
            f"1. ONLY evaluate the Candidate's Answer. Do NOT evaluate the Model Answer.\n"
            f"2. If the Candidate's Answer is evasive (e.g., 'you tell me', 'I don't know'), extremely short, nonsensical, or completely incorrect, you MUST give a score of 0, 1, or 2.\n"
            f"3. Be a strict grader. Only give 8+ if the answer is highly detailed and technically accurate.\n\n"
            f"Evaluate the candidate and output strictly in VALID JSON format with exact keys: "
            f"'score' (integer 0-10), 'summary' (string), 'strengths' (list of strings), 'weaknesses' (list of strings), 'improvement_tips' (list of strings), 'improved_answer' (string).\n"
            f"Do not output any markdown formatting or extra text."
        )

        feedback_json_str = await call_watsonx_async(prompt, max_tokens=600, temperature=0.2)
        if feedback_json_str:
            try:
                # Robust JSON extraction
                match = re.search(r'\{.*\}', feedback_json_str, re.DOTALL)
                if match:
                    clean_json = match.group(0)
                else:
                    clean_json = re.sub(r'```json|```', '', feedback_json_str).strip()
                parsed = json.loads(clean_json)
                
                score = parsed.get("score", 5)
                # Log score to SQLite
                database.log_score(req.session_id, req.question, float(score))
                
                return {"feedback": parsed, "source": "ibm-watsonx"}
            except Exception as e:
                print(f"JSON Parse error in evaluate: {e}, raw: {feedback_json_str[:300]}")
                raise HTTPException(status_code=500, detail="Failed to parse Watsonx evaluation.")
        else:
            raise HTTPException(status_code=502, detail="IBM Watsonx API call failed.")
    else:
        # Mock logic
        database.log_score(req.session_id, req.question, 7.0)
        return {
            "feedback": {
                "score": 7,
                "summary": "Mock summary.",
                "strengths": ["Mock strength"],
                "weaknesses": ["Mock weakness"],
                "improvement_tips": ["Mock tip"],
                "improved_answer": "Mock improved answer."
            },
            "source": "mock"
        }

@app.get("/api/history/all")
async def get_all_historical_scores():
    try:
        data = database.get_all_history()
        return {"history": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/history/clear")
async def clear_all_historical_scores():
    try:
        database.clear_history()
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/report")
@limiter.limit("5/minute")
async def generate_report(request: Request, req: SessionRequest):
    history = database.get_session_history(req.session_id)
    if not history:
        return {"report": "No interview history found for this session."}
        
    avg_score = sum(h["score"] for h in history) / len(history)
    history_text = "\n".join([f"Q: {h['question']} | Score: {h['score']}/10" for h in history])
    
    prompt = (
        f"You are a career coach giving a final debrief.\n"
        f"Candidate: {req.profile_name} ({req.role})\n"
        f"Average Score: {avg_score:.1f}/10\n"
        f"Session History:\n{history_text}\n\n"
        f"Generate a VERY BRIEF and concise summary report (maximum 3-4 bullet points). "
        f"Highlight the top weak areas and give a quick study plan. Be direct and short."
    )
    
    result = await call_watsonx_async(prompt, max_tokens=250, temperature=0.5)
    if result:
        return {"report": result, "average_score": avg_score}
    return {"report": "Failed to generate report.", "average_score": avg_score}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
