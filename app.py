import json
import mimetypes
import os
from typing import Any, List, Optional

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request
from flask_cors import CORS
from google import genai
from google.genai import types

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")
MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

if not API_KEY:
    raise RuntimeError("GEMINI_API_KEY missing. Add it to .env before starting the app.")

client = genai.Client(api_key=API_KEY)

app = Flask(__name__)
CORS(app)

ALLOWED_MIME_PREFIXES = ("image/", "application/pdf", "text/")
MAX_FILES = 12
MAX_FILE_BYTES = 20 * 1024 * 1024  # 20 MB per file

ASSESSMENT_PROMPT = """You are an AI-powered Green Credit Assessment Engine for MSME lending.

Your role is to analyze borrower-submitted sustainability documents, extract verifiable ESG evidence, calculate a Green Score, explain the reasoning behind each component score, identify missing or inconsistent evidence, and return a regulator-friendly structured JSON response.

Green Score Formula:
GreenScore = 0.35E + 0.25V + 0.20T + 0.20G

Where:
E = Emissions Performance
V = External Verification
T = Year-over-Year Sustainability Improvement
G = Governance Maturity

DOCUMENT INPUT TYPES

1. Utility Bills -> used for E
   Extract: billing_period, total_kwh, total_water_usage, fuel_consumption,
   renewable_generation, service_address, meter_id

2. ISO Certificates -> used for V
   Extract: certificate_standard, certificate_number, issuing_body,
   issue_date, expiry_date, site_scope

3. GHG Reports -> used for T
   Extract: reporting_year, baseline_year, scope1_emissions, scope2_emissions,
   scope3_emissions, emissions_intensity, methodology, assurance_provider
   IMPORTANT: If no baseline year or prior-year comparison exists, mark T as "insufficient evidence".

4. Supplier Policy Documents -> used for G
   Extract: policy_owner, approval_date, review_frequency,
   compliance_requirements, supplier_audit_frequency, escalation_procedure

SCORING LOGIC (each dimension 0-100):

E (Emissions Performance): energy efficiency, emissions intensity, renewable usage, consumption normalization
V (External Verification): certificate validity, recognized standards, independent assurance, expiry status
T (YoY Improvement): baseline vs current year emissions, emissions intensity reduction, trend consistency
   If no baseline: score = null, confidence = low, reason = "insufficient historical evidence"
G (Governance Maturity): existence of governance policy, approval authority, review frequency, supplier compliance controls

RISK FLAGS to detect:
- expired certificates
- missing signatures
- inconsistent dates
- duplicate documents
- suspicious OCR anomalies
- sudden emissions drops without operational evidence
- unverifiable claims

RATING THRESHOLDS:
90-100 = Excellent | 75-89 = Strong | 60-74 = Moderate | 40-59 = Weak | <40 = Insufficient Evidence

LENDING GUIDANCE:
Score >= 85: 30-40 bps green discount, Eligible
Score >= 70: 10-20 bps discount, Eligible
Score >= 50: No pricing benefit, Conditional
Score < 50: Manual Review
Missing critical evidence: Reject or request additional documents

OUTPUT - Return JSON ONLY. No markdown. No code fences. No commentary outside the JSON.

Use this exact structure:
{
  "introduction": "Green credit assessment completed.",
  "green_score_formula": "0.35E + 0.25V + 0.20T + 0.20G",
  "scores": {
    "E": { "score": 0, "confidence": 0, "reasoning": "" },
    "V": { "score": 0, "confidence": 0, "reasoning": "" },
    "T": { "score": null, "confidence": 0, "reasoning": "" },
    "G": { "score": 0, "confidence": 0, "reasoning": "" }
  },
  "documents": [
    { "document_type": "", "document_name": "", "extracted_fields": {} }
  ],
  "risk_flags": [
    { "severity": "low|medium|high", "message": "" }
  ],
  "summary": {
    "green_score": 0,
    "rating": "Excellent|Strong|Moderate|Weak|Insufficient Evidence",
    "recommended_green_rate_discount_bps": 0,
    "decision": "Eligible|Conditional|Manual Review|Reject",
    "key_reasons": []
  }
}

Confidence values are 0-100 integers reflecting how strongly the evidence supports the score.
Always populate "documents" with one entry per uploaded file using the file name supplied.
If a category has zero documents, score it 0 with confidence 0 and explain "no document provided" — except T, which uses null per the rules above.
"""


def guess_mime(filename: str, fallback: Optional[str]) -> str:
    if fallback and fallback != "application/octet-stream":
        return fallback
    guessed, _ = mimetypes.guess_type(filename)
    return guessed or "application/octet-stream"


def build_parts(files) -> List[Any]:
    parts: List[Any] = []
    manifest_lines = []
    for f in files:
        data = f.read()
        if len(data) > MAX_FILE_BYTES:
            raise ValueError(f"{f.filename} exceeds {MAX_FILE_BYTES // (1024 * 1024)} MB limit")
        mime = guess_mime(f.filename, f.mimetype)
        if not mime.startswith(ALLOWED_MIME_PREFIXES):
            raise ValueError(f"{f.filename}: unsupported file type ({mime})")
        manifest_lines.append(f"- {f.filename} ({mime})")
        parts.append(types.Part.from_bytes(data=data, mime_type=mime))

    manifest = "Files attached for assessment:\n" + "\n".join(manifest_lines)
    parts.append(manifest)
    parts.append(ASSESSMENT_PROMPT)
    return parts


def coerce_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        # Strip ```json ... ``` if the model added fences anyway.
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    return json.loads(text)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/assess", methods=["POST"])
def assess():
    files = request.files.getlist("documents")
    files = [f for f in files if f and f.filename]
    if not files:
        return jsonify({"error": "Upload at least one document."}), 400
    if len(files) > MAX_FILES:
        return jsonify({"error": f"Maximum {MAX_FILES} files per assessment."}), 400

    try:
        parts = build_parts(files)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=parts,
            config=types.GenerateContentConfig(
                temperature=0.1,
                response_mime_type="application/json",
            ),
        )
    except Exception as e:
        return jsonify({"error": f"Gemini request failed: {e}"}), 502

    raw = response.text or ""
    try:
        result = coerce_json(raw)
    except json.JSONDecodeError:
        return jsonify({"error": "Model returned non-JSON output", "raw": raw}), 502

    return jsonify(result)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5006, debug=True)
