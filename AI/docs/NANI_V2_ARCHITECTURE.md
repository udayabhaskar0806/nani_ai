# N.A.N.I. V2 — SYSTEM ARCHITECTURE SPECIFICATION
**Neural Analytical Network Intelligence | Version 2.0 Core Architecture**
**Target OS:** Ubuntu Linux 22.04+ (X11 Display `:0`, Dell Latitude i5-1155G7, 8GB RAM)

---

## 1. Architectural Philosophy & Mission

N.A.N.I. is a persistent, general-purpose autonomous computer-operating agent running on Ubuntu Linux. It is **not** a chatbot and does not operate via single-turn prompt-response cycles.

### Foundational Principles
1. **Goal-Oriented Autonomy:** The user specifies high-level objectives (e.g., *"Inspect project X, find why SPI driver fails, fix it, compile and test"* or *"Open browser, find best flight to Delhi tomorrow"*). N.A.N.I. plans, executes, and verifies intermediate steps autonomously.
2. **Strict Closed-Loop Control:**
   $$\text{GOAL} \longrightarrow \text{UNDERSTAND} \longrightarrow \text{OBSERVE} \longrightarrow \text{PLAN} \longrightarrow \text{ACT} \longrightarrow \text{OBSERVE RESULT} \longrightarrow \text{VERIFY} \longrightarrow \text{REPLAN} \longrightarrow \text{REPORT}$$
   No action is assumed successful without empirical, observable evidence (compiler exit codes, DOM state, screen pixel changes).
3. **Decoupled User Interfaces:** Input and output channels (Terminal CLI, Web Dashboard, and future Voice) are thin presentation clients. The core intelligence, task state machine, and agent workers exist completely independent of UI lifecycles.
4. **Hierarchical Tool Selection:** Direct, structured, low-latency machine interfaces are always preferred over human-mimicking graphical interfaces:
   $$\text{Native API / MCP} \succ \text{Filesystem API} \succ \text{CLI / Shell} \succ \text{Browser DOM / Playwright} \succ \text{Accessibility (AT-SPI)} \succ \text{Vision + Mouse/Keyboard}$$
   Desktop GUI automation is the universal fallback, never the primary interface when structured programmatic access exists.

---

## 2. Core High-Level Topology

```
                       USER
                        │
         ┌──────────────┴──────────────┐
         ▼                             ▼
   TERMINAL CLI                  WEB DASHBOARD
 (Primary Dev / Debug)         (Visual Telemetry)
         │                             │
         └──────────────┬──────────────┘
                        │  (JSON-RPC / In-Process Event Stream)
                        ▼
                NANI ORCHESTRATOR
                        │
         ┌──────────────┼──────────────┐
         ▼              ▼              ▼
    TASK RUNTIME      MEMORY      WORLD STATE
  (State Machine &  (SQLite &     (System, Desktop,
   Action Journal)   Working)      Project State)
         │
         ▼
      PLANNER
         │
         ▼
  CAPABILITY ROUTER
         │
 ┌───────┼─────────────┬─────────────┬─────────────┐
 ▼       ▼             ▼             ▼             ▼
CODING  BROWSER   COMPUTER/DESKTOP  SYSTEM      RESEARCH
WORKER  WORKER        WORKER        WORKER       WORKER
 │       │             │             │             │
 ▼       ▼             ▼             ▼             ▼
[Adapters & Native Tools Operating against Ubuntu Linux OS]
```

---

## 3. The Task Runtime & State Machine

Every user objective creates an immutable, persistent `Task` instance tracked by the `TaskManager`. Tasks survive process restarts and model failures.

### 3.1 Task Lifecycle State Machine
```
   [CREATED]
       │
       ▼
  [PLANNING] ◄────────────────────────────────────────┐
       │                                              │
       ▼                                              │
   [RUNNING] ──────► [WAITING (User Approval)]        │
       │                   │                          │
       ▼                   ▼ (Approved)               │
   [OBSERVE] ──────► [RECOVERY / REPLAN] ─────────────┘
       │
       ▼
  [VERIFYING]
       │
  ┌────┴────┐
  ▼         ▼
[SUCCESS] [FAILED]
```

* **`CREATED`**: Objective parsed, ID assigned, working context allocated.
* **`PLANNING`**: High-level goal decomposed into discrete, testable sub-steps.
* **`RUNNING`**: Active worker executing current sub-step.
* **`WAITING`**: Execution paused at a High-Risk security boundary (financial transactions, external messages, destructive operations) awaiting creator confirmation.
* **`VERIFYING`**: Independent validation of results (running test suites, checking git diffs, inspecting DOM elements).
* **`RECOVERY`**: Transient failure detected; diagnostics running to attempt alternative strategies.
* **`COMPLETED`**: Final verification passed; status report prepared.
* **`FAILED`**: Maximum retries exceeded or fatal unrecoverable state reached.

