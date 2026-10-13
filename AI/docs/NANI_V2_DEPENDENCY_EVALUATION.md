# N.A.N.I. V2 — OPEN-SOURCE DEPENDENCY EVALUATION & DECISION MATRIX
**Evaluation Date:** October 2026 | **Target Environment:** Ubuntu Linux (8GB RAM, i5-1155G7, X11 Display)

---

## 1. Evaluation Methodology & Rules

To build N.A.N.I. as rapidly as possible without accumulating technical debt or bloat:
1. **GitHub stars are not an architectural criterion.** We evaluate actual code quality, memory footprint, Python API stability, and Linux suitability.
2. **Every external dependency must be encapsulated behind an adapter.** Core N.A.N.I. code must never import external agent frameworks directly.
3. **Recommendation tags are strictly constrained to:**
   - **`USE`**: Direct runtime dependency (minimal, high-quality, production-grade library).
   - **`ADAPT`**: Encapsulate behind an optional worker adapter plugin.
   - **`REFERENCE`**: Study architecture, design patterns, or prompts; implement natively without pulling the dependency.
   - **`REJECT`**: Do not use; introduces unacceptable overhead, bloat, platform friction, or architectural anti-patterns.

---

## 2. Category 1: Autonomous Coding Agents

### 1.1 OpenHands (formerly OpenDevin)
* **Repository:** `All-Hands-AI/OpenHands`
* **License:** MIT
* **Language:** Python / TypeScript (Frontend)
* **Maintenance:** Extremely high (active commercial backing, continuous releases).
* **Linux Support:** Native Linux / Docker.
* **Python Integration:** Has recently decoupled into `openhands.sdk`, `openhands.tools`, and `openhands.workspace`. Can be imported directly into Python scripts.
* **Model Independence:** Full (supports LiteLLM, OpenAI, Anthropic, Gemini, local Ollama).
* **Local-Model Support:** Yes (via Ollama/vLLM endpoints).
* **Capabilities:** Full workspace exploration, file editing, bash execution, task tracking, multi-agent evaluation.
* **Dependencies:** Heavy if full server is installed (Docker, poetry, large dependency tree); moderate if using `openhands.sdk`.
* **Resource Usage:** High (~1.5GB–3GB RAM when running with Docker sandboxing).
* **Integration Difficulty:** Moderate (requires isolating the SDK from the full containerized server).
* **Security Implications:** Strong sandboxing when using its Docker workspace; requires daemon permissions.
* **Advantages:** Proven on SWE-bench; battle-tested toolset for code editing and bash recovery.
* **Disadvantages:** Significant overhead for lightweight personal laptop tasks; full installation is heavyweight.
* **Overlap:** High overlap with N.A.N.I.'s proposed coding agent.
* **Recommendation:** **`ADAPT`**
  *(Build `agents/coding/openhands_adapter.py`. Keep it optional; do not mandate it for initial alpha bootstrap).*

---

### 1.2 Aider
* **Repository:** `Aider-AI/aider`
* **License:** Apache 2.0
* **Language:** Python
* **Maintenance:** Extremely active (industry standard for terminal-based pair programming).
* **Linux Support:** 100% native.
* **Python Integration:** Modular internal classes (`Coder.create()`, `Model`, `InputOutput` in `aider.coders`). Can be scripted or run directly via clean subprocess/API.
* **Model Independence:** Full (supports 100+ models via LiteLLM).
* **Local-Model Support:** Excellent (optimized for DeepSeek-Coder, Qwen 2.5 Coder, Ollama).
* **Capabilities:** `tree-sitter` repository map (`RepoMap`), concise AST symbol context, search/replace diff editing, automated git commits, iterative lint/test repair loops.
* **Dependencies:** Moderate (`tree-sitter`, `gitpython`, `litellm`, `rich`).
* **Resource Usage:** Very low (<250MB RAM).
* **Integration Difficulty:** Low to Moderate (wrap `Coder.create` with custom non-interactive IO).
* **Security Implications:** Operates directly on local Git repo; low risk if Git checkpoints are used.
* **Advantages:** Unmatched token efficiency via AST repository mapping; extremely fast; designed specifically for developers.
* **Disadvantages:** Internal API is not formally versioned for third-party consumers (though stable in practice).
* **Overlap:** Perfect match for N.A.N.I.'s target coding worker.
* **Recommendation:** **`ADAPT`**
  *(Build `agents/coding/aider_adapter.py`. Best candidate for fast coding alpha integration).*

