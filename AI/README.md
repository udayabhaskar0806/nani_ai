# ⚡ N.A.N.I. (Neural Analytical Network Intelligence)

> **First-Principles AI Systems Co-Pilot & Tech Radar**  
> *"Question everything down to the silicon and the syscalls."*

---

## 🌟 What is N.A.N.I.?

**N.A.N.I.** is a lightweight, low-cost personal AI operating system inspired by Tony Stark's J.A.R.V.I.S., engineered for low-level systems developers (C/C++, Linux internals, networking, CPU architectures).

Instead of surface-level fluff, N.A.N.I. operates on the **"Why? Why like that?"** first-principles rule:
1. **GitHub AI Radar:** Scans, filters, and inspects the fastest-moving open-source AI and systems repos on GitHub.
2. **Deep Systems Research:** Autonomous recursive inquiry into tech architectures, memory layouts, cache misses, and protocols with live web retrieval ($0 cost).
3. **Hardware Telemetry:** Direct Linux system inspection (CPU load, AVX capabilities, RAM utilization, Linux kernel stats).
4. **Task & Reminder Scheduling:** Schedules alerts and fires native Linux desktop notifications via `notify-send`.
5. **Mobile & Desktop Sync:** Zero-latency Telegram bot interface so you can talk to N.A.N.I. directly from your Android phone or laptop.
6. **Persistent SQLite Memory:** Retains your developer profile, past conversations, and system preferences locally.

---

## 🏗️ Architecture

```
nani/
├── config.py              # Central settings and hardware profile
├── core/
│   ├── persona.py         # Cognitive J.A.R.V.I.S. persona ("Why? Why?" rule)
│   ├── engine.py          # Unified LLM provider (Ollama, Groq, DeepSeek, Gemini)
│   └── memory.py          # SQLite persistent storage (profile, history, reminders)
├── tools/
│   ├── github_radar.py    # GitHub trending repos & deep code analysis
│   ├── researcher.py      # Recursive web search & first-principles engine
│   ├── reminders.py       # Task scheduler & Linux notify-send alerts
│   └── system_ops.py      # Hardware telemetry & procfs inspector
└── interfaces/
    ├── cli.py             # Cyberpunk Rich terminal interface
    └── telegram_bot.py    # Mobile Android & desktop sync via Telegram
```

---

## 🚀 Quickstart

### 1. Launch N.A.N.I. Web Command Deck (Visual AI Interface)
```bash
cd "/home/dell/Vibe Coding/AI"
./venv/bin/python3 run_web.py
```
*Opens a futuristic J.A.R.V.I.S. Command Center in your browser at `http://localhost:8000` with live hardware gauges, screen vision, chat copilot, and direct laptop controls.*

### 2. Or Launch Interactive Terminal Console
```bash
cd "/home/dell/Vibe Coding/AI"
./venv/bin/python3 main.py
```

### 2. Available Terminal Commands
* `/radar` — Scan trending AI & systems repositories on GitHub
* `/inspect <owner/repo>` — Dissect a GitHub repository's architecture and code
* `/research <topic>` — Run a multi-layered deep research dossier
* `/remind <min> <task>` — Schedule a reminder with Linux desktop notification
* `/reminders` — List active reminders
* `/stats` — Live Linux hardware telemetry (CPU, RAM, Kernel)
* `/memory` — View stored memory and profile
* `/help` — Display command list

---

## 🧠 Connecting AI Brains (Budget & Free Options)

Configure your choice in `.env`:

### Option A: 100% Free & Local (Ollama)
Runs offline using your CPU's **AVX-512 vector acceleration**:
```bash
# In your terminal:
curl -fsSL https://ollama.com/install.sh | sh
ollama run qwen2.5:3b
```
In `.env`:
```ini
AI_PROVIDER=ollama
AI_BASE_URL=http://localhost:11434/v1
AI_MODEL_NAME=qwen2.5:3b
```

### Option B: Free Cloud Tier (Groq / Gemini / DeepSeek)
For super-fast reasoning with 70B models for deep research:
```ini
AI_PROVIDER=groq
AI_API_KEY=your_groq_api_key_here
AI_MODEL_NAME=llama-3.3-70b-versatile
```

---

## 📱 Mobile Access (Android / Desktop via Telegram)

1. Open Telegram and message `@BotFather`.
2. Type `/newbot`, name it (e.g., `MyNaniBot`), and copy the API token.
3. Add to `.env`:
   ```ini
   TELEGRAM_BOT_TOKEN=your_token_here
   ```
4. Start the bot:
   ```bash
   ./venv/bin/python3 -m nani.interfaces.telegram_bot
   ```
Now you can chat with N.A.N.I. and receive reminder alerts directly on your phone!
