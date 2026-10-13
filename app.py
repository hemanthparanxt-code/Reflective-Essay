"""
Aurora Reflective Essay Evaluator — local backend
Uses Gemini to evaluate extracted PDF text. Keep GEMINI_API_KEY on this machine;
never paste it into browser-console JavaScript.
"""
import os
import re
import json
import tempfile
from pathlib import Path

from flask import Flask, request, jsonify
from flask_cors import CORS
from pypdf import PdfReader
from google import genai
from google.genai import types

app = Flask(__name__)
CORS(app, resources={r"/evaluate": {"origins": "*"}})

MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
API_KEY = os.getenv("GEMINI_API_KEY")
MAX_PDF_BYTES = 20 * 1024 * 1024

QUESTIONS = [
    {
        "number": 1, "max_points": 40,
        "question": "Reflect on how studying the foundations of Artificial Intelligence, intelligent agents, AI classifications, ethical considerations, and societal applications, together with state-space formulation and uninformed search, shaped your understanding of how an AI system converts a real-world problem into a structured computational problem and explores possible solutions."
    },
    {
        "number": 2, "max_points": 40,
        "question": "Reflect on how heuristic evaluation and informed search strategies, together with adversarial search, constraint satisfaction, and Monte Carlo Tree Search, influenced your understanding of how an AI system can prioritize promising possibilities, handle competing choices, and reduce the effort required to reach an effective solution."
    },
    {
        "number": 3, "max_points": 40,
        "question": "Reflect on how studying logical inference, unification, chaining, and resolution, followed by knowledge-based systems, influenced your understanding of how AI represents knowledge and derives conclusions."
    },
    {
        "number": 4, "max_points": 40,
        "question": "Evaluate how the topics covered in Fundamentals of Artificial Intelligence influenced your understanding of how AI can be applied to practical problems, including the strengths, limitations, and ethical considerations of those applications."
    },
    {
        "number": 5, "max_points": 40,
        "question": "Reflect on your overall learning in Fundamentals of Artificial Intelligence, explaining the concepts you understood, how you could apply them, and what limitations or questions you still recognize."
    },
]

def extract_pdf_text(pdf_bytes: bytes) -> str:
    if not pdf_bytes:
        raise ValueError("No PDF file was received.")
    if len(pdf_bytes) > MAX_PDF_BYTES:
        raise ValueError("PDF exceeds the 20 MB limit.")
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(pdf_bytes)
        path = tmp.name
    try:
        reader = PdfReader(path)
        text_parts = []
        for page in reader.pages:
            text_parts.append(page.extract_text() or "")
        text = "\n".join(text_parts).strip()
        if len(text) < 100:
            raise ValueError(
                "Very little selectable text was extracted. This may be a scanned/image-only PDF; "
                "OCR is required before this evaluator can grade it."
            )
        return text[:60000]
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass

def make_prompt(essay_text: str) -> str:
    question_block = "\n\n".join(
        f"QUESTION {q['number']} (maximum {q['max_points']} points):\n{q['question']}"
        for q in QUESTIONS
    )
    return f"""
You are a careful university-level evaluator for a B.Tech Fundamentals of Artificial Intelligence reflective essay.
Assess the student's actual content, not submission duration, page count, writing length alone, or name.
Do not assume that claims are correct just because the student states them confidently.
Do not reward generic repetition that does not answer the prompt.

Evaluate these five questions, each worth 40 points:
{question_block}

For EACH question, judge:
- relevance to that specific question;
- factual/conceptual correctness;
- explanation and depth;
- use of appropriate AI concepts and examples;
- reflection/application and clarity.
Be fair to students with simple language or grammar mistakes when the meaning is understandable.
Do not penalize grammar heavily unless it prevents understanding.
If a question has no identifiable answer, award 0 for that question.
If an answer is mostly unrelated, cap that question at 8/40.
If an answer is relevant but contains major misconceptions, reflect that in the score.
Do not invent content absent from the submission.

Mark policy:
- Return a total from 0 to 200 based on evidence.
- For a submitted essay that makes a genuine, relevant attempt at the questions, typical acceptable scores may fall between 125 and 200; do NOT force a minimum of 125 when the work is unrelated, empty, or seriously incorrect.
- Never assign 125 automatically merely because a PDF was submitted.
- A score above 180 requires consistently strong, accurate, specific answers across the questions.
- Scores must equal the sum of the five question scores.

Return ONLY valid JSON matching this schema:
{{
  "questions": [
    {{
      "number": 1,
      "score": 0,
      "relevance": "short assessment",
      "correctness": "short assessment",
      "feedback": "one or two specific sentences explaining the score"
    }}
  ],
  "total": 0,
  "overall_feedback": "brief, constructive feedback",
  "needs_human_review": false,
  "review_reason": ""
}}
Include exactly five question entries in order. Each score must be an integer from 0 to 40. Total must equal their sum.
Set needs_human_review=true if text extraction is incomplete, answers cannot be confidently separated, or the document content is ambiguous.

STUDENT SUBMISSION TEXT:
<<<
{essay_text}
>>>
"""

@app.get("/health")
def health():
    return jsonify({"ok": True, "model": MODEL, "api_key_configured": bool(API_KEY)})

@app.post("/evaluate")
def evaluate():
    if not API_KEY:
        return jsonify({"error": "GEMINI_API_KEY is not configured on the backend."}), 500
    if "file" not in request.files:
        return jsonify({"error": "Request must include a PDF in the 'file' field."}), 400
    uploaded = request.files["file"]
    if not uploaded.filename.lower().endswith(".pdf"):
        return jsonify({"error": "The uploaded submission does not look like a PDF."}), 400
    try:
        essay_text = extract_pdf_text(uploaded.read())
        client = genai.Client(api_key=API_KEY)
        response = client.models.generate_content(
            model=MODEL,
            contents=make_prompt(essay_text),
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1,
            ),
        )
        raw = response.text or ""
        data = json.loads(raw)
        qs = data.get("questions", [])
        if len(qs) != 5:
            raise ValueError("Model returned an invalid number of question scores.")
        scores = []
        for i, q in enumerate(qs, start=1):
            if int(q.get("number", -1)) != i:
                raise ValueError("Question entries are not in the expected order.")
            score = int(q.get("score", -1))
            if not 0 <= score <= 40:
                raise ValueError(f"Question {i} score is outside 0–40.")
            q["score"] = score
            scores.append(score)
        total = sum(scores)
        if int(data.get("total", -1)) != total:
            data["total"] = total
            data["needs_human_review"] = True
            data["review_reason"] = (
                (data.get("review_reason", "") + " Model total did not match question-score sum; total corrected.")
            ).strip()
        data["total"] = total
        data["model"] = MODEL
        data["extracted_characters"] = len(essay_text)
        return jsonify(data)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

if __name__ == "__main__":
    if not API_KEY:
        print("WARNING: Set GEMINI_API_KEY before grading.")
    print(f"Starting local evaluator on http://127.0.0.1:8765 (model={MODEL})")
    app.run(host="127.0.0.1", port=8765, debug=False)
