# FILE: ~/dev/bizsproutai-backend/main.py

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
import openai
import json
import os

# Load environment variables from .env file
load_dotenv()

# --- INIT ---
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- MODELS ---
class ValidationRequest(BaseModel):
    idea: str

class RoadmapRequest(BaseModel):
    validated_idea: str
    region: str
    business_type: str
    email: str | None = None

class ReportRequest(BaseModel):
    validated_idea: str
    region: str
    business_type: str
    roadmap_data: dict | None = None

# --- PROMPTS ---

VALIDATION_PROMPT = """
### ROLE: The Adaptive Validator
Analyze the user's business idea.

### OUTPUT JSON:
{
  "score": 0-100,
  "status": "GO/FIX/STOP",
  "region": "Detected Region",
  "business_type": "Service/SaaS/Marketplace",
  "feedback": "Short summary.",
  "risk_assessment": {
    "demand": { "score": 0-100, "explanation": "..." },
    "economics": { "score": 0-100, "explanation": "..." },
    "distribution": { "score": 0-100, "explanation": "..." },
    "moat": { "score": 0-100, "explanation": "..." }
  },
  "fixes": [
    { "problem": "...", "fix": "..." }
  ]
}
"""

ROADMAP_ARCHITECT_PROMPT = """
### ROLE: The Localized Roadmap Architect
Generate a "Build Plan" accurate for the user's specific region.

**CORE RULES (REGION-SPECIFIC):**
1. LEGAL:
   - Nigeria: Suggest CAC Registration, TIN.
   - US: Suggest LLC, EIN.
   - General Emerging: Focus on formalizing just enough to get paid.
2. INFRASTRUCTURE:
   - Emerging: WhatsApp Business, Paystack, Cash Logistics.
   - Developed: Stripe, Website.

**OUTPUT JSON:**
{
  "phase_1_legal": { "step_name": "...", "description": "...", "estimated_cost": "..." },
  "phase_2_infrastructure": { "step_name": "...", "description": "..." },
  "phase_3_launch": { "step_name": "...", "description": "..." },
  "warnings": ["..."]
}
"""

REPORT_GENERATOR_PROMPT = """
### ROLE: The Executive Business Analyst
You are writing a "Due Diligence Report". You MUST use the provided [Roadmap Plan] to fill in the Action Plan.

### STRICT DATA RULES (DO NOT HALLUCINATE):
1. **MARKET INTELLIGENCE:**
   - NEVER say "Unknown".
   - **Infer Qualitative Data:** If Region is "Lagos" and Idea is "Logistics", Saturation is "HIGH".
   - Growth Rate: Estimate based on region (e.g., "Emerging Market High Growth").

2. **DISTRIBUTION:**
   - Look at the Idea. If "WhatsApp" is mentioned, channel count is 1.
   - Do NOT say "0+ channels".

3. **ACTION PLAN (CRITICAL):**
   - **MUST COPY** the specific steps from the `Roadmap Plan` provided in context.
   - If Roadmap says "Register with CAC", the Report Action MUST be "Formalize Entity (CAC)".

### OUTPUT JSON:
{
  "market_analysis": {
    "saturation_level": "High/Medium/Low",
    "market_insight": "Specific insight (e.g., 'Lagos logistics is crowded but cash-heavy')."
  },
  "distribution_score": {
    "score": 60,
    "analysis": "Specific analysis of channels."
  },
  "financial_outlook": {
    "rating": "Positive/Neutral",
    "reasoning": "Reasoning based on overhead and region."
  },
  "action_plan": [
    "Step 1 from Roadmap Phase 1",
    "Step 2 from Roadmap Phase 2",
    "Step 3 from Roadmap Phase 3"
  ]
}
"""

# --- INTERNAL HELPERS ---
async def internal_generate_roadmap(idea: str, region: str, biz_type: str):
    """Generates roadmap silently if missing."""
    user_context = f"PROJECT CONTEXT:\n- Idea: {idea}\n- Region: {region}\n- Type: {biz_type}\n\nACTION: Create localized roadmap."
    try:
        response = openai.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": ROADMAP_ARCHITECT_PROMPT},
                {"role": "user", "content": user_context}
            ],
            temperature=0.4,
            response_format={"type": "json_object"}
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"Internal Roadmap Error: {e}")
        return None

# --- ROUTES ---

@app.post("/api/validate")
async def validate_idea(request: ValidationRequest):
    print(f"Validating: {request.idea[:20]}...")
    try:
        response = openai.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "system", "content": VALIDATION_PROMPT}, {"role": "user", "content": f"Idea: {request.idea}"}],
            response_format={"type": "json_object"}
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/generate_roadmap")
async def generate_roadmap(request: RoadmapRequest):
    print(f"Generating Roadmap for {request.region}...")
    data = await internal_generate_roadmap(request.validated_idea, request.region, request.business_type)
    if not data: raise HTTPException(status_code=500, detail="Failed generation")
    return data

@app.post("/api/generate_report")
async def generate_report(request: ReportRequest):
    print(f"Generating SMART Report for {request.region}...")

    # 1. ENSURE WE HAVE ROADMAP DATA
    current_roadmap = request.roadmap_data
    if not current_roadmap:
        print("Roadmap missing. Generating internally...")
        current_roadmap = await internal_generate_roadmap(request.validated_idea, request.region, request.business_type)

    # 2. INJECT INTO PROMPT
    roadmap_str = json.dumps(current_roadmap) if current_roadmap else "Standard Setup"

    user_context = f"""
    CONTEXT:
    - Idea: "{request.validated_idea}"
    - Region: "{request.region}"
    - **Roadmap Strategy to Follow**: {roadmap_str}
    """

    try:
        response = openai.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": REPORT_GENERATOR_PROMPT},
                {"role": "user", "content": user_context}
            ],
            temperature=0.3,
            response_format={"type": "json_object"}
        )
        return json.loads(response.choices[0].message.content)

    except Exception as e:
        print(f"Report Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
def home():
    return {"status": "BizSproutAI Brain is Online"}
