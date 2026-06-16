"""
All-In-Land Construction — Estimate Bot for Telegram
Connects to Claude API with full business rules baked in.
"""

import os
import logging
from anthropic import Anthropic
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ── Logging ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── Clients ──────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
TELEGRAM_TOKEN   = os.environ["TELEGRAM_TOKEN"]

# Optional: lock the bot to your Telegram user ID so nobody else can use it.
# Set ALLOWED_USER_ID in Railway environment variables (your Telegram numeric ID).
ALLOWED_USER_ID = int(os.environ["ALLOWED_USER_ID"]) if os.environ.get("ALLOWED_USER_ID") else None

anthropic_client = Anthropic(api_key=ANTHROPIC_API_KEY)

# ── System prompt — All-In-Land business rules ───────────────────────────────
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
Service area: [Florida — adjust permit / code notes accordingly]
Brand colors: Gold #FFC600, Charcoal #3D3935
""".strip()

# ── Per-user conversation history ────────────────────────────────────────────
# Stores messages per Telegram user_id so context carries across messages.
conversation_histories: dict[int, list[dict]] = {}
MAX_HISTORY = 20  # keep last 20 turns to stay within token limits


def get_history(user_id: int) -> list[dict]:
    return conversation_histories.setdefault(user_id, [])


def trim_history(user_id: int):
    h = conversation_histories.get(user_id, [])
    if len(h) > MAX_HISTORY * 2:  # each turn = 2 messages (user + assistant)
        conversation_histories[user_id] = h[-(MAX_HISTORY * 2):]


# ── Handlers ─────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Hey Valerio! I'm your All-In-Land estimate bot.\n\n"
        "Describe a job and I'll break down the costs.\n"
        "Example: *500 sq ft turf job with demo, 2 workers*\n\n"
        "Type /reset to clear the conversation history.",
        parse_mode="Markdown",
    )


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conversation_histories.pop(user_id, None)
    await update.message.reply_text("✅ Conversation cleared. Start fresh!")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # Access control
    if ALLOWED_USER_ID and user_id != ALLOWED_USER_ID:
        await update.message.reply_text("⛔ Sorry, this bot is private.")
        return

    user_text = update.message.text.strip()
    if not user_text:
        return

    history = get_history(user_id)
    history.append({"role": "user", "content": user_text})

    # Send "typing…" indicator
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    try:
        response = anthropic_client.messages.create(
            model="claude-opus-4-8",        # change to claude-haiku-4-5-20251001 to cut cost
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            messages=history,
        )
        reply = response.content[0].text
    except Exception as e:
        logger.error("Claude API error: %s", e)
        reply = "⚠️ Something went wrong calling the AI. Try again in a moment."

    history.append({"role": "assistant", "content": reply})
    trim_history(user_id)

    # Telegram has a 4096-char message limit — split if needed
    for chunk in split_text(reply, 4096):
        await update.message.reply_text(chunk, parse_mode="Markdown")


def split_text(text: str, limit: int) -> list[str]:
    """Split long text into chunks at newlines, respecting Telegram's limit."""
    if len(text) <= limit:
        return [text]
    chunks, current = [], ""
    for line in text.splitlines(keepends=True):
        if len(current) + len(line) > limit:
            chunks.append(current)
            current = line
        else:
            current += line
    if current:
        chunks.append(current)
    return chunks


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot is running…")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
