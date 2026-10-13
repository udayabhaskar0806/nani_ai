# N.A.N.I. V2 — MIGRATION PLAN
**Transition Strategy from V1.2 Prototype to V2 Autonomous Operating Agent**

---

## 1. Inventory of Existing Codebase (`/home/dell/Vibe Coding/AI`)

| Existing File / Path | Current Responsibility | V2 Disposition | Target Location in V2 |
| :--- | :--- | :--- | :--- |
| `nani/config.py` | Environment variables, model definitions | **RETAIN & EXPAND** | `nani/config.py` (Add capability mappings) |
| `nani/core/rotator.py` | Multi-provider free key failover | **REFACTOR** | `nani/models/router.py` |
| `nani/core/gemini_client.py` | Direct Gemini REST client & multimodal vision | **WRAP INTO ADAPTER** | `nani/models/providers/gemini_provider.py` |
| `nani/core/council.py` | Parallel Multi-AI consensus deliberator | **RETAIN AS TOOL** | `nani/agents/research/council.py` |
| `nani/core/memory.py` | SQLite database for profile/notes | **MIGRATE & EXPAND** | `nani/memory/database.py` (Add task tables) |
| `nani/core/persona.py` | System prompt defining J.A.R.V.I.S. archetype | **RETAIN** | `nani/core/persona.py` |
| `nani/core/engine.py` | Single-turn generation wrapper | **DEPRECATE** | Replaced by `nani/core/orchestrator.py` |
| `nani/core/agent.py` | Monolithic agent with regex `<<<ACTION>>>` | **DEPRECATE** | Replaced by `nani/core/task_manager.py` |
| `nani/tools/laptop_control.py`| GNOME DBus backlight, `pactl`, battery sysfs | **MIGRATE** | `nani/tools/system_hardware.py` |
| `nani/tools/system_ops.py` | CPU/RAM/kernel hardware telemetry | **MIGRATE** | `nani/tools/telemetry.py` |
| `nani/tools/screen_vision.py` | Screen capture with MSS and PIL | **SPLIT & MIGRATE** | `nani/computer/screen.py` & `vision.py` |
| `nani/tools/github_radar.py` | GitHub Trending scanning & dissection | **RETAIN AS TOOL** | `nani/agents/research/github_radar.py` |
| `nani/tools/researcher.py` | DuckDuckGo search + deep research | **RETAIN AS TOOL** | `nani/agents/research/web_research.py` |
| `nani/tools/reminders.py` | APScheduler reminders | **RETAIN** | `nani/tools/reminders.py` |
| `nani/interfaces/cli.py` | Rich terminal console interface | **REFACTOR** | `nani/interfaces/cli.py` (Binds to TaskManager) |
| `nani/web/server.py` | FastAPI web dashboard | **PRESERVE** | `nani/interfaces/web.py` (Independent presentation) |
| `run_web.py` | Script to launch web dashboard | **PRESERVE** | `run_web.py` (Preserved as alternative UI) |
| `main.py` | Application entrypoint | **UPDATE** | `main.py` (Launches CLI connected to V2 core) |

---

## 2. Interface Preservation Policy

As strictly mandated:
1. **The Web Interface is NOT deleted or deprecated.**
   - `nani/web/` and `run_web.py` remain fully functional as an optional presentation layer.
   - The Web server will consume the same `TaskManager` and `Orchestrator` event streams that the CLI consumes.
2. **The Terminal CLI is the Primary Development & Debug Interface.**
   - All immediate feature testing, action journaling, and closed-loop verifications will be monitored directly in the terminal via Rich.
3. **Future Voice Layer:**
   - Kept completely separate from core runtime. Will attach as a speech-to-text listener feeding high-level goals into `TaskManager.submit_task()`.

---

## 3. Migration Sequence (Zero-Downtime Approach)

To ensure that existing capabilities (hardware control, vision, chat) are never broken during the transition:

### Phase A: Non-Destructive Scaffolding
* Create new directory packages without deleting old files:
  - `nani/core/task.py` (New Task model)
  - `nani/core/task_manager.py` (New state machine)
  - `nani/models/base.py` & `nani/models/router.py` (New capability routing)
* The existing `cli.py` and `main.py` continue running the current agent while new modules are unit tested.

### Phase B: Tool Extraction & Standardization
* Wrap `laptop_control.py`, `system_ops.py`, and `screen_vision.py` to return standard structured JSON:
  ```json
  {
    "success": true,
    "exit_code": 0,
    "stdout": "...",
    "stderr": "",
    "data": { ... },
    "duration_ms": 42
  }
  ```
* Standardize all filesystem operations into `nani/tools/filesystem.py`.

### Phase C: Adapter Layer Initialization
* Implement `agents/computer/native_linux.py` wrapping verified MSS + PyAutoGUI + coordinate scaling.
* Implement `agents/coding/native.py` for direct file edits and compiler runs.
* Implement `agents/browser/playwright_native.py` for DOM navigation.

### Phase D: Orchestrator Switchover
* Connect `TaskManager` and `Orchestrator` to `cli.py`.
* Redirect `main.py` to start the V2 Orchestrator.
* Move `nani/web/server.py` to import from `nani/core/task_manager.py`.
