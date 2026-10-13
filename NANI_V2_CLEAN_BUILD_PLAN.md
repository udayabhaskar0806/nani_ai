# N.A.N.I. V2 — CLEAN BUILD EXECUTION PLAN
**Clean Repository Reset Strategy: From Prototype Archive to Production V2 Architecture**
**Supersedes:** `NANI_V2_MIGRATION_PLAN.md` (which is retained as historical analysis)
**Preservation Baseline:** Git Commit `eaae6ee`, Branch `archive/nani-v1.2`, Tag `nani-v1.2-final`

---

## 1. Clean Build Philosophy

Rather than incrementally migrating or refactoring prototype code (which risks carrying forward technical debt, monolithic classes, and brittle regex-based tool calls), N.A.N.I. V2 is being built **from a clean slate**:
1. **Zero Legacy Imports:** The V2 runtime will **never** import old modules (`agent.py`, `engine.py`, `rotator.py`, `council.py`, or legacy GUI scripts).
2. **Pure Interface Contracts:** All components communicate exclusively through typed, immutable data contracts (`Task`, `PlanStep`, `Action`, `Observation`, `WorkerResult`, `ToolResult`, `WorldState`).
3. **Replaceable Adapters:** External tools (Playwright, Browser-Use, Aider, OpenHands) exist strictly behind replaceable adapter boundaries.
4. **Historical Archive:** The entire working V1.2 prototype is safely tagged as `nani-v1.2-final` and branched as `archive/nani-v1.2` for read-only reference.

---

## 2. Directory Structure of Clean V2 (`AI/`)

```
AI/
├── nani/
│   ├── core/
│   │   ├── __init__.py
│   │   ├── orchestrator.py        # Master loop coordinator
│   │   ├── task.py                # Task & PlanStep data models
│   │   ├── task_manager.py        # Task lifecycle & state machine
│   │   ├── planner.py             # High-level goal decomposition
│   │   ├── router.py              # Capability-to-worker dispatch
│   │   ├── state.py               # WorldState schema
│   │   ├── verifier.py            # Independent proof-of-work validator
│   │   └── recovery.py            # Diagnostic & replanning recovery
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── base.py                # ModelProvider abstract interface
│   │   ├── router.py              # Capability-based model router
│   │   └── providers/
│   │       ├── __init__.py
│   │       ├── gemini.py          # Gemini 3.1 Flash Lite REST client
│   │       ├── groq.py            # Groq fast-inference client
│   │       └── local_ollama.py    # Local fallback client
│   │
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── coding/
│   │   │   ├── __init__.py
│   │   │   ├── base.py            # BaseCodingWorker interface
│   │   │   ├── native.py          # Native AST/grep/diff patcher
│   │   │   └── aider_adapter.py   # Optional Aider pair-programming adapter
│   │   ├── browser/
│   │   │   ├── __init__.py
│   │   │   ├── base.py            # BaseBrowserWorker interface
│   │   │   ├── playwright_native.py # Direct DOM Playwright driver
│   │   │   └── browser_use_adapter.py # Optional visual Browser-Use adapter
│   │   ├── computer/
│   │   │   ├── __init__.py
│   │   │   ├── base.py            # BaseComputerWorker interface
│   │   │   └── native_linux.py    # Linux X11 screen perception & input
│   │   ├── system/
│   │   │   ├── __init__.py
│   │   │   └── native.py          # Filesystem, shell, process, hardware
│   │   └── research/
│   │       ├── __init__.py
│   │       └── native.py          # Technical search & synthesis
│   │
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── registry.py            # ToolRegistry & schema dispatcher
│   │   ├── result.py              # ToolResult standard contract
│   │   ├── filesystem.py          # Structured file read/write/patch
│   │   ├── shell.py               # Async bash runner with process groups
│   │   ├── process.py             # Process inspection & management
│   │   ├── git.py                 # Git status, diff, log
│   │   └── system.py              # GNOME DBus backlight, pactl, battery
│   │
│   ├── computer/
│   │   ├── __init__.py
│   │   ├── screen.py              # Frame grab & resolution scaling
│   │   ├── windows.py             # X11 window management (wmctrl/xdotool)
│   │   ├── mouse.py               # Mouse moves, clicks, drags
│   │   ├── keyboard.py            # Typing, shortcuts, navigation
│   │   └── vision.py              # Visual coordinate mapping (0-1000)
│   │
│   ├── memory/
│   │   ├── __init__.py
│   │   ├── database.py            # SQLite schema initialization & WAL
│   │   ├── journal.py             # ActionJournal recorder
│   │   ├── working.py             # In-memory active task context
│   │   └── projects.py            # Project layout & build flags
│   │
│   ├── security/
│   │   ├── __init__.py
│   │   ├── policy.py              # Risk classification (LOW, MEDIUM, HIGH)
│   │   ├── approvals.py           # Human-in-the-loop confirmation gates
│   │   └── sandbox.py             # Resource limits & working-dir boundaries
│   │
│   ├── interfaces/
│   │   ├── __init__.py
│   │   ├── cli.py                 # Rich Terminal Console (primary dev UI)
│   │   └── web/                   # Decoupled web telemetry dashboard
│   │
│   ├── skills/                    # Specialized task procedures
│   ├── config.py                  # Environment & capability mapping
│   └── main.py                    # Root entrypoint
│
├── tests/
│   ├── unit/                      # Fast in-memory unit tests
│   ├── integration/               # Multi-component pipeline tests
│   ├── acceptance/                # Acceptance benchmarks (SPI, Browser)
│   └── fixtures/                  # Mock repos, broken code, test files
│
├── data/                          # SQLite databases & runtime storage
├── logs/                          # Structured JSONL event logs
├── config/                        # Default configuration files
├── scripts/                       # Developer utility scripts
├── docs/                          # Architecture documents
├── .env.example                   # Clean template for API keys
├── .gitignore                     # Protection for keys, venvs, and caches
├── pyproject.toml                 # Modern packaging & dependencies
├── README.md                      # Comprehensive project documentation
└── main.py                        # Root launcher
```

