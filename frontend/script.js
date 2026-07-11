/**
 * Parse the structured Watsonx evaluation response into readable HTML.
 * Expected sections: SCORE, SUMMARY, STRENGTHS, WEAKNESSES, IMPROVEMENT_TIPS
 * Falls back to a plain-text render if the format is unexpected.
 */
function formatFeedback(text) {
    // Strip any LLM "tail" that appears after the last real bullet/content line.
    // This removes stray code blocks, function defs, comments, etc.
    function stripTail(src) {
        // Cut at the first line that looks like code/markdown-fence/comment
        return src.replace(/\n```[\s\S]*$/m, '')   // ```...
                  .replace(/\ndef [a-z][\s\S]*$/m, '')  // def foo():
                  .replace(/\nclass [A-Z][\s\S]*$/m, '') // class Foo:
                  .replace(/\nNote:[\s\S]*$/im, '')      // Note: ...
                  .replace(/\n\*\*Note[\s\S]*$/im, '');  // **Note...
    }

    // Extract a named section's content between its header and the next header
    function extract(label, src) {
        const re = new RegExp(label + ':?\\s*([\\s\\S]*?)(?=\\n[A-Z_]+:|$)', 'i');
        const m = src.match(re);
        return m ? stripTail(m[1].trim()) : null;
    }

    // Parse bullet lines (lines starting with - or *)
    function bulletList(block) {
        if (!block) return '';
        const items = block.split('\n')
            .map(l => l.replace(/^[\-\*]\s*/, '').trim())
            // drop empty lines and any stray non-content lines the LLM appends
            .filter(l => l.length > 0
                      && !l.startsWith('`')
                      && !l.startsWith('#')
                      && !l.startsWith('def ')
                      && !l.startsWith('print(')
                      && !l.startsWith('no_code')
                      && !l.match(/^\w+\(\)$/));   // bare function calls like no_code_required()
        if (items.length === 0) return '';
        return '<ul>' + items.map(i => `<li>${escHtml(i)}</li>`).join('') + '</ul>';
    }

    function escHtml(s) {
        return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    }

    const score           = extract('SCORE', text);
    const summary         = extract('SUMMARY', text);
    const strengths       = extract('STRENGTHS', text);
    const weaknesses      = extract('WEAKNESSES', text);
    const tips            = extract('IMPROVEMENT_TIPS', text);
    const improvedAnswer  = extract('IMPROVED_ANSWER', text);

    // If none of the expected markers are present, fall back to plain text
    if (!score && !summary && !strengths) {
        return '<p>' + escHtml(text).replace(/\n/g, '<br>') + '</p>';
    }

    let html = '';

    if (score) {
        const numeric = score.replace('/10', '').trim();
        html += `<div class="fb-score">
                    <span class="score-num">${escHtml(numeric)}</span>
                    <span class="score-denom">&nbsp;/ 10</span>
                 </div>`;
    }

    if (summary) {
        html += `<p class="fb-summary">${escHtml(summary)}</p>`;
    }

    if (strengths) {
        html += `<div class="fb-section">
                    <h4 class="fb-heading fb-strengths">✔ Strengths</h4>
                    ${bulletList(strengths)}
                 </div>`;
    }

    if (weaknesses) {
        html += `<div class="fb-section">
                    <h4 class="fb-heading fb-weaknesses">✘ Weaknesses</h4>
                    ${bulletList(weaknesses)}
                 </div>`;
    }

    if (tips) {
        html += `<div class="fb-section">
                    <h4 class="fb-heading fb-tips">💡 Improvement Tips</h4>
                    ${bulletList(tips)}
                 </div>`;
    }

    if (improvedAnswer) {
        // Clean up: strip "END" if it leaked in, strip code fences
        const clean = improvedAnswer.replace(/\bEND\b\s*$/i, '').replace(/```[\s\S]*?```/g, '').trim();
        if (clean) {
            html += `<div class="fb-section fb-improved">
                        <h4 class="fb-heading fb-improved-heading">✏️ How Your Answer Could Look</h4>
                        <div class="improved-answer-box">${escHtml(clean)}</div>
                     </div>`;
        }
    }

    return html;
}


const API_URL = "http://127.0.0.1:8000";

let currentModelAnswer = null;
let currentQuestion    = '';
let currentRole        = '';
let currentExp         = '';
const sessionId        = crypto.randomUUID(); // Unique session ID for tracking


const elements = {
    profileName:       document.getElementById('profile-name'),
    roleSelect:        document.getElementById('role-select'),
    expSelect:         document.getElementById('exp-select'),
    resumeFile:        document.getElementById('resume-file'),
    uploadResumeBtn:   document.getElementById('upload-resume-btn'),
    resumeText:        document.getElementById('resume-text'),
    setupSection:      document.getElementById('setup-section'),
    generateStrategyBtn: document.getElementById('generate-strategy-btn'),
    strategySection:   document.getElementById('strategy-section'),
    strategyText:      document.getElementById('strategy-text'),
    startInterviewBtn: document.getElementById('start-interview-btn'),
    interviewSection:  document.getElementById('interview-section'),
    endInterviewBtn:   document.getElementById('end-interview-btn'),
    questionText:      document.getElementById('question-text'),
    userAnswer:        document.getElementById('user-answer'),
    submitBtn:         document.getElementById('submit-btn'),
    generateNextBtn:   document.getElementById('generate-next-btn'),
    questionTypeSelect:document.getElementById('question-type-select'),
    showAnswerBtn:     document.getElementById('show-answer-btn'),
    showAnswerSection: document.getElementById('show-answer-section'),
    modelAnswerText:   document.getElementById('model-answer-text'),
    keyPointsSection:  document.getElementById('key-points-section'),
    kpRows:            document.getElementById('kp-rows'),
    kpAddBtn:          document.getElementById('kp-add-btn'),
    kpGenerateBtn:     document.getElementById('kp-generate-btn'),
    framedAnswerBox:   document.getElementById('framed-answer-box'),
    framedAnswerText:  document.getElementById('framed-answer-text'),
    feedbackSection:   document.getElementById('feedback-section'),
    feedbackContent:   document.getElementById('feedback-content'),
    reportSection:     document.getElementById('report-section'),
    reportAvgScore:    document.getElementById('report-avg-score'),
    reportContent:     document.getElementById('report-content'),
    backHomeBtn:       document.getElementById('back-home-btn')
};

elements.uploadResumeBtn.addEventListener('click', async () => {
    const file = elements.resumeFile.files[0];
    if (!file) {
        alert("Please select a file first.");
        return;
    }
    const formData = new FormData();
    formData.append("file", file);
    
    elements.uploadResumeBtn.textContent = 'Uploading...';
    elements.uploadResumeBtn.disabled = true;
    
    try {
        const response = await fetch(`${API_URL}/api/upload_resume`, {
            method: 'POST',
            body: formData
        });
        if (response.ok) {
            const data = await response.json();
            elements.resumeText.value = data.resume_text;
            alert("Resume parsed successfully!");
        } else {
            alert("Failed to parse resume.");
        }
    } catch (error) {
        alert("Connection error during upload.");
    } finally {
        elements.uploadResumeBtn.textContent = 'Upload';
        elements.uploadResumeBtn.disabled = false;
    }
});

elements.generateStrategyBtn.addEventListener('click', async () => {
    const profileName = elements.profileName.value.trim();
    const role = elements.roleSelect.value;
    const experience = elements.expSelect.value;
    const resume = elements.resumeText.value.trim();

    if (!profileName || !resume) {
        alert("Please enter your name and paste a brief resume or background summary!");
        return;
    }
    
    const originalText = elements.generateStrategyBtn.textContent;
    elements.generateStrategyBtn.innerHTML = '<span class="loader"></span> Analyzing...';
    elements.generateStrategyBtn.disabled = true;

    try {
        const response = await fetch(`${API_URL}/api/strategy`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: sessionId, profile_name: profileName, role: role, experience: experience, resume: resume })
        });

        if (response.ok) {
            const data = await response.json();
            // Format strategy with line breaks
            elements.strategyText.innerHTML = data.strategy.replace(/\n/g, '<br>');
            elements.strategySection.classList.remove('hidden');
            currentRole = role;
            currentExp = experience;
        } else {
            alert('Failed to fetch strategy.');
        }
    } catch (error) {
        alert('Connection error. Ensure backend is running.');
    } finally {
        elements.generateStrategyBtn.textContent = originalText;
        elements.generateStrategyBtn.disabled = false;
    }
});

