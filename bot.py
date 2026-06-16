All-In-Land Construction — Estimate Bot for Telegram
Prices jobs conversationally, then generates full branded PDF estimates on demand.

Usage:
  Describe a job → bot prices it with all your real rates.
  Type /pdf      → bot asks for client name, address, estimate # → sends branded PDF.
  Type /reset    → clear conversation history.
"""

import os
import base64
import json
import logging
import tempfile
from io import BytesIO
from datetime import date

from anthropic import Anthropic
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from reportlab.lib.pagesizes import letter
from reportlab.lib.colors import HexColor
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib.utils import ImageReader, simpleSplit

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
TELEGRAM_TOKEN    = os.environ["TELEGRAM_TOKEN"]
ALLOWED_USER_ID   = int(os.environ["ALLOWED_USER_ID"]) if os.environ.get("ALLOWED_USER_ID") else None

anthropic_client = Anthropic(api_key=ANTHROPIC_API_KEY)

# ── Brand colors ──────────────────────────────────────────────────────────────
GOLD       = HexColor("#FFC600")
CHARCOAL   = HexColor("#3D3935")
WHITE      = HexColor("#FFFFFF")
LIGHT_GRAY = HexColor("#F7F7F7")
MED_GRAY   = HexColor("#CCCCCC")
TEXT_DARK  = HexColor("#222222")

# ── Logo (embedded — no external file needed on Railway) ─────────────────────
LOGO_B64 = "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"

# ── Pricing / System prompt ───────────────────────────────────────────────────
SYSTEM_PROMPT = """
You are the internal estimating assistant for All-In-Land Construction & Remodeling.
You help Valerio (the owner) quickly price jobs, think through costs, and prepare
estimate summaries he can later format into a formal client proposal.

═══════════════════════════════════════════════════
PRICING RULES — follow these on every estimate
═══════════════════════════════════════════════════

LABOR
• Crew labor = $150 per worker per day.
• Build every labor line as: workers × days × $150.
• Typical headcount: 2–4 workers depending on job size.
• Jobs involving excavation, grading, or artificial-turf base prep need a
  Bobcat rental — assume ~$800 for 2 days unless Valerio says otherwise.

MATERIALS — SOURCING & PRICING
• Default supplier: Home Depot (HD). Research current HD prices when possible.
• Fallback: Harbor Freight for any item HD doesn't carry — flag it clearly.
• EXCEPTION — Artificial turf jobs:
    – Turf: ~$1.25 per sq ft (wholesale supplier, NOT Home Depot retail).
    – Base: ~$550 on site (recycled concrete from recycler, NOT bagged HD concrete).
    – Mark source as "Turf supplier" / "Recycler".
• Do NOT price turf at HD retail (~$3.25/sq ft) — it massively overstates cost.

FIXED EXPENSES — include ALL of these on every job:
  1. Labor (workers × days × $150)
  2. Gas (fuel for trucks — estimate based on job distance / duration, ~$50–$150/day)
  3. Food (crew meals — ~$15–$20 per worker per day)
  4. Tooling / consumables (blades, nails, tape, etc. — typically 2–5% of materials)
  5. Insurance (~3% of direct cost)
  6. Equipment rental (Bobcat, scissor lift, etc. — only when applicable)
  7. Management fee = 15% of direct cost (all lines above combined)
  8. DISPOSAL / DUMPSTER — MANDATORY on any job with demolition or material removal.
     Never skip this. Typical dumpster rental $350–$600 for a standard remodel.

MARGIN TARGET
• Client price = total cost (direct + mgmt fee) ÷ 0.80  →  this yields ~20% gross margin.
• If Valerio asks to value-engineer (VE), only adjust finish items — never cut
  foundation, structural shell, roof, or impact-envelope costs.

MANAGEMENT FEE
• Always 15% of direct cost (not of client price).
• Direct cost = labor + materials + equipment + gas + food + tooling + disposal.

═══════════════════════════════════════════════════
HOW TO RESPOND TO ESTIMATE REQUESTS
═══════════════════════════════════════════════════

When Valerio describes a job (e.g. "turf job 500 sq ft with demo"), reply with:

1. **COST BREAKDOWN** — a clean table:
   | Line Item          | Qty  | Unit $  | Total $  |
   |--------------------|------|---------|----------|
   | Labor (2w × 3d)   | 6    | $150    | $900     |
   | Artificial Turf   | 500  | $1.25   | $625     |
   | … etc.            |      |         |          |
   | **Direct Cost**   |      |         | $X,XXX   |
   | Management Fee 15%|      |         | $XXX     |
   | **Total Cost**    |      |         | $X,XXX   |
   | **Client Price**  |      |         | $X,XXX   |  ← Total ÷ 0.80

2. **ASSUMPTIONS** — bullet list of any guesses you made (crew size, days, etc.)
   that Valerio should confirm or adjust.

3. **NOTES** — flag anything unusual: permit requirements, city comments,
   potential hidden costs (temp fence, density testing, swale grading), etc.

Keep responses clear and scannable. Use tables whenever you're showing numbers.
When in doubt, ask a quick clarifying question before pricing (sq footage,
demo involved? materials already on hand? etc.)

