import streamlit as st
import requests

API_URL = "http://127.0.0.1:8000"

st.set_page_config(page_title="AI Interview Trainer", page_icon="🤖", layout="centered")

st.title("🤖 AI Interview Trainer")
st.write("Welcome to your technical interview! Built with IBM Cloud components in mind.")

# Initialize session state variables
if "current_question" not in st.session_state:
    st.session_state.current_question = None
if "model_answer" not in st.session_state:
    st.session_state.model_answer = None
if "feedback" not in st.session_state:
    st.session_state.feedback = None

role = st.selectbox("Select your Interview Role:", [
    "Machine Learning Engineer", 
    "Data Scientist", 
    "Data Analyst", 
    "AI Engineer"
])

if st.button("Generate Interview Question"):
    try:
        response = requests.post(f"{API_URL}/api/start", json={"role": role})
        if response.status_code == 200:
            data = response.json()
            st.session_state.current_question = data.get("question")
            st.session_state.model_answer = data.get("model_answer")
            st.session_state.feedback = None # Reset feedback
        else:
            st.error(f"Error fetching question: {response.text}")
    except requests.exceptions.ConnectionError:
        st.error("Could not connect to the Backend API. Ensure your FastAPI server is running!")

if st.session_state.current_question:
    st.subheader("Your Question:")
    st.info(st.session_state.current_question)
    
    user_answer = st.text_area("Your Answer:", height=150)
    
    if st.button("Submit Answer"):
        if not user_answer.strip():
            st.warning("Please enter an answer before submitting.")
        else:
            with st.spinner("Evaluating your answer via IBM watsonx.ai (or mock)..."):
                try:
                    payload = {
                        "question": st.session_state.current_question,
                        "model_answer": st.session_state.model_answer,
                        "user_answer": user_answer
                    }
                    eval_res = requests.post(f"{API_URL}/api/evaluate", json=payload)
                    
                    if eval_res.status_code == 200:
                        st.session_state.feedback = eval_res.json().get("feedback")
                    else:
                        st.error("Evaluation failed.")
                except requests.exceptions.ConnectionError:
                    st.error("Could not connect to the Backend API.")

if st.session_state.feedback:
    st.subheader("Evaluation Feedback")
    st.success(st.session_state.feedback)