elements.startInterviewBtn.addEventListener('click', () => {
    elements.setupSection.classList.add('hidden');
    elements.interviewSection.classList.remove('hidden');
    elements.generateNextBtn.click();
});

elements.generateNextBtn.addEventListener('click', async () => {
    const profileName = elements.profileName.value.trim();
    const role = elements.roleSelect.value;
    const experience = elements.expSelect.value;
    const resume = elements.resumeText.value.trim();
    const questionType = elements.questionTypeSelect.value;
    
    // UI Loading State
    const originalText = elements.generateNextBtn.textContent;
    elements.generateNextBtn.innerHTML = '<span class="loader"></span> Generating...';
    elements.generateNextBtn.disabled = true;
    elements.feedbackSection.classList.add('hidden');
    elements.userAnswer.value = '';

    try {
        const response = await fetch(`${API_URL}/api/start`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: sessionId, profile_name: profileName, role: role, experience: experience, resume: resume, question_type: questionType })
        });

        if (response.ok) {
            const data = await response.json();
            currentQuestion    = data.question;
            currentModelAnswer = data.model_answer;
            elements.questionText.textContent = data.question;
            
            // Reset secondary UI for fresh question
            elements.showAnswerSection.classList.add('hidden');
            elements.feedbackSection.classList.add('hidden');
            elements.userAnswer.value = '';
            elements.framedAnswerBox.classList.add('hidden');
            elements.kpRows.innerHTML = '<div class="kp-row"><input class="kp-input" type="text" placeholder="e.g. Used transfer learning with ResNet50"></div>';
        } else {
            alert('Failed to fetch question. Check if backend is running.');
        }
    } catch (error) {
        alert('Connection error. Ensure the FastAPI backend is running on port 8000.');
    } finally {
        elements.generateNextBtn.textContent = originalText;
        elements.generateNextBtn.disabled = false;
    }
});