═══════════════════════════════════════════════════
CONTEXT
═══════════════════════════════════════════════════
Company: All-In-Land Construction & Remodeling
Owner: Valerio
Service area: Florida — adjust permit / code notes accordingly
Brand colors: Gold #FFC600, Charcoal #3D3935
""".strip()

# ── PDF data extraction prompt ────────────────────────────────────────────────
PDF_EXTRACT_PROMPT = """
Extract structured estimate data from this conversation and return ONLY valid JSON.
No markdown fences, no explanation — raw JSON only.

Use this exact structure:
{
  "client_name": "string",
  "client_address": "string",
  "estimate_number": "string",
  "date": "string",
  "scope_description": "1-2 sentence job description",
  "line_items": [
    {"description": "string", "qty": "string", "unit_price": 0.00, "total": 0.00}
  ],
  "direct_cost": 0.00,
  "management_fee": 0.00,
  "client_price": 0.00,
  "notes": "key assumptions or flags"
}

Rules:
- Pull every line item from the cost breakdown in the conversation
- direct_cost = sum of all line items
- management_fee = direct_cost × 0.15
- client_price = (direct_cost + management_fee) / 0.80
- scope_description: brief, client-facing description of the work
- notes: list key assumptions (crew size, days, etc.) in plain text
- If client info is missing use the placeholder provided in the user message
""".strip()

# ── Estimate counter (persists in a local file between restarts) ──────────────
COUNTER_FILE = "estimate_counter.json"

def _load_counter() -> dict:
    try:
        with open(COUNTER_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"year": date.today().year, "seq": 11}   # start after EST-2026-011

def _save_counter(data: dict):
    with open(COUNTER_FILE, "w") as f:
        json.dump(data, f)

def next_estimate_number() -> str:
    """Increment and return the next estimate number, rolling year automatically."""
    c = _load_counter()
    current_year = date.today().year
    if c["year"] != current_year:          # new calendar year → reset sequence
        c = {"year": current_year, "seq": 0}
    c["seq"] += 1
    _save_counter(c)
    return f"EST-{c['year']}-{c['seq']:03d}"

def set_estimate_sequence(seq: int):
    """Manually set the sequence number (next PDF will use seq+1)."""
    c = _load_counter()
    c["year"] = date.today().year
    c["seq"] = seq - 1          # next_estimate_number() will add 1
    _save_counter(c)

def peek_next_number() -> str:
    """Return what the next number will be without incrementing."""
    c = _load_counter()
    current_year = date.today().year
    year = current_year if c["year"] != current_year else c["year"]
    return f"EST-{year}-{c['seq'] + 1:03d}"

# ── Conversation state ─────────────────────────────────────────────────────────
conversation_histories: dict[int, list[dict]] = {}
MAX_HISTORY = 20

def get_history(user_id: int) -> list[dict]:
    return conversation_histories.setdefault(user_id, [])

def trim_history(user_id: int):
    h = conversation_histories.get(user_id, [])
    if len(h) > MAX_HISTORY * 2:
        conversation_histories[user_id] = h[-(MAX_HISTORY * 2):]

# ── PDF generation ─────────────────────────────────────────────────────────────
def generate_estimate_pdf(data: dict) -> bytes:
    """Generate a full branded PDF estimate. Returns PDF bytes."""
    buf = BytesIO()
    W, H = letter  # 612 × 792 pt
    c = rl_canvas.Canvas(buf, pagesize=letter)
    margin = 36
    content_w = W - 2 * margin

    # ── Header bar ─────────────────────────────────────────────────────────────
    header_h = 54
    header_y = H - header_h

    c.setFillColor(CHARCOAL)
    c.rect(0, header_y, W, header_h, fill=1, stroke=0)

    # Logo
    try:
        logo_bytes = base64.b64decode(LOGO_B64)
        logo_img = ImageReader(BytesIO(logo_bytes))
        c.drawImage(logo_img, margin, header_y + 7, width=40, height=40, mask="auto")
        text_x = margin + 50
    except Exception:
        text_x = margin

    # Company name in white
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 13)
    c.drawString(text_x, header_y + 31, "ALL-IN-LAND CONSTRUCTION & REMODELING")
    c.setFont("Helvetica", 8)
    c.drawString(text_x, header_y + 17, "Licensed & Insured  |  South Florida")

    # Gold "ESTIMATE" block (right side of header)
    est_w = 112
    c.setFillColor(GOLD)
    c.rect(W - est_w, header_y, est_w, header_h, fill=1, stroke=0)
    c.setFillColor(CHARCOAL)
    c.setFont("Helvetica-Bold", 17)
    c.drawCentredString(W - est_w / 2, header_y + 18, "ESTIMATE")

    # Gold separator line under header
    c.setStrokeColor(GOLD)
    c.setLineWidth(2)
    c.line(0, header_y, W, header_y)

    # ── Contact line ───────────────────────────────────────────────────────────
    cy = header_y - 13
    c.setFillColor(CHARCOAL)
    c.setFont("Helvetica", 7.5)
    c.drawCentredString(
