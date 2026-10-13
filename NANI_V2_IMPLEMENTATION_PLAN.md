# N.A.N.I. V2 — STEP-BY-STEP IMPLEMENTATION PLAN
**Engineering Execution Roadmap with Acceptance Gates and Rollback Strategies**

---

## 1. Master Build-vs-Reuse Decision Table

| Capability / Subsystem | Existing N.A.N.I. State | Evaluated External Candidates | Architectural Decision | Rationale |
| :--- | :--- | :--- | :--- | :--- |
| **Task State Machine & Lifecycle** | Minimal / stateless in `agent.py` | LangGraph, AutoGen, CrewAI, PydanticAI | **BUILD (In-House)** | Heavy frameworks add unnecessary graph abstractions. A lightweight Python `TaskManager` (~350 LOC) with SQLite persistence is faster, zero-bloat, and 100% transparent. |
| **Model Routing & Failover** | Working multi-key rotator in `rotator.py` | LiteLLM, OpenRouter SDK | **REFACTOR & BUILD** | Refactor existing free-tier rotator into a capability-based interface (`FAST`, `REASONING`, `CODING`, `VISION`). Zero external framework overhead. |
| **Linux Hardware & Telemetry** | Complete (`pactl`, DBus, sysfs) | Linux MCP, UFO | **MIGRATE (In-House)** | Already verified and hardware-accurate for Dell Latitude on Ubuntu X11. Migrate into `nani/tools/`. |
| **Desktop Screen Vision & Input** | Working `screen_vision.py` + `operator.py` | UFO³, Anthropic Computer-Use Demo, PyAutoGUI | **BUILD NATIVE + REFERENCE** | Reference Anthropic's coordinate scaling and process group isolation; implement via `mss` + `pyautogui` + `xdotool` in `agents/computer/native_linux.py`. |
| **Browser Automation (DOM/Visual)**| `xdg-open` URL launcher | Playwright, Browser Use, Stagehand | **USE Playwright + ADAPT Browser Use** | Playwright handles fast deterministic DOM tasks. `browser-use` is wrapped behind an adapter for open-ended visual search when DOM selectors are dynamic. |
| **Autonomous Coding Worker** | Basic read/write strings | OpenHands, Aider, SWE-agent | **BUILD Native + ADAPT Aider** | Build native AST/diff patcher for immediate speed; adapt Aider's `repomap` and pair-programming pipeline as an optional plug-in worker. |
| **Action Journal & Memory** | Basic SQLite profile store | Mem0, Chroma, LangChain Memory | **BUILD (In-House SQLite)** | Standard `sqlite3` with atomic transactions and `FTS5` full-text search meets 100% of single-user personal needs with zero background RAM usage. |
| **Security & Safety Gates** | Ad-hoc checks | Docker, Bubblewrap (`bwrap`) | **BUILD Native Policies** | Implement risk tiers (`LOW`, `MEDIUM`, `HIGH`) and Human-in-the-Loop `safe_pause` natively. Docker remains optional. |

---

## 2. Phased Development Roadmap

### Phase 0: Architecture Research & Open-Source Audit (CURRENT)
* **Objective:** Complete dependency analysis, establish architectural boundaries, formulate documents.
* **Estimated Effort:** Completed.
* **Dependencies:** None.
* **Files Affected:** `NANI_V2_ARCHITECTURE.md`, `NANI_V2_DEPENDENCY_EVALUATION.md`, `NANI_V2_MIGRATION_PLAN.md`, `NANI_V2_IMPLEMENTATION_PLAN.md`.
* **Acceptance Test:** User review and formal approval of architectural plans.
* **Rollback Strategy:** N/A (no code modified).

---

### Phase 1: Core Runtime & Task State Machine
* **Objective:** Build the deterministic `Task` lifecycle, `TaskManager`, SQLite `ActionJournal`, and capability-based `ModelRouter`.
* **Estimated Effort:** 1–2 days.
* **Dependencies:** Python standard library (`asyncio`, `sqlite3`, `dataclasses`, `uuid`).
* **Files Affected:**
  - `nani/core/task.py` (New)
  - `nani/core/task_manager.py` (New)
  - `nani/core/state.py` (New)
  - `nani/models/base.py` (New)
  - `nani/models/router.py` (New)
  - `nani/memory/database.py` (Refactor `nani/core/memory.py`)
* **Acceptance Test:**
  - Create a dummy task with 3 steps.
  - Verify state transitions: `CREATED` $\to$ `PLANNING` $\to$ `RUNNING` $\to$ `VERIFYING` $\to$ `COMPLETED`.
  - Simulate process kill mid-task; verify task resumes from SQLite checkpoint.
  - Request `router.get_model(capability=ModelCapability.VISION)` and verify it resolves to active Gemini/Groq keys.
* **Rollback Strategy:** Revert new files in `nani/core/`; existing `nani/core/agent.py` remains active.

---

### Phase 2: Structured System Tools & Hardware Migration
* **Objective:** Expose standard structured tools returning `{success, exit_code, stdout, stderr, duration_ms}`.
* **Estimated Effort:** 1 day.
* **Dependencies:** `subprocess`, `pactl`, `gdbus`, `loginctl`.
* **Files Affected:**
  - `nani/tools/filesystem.py` (New: read, write, patch, search, list)
  - `nani/tools/shell.py` (New: async bash with timeout & process group management)
  - `nani/tools/system_hardware.py` (Migrated from `laptop_control.py`)
  - `nani/tools/telemetry.py` (Migrated from `system_ops.py`)
