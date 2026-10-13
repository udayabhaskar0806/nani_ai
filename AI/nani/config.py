import os
from pathlib import Path
from dotenv import load_dotenv

# Base paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

# Load environment variables
load_dotenv(BASE_DIR / ".env")

class Config:
    # App info
    APP_NAME = "N.A.N.I."
    APP_TAGLINE = "Neural Analytical Network Intelligence"
    VERSION = "0.1.0"

    # Database
    DB_PATH = DATA_DIR / "nani_memory.db"

    # AI Model Settings
    AI_PROVIDER = os.getenv("AI_PROVIDER", "auto")  # 'auto' for rotator, or 'ollama', 'groq', 'openrouter', 'gemini'
    API_KEY = os.getenv("AI_API_KEY", "")
    BASE_URL = os.getenv("AI_BASE_URL", "http://localhost:11434/v1")
    MODEL_NAME = os.getenv("AI_MODEL_NAME", "qwen2.5:3b")

    # Multi-Provider Free Tier Keys for Auto-Rotator
    GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
    OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")

    # GitHub API (Optional token to bypass rate limits, but works without it)
    GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")

    # Hardware Info
    HARDWARE_PROFILE = {
        "cpu": "Intel Core i5-1155G7 (AVX-512)",
        "ram_gb": 8,
        "os": "Linux",
    }
