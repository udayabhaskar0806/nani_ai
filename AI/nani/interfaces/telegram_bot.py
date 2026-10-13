"""N.A.N.I. Telegram Interface
Bridges N.A.N.I. directly to your Android phone and desktop via Telegram.
"""

import os
import sys
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters

from nani.config import Config
from nani.core.memory import MemoryStore
from nani.core.engine import LLMEngine
from nani.tools.github_radar import GitHubRadar
from nani.core.council import MultiAICouncil
from nani.core.agent import SystemAgent
from nani.tools.researcher import DeepResearcher
from nani.tools.reminders import ReminderManager
from nani.tools.system_ops import SystemOps

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

memory = MemoryStore()
engine = LLMEngine(memory=memory)
council = MultiAICouncil(rotator=engine.rotator)
agent = SystemAgent(memory=memory, engine=engine)
radar = GitHubRadar()
researcher = DeepResearcher()
reminders = ReminderManager(memory=memory)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.first_name
    msg = (
        f"⚡ *N.A.N.I. Online* ⚡\n"
        f"Neural Analytical Network Intelligence v{Config.VERSION}\n\n"
        f"Greetings, {user}. I am your first-principles systems co-pilot.\n\n"
        f"Commands:\n"
        f"• `/radar` - Scan trending AI repositories\n"
        f"• `/inspect <owner/repo>` - Dissect a GitHub repo architecture\n"
        f"• `/research <topic>` - Deep multi-layered 'Why?' analysis\n"
        f"• `/remind <minutes> <task>` - Set a reminder\n"
        f"• `/stats` - Live Linux hardware telemetry\n"
        f"• Or chat with me directly."
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stats = SystemOps.get_hardware_telemetry()
    msg = (
        f"🖥️ *Hardware Telemetry*\n"
        f"• *CPU:* `{stats['cpu_model']}` ({stats['arch']})\n"
        f"• *Kernel:* `{stats['kernel']}`\n"
        f"• *RAM:* {stats['ram_available_mb']} MB free / {stats['ram_total_mb']} MB ({stats['ram_percent_used']}% used)\n"
        f"• *Load:* `{stats['load_avg']}`"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

async def radar_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args) if context.args else "topic:ai"
    await update.message.reply_text(f"🛰️ Scanning GitHub AI Radar for `{query}`...")
    repos = radar.scan_trending_ai(query=query, limit=5)
    
    if not repos or "error" in repos[0]:
        await update.message.reply_text("Could not fetch repositories at this time.")
        return

    text = "🚀 *GitHub AI Radar Highlights:*\n\n"
    for r in repos:
        text += f"• *[{r['name']}]({r['url']})* ⭐ {r['stars']} | `{r['language']}`\n  {r['description'][:100]}\n\n"
    await update.message.reply_text(text, parse_mode="Markdown", disable_web_page_preview=True)

async def inspect_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: `/inspect <owner/repo>`", parse_mode="Markdown")
        return
    repo_name = context.args[0]
    await update.message.reply_text(f"🔍 Dissecting architecture for `{repo_name}`...")
    analysis = radar.analyze_repo(repo_name, engine)
    await update.message.reply_text(analysis[:4000])

async def research_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: `/research <topic>`", parse_mode="Markdown")
        return
    topic = " ".join(context.args)
    await update.message.reply_text(f"🔬 Conducting deep research on: *{topic}*...", parse_mode="Markdown")
    report = researcher.research(topic, engine)
    # Split if too long for telegram (4096 char limit)
    for chunk in [report[i:i+4000] for i in range(0, len(report), 4000)]:
        await update.message.reply_text(chunk)

async def remind_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2 or not context.args[0].isdigit():
        await update.message.reply_text("Usage: `/remind <minutes> <task>`", parse_mode="Markdown")
        return
    mins = int(context.args[0])
    task = " ".join(context.args[1:])
    job = reminders.schedule_in_minutes(task, mins)
    await update.message.reply_text(f"⏰ Reminder registered for `{job['trigger_time']}`: {task}", parse_mode="Markdown")

async def council_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: `/council <question>`", parse_mode="Markdown")
        return
    question = " ".join(context.args)
    await update.message.reply_text(f"🏛️ *Convening Multi-AI Council* on:\n`{question}`\n\n_Consulting DeepSeek-R1, Llama 3.3, Qwen Coder, and Gemini in parallel..._", parse_mode="Markdown")
    result = await council.convene(question)
    master = result["master_answer"]
    for chunk in [master[i:i+4000] for i in range(0, len(master), 4000)]:
        await update.message.reply_text(chunk)

async def rotator_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    summary = engine.rotator.get_status_summary()
    text = "🔄 *Free Token Rotator Status:*\n\n"
    for s in summary:
        text += f"• *{s['provider'].upper()}* (`{s['model']}`): {s['state']} (Calls: {s['calls']}, Errors: {s['errors']})\n"
    await update.message.reply_text(text, parse_mode="Markdown")

async def see_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    question = " ".join(context.args) if context.args else "What is currently on my screen?"
    await update.message.reply_text("📸 *Capturing laptop display & analyzing visual feed...*", parse_mode="Markdown")
    
    shot = agent.laptop.capture_screenshot()
    if shot["success"] and os.path.exists(shot["path"]):
        with open(shot["path"], "rb") as photo_file:
            await update.message.reply_photo(photo=photo_file, caption="🖥️ Live Screen Snapshot")
    
    analysis = agent.vision.see_and_analyze(question)
    for chunk in [analysis[i:i+4000] for i in range(0, len(analysis), 4000)]:
        await update.message.reply_text(chunk)

async def chat_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    memory.log_message("user", user_text)
    
    # Process through full autonomous system agent
    response = agent.process_request(user_text)
    memory.log_message("assistant", response)
    
    for chunk in [response[i:i+4000] for i in range(0, len(response), 4000)]:
        await update.message.reply_text(chunk)

def run_telegram():
    if not TELEGRAM_TOKEN:
        print("\n❌ Error: TELEGRAM_BOT_TOKEN is not set in your .env file.")
        print("To enable Telegram mobile access:")
        print("1. Message @BotFather on Telegram and send /newbot")
        print("2. Copy the API token")
        print("3. Add to your .env: TELEGRAM_BOT_TOKEN=your_token_here")
        print("4. Run: ./venv/bin/python3 -m nani.interfaces.telegram_bot\n")
        sys.exit(1)

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("stats", stats_cmd))
    app.add_handler(CommandHandler("council", council_cmd))
    app.add_handler(CommandHandler("rotator", rotator_cmd))
    app.add_handler(CommandHandler("see", see_cmd))
    app.add_handler(CommandHandler("radar", radar_cmd))
    app.add_handler(CommandHandler("inspect", inspect_cmd))
    app.add_handler(CommandHandler("research", research_cmd))
    app.add_handler(CommandHandler("remind", remind_cmd))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), chat_handler))

    print(f"⚡ N.A.N.I. Telegram Bot polling active. Listening for mobile messages...")
    app.run_polling()

if __name__ == "__main__":
    run_telegram()