---

## 3. Clean Build Phases

### Phase 0: Foundations & Data Contracts (CURRENT)
- Create clean directory tree.
- Configure `pyproject.toml`, `.gitignore`, `.env.example`, `README.md`.
- Define immutable core contracts:
  `Task`, `PlanStep`, `Action`, `Observation`, `WorkerResult`, `ToolResult`, `WorldState`, `BaseWorker`, `BaseTool`, `ModelProvider`, `RiskLevel`, `TaskStatus`, `ModelCapability`.
- SQLite schema with WAL mode & version tracking.
- Structured logging (with secret redaction).
- Fast unit tests verifying contracts and serialization without external API/hardware dependencies.
- Verify `pytest`, `ruff`, and `mypy`.
- Create clean Phase 0 commit and **STOP**.

### Phase 1: Core Runtime & System Execution (NEXT — Awaiting User Approval)
- Implement `TaskManager` and `ActionJournal`.
- Implement `ToolRegistry` and structured tools (`filesystem`, `shell`, `git`, `process`, `system`).
- Implement basic `ModelRouter` interface with free-tier providers.
- Implement `Orchestrator` skeleton executing system steps deterministically.

### Phase 2: Desktop Computer & Browser Automation
- Implement `agents/computer/native_linux.py` (closed-loop screen perception + PyAutoGUI/X11).
- Implement `agents/browser/playwright_native.py` (DOM-first web navigation).
- Enforce the `safe_pause` human-in-the-loop security gate for financial/sensitive flows.

### Phase 3: Autonomous Coding Worker
- Implement `agents/coding/native.py` (direct AST search, diff patching, compiler feedback).
- Implement optional `aider_adapter.py` for repository-wide `RepoMap` analysis.

### Phase 4: Unified Autonomous Closed-Loop
- Wire `Planner`, `CapabilityRouter`, workers, and independent `Verifier`.
- Validate against Acceptance Test 1 (Fix broken SPI driver) and Acceptance Test 2 (Browser travel search).
