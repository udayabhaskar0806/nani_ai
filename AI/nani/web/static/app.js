// ==========================================================================
// N.A.N.I. Web Command Deck Frontend Logic
// ==========================================================================

document.addEventListener("DOMContentLoaded", () => {
  // Elements
  const chatMessages = document.getElementById("chat-messages");
  const chatForm = document.getElementById("chat-form");
  const userInput = document.getElementById("user-input");
  const sendBtn = document.getElementById("send-btn");
  
  // Hardware Controls
  const volSlider = document.getElementById("vol-slider");
  const volDisplay = document.getElementById("vol-display");
  const brightSlider = document.getElementById("bright-slider");
  const brightDisplay = document.getElementById("bright-display");
  const btnMute = document.getElementById("btn-mute");
  const btnLock = document.getElementById("btn-lock");
  const btnSnap = document.getElementById("btn-snap");

  // Vision Elements
  const liveScreenImg = document.getElementById("live-screen-img");
  const miniScreenImg = document.getElementById("mini-screen-img");
  const visionAnalysis = document.getElementById("vision-analysis");
  const btnRefreshVision = document.getElementById("btn-refresh-vision");

  // Council Elements
  const councilInput = document.getElementById("council-input");
  const btnRunCouncil = document.getElementById("btn-run-council");
  const councilOutput = document.getElementById("council-output");

  // Radar Elements
  const radarSearch = document.getElementById("radar-search");
  const btnSearchRadar = document.getElementById("btn-search-radar");
  const repoGrid = document.getElementById("repo-grid");

  // Telemetry Elements
  const headerBattery = document.getElementById("header-battery");
  const headerCpu = document.getElementById("header-cpu");
  const headerRam = document.getElementById("header-ram");
  const metricLoad = document.getElementById("metric-load");
  const metricRamUsed = document.getElementById("metric-ram-used");
  const metricBattery = document.getElementById("metric-battery");
  const metricPower = document.getElementById("metric-power");
  const specKernel = document.getElementById("spec-kernel");
  const specCpuModel = document.getElementById("spec-cpu-model");

  // Tab Switching
  const navItems = document.querySelectorAll(".nav-item");
  const tabPanes = document.querySelectorAll(".tab-pane");

  navItems.forEach(btn => {
    btn.addEventListener("click", () => {
      navItems.forEach(b => b.classList.remove("active"));
      tabPanes.forEach(p => p.classList.remove("active"));

      btn.classList.add("active");
      const targetId = btn.getAttribute("data-tab");
      const targetPane = document.getElementById(targetId);
      if (targetPane) targetPane.classList.add("active");

      // Auto load tab data
      if (targetId === "radar-tab") loadRadar();
      if (targetId === "vision-tab") refreshScreen();
    });
  });

  // Action Chips
  document.querySelectorAll(".chip").forEach(chip => {
    chip.addEventListener("click", () => {
      const cmd = chip.getAttribute("data-cmd");
      userInput.value = cmd;
      chatForm.dispatchEvent(new Event("submit"));
    });
  });

  // ==========================================================================
  // Chat Interaction
  // ==========================================================================
  function appendMessage(sender, text, isNani = false) {
    const msgDiv = document.createElement("div");
    msgDiv.className = `message ${isNani ? "nani-message" : "user-message"}`;

    const parsedContent = typeof marked !== "undefined" ? marked.parse(text) : text;

    msgDiv.innerHTML = `
      <div class="message-header">
        <span class="avatar">${isNani ? "⚡" : "👤"}</span>
        <span class="sender-name">${sender}</span>
        <span class="timestamp">${new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
      </div>
      <div class="message-body">${parsedContent}</div>
    `;

    chatMessages.appendChild(msgDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
  }

  chatForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const text = userInput.value.trim();
    if (!text) return;

    appendMessage("You", text, false);
    userInput.value = "";

    // Show temporary thinking indicator
    const thinkingId = "thinking-" + Date.now();
    const thinkingDiv = document.createElement("div");
    thinkingDiv.className = "message nani-message";
    thinkingDiv.id = thinkingId;
    thinkingDiv.innerHTML = `
      <div class="message-header">
        <span class="avatar">⚡</span>
        <span class="sender-name">N.A.N.I.</span>
      </div>
      <div class="message-body"><em>Evaluating system intent & executing...</em></div>
    `;
    chatMessages.appendChild(thinkingDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;

    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text })
      });
      const data = await res.json();

      const thinkingEl = document.getElementById(thinkingId);
      if (thinkingEl) thinkingEl.remove();

      appendMessage("N.A.N.I.", data.reply, true);
      refreshScreen();
      pollTelemetry();
    } catch (err) {
      const thinkingEl = document.getElementById(thinkingId);
      if (thinkingEl) thinkingEl.remove();
      appendMessage("N.A.N.I.", `❌ Execution Error: ${err.message}`, true);
    }
  });

  // ==========================================================================
  // Hardware Telemetry & Controls
  // ==========================================================================
  async function pollTelemetry() {
    try {
      const res = await fetch("/api/stats");
      const data = await res.json();
      const t = data.telemetry;
      const b = data.battery;

      // Header metrics
      if (b && b.present) {
        headerBattery.textContent = `${b.percentage}% ${b.on_ac ? '(AC)' : '(Bat)'}`;
        metricBattery.textContent = `${b.percentage}%`;
        metricPower.textContent = b.on_ac ? "AC Power" : b.status;
      }
      if (t) {
        headerCpu.textContent = `Load ${t.load_avg[0]}`;
        headerRam.textContent = `RAM ${t.ram_percent_used}%`;
        metricLoad.textContent = t.load_avg[0];
        metricRamUsed.textContent = `${t.ram_percent_used}%`;
        specKernel.textContent = t.kernel;
        specCpuModel.textContent = t.cpu_model.split("@")[0].trim();
      }
    } catch (e) {
      console.warn("Telemetry poll error:", e);
    }
  }

  setInterval(pollTelemetry, 3500);
  pollTelemetry();

  // Volume
  volSlider.addEventListener("change", async () => {
    const val = parseInt(volSlider.value);
    volDisplay.textContent = `${val}%`;
    await fetch("/api/control", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "volume", value: val })
    });
  });

  // Brightness
  brightSlider.addEventListener("change", async () => {
    const val = parseInt(brightSlider.value);
    brightDisplay.textContent = `${val}%`;
    await fetch("/api/control", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "brightness", value: val })
    });
  });

  btnMute.addEventListener("click", async () => {
    await fetch("/api/control", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "mute" })
    });
  });

  btnLock.addEventListener("click", async () => {
    await fetch("/api/control", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "lock" })
    });
  });

  btnSnap.addEventListener("click", refreshScreen);

  // ==========================================================================
  // Vision & Screen
  // ==========================================================================
  function refreshScreen() {
    const cacheBuster = `?t=${Date.now()}`;
    liveScreenImg.src = `/api/screenshot${cacheBuster}`;
    miniScreenImg.src = `/api/screenshot${cacheBuster}`;
  }

  btnRefreshVision.addEventListener("click", async () => {
    refreshScreen();
    visionAnalysis.innerHTML = `<p><em>N.A.N.I. Vision examining screen pixels...</em></p>`;
    try {
      const res = await fetch("/api/see", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: "Describe active windows, visible code, or errors on this display." })
      });
      const data = await res.json();
      visionAnalysis.innerHTML = marked.parse(data.analysis);
    } catch (err) {
      visionAnalysis.innerHTML = `<p style="color:var(--accent-red)">Error: ${err.message}</p>`;
    }
  });

  // ==========================================================================
  // Multi-AI Council
  // ==========================================================================
  btnRunCouncil.addEventListener("click", async () => {
    const topic = councilInput.value.trim();
    if (!topic) return;

    councilOutput.innerHTML = `<p><em>🏛️ Convening Council (DeepSeek-R1, Llama 3.3 70B, Qwen Coder, Gemini 2.0 Flash in parallel)...</em></p>`;
    try {
      const res = await fetch("/api/council", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ topic })
      });
      const data = await res.json();
      councilOutput.innerHTML = marked.parse(data.master_answer);
    } catch (err) {
      councilOutput.innerHTML = `<p style="color:var(--accent-red)">Council deliberation error: ${err.message}</p>`;
    }
  });

  // ==========================================================================
  // GitHub Radar
  // ==========================================================================
  async function loadRadar(query = "topic:ai") {
    repoGrid.innerHTML = `<p><em>🛰️ Scanning GitHub repositories...</em></p>`;
    try {
      const res = await fetch(`/api/radar?query=${encodeURIComponent(query)}`);
      const data = await res.json();
      const repos = data.repos;

      if (!repos || !repos.length || repos[0].error) {
        repoGrid.innerHTML = `<p>No repositories returned or rate limit hit.</p>`;
        return;
      }

      repoGrid.innerHTML = repos.map(r => `
        <div class="repo-card">
          <a class="repo-title" href="${r.url}" target="_blank">${r.name}</a>
          <span class="repo-stars">⭐ ${r.stars} | ${r.language}</span>
          <p class="repo-desc">${r.description || 'No description'}</p>
        </div>
      `).join("");
    } catch (e) {
      repoGrid.innerHTML = `<p style="color:var(--accent-red)">Error loading radar: ${e.message}</p>`;
    }
  }

  btnSearchRadar.addEventListener("click", () => {
    const q = radarSearch.value.trim() || "topic:ai";
    loadRadar(q);
  });
});