### 3.2 Persistent Task Schema (`Task`)
```python
class Task:
    task_id: str  # UUIDv4
    original_goal: str  # Raw user input
    interpreted_goal: str  # Clarified objective
    workspace_path: Path  # Working directory
    status: TaskStatus  # Enum (CREATED, PLANNING, RUNNING, etc.)
    risk_level: RiskLevel  # LOW, MEDIUM, HIGH
    plan: List[PlanStep]  # Ordered steps with completion status
    current_step_index: int  # Pointer to active step
    action_history: List[Action]  # Chronological executed actions
    observations: List[Observation]  # Empirical before/after evidence
    retries: int  # Current retry count
    max_retries: int  # Limit (e.g., 3 per step, 10 per task)
    created_at: float
    updated_at: float
```

### 3.3 The Action Journal
Every single atomic operation is recorded to SQLite (`data/nani_journal.db`):
- `timestamp`, `task_id`, `step_index`, `worker_name`, `action_name`
- `parameters` (sanitized inputs)
- `result` (exit code, stdout, stderr, or structured output)
- `observation_before` & `observation_after` (text snippets, hashes, or screenshot paths)
- `error` (if any), `duration_ms`

---

## 4. Capability-Based Model Routing

N.A.N.I. does not hardcode any specific model or provider. The internal architecture requests **Capabilities**, and the `ModelRouter` binds the request to the optimal available model based on latency, context size, cost, and provider health.

### 4.1 Capability Matrix
```python
class ModelCapability(Enum):
    FAST = "fast"  # Query routing, classification, intent extraction
    REASONING = "reasoning"  # Complex planning, algorithm debugging, logic
    CODING = "coding"  # Repo refactoring, patch generation, syntax fixes
    VISION = "vision"  # Screen pixel analysis, UI localization, OCR
    RESEARCH = "research"  # Deep synthesis, web crawling, documentation
    VERIFICATION = "verification"  # Independent reviewer, diff scrutiny, test validation
```

### 4.2 Router Architecture
```
Capability Request (e.g., capability="vision", max_tokens=2048)
       │
       ▼
  ModelRouter
       │
       ├── Provider Health & Free-Tier Quota Monitor
       │     (Google Gemini, Groq, OpenRouter, DeepSeek, Local Ollama)
       │
       ├── Priority Waterfall:
       │     Primary Tier (Free fast cloud) ──[HTTP 429]──► Failover Tier ──► Local Fallback
       │
       ▼
Unified Completion / Multimodal Stream
```

---

## 5. Specialized Worker Subsystems (Adapter Architecture)

N.A.N.I. exposes a single unified intelligence to the user, while internally delegating work to decoupled workers via standard abstract base classes. **External open-source systems are never imported into core; they exist strictly behind adapters.**

### 5.1 The Base Worker Interface
```python
class BaseWorker(ABC):
    @abstractmethod
    async def can_handle(self, step: PlanStep, world_state: WorldState) -> bool:
        """Determines if this worker is capable of executing the plan step."""
        pass

    @abstractmethod
    async def execute(self, step: PlanStep, context: TaskContext) -> WorkerResult:
        """Executes the step, returning structured output and empirical observations."""
        pass
```

### 5.2 Coding Worker (`agents/coding/`)
* **`base.py`**: Defines standard repository operations (read, search, edit, patch, build, test, git).
* **`native.py`**: Built-in, lightweight Python coding engine using AST/tree-sitter search, direct file diff patching, and subprocess compiler execution (`gcc`, `make`, `pytest`).
* **`openhands_adapter.py`**: Adapter wrapping the `openhands.sdk` for complex multi-file autonomous refactoring inside sandboxed workspaces.
* **`aider_adapter.py`**: Adapter wrapping Aider's `repomap` and architect/editor coder pipeline for fast git-native pair programming.

### 5.3 Browser Worker (`agents/browser/`)
* **`base.py`**: Defines browser automation methods (`open_url`, `click_locator`, `fill`, `extract_content`, `screenshot`).
* **`playwright_native.py`**: Direct Python Playwright integration driving headless or headed Firefox/Chromium via DOM selectors and accessibility trees. Fast, token-efficient, zero external agent overhead.
* **`browser_use_adapter.py`**: Adapter wrapping `browser-use` for autonomous multi-step visual web navigation (e.g., flight searches, dynamic booking flows) where DOM selectors are dynamic or obfuscated.

