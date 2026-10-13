"""N.A.N.I. Web Command Center Backend
FastAPI server connecting the web interface with full laptop access, vision, and AI engines.
"""

import os
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any

from nani.config import Config
from nani.core.memory import MemoryStore
from nani.core.engine import LLMEngine
from nani.core.council import MultiAICouncil
from nani.core.agent import SystemAgent
from nani.tools.laptop_control import LaptopController
from nani.tools.screen_vision import ScreenVision
from nani.tools.system_ops import SystemOps
from nani.tools.github_radar import GitHubRadar

app = FastAPI(title="N.A.N.I. Command Deck", version=Config.VERSION)

# Core Instances
memory = MemoryStore()
engine = LLMEngine(memory=memory)
council = MultiAICouncil(rotator=engine.rotator)
agent = SystemAgent(memory=memory, engine=engine)
laptop = LaptopController()
vision = ScreenVision(engine=engine)
radar = GitHubRadar()

STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(exist_ok=True)

class ChatRequest(BaseModel):
    message: str

class ControlRequest(BaseModel):
    action: str  # 'volume', 'mute', 'brightness', 'lock', 'screenshot'
    value: Optional[int] = None

class CouncilRequest(BaseModel):
    topic: str

class VisionRequest(BaseModel):
    question: Optional[str] = "What is currently happening on my screen?"

@app.get("/api/stats")
async def get_stats():
    telemetry = SystemOps.get_hardware_telemetry()
    battery = laptop.get_battery_info()
    return {
        "telemetry": telemetry,
        "battery": battery,
        "rotator": engine.rotator.get_status_summary()
    }

@app.post("/api/chat")
async def chat(req: ChatRequest):
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Empty message")
    
    memory.log_message("user", req.message)
    reply = agent.process_request(req.message)
    memory.log_message("assistant", reply)

    return {
        "reply": reply,
        "battery": laptop.get_battery_info(),
        "telemetry": SystemOps.get_hardware_telemetry()
    }

@app.post("/api/control")
async def control(req: ControlRequest):
    act = req.action.lower()
    if act == "volume":
        res = laptop.set_volume(req.value if req.value is not None else 50)
    elif act == "mute":
        res = laptop.toggle_mute()
    elif act == "brightness":
        res = laptop.set_brightness(req.value if req.value is not None else 70)
    elif act == "lock":
        res = laptop.lock_screen()
    elif act == "screenshot":
        shot = laptop.capture_screenshot()
        res = f"Saved to {shot['path']}" if shot["success"] else "Failed"
    else:
        raise HTTPException(status_code=400, detail=f"Unknown action: {act}")
    
    return {"status": "ok", "result": res}

@app.get("/api/screenshot")
async def get_screenshot():
    shot = laptop.capture_screenshot("latest_view.png")
    if shot["success"] and Path(shot["path"]).exists():
        return FileResponse(shot["path"], media_type="image/png")
    raise HTTPException(status_code=500, detail="Could not capture screen")

@app.post("/api/see")
async def see_screen(req: VisionRequest):
    analysis = vision.see_and_analyze(req.question or "What is currently happening on my screen?")
    return {"analysis": analysis}

@app.get("/api/radar")
async def get_radar(query: str = "topic:ai"):
    repos = radar.scan_trending_ai(query=query, limit=6)
    return {"repos": repos}

@app.post("/api/council")
async def convene_council(req: CouncilRequest):
    result = await council.convene(req.topic)
    return result

# Serve Static Web UI
app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")

def run_server(host="0.0.0.0", port=8000):
    import uvicorn
    print(f"\n🚀 N.A.N.I. Command Deck launching on http://localhost:{port}")
    uvicorn.run(app, host=host, port=port)

if __name__ == "__main__":
    run_server()