---

### 1.3 SWE-agent
* **Repository:** `SWE-agent/SWE-agent` (Princeton University)
* **License:** MIT
* **Language:** Python
* **Maintenance:** Moderate (academic maintenance focused on benchmark evaluation).
* **Linux Support:** Native Linux.
* **Python Integration:** Scriptable, but tightly coupled to benchmark evaluation harnesses.
* **Capabilities:** Agent-Computer Interface (ACI) with specialized bash search/view/edit commands.
* **Dependencies:** Heavy.
* **Resource Usage:** High.
* **Integration Difficulty:** High (requires refactoring away benchmark boilerplate).
* **Recommendation:** **`REFERENCE`**
  *(Study its ACI command designs: paging file viewer, directory outline, and syntax checker; do not install the package).*

---

### 1.4 Cline / Roo-Code Architecture
* **Repository:** `cline/cline` / `RooVetGit/Roo-Code`
* **License:** Apache 2.0
* **Language:** TypeScript
* **Maintenance:** Extremely high.
* **Linux Support:** N/A (VS Code Extension).
* **Python Integration:** None (TypeScript/Node.js).
* **Recommendation:** **`REFERENCE`**
  *(Reference their prompt schemas for tool calling, diff application, and Model Context Protocol handling).*

---

## 3. Category 2: Browser Automation Agents

### 2.1 Playwright Python
* **Repository:** `microsoft/playwright-python`
* **License:** Apache 2.0
* **Language:** Python / Node backend
* **Maintenance:** Massive (Microsoft official browser automation platform).
* **Linux Support:** Native (headless & headed support for Chromium, Firefox, WebKit).
* **Python Integration:** Clean, async-first Python API (`playwright.async_api`).
* **Model Independence:** Completely model-agnostic (pure automation infrastructure).
* **Capabilities:** DOM traversal, selector matching, text extraction, page screenshots, network interception, multi-tab management, accessibility snapshots.
* **Dependencies:** Minimal (Playwright wheel + browser binaries).
* **Resource Usage:** Moderate (~300MB RAM per running browser instance).
* **Integration Difficulty:** Very Low.
* **Security Implications:** Standard browser security sandbox.
* **Advantages:** Fast, deterministic, resilient auto-waiting, low token consumption when extracting clean DOM.
* **Disadvantages:** Does not include autonomous LLM reasoning out of the box (requires prompting).
* **Recommendation:** **`USE`**
  *(The bedrock browser automation library for N.A.N.I.).*

---

### 2.2 Browser Use (`browser-use`)
* **Repository:** `browser-use/browser-use`
* **License:** MIT
* **Language:** Python
* **Maintenance:** Very high (leading open-source autonomous web browsing agent).
* **Linux Support:** Native Linux on top of Playwright.
* **Python Integration:** Native Python library (`from browser_use import Agent`). Integrates seamlessly with `asyncio`.
* **Model Independence:** High (supports LangChain/LiteLLM interfaces: OpenAI, Anthropic, Gemini, Ollama).
* **Local-Model Support:** Yes (supports local vision/instruct models).
* **Capabilities:** Autonomous multi-step web agent, visual coordinate detection, dynamic DOM parsing, multi-tab navigation, Pydantic structured output extraction.
* **Dependencies:** Playwright, LangChain/LiteLLM primitives, Pydantic.
* **Resource Usage:** Moderate (~400MB–600MB RAM including Playwright).
* **Integration Difficulty:** Low (wraps into an adapter in <150 lines of code).
* **Security Implications:** Requires strict human-in-the-loop gates for payments and form submissions.
* **Advantages:** Solves the hard problem of navigating unpredictable dynamic web apps without writing manual selectors.
* **Disadvantages:** Consumes significant multimodal/reasoning tokens if allowed to run open loops.
* **Recommendation:** **`ADAPT`**
  *(Build `agents/browser/browser_use_adapter.py` on top of Playwright. Sits above Playwright as an autonomous fallback).*

