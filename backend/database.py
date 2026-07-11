import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'history.db')

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            question TEXT,
            score REAL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def log_score(session_id: str, question: str, score: float):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO history (session_id, question, score) VALUES (?, ?, ?)", 
              (session_id, question, score))
    conn.commit()
    conn.close()

def get_recent_scores(session_id: str, limit: int = 3):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT score FROM history WHERE session_id = ? ORDER BY timestamp DESC LIMIT ?", 
              (session_id, limit))
    rows = c.fetchall()
    conn.close()
    return [r[0] for r in rows]

def get_session_history(session_id: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT question, score FROM history WHERE session_id = ? ORDER BY timestamp ASC", (session_id,))
    rows = c.fetchall()
    conn.close()
    return [{"question": r[0], "score": r[1]} for r in rows]

def get_all_history():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT session_id, question, score, timestamp FROM history ORDER BY timestamp DESC")
    rows = c.fetchall()
    conn.close()
    
    history_dict = {}
    for r in rows:
        sid, q, score, ts = r
        if sid not in history_dict:
            history_dict[sid] = {"session_id": sid, "timestamp": ts, "questions": []}
        history_dict[sid]["questions"].append({"question": q, "score": score, "timestamp": ts})
        
    return list(history_dict.values())

def clear_history():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM history")
    conn.commit()
    conn.close()