### 5.4 Desktop Computer Worker (`agents/computer/`)
* **`base.py`**: Defines desktop operations (`capture_screen`, `click`, `type`, `press`, `focus_window`, `launch_app`).
* **`native_linux.py`**: Ubuntu-tailored desktop controller:
  - Screen capture via `mss` / X11 SHM.
  - Window management and focus via `wmctrl` and `xdotool` (EWMH compliant).
  - Virtual mouse and keyboard input via `pyautogui` / `xdotool`.
  - Normalized coordinate translation ($0 \to 1000$ to physical $3072 \times 1728$).
* **Closed-Loop Verification:** Executes action $\to$ re-captures frame $\to$ computes structural diff $\to$ verifies window/UI state change.

### 5.5 System Worker (`agents/system/`)
* **`filesystem.py`**: Structured file operations returning `{success, path, bytes_written, diff}`.
* **`shell.py`**: Managed bash executor using `asyncio.subprocess` with process group isolation (`os.setsid`), strict timeouts, and clean stdout/stderr streaming.
* **`system_hardware.py`**: Native Linux laptop controls:
  - Volume/mute via `pactl`.
  - Hardware backlight via GNOME Power DBus (`org.gnome.SettingsDaemon.Power.Screen`).
  - Battery/AC telemetry via sysfs (`/sys/class/power_supply/BAT0`).
  - Session lock via `loginctl lock-session`.

### 5.6 Research Worker (`agents/research/`)
* Executes multi-stage technical research via web search APIs (DuckDuckGo/Tavily), fetches raw documentation/RFCs, and summarizes architectural tradeoffs.

---

## 6. Memory Architecture

```
                    MEMORY STORE (SQLite: data/nani_memory.db)
                                     │
    ┌──────────────┬─────────────────┼─────────────────┬──────────────┐
    ▼              ▼                 ▼                 ▼              ▼
 WORKING        PROJECT           EPISODIC          SEMANTIC        SKILL
 MEMORY         MEMORY            MEMORY            MEMORY          MEMORY
(Active Task   (Repo layout,    (Past Task        (User Profile,  (Verified
Context &      Build flags,     Actions &         Hardware Specs, Workflows &
Step State)    Known bugs)      Outcomes)         Preferences)    Solutions)
```

1. **Working Memory:** In-memory, task-scoped context containing current plan, immediate observations, and active step variables.
2. **Project Memory:** Persistent SQLite table storing repository metadata (build commands, compiler flags, directory maps) so N.A.N.I. remembers how to build project X without re-discovering it every turn.
3. **Episodic Memory:** History of previous tasks, including encountered errors and successful recovery paths.
4. **No Premature Vector DB:** Structured SQL queries with full-text search (`FTS5`) handle 98% of developer retrieval needs with zero RAM overhead. Vector embeddings are deferred until semantic code search scale demands it.

---

## 7. Security & Human-in-the-Loop Governance

Autonomy is categorized into three strict risk tiers:

| Risk Tier | Autonomous Execution | Actions Included | Security Gate |
| :--- | :--- | :--- | :--- |
| **LOW** | Fully Autonomous | Reading files, compiling code, running tests, inspecting system metrics, web searches, capturing screen | None (Logged to Action Journal) |
| **MEDIUM** | Autonomous with Journaling | Writing/patching project source files, launching local applications, restarting dev servers | Logged with automatic Git commit / diff checkpoint |
| **HIGH** | **Blocked until Explicit Creator Confirmation** | Financial checkout, entering card/UPI details, sending external emails/LinkedIn messages, deleting directories, pushing to remote Git branches | **Execution pauses (`safe_pause`).** Prompt rendered to CLI/Web for explicit creator override. |

---

## 8. User-Visible Observability (No Hidden CoT)

N.A.N.I. communicates execution state using clean, structured progress indicators rather than raw, private chain-of-thought dumps:

```text
╔════════════════════════════════════════════════════════════════════════╗
║ Task #104: Fix SPI Driver Compilation Failure                          ║
╠════════════════════════════════════════════════════════════════════════╣
║ Status: RUNNING | Risk: MEDIUM | Step: 4/7                             ║
║                                                                        ║
║ PLAN:                                                                  ║
║  ✓ [Step 1] Locate repository & inspect git branch                     ║
║  ✓ [Step 2] Identify build system (Makefile detected)                  ║
║  ✓ [Step 3] Run make to reproduce error                                ║
║  ● [Step 4] Diagnose compiler error & patch spi_master.c               ║
║  ○ [Step 5] Recompile and verify clean build                           ║
║  ○ [Step 6] Execute hardware loopback tests                            ║
║  ○ [Step 7] Review git diff and report solution                        ║
║                                                                        ║
║ ACTION: Patching spi_master.c:142 (Fixing struct pointer cast)        ║
║ OBSERVATION: File patched successfully (+2 lines, -1 line).            ║
║ NEXT: Triggering 'make -j4' rebuild...                                 ║
╚════════════════════════════════════════════════════════════════════════╝
```
