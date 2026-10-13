# N.A.N.I. V2 — Personal AI Computer Operating Agent
**Neural Analytical Network Intelligence**
*Target OS: Ubuntu Linux (Dell Latitude i5-1155G7, 8GB RAM, X11 Display)*

---

## 1. What N.A.N.I. Is
N.A.N.I. is a persistent, general-purpose autonomous computer-operating agent designed to run natively on top of Ubuntu Linux. It accepts **high-level objectives** from its creator and autonomously derives intermediate steps, executes commands, manipulates the desktop GUI when necessary, inspects outcomes, and independently verifies task completion.

N.A.N.I. operates on a strict closed-loop control principle:
$$\text{GOAL} \longrightarrow \text{UNDERSTAND} \longrightarrow \text{OBSERVE} \longrightarrow \text{PLAN} \longrightarrow \text{ACT} \longrightarrow \text{OBSERVE RESULT} \longrightarrow \text{VERIFY} \longrightarrow \text{REPLAN} \longrightarrow \text{REPORT}$$

No action is assumed to have succeeded simply because a script was launched or a button was clicked; every meaningful step must produce empirical, observable evidence.

## 2. What N.A.N.I. Is NOT
* **Not a Chatbot:** N.A.N.I. does not operate via chatty single-turn prompt-response conversations.
* **Not an API Wrapper:** N.A.N.I. is an active operating agent with hands on the machine.
* **Not a Brute-Force GUI Automator:** N.A.N.I. follows a strict tool hierarchy: direct APIs and filesystem commands are always preferred over slow, error-prone visual screen scrolling.
* **Not Tethered to a Single AI Provider:** N.A.N.I. routes work based on abstract **Capabilities** (`FAST`, `REASONING`, `CODING`, `VISION`, `RESEARCH`, `VERIFICATION`), with automated free-tier failover.

---

## 3. System Architecture Topology

```
                       USER
                        │
         ┌──────────────┴──────────────┐
         ▼                             ▼
   TERMINAL CLI                  WEB DASHBOARD
 (Primary Dev / Debug)         (Visual Telemetry)
         │                             │
         └──────────────┬──────────────┘
                        │
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

## 4. Current Phase: Phase 0 (Foundation & Contracts)
We are currently in **Phase 0: Repository Bootstrap & Core Contracts**.
* **Status:** Core data contracts, immutable models, SQLite schema with WAL mode, and test harnesses established.
* **Next Gate:** Phase 1 (Task Runtime, Action Journal, Structured Tools) awaiting creator approval.

---

## 5. Directory Structure

```
AI/
├── nani/
│   ├── core/                  # Orchestrator, Task state machine, Planner, Router
│   ├── models/                # Capability-based model router & provider clients
│   ├── agents/                # Decoupled worker adapters (Coding, Browser, Desktop)
│   ├── tools/                 # Standardized system tools returning ToolResult
│   ├── computer/              # Native Linux screen capture, X11 windows, input
│   ├── memory/                # SQLite WAL database & ActionJournal
│   ├── security/              # Risk classification (LOW, MEDIUM, HIGH) & gates
│   ├── interfaces/            # Rich CLI console & decoupled Web UI
│   ├── config.py              # Environment configuration
│   └── main.py                # Core entrypoint
├── tests/
│   ├── unit/                  # In-memory unit tests (contracts, serialization, db)
│   ├── integration/           # Multi-worker pipeline tests
│   └── acceptance/            # Acceptance tests (SPI driver, browser booking)
├── data/                      # Local persistent SQLite databases
├── logs/                      # Structured JSONL event logs (secrets redacted)
├── pyproject.toml             # Modular dependency specification
└── README.md
```

---

## 6. Installation & Development Commands

### Prerequisites
Ubuntu Linux 22.04+, Python 3.10+, X11 display session.

```bash
cd "/home/dell/Vibe Coding/AI"

# 1. Create and activate clean virtual environment
python3 -m venv venv
source venv/bin/activate

# 2. Install core development runtime
pip install -e ".[dev]"

# 3. Optional: Install desktop or browser capabilities
pip install -e ".[desktop,browser]"

# 4. Run test suite
pytest -v

# 5. Lint and Typecheck
ruff check .
mypy nani
```

---

## 7. Security Philosophy & Risk Tiers

N.A.N.I. enforces scoped autonomy from Day Zero:

* **LOW Risk (Fully Autonomous):** Reading files, compiling code, running tests, inspecting system metrics, web searches, capturing screen.
* **MEDIUM Risk (Autonomous with Journaling):** Writing/patching project source files, launching local applications, restarting dev servers. Every action creates an automatic Git/diff checkpoint.
* **HIGH Risk (Blocked — Requires Creator Confirmation):** Financial checkout, entering card/UPI details, sending external communications, deleting directories, pushing to remote Git branches. Execution halts in `WAITING` state until explicit confirmation is provided.

---

## 8. Target Interaction Example *(Target Behavior — Under Development)*

```text
User:
"NANI, inspect my project in /home/dell/projects/driver, fix the build problem and test it."

N.A.N.I. Autonomous Execution:
1. Creates persistent Task #101 [Status: PLANNING]
2. Decomposes high-level goal into discrete steps:
   - Step 1: Inspect repository & git status
   - Step 2: Determine build system (Makefile detected)
   - Step 3: Run make to reproduce error
   - Step 4: Diagnose compiler error & patch source
   - Step 5: Rebuild & execute test suite
   - Step 6: Verify clean git diff & report
3. Routes Step 1-3 to System Worker via direct filesystem and bash runner.
4. Identifies compiler error: 'incompatible pointer type in spi_core.c:142'.
5. Routes Step 4 to Coding Worker: applies unified diff patch.
6. Routes Step 5 to System Worker: rebuilds via 'make -j4', runs loopback test.
7. Verification Agent confirms exit code 0 and all tests pass.
8. Displays concise summary of changed lines and verified build status.
```

---

## 9. Historical Reference
The working V1.2 prototype has been permanently preserved in Git:
- **Git Branch:** `archive/nani-v1.2`
- **Git Tag:** `nani-v1.2-final`
- **Commit:** `eaae6ee22d992cdbcdbfc3dcd46aac9bccff193b`