elements.submitBtn.addEventListener('click', async () => {
    const answer = elements.userAnswer.value.trim();
    if (!answer) {
        alert('Please enter your answer before submitting.');
        return;
    }

    // UI Loading State
    const originalText = elements.submitBtn.textContent;
    elements.submitBtn.innerHTML = '<span class="loader"></span> Evaluating...';
    elements.submitBtn.disabled = true;

    try {
        const payload = {
            session_id: sessionId,
            question: currentQuestion,
            model_answer: currentModelAnswer,
            user_answer: answer
        };

        const response = await fetch(`${API_URL}/api/evaluate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (response.ok) {
            const data = await response.json();
            
            // Format feedback from JSON
            const fb = data.feedback;
            let fbHtml = `<div class="fb-score"><span class="score-num">${fb.score}</span><span class="score-denom">&nbsp;/ 10</span></div>`;
            fbHtml += `<p class="fb-summary">${fb.summary || ''}</p>`;
            if (fb.strengths && fb.strengths.length) {
                fbHtml += `<div class="fb-section"><h4 class="fb-heading fb-strengths">✔ Strengths</h4><ul>${fb.strengths.map(s => `<li>${s}</li>`).join('')}</ul></div>`;
            }
            if (fb.weaknesses && fb.weaknesses.length) {
                fbHtml += `<div class="fb-section"><h4 class="fb-heading fb-weaknesses">✘ Weaknesses</h4><ul>${fb.weaknesses.map(s => `<li>${s}</li>`).join('')}</ul></div>`;
            }
            if (fb.improvement_tips && fb.improvement_tips.length) {
                fbHtml += `<div class="fb-section"><h4 class="fb-heading fb-tips">💡 Improvement Tips</h4><ul>${fb.improvement_tips.map(s => `<li>${s}</li>`).join('')}</ul></div>`;
            }
            if (fb.improved_answer) {
                fbHtml += `<div class="fb-section fb-improved"><h4 class="fb-heading fb-improved-heading">✏️ How Your Answer Could Look</h4><div class="improved-answer-box">${fb.improved_answer}</div></div>`;
            }
            
            elements.feedbackContent.innerHTML = fbHtml;
            elements.feedbackSection.classList.remove('hidden');
        } else {
            const err = await response.json().catch(() => ({}));
            alert('Evaluation failed: ' + (err.detail || response.statusText));
        }
    } catch (error) {
        alert('Connection error during evaluation.');
    } finally {
        elements.submitBtn.textContent = originalText;
        elements.submitBtn.disabled = false;
    }
});



elements.endInterviewBtn.addEventListener('click', async () => {
    elements.endInterviewBtn.innerHTML = '<span class="loader"></span> Generating...';
    elements.endInterviewBtn.disabled = true;

    try {
        const response = await fetch(`${API_URL}/api/report`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                session_id: sessionId, 
                profile_name: elements.profileName.value.trim(), 
                role: elements.roleSelect.value, 
                experience: elements.expSelect.value, 
                resume: elements.resumeText.value.trim() 
            })
        });

        if (response.ok) {
            const data = await response.json();
            elements.reportAvgScore.textContent = (data.average_score || 0).toFixed(1);
            elements.reportContent.innerHTML = (data.report || "").replace(/\n/g, '<br>');
            elements.interviewSection.classList.add('hidden'); // Hide the interview
            elements.reportSection.classList.remove('hidden');
            elements.reportSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
        } else {
            alert('Failed to generate report.');
        }
    } catch (error) {
        alert('Connection error.');
    } finally {
        elements.endInterviewBtn.textContent = '🛑 End Mock Interview';
        elements.endInterviewBtn.disabled = false;
    }
});

elements.backHomeBtn.addEventListener('click', () => {
    // Reset to start page
    elements.reportSection.classList.add('hidden');
    elements.setupSection.classList.remove('hidden');
    elements.setupSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
    
    // Clear inputs
    elements.profileName.value = '';
    elements.resumeFile.value = '';
    elements.resumeText.value = '';
    elements.strategyText.innerHTML = '';
    elements.strategySection.classList.add('hidden');
    
    // Refresh the page fully to reset all state variables
    window.location.reload();
});

/* ── Show Answer ──────────────────────────────────────────────────── */
elements.showAnswerBtn.addEventListener('click', () => {
    // Populate model answer text
    elements.modelAnswerText.textContent = currentModelAnswer || 'No model answer available.';

    // Detect project questions: show key-points collector
    const isProjectQ = /project|built|developed|implemented|deployed|worked on/i.test(currentQuestion);
    elements.keyPointsSection.classList.toggle('hidden', !isProjectQ);

    elements.showAnswerSection.classList.remove('hidden');
    elements.showAnswerSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
});

/* ── Add key-point row ────────────────────────────────────────────── */
elements.kpAddBtn.addEventListener('click', () => {
    const row = document.createElement('div');
    row.className = 'kp-row';
    row.innerHTML = `<input class="kp-input" type="text" placeholder="Add another key point…">
                     <button class="kp-remove-btn" onclick="this.parentElement.remove()">−</button>`;
    elements.kpRows.appendChild(row);
});

/* ── Generate framed answer from key points ───────────────────────── */
elements.kpGenerateBtn.addEventListener('click', async () => {
    const points = [...document.querySelectorAll('.kp-input')]
        .map(i => i.value.trim()).filter(Boolean);
    if (points.length === 0) { alert('Please enter at least one key point.'); return; }

    const btn = elements.kpGenerateBtn;
    btn.innerHTML = '<span class="loader"></span> Generating…'; btn.disabled = true;
    try {
        const r = await fetch(`${API_URL}/api/frame_answer`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                question: currentQuestion,
                key_points: points,
                role: currentRole,
                experience: currentExp
            })
        });
        const d = await r.json();
        elements.framedAnswerText.textContent = d.framed_answer;
        elements.framedAnswerBox.classList.remove('hidden');
        elements.framedAnswerBox.scrollIntoView({ behavior: 'smooth', block: 'start' });
    } catch (_) { alert('Failed to generate framed answer.'); }
    finally { btn.textContent = 'Generate Framed Answer'; btn.disabled = false; }
});
