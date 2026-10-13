"""
Aurora Reflective Essay Evaluator — Backend (Render & Local compatible)
Uses Gemini to evaluate extracted PDF text. Keep GEMINI_API_KEY in environment variables;
never paste it into browser-console JavaScript.
"""
import os
import re
import io
import json
import logging
import urllib.request
from flask import Flask, request, jsonify
from flask_cors import CORS
from pypdf import PdfReader
from google import genai
from google.genai import types

# Configure logging for production and local environments
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("aurora_evaluator")

app = Flask(__name__)

# Allow Cross-Origin Resource Sharing from any origin (e.g., faculty portal pages)
CORS(app, resources={r"/*": {"origins": "*"}})

MAX_PDF_BYTES = 20 * 1024 * 1024  # 20 MB

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

def get_api_key() -> str | None:
    return os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")

def get_model_name() -> str:
    return os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

def extract_pdf_text(pdf_bytes: bytes) -> str:
    if not pdf_bytes:
        raise ValueError("No PDF file was received.")
    if len(pdf_bytes) > MAX_PDF_BYTES:
        raise ValueError("PDF exceeds the 20 MB limit.")

    stream = io.BytesIO(pdf_bytes)
    reader = PdfReader(stream)
    text_parts = []
    for page in reader.pages:
        page_text = page.extract_text() or ""
        text_parts.append(page_text)
    
    text = "\n".join(text_parts).strip()
    if len(text) < 100:
        raise ValueError(
            "Very little selectable text was extracted. This may be a scanned/image-only PDF; "
            "OCR is required before this evaluator can grade it."
        )
    return text[:60000]

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

@app.get("/")
def index():
    api_key = get_api_key()
    model = get_model_name()
    return jsonify({
        "status": "online",
        "service": "Aurora Reflective Essay Evaluator Backend",
        "model": model,
        "api_key_configured": bool(api_key),
        "endpoints": {
            "health": "/health",
            "evaluate": "POST /evaluate"
        }
    })

@app.get("/health")
def health():
    api_key = get_api_key()
    model = get_model_name()
    return jsonify({
        "ok": True,
        "model": model,
        "api_key_configured": bool(api_key)
    })

@app.post("/evaluate")
def evaluate():
    api_key = get_api_key()
    model = get_model_name()

    if not api_key:
        logger.error("GEMINI_API_KEY is not configured.")
        return jsonify({
            "error": "GEMINI_API_KEY is not configured on the backend. Please set GEMINI_API_KEY in Render Environment Variables."
        }), 500

    pdf_bytes = None
    filename = "submission.pdf"

    # Option 1: PDF URL provided in JSON or Form Data (bypasses browser CORS on S3/cloud storage)
    pdf_url = None
    if request.is_json:
        pdf_url = request.json.get("pdf_url")
    elif request.form.get("pdf_url"):
        pdf_url = request.form.get("pdf_url")

    if pdf_url:
        logger.info("Downloading PDF directly from URL: %s", pdf_url)
        try:
            req = urllib.request.Request(
                pdf_url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                }
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                pdf_bytes = resp.read(MAX_PDF_BYTES + 1)
                if len(pdf_bytes) > MAX_PDF_BYTES:
                    return jsonify({"error": "PDF exceeds the 20 MB limit."}), 400
                filename = pdf_url.split("?")[0].split("/")[-1] or "submission.pdf"
        except Exception as dl_err:
            logger.exception("Failed to download PDF from URL: %s", str(dl_err))
            return jsonify({"error": f"Failed to download PDF from URL: {str(dl_err)}"}), 400

    # Option 2: File uploaded directly via multipart/form-data
    elif "file" in request.files:
        uploaded = request.files["file"]
        if not (uploaded.filename and uploaded.filename.lower().endswith(".pdf")):
            return jsonify({"error": "The uploaded submission does not look like a PDF."}), 400
        pdf_bytes = uploaded.read()
        filename = uploaded.filename

    else:
        return jsonify({"error": "Request must include either 'pdf_url' or a PDF file in the 'file' field."}), 400

    if not pdf_bytes:
        return jsonify({"error": "No PDF data could be retrieved."}), 400

    try:
        logger.info("Processing PDF: %s (%d bytes)", filename, len(pdf_bytes))
        essay_text = extract_pdf_text(pdf_bytes)
        logger.info("Extracted %d characters. Calling Gemini model: %s", len(essay_text), model)

        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=model,
            contents=make_prompt(essay_text),
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1,
            ),
        )

        raw = (response.text or "").strip()
        # Clean potential markdown fences
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)

        data = json.loads(raw)
        qs = data.get("questions", [])
        if len(qs) != 5:
            raise ValueError(f"Model returned {len(qs)} question scores instead of expected 5.")

        scores = []
        for i, q in enumerate(qs, start=1):
            if int(q.get("number", -1)) != i:
                raise ValueError("Question entries are not in the expected order.")
            score = int(q.get("score", -1))
            if not 0 <= score <= 40:
                raise ValueError(f"Question {i} score ({score}) is outside allowed range 0–40.")
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
        data["model"] = model
        data["extracted_characters"] = len(essay_text)
        logger.info("Grading successful: %d/200 points awarded.", total)
        return jsonify(data)

    except Exception as exc:
        logger.exception("Evaluation failed: %s", str(exc))
        return jsonify({"error": str(exc)}), 500

if __name__ == "__main__":
    api_key = get_api_key()
    model = get_model_name()
    if not api_key:
        print("WARNING: GEMINI_API_KEY environment variable is not set.")

    # Render injects PORT; fallback to 8765 for local dev
    port = int(os.environ.get("PORT", 8765))
    host = "0.0.0.0"
    print(f"Starting evaluator backend on http://{host}:{port} (model={model})")
    app.run(host=host, port=port, debug=False)
