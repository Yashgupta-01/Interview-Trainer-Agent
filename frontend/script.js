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

    const score    = extract('SCORE', text);
    const summary  = extract('SUMMARY', text);
    const strengths = extract('STRENGTHS', text);
    const weaknesses = extract('WEAKNESSES', text);
    const tips     = extract('IMPROVEMENT_TIPS', text);

    // If none of the expected markers are present, fall back to plain text
    if (!score && !summary && !strengths) {
        return '<p>' + escHtml(text).replace(/\n/g, '<br>') + '</p>';
    }

    let html = '';

    if (score) {
        // Highlight the numeric score
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

    return html;
}


const API_URL = "http://127.0.0.1:8000";

let currentModelAnswer = null;

const elements = {
    roleSelect: document.getElementById('role-select'),
    expSelect: document.getElementById('exp-select'),
    resumeText: document.getElementById('resume-text'),
    generateBtn: document.getElementById('generate-btn'),
    interviewSection: document.getElementById('interview-section'),
    questionText: document.getElementById('question-text'),
    userAnswer: document.getElementById('user-answer'),
    submitBtn: document.getElementById('submit-btn'),
    feedbackSection: document.getElementById('feedback-section'),
    feedbackContent: document.getElementById('feedback-content')
};

elements.generateBtn.addEventListener('click', async () => {
    const role = elements.roleSelect.value;
    const experience = elements.expSelect.value;
    const resume = elements.resumeText.value.trim();

    if (!resume) {
        alert("Please paste a brief resume or background summary so our AI can fetch tailored questions via RAG!");
        return;
    }
    
    // UI Loading State
    const originalText = elements.generateBtn.textContent;
    elements.generateBtn.innerHTML = '<span class="loader"></span> Generating...';
    elements.generateBtn.disabled = true;
    elements.feedbackSection.classList.add('hidden');
    elements.userAnswer.value = '';

    try {
        const response = await fetch(`${API_URL}/api/start`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ role: role, experience: experience, resume: resume })
        });

        if (response.ok) {
            const data = await response.json();
            elements.questionText.textContent = data.question;
            currentModelAnswer = data.model_answer;
            
            // Show interview section with slide animation
            elements.interviewSection.classList.remove('hidden');
        } else {
            alert('Failed to fetch question. Check if backend is running.');
        }
    } catch (error) {
        alert('Connection error. Ensure the FastAPI backend is running on port 8000.');
    } finally {
        elements.generateBtn.textContent = originalText;
        elements.generateBtn.disabled = false;
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
            question: elements.questionText.textContent,
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
            elements.feedbackContent.innerHTML = formatFeedback(data.feedback);
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