* **Acceptance Test:**
  - Execute command `ls -la` $\to$ verify structured JSON output with exit code 0.
  - Read non-existent file $\to$ verify clean error JSON without unhandled exceptions.
  - Query battery and adjust volume $\to$ verify verified hardware response.
* **Rollback Strategy:** Revert to direct calls in `laptop_control.py`.

---

### Phase 3: Desktop Computer Worker (Closed-Loop Vision + Input)
* **Objective:** Implement `agents/computer/native_linux.py` supporting closed-loop observation $\to$ action $\to$ observation.
* **Estimated Effort:** 1–2 days.
* **Dependencies:** `pyautogui`, `mss`, `pillow`, `wmctrl`, `xdotool`.
* **Files Affected:**
  - `nani/computer/screen.py` (Frame grab & resolution downscaling)
  - `nani/computer/windows.py` (Window search, list, and focus via X11)
  - `nani/agents/computer/base.py` (Abstract worker interface)
  - `nani/agents/computer/native_linux.py` (Physical desktop worker)
* **Acceptance Test:**
  - Command: *"Focus terminal window, type 'echo NANI_ONLINE', press enter"*.
  - Verify action succeeds and screen observation confirms the output appeared on screen.
* **Rollback Strategy:** Fallback to existing `nani/tools/screen_vision.py`.

---

### Phase 4: Browser Worker (Playwright DOM + Browser Use Adapter)
* **Objective:** Build dual-tier web automation (DOM-first Playwright + Visual Browser-Use adapter).
* **Estimated Effort:** 1–2 days.
* **Dependencies:** `playwright`, optional `browser-use`.
* **Files Affected:**
  - `nani/agents/browser/base.py`
  - `nani/agents/browser/playwright_native.py`
  - `nani/agents/browser/browser_use_adapter.py`
* **Acceptance Test (Section 26 Test):**
  - Goal: *"Open browser, go to Google Flights or BookMyShow, find prices/timings"*.
  - Verify browser launches, extracts data via DOM/Playwright, pauses safely before any payment action.
* **Rollback Strategy:** Disable `browser_use_adapter`; rely on standard Playwright script runner.

---

### Phase 5: Autonomous Coding Worker
* **Objective:** Build `agents/coding/native.py` for direct repo exploration, diff patching, and compiler execution.
* **Estimated Effort:** 2 days.
* **Dependencies:** `git`, `tree-sitter` (optional), standard library.
* **Files Affected:**
  - `nani/agents/coding/base.py`
  - `nani/agents/coding/native.py`
  - `nani/agents/coding/aider_adapter.py` (Optional adapter)
* **Acceptance Test (Section 25 Alpha Acceptance Test):**
  - Setup broken C test project (`test_spi_driver/`) with missing semicolon and pointer type mismatch in Makefile.
  - Goal: *"NANI, inspect this project, find why it doesn't build, fix it, compile and test"*.
  - Verify: Reads files directly $\to$ runs `make` $\to$ diagnoses error $\to$ patches file $\to$ rebuilds $\to$ tests pass.
* **Rollback Strategy:** Revert worker; fall back to simple file editing tool.

---

### Phase 6: Unified Orchestrator & Autonomous Loop
* **Objective:** Connect `Planner`, `CapabilityRouter`, workers, and independent `Verifier` into the unified closed loop.
* **Estimated Effort:** 2 days.
* **Dependencies:** All previous phases.
* **Files Affected:**
  - `nani/core/planner.py`
  - `nani/core/router.py`
  - `nani/core/recovery.py`
  - `nani/core/verifier.py`
  - `nani/core/orchestrator.py`
  - `nani/interfaces/cli.py` (Rich terminal binding)
* **Acceptance Test:**
  - Full end-to-end execution of multi-step goals with live Rich progress cards (Goal, Plan, Step, Action, Observation, Verification).
* **Rollback Strategy:** Retain legacy CLI flag `--legacy` to launch old `agent.py`.

---

### Phase 7: Security Governance & Human-in-the-Loop Gate
* **Objective:** Enforce `safe_pause` for all high-risk operations (financial, sensitive data, destructive commands).
* **Estimated Effort:** 1 day.
* **Files Affected:**
  - `nani/security/policy.py`
  - `nani/security/approvals.py`
* **Acceptance Test:**
  - Trigger mock payment or `rm -rf` $\to$ verify system halts in `WAITING` state and requires explicit `[Y/n]` override.
* **Rollback Strategy:** Default to strict confirmation on all external commands.

---

## 3. Rollback & Failsafe Guarantees

1. **Git Branching Isolation:** All V2 implementation will occur on a feature branch (`v2-core-runtime`) or modular package structure without touching working V1 code until Phase 6 verification passes.
2. **Interface Parity:** The Rich CLI and Web Dashboard will continue to launch seamlessly.
3. **Hardware Safety:** All brightness, audio, and battery DBus hooks have strict value clamping ($10 \le \text{brightness} \le 100$, $0 \le \text{volume} \le 100$) to prevent hardware misuse.