---

## 4. Category 3: Linux Computer Use & Desktop Automation

### 4.1 Anthropic Computer Use Reference Architecture
* **Repository:** `anthropics/anthropic-quickstarts/computer-use-demo`
* **License:** MIT
* **Language:** Python
* **Maintenance:** Active reference implementation.
* **Linux Support:** Native Ubuntu / X11.
* **Python Integration:** Clean, modular Python modules (`computer.py`, `bash.py`, `edit.py`).
* **Capabilities:** Coordinate downscaling and mapping, X11 event injection via `xdotool` and `pyautogui`, persistent bash sessions with process group controls (`os.setsid`), string-replacement file editing.
* **Dependencies:** `xdotool`, `wmctrl`, `pyautogui`, `pillow`, `mss`.
* **Resource Usage:** Very low (<150MB RAM).
* **Integration Difficulty:** Very Low.
* **Advantages:** Mathematically proven resolution scaling for LLM vision; robust async shell stream management.
* **Disadvantages:** Hardcoded to Anthropic API formatting in the demo; requires generalizing to capability router.
* **Recommendation:** **`ADAPT` / `REFERENCE`**
  *(Directly adopt its resolution scaling formulas and persistent bash session pattern into N.A.N.I.'s native Linux computer worker).*

---

### 4.2 Microsoft UFO³
* **Repository:** `microsoft/UFO`
* **License:** MIT
* **Language:** Python
* **Maintenance:** High.
* **Linux Support:** Primarily Windows-native; UFO³ recently introduced Linux MCP client and Docker hooks.
* **Python Integration:** Complex, heavy framework.
* **Capabilities:** Multi-agent OS hierarchy, cross-device orchestration protocol.
* **Dependencies:** Heavy.
* **Resource Usage:** High.
* **Integration Difficulty:** High (Windows Win32/UIA assumptions remain deeply ingrained in core modules).
* **Disadvantages:** Overly complex for a single-laptop Linux assistant.
* **Recommendation:** **`REJECT`**

---

### 4.3 Native Linux Desktop Stack (`pyautogui` + `xdotool` + `wmctrl` + `mss`)
* **Libraries/Tools:** `pyautogui`, `mss`, `wmctrl`, `xdotool`, `pillow`
* **License:** Open Source / GPL / BSD
* **Language:** Python + Native Linux binaries
* **Maintenance:** Standard Linux system utilities.
* **Linux Support:** 100% native X11 support.
* **Python Integration:** Direct library calls and subprocess wrappers.
* **Capabilities:** High-speed screen capture (`mss`), window list/focus/minimize (`wmctrl`), physical click/type/hotkey (`pyautogui`/`xdotool`).
* **Dependencies:** Tiny system packages (`sudo apt install wmctrl xdotool`).
* **Resource Usage:** Minimal (<50MB RAM).
* **Integration Difficulty:** None (already partially verified in N.A.N.I.).
* **Recommendation:** **`USE`**
  *(Primary native desktop foundation for `agents/computer/native_linux.py`).*

---

## 5. Category 4: Agent Orchestration Frameworks

### 5.1 LangGraph
* **Repository:** `langchain-ai/langgraph`
* **License:** MIT
* **Language:** Python
* **Capabilities:** Graph-based state machines, cyclical agent loops, checkpoint persistence.
* **Dependencies:** Massive (pulls LangChain ecosystem, Pydantic, extensive dependency tree).
* **Resource Usage:** High.
* **Integration Difficulty:** High (forces LangChain abstractions onto every tool and prompt).
* **Recommendation:** **`REJECT`**
  *(Unnecessary abstraction layer; violates the low-overhead systems engineering principle).*

---

### 5.2 AutoGen / CrewAI
* **Repositories:** `microsoft/autogen`, `crewAIInc/crewAI`
* **License:** MIT
* **Language:** Python
* **Capabilities:** Conversational role-playing multi-agent systems.
* **Disadvantages:** Prone to conversational ping-pong loops, high token burn, difficult to control deterministically.
* **Recommendation:** **`REJECT`**

---

### 5.3 PydanticAI
* **Repository:** `pydantic/pydantic-ai`
* **License:** MIT
* **Language:** Python
* **Maintenance:** High (backed by Pydantic team).
* **Capabilities:** Type-safe agent runs, dependency injection (`RunContext`), model-agnostic, streaming event iterators, built-in retry and verification hooks.
* **Dependencies:** Lightweight (`pydantic`, `httpx`, model clients).
* **Resource Usage:** Low (<100MB RAM).
* **Integration Difficulty:** Low.
* **Recommendation:** **`ADAPT` / `REFERENCE`**
  *(Excellent modern agent design. Can be used for individual worker definitions if typed tool calling is needed, or referenced for clean state patterns).*

---

### 5.4 N.A.N.I. Custom Lightweight Task Runtime
* **Implementation:** Pure Python (~400 lines in `nani/core/task_manager.py` + `orchestrator.py`).
* **Capabilities:** Deterministic state machine (`Task`), explicit step progression, SQLite action journaling, zero third-party framework overhead, instant startup, 100% transparent debugging.
* **Dependencies:** Standard library (`asyncio`, `sqlite3`, `dataclasses`, `uuid`).
* **Recommendation:** **`USE`**
  *(The N.A.N.I. orchestrator and task lifecycle MUST be owned directly by N.A.N.I. No external framework should own the top-level loop).*

---

## 6. Category 5: Memory & Sandboxing

### 6.1 SQLite + FTS5
* **Implementation:** Python standard library `sqlite3`.
* **Capabilities:** Atomic transactions, task state persistence, action journal, project profiles, full-text search across past tasks and notes.
* **Resource Usage:** <10MB RAM.
* **Recommendation:** **`USE`** (Foundation of N.A.N.I. persistent memory).

### 6.2 Linux Subprocess Isolation vs Docker
* **Recommendation:**
  - **Local Development / Alpha:** Use Linux process-group isolation (`os.setsid`), resource limits (`prctl` / `resource`), and strict working-directory boundaries.
  - **Untrusted Code Execution (Future):** Bubblewrap (`bwrap`) or optional Docker container via `openhands_adapter`.

---

## 7. The Minimum Dependency Set

To achieve maximum functionality with zero framework bloat:

```
N.A.N.I. CORE (Owned & Built In-House)
├── Orchestrator & State Machine (nani/core/orchestrator.py, task_manager.py)
├── Capability-Based Model Router (nani/models/router.py)
├── System Worker & Hardware Telemetry (nani/tools/, agents/system/)
└── Action Journal & Persistent Memory (SQLite: data/nani_journal.db)

EXTERNAL PACKAGES TO DIRECTLY 'USE' (Minimal Base)
├── playwright (Microsoft browser automation)
├── mss + pillow (Fast Linux screen capture)
├── pyautogui (Native X11 input automation)
├── rich (Cyberpunk terminal UI & telemetry)
└── httpx (Fast REST calls to model providers)

EXTERNAL SYSTEMS TO 'ADAPT' (Optional Modular Workers)
├── aider (Adapted via agents/coding/aider_adapter.py for tree-sitter git coding)
└── browser-use (Adapted via agents/browser/browser_use_adapter.py for visual web search)
```
