import os
import json
import urllib.parse
import requests
from pydantic import BaseModel, Field
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters
from google import genai
from google.genai import types

# Environment Variables
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
TELEGRAM_USERNAME = os.getenv("TELEGRAM_USERNAME")  # Without '@'

# Initialize Gemini Client
ai_client = genai.Client(api_key=GEMINI_API_KEY)

# Define Structured Output Schema
class TradingSignal(BaseModel):
    action: str = Field(description="'BUY', 'SELL', or 'HOLD'")
    confidence: int = Field(description="Confidence percentage from 0 to 100")
    ticker: str = Field(description="Asset ticker and timeframe, e.g., BTCUSDT 15m")
    entry: str = Field(description="Suggested entry level or range")
    stop_loss: str = Field(description="Suggested stop loss level")
    take_profit: str = Field(description="Suggested take profit level")
    reason: str = Field(description="Short technical reasoning: indicators, patterns, support/resistance")

def trigger_phone_call(message: str):
    """Triggers an audio call to your phone via CallMeBot."""
    if not TELEGRAM_USERNAME:
        return
    encoded_text = urllib.parse.quote(message[:250])
    call_url = f"http://api.callmebot.com/start.php?user=@{TELEGRAM_USERNAME}&text={encoded_text}&lang=en-US-Standard-C&rpt=2"
    try:
        requests.get(call_url, timeout=10)
    except Exception as e:
        print(f"Call trigger failed: {e}")

async def handle_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Restrict to your chat ID only
    if str(update.effective_chat.id) != str(TELEGRAM_CHAT_ID):
        await update.message.reply_text("Unauthorized user.")
        return

    status_msg = await update.message.reply_text("🔍 Analyzing chart screenshot...")

    try:
        # Download screenshot sent by user
        photo = await update.message.photo[-1].get_file()
        image_bytes = await photo.download_as_bytearray()

        prompt = (
            "Analyze this TradingView chart screenshot thoroughly. Identify key candlestick formations, "
            "indicator readings (RSI, MACD, Moving Averages), breakout/breakdown levels, and market structure. "
            "Provide strict structured trade setup details."
        )

        response = ai_client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[
                types.Part.from_bytes(data=bytes(image_bytes), mime_type="image/jpeg"),
                prompt
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=TradingSignal,
                temperature=0.2
            )
        )

        data = json.loads(response.text)

        # Build Alert Message
        result_text = (
            f"🚨 *TRADE ALERT: {data['action']} ({data['ticker']})*\n\n"
            f"🎯 *Confidence:* `{data['confidence']}%`\n"
            f"📈 *Entry:* `{data['entry']}`\n"
            f"🛑 *Stop Loss:* `{data['stop_loss']}`\n"
            f"💰 *Target:* `{data['take_profit']}`\n\n"
            f"📝 *Analysis:* {data['reason']}"
        )

        await status_msg.edit_text(result_text, parse_mode="Markdown")

        # Escalate high-conviction signals to an audio call
        if data["action"] in ["BUY", "SELL"] and data["confidence"] >= 75:
            call_text = f"Urgent Trade Alert: {data['action']} signal triggered on {data['ticker']} with {data['confidence']} percent confidence."
            trigger_phone_call(call_text)

    except Exception as e:
        await status_msg.edit_text(f"❌ Error analyzing chart: {str(e)}")

if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.PHOTO, handle_screenshot))
    print("Bot is listening for screenshots...")
    app.run_polling()
