// Chat functionality
const chatMessages = document.getElementById("chatMessages");
const userInput = document.getElementById("userInput");
const sendBtn = document.getElementById("sendBtn");
const status = document.getElementById("status");
const chatForm = document.getElementById("chatForm");

// ── Connect-Account panel ──────────────────────────────────────────────────
const connectBtn = document.getElementById("connectBtn");
const connectPanel = document.getElementById("connectPanel");
const connectForm = document.getElementById("connectForm");
const connectStatus = document.getElementById("connectStatus");
const connectSubmitBtn = document.getElementById("connectSubmitBtn");
const connectCancelBtn = document.getElementById("connectCancelBtn");

// Reflect saved connection state from localStorage
function refreshConnectBtnLabel() {
  const connected = localStorage.getItem("siteConnected") === "true";
  if (connected) {
    connectBtn.textContent = "✅ Connected";
    connectBtn.classList.add("connected");
  } else {
    connectBtn.textContent = "🔗 Connect Account";
    connectBtn.classList.remove("connected");
  }
}

function openConnectPanel() {
  connectPanel.classList.remove("hidden");
  connectPanel.classList.add("visible");
  connectStatus.textContent = "";
  connectStatus.className = "connect-status";
}

function closeConnectPanel() {
  connectPanel.classList.remove("visible");
  connectPanel.classList.add("hidden");
}

connectBtn.addEventListener("click", () => {
  const isOpen = connectPanel.classList.contains("visible");
  isOpen ? closeConnectPanel() : openConnectPanel();
});

connectCancelBtn.addEventListener("click", closeConnectPanel);

connectForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const username = document.getElementById("siteUsername").value.trim();
  const password = document.getElementById("sitePassword").value;
  if (!username || !password) return;

  connectSubmitBtn.disabled = true;
  connectStatus.textContent = "Connecting…";
  connectStatus.className = "connect-status";

  try {
    const res = await fetch("/api/auth/site-login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    const data = await res.json();
    if (res.ok && data.success) {
      localStorage.setItem("siteConnected", "true");
      refreshConnectBtnLabel();
      connectStatus.textContent =
        "✅ Connected! The AI can now access live data.";
      connectStatus.className = "connect-status success";
      setTimeout(closeConnectPanel, 1800);
    } else {
      connectStatus.textContent = "❌ " + (data.error || "Login failed.");
      connectStatus.className = "connect-status error";
    }
  } catch (err) {
    connectStatus.textContent = "❌ Could not reach server.";
    connectStatus.className = "connect-status error";
  } finally {
    connectSubmitBtn.disabled = false;
  }
});

refreshConnectBtnLabel();
// ──────────────────────────────────────────────────────────────────────────

// Store chart instances for cleanup
const chartInstances = new Map();
let modalChartInstance = null;

function getSafeChartType(rawType) {
  const type = String(rawType || "bar").toLowerCase();
  const supported = new Set([
    "bar",
    "line",
    "pie",
    "doughnut",
    "radar",
    "polararea",
    "scatter",
    "bubble",
  ]);

  if (!supported.has(type)) {
    return "bar";
  }

  return type === "polararea" ? "polarArea" : type;
}

function getChartScales(type) {
  const cartesianTypes = new Set(["bar", "line", "scatter", "bubble"]);
  if (!cartesianTypes.has(type)) {
    return undefined;
  }

  return {
    x: {
      beginAtZero: true,
    },
    y: {
      beginAtZero: true,
    },
  };
}

function cloneChartData(data) {
  if (!data || typeof data !== "object") {
    return {};
  }

  try {
    if (typeof structuredClone === "function") {
      return structuredClone(data);
    }
  } catch (error) {}

  try {
    return JSON.parse(JSON.stringify(data));
  } catch (error) {
    return {};
  }
}

function sanitizeNumericDatasets(data) {
  const normalized = data && typeof data === "object" ? data : {};
  const datasets = Array.isArray(normalized.datasets)
    ? normalized.datasets
    : [];

  const cleanedDatasets = datasets.map((dataset) => {
    const values = Array.isArray(dataset.data) ? dataset.data : [];
    return {
      ...dataset,
      data: values.map((value) => {
        if (value === null || value === undefined || Number.isNaN(value)) {
          return 0;
        }
        return value;
      }),
    };
  });

  const maxLength = cleanedDatasets.reduce(
    (length, dataset) => Math.max(length, dataset.data.length),
    0,
  );

  let labels = Array.isArray(normalized.labels) ? normalized.labels : [];
  if (maxLength > 0 && labels.length < maxLength) {
    labels = Array.from({ length: maxLength }, (_, index) =>
      labels[index] !== undefined ? labels[index] : `Item ${index + 1}`,
    );
  }

  return {
    ...normalized,
    labels,
    datasets: cleanedDatasets,
  };
}

function normalizeChartPayload(rawData, chartType) {
  const data = sanitizeNumericDatasets(cloneChartData(rawData));
  const datasets = Array.isArray(data.datasets) ? data.datasets : [];

  if (chartType === "scatter" || chartType === "bubble") {
    const normalizedDatasets = datasets.map((dataset) => {
      const values = Array.isArray(dataset.data) ? dataset.data : [];
      const pointLike = values.every(
        (value) =>
          value &&
          typeof value === "object" &&
          Object.prototype.hasOwnProperty.call(value, "x") &&
          Object.prototype.hasOwnProperty.call(value, "y"),
      );

      if (pointLike) {
        return dataset;
      }

      const points = values.map((value, index) => ({ x: index + 1, y: value }));
      return {
        ...dataset,
        data: points,
      };
    });

    return {
      ...data,
      labels: undefined,
      datasets: normalizedDatasets,
    };
  }

  return {
    ...data,
    datasets,
  };
}

// Auto-scroll to bottom
function scrollToBottom() {
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

// Add message to chat (text or chart)
function addMessage(data, isUser = false) {
  const messageDiv = document.createElement("div");
  messageDiv.className = `message ${isUser ? "user-message" : "ai-message"}`;

  const avatar = document.createElement("span");
  avatar.className = "avatar";
  avatar.textContent = isUser ? "👤" : "🤖";

  const content = document.createElement("div");
  content.className = "message-content";

  // Check if this is chart data
  if (
    typeof data === "object" &&
    data !== null &&
    (data.type === "chart" || data.chartType)
  ) {
    renderChart(content, data);
  } else {
    // Regular text message
    content.textContent =
      typeof data === "string" ? data : JSON.stringify(data);
  }

  messageDiv.appendChild(avatar);
  messageDiv.appendChild(content);
  chatMessages.appendChild(messageDiv);

  scrollToBottom();
  return messageDiv;
}

// Render a chart in the message
function renderChart(container, chartData) {
  const canvas = document.createElement("canvas");
  canvas.style.maxWidth = "100%";
  canvas.style.height = "700px";
  canvas.height = 700;

  // Create title header with fullscreen button
  const titleHeader = document.createElement("div");
  titleHeader.style.display = "flex";
  titleHeader.style.justifyContent = "space-between";
  titleHeader.style.alignItems = "center";
  titleHeader.style.marginBottom = "10px";

  const title = document.createElement("div");
  title.style.fontWeight = "bold";
  title.textContent = chartData.title || "Chart";

  // Create fullscreen button
  const fullscreenBtn = document.createElement("button");
  fullscreenBtn.className = "chart-fullscreen-btn";
  fullscreenBtn.innerHTML = '<span class="material-icons">fullscreen</span>';
  fullscreenBtn.title = "Enlarge chart";
  fullscreenBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    openChartModal(chartData);
  });

  titleHeader.appendChild(title);
  titleHeader.appendChild(fullscreenBtn);
  container.appendChild(titleHeader);

  // Create chart wrapper
  const chartWrapper = document.createElement("div");
  chartWrapper.style.position = "relative";
  chartWrapper.style.display = "inline-block";
  chartWrapper.style.width = "100%";

  chartWrapper.appendChild(canvas);
  container.appendChild(chartWrapper);

  const chartId = Date.now() + Math.random();

  try {
    const ctx = canvas.getContext("2d");
    const chartType = getSafeChartType(
      chartData.chartType || chartData.type || "bar",
    );
    const data = normalizeChartPayload(
      chartData.chartData || chartData.data || chartData,
      chartType,
    );

    // Create the chart
    const chart = new Chart(ctx, {
      type: chartType,
      data: data,
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            display: true,
            position: "top",
          },
          title: {
            display: false,
          },
        },
        scales: getChartScales(chartType),
      },
    });

    // Store chart instance for cleanup
    chartInstances.set(chartId, chart);
    canvas.dataset.chartId = chartId;
  } catch (error) {
    console.error("Error rendering chart:", error);
    container.innerHTML = `<div style="color: red;">Error rendering chart: ${error.message}</div>`;
  }
}

// Open chart in modal
function openChartModal(chartData) {
  const modal = document.getElementById("chartModal");
  const modalCanvas = document.getElementById("modalChartCanvas");
  const modalTitle = document.getElementById("modalChartTitle");

  // Set title
  modalTitle.textContent = chartData.title || "Chart";

  // Destroy previous chart instance if exists
  if (modalChartInstance) {
    modalChartInstance.destroy();
    modalChartInstance = null;
  }

  // Create enlarged chart
  const ctx = modalCanvas.getContext("2d");
  const chartType = getSafeChartType(
    chartData.chartType || chartData.type || "bar",
  );
  const data = normalizeChartPayload(
    chartData.chartData || chartData.data || chartData,
    chartType,
  );

  modalChartInstance = new Chart(ctx, {
    type: chartType,
    data: data,
    options: {
      responsive: true,
      maintainAspectRatio: true,
      plugins: {
        legend: {
          display: true,
          position: "top",
          labels: {
            font: {
              size: 14,
            },
          },
        },
        title: {
          display: false,
        },
      },
      scales: getChartScales(chartType),
    },
  });

  // Show modal
  modal.classList.add("show");
}

// Close chart modal
function closeChartModal() {
  const modal = document.getElementById("chartModal");
  modal.classList.remove("show");

  // Destroy chart instance
  if (modalChartInstance) {
    modalChartInstance.destroy();
    modalChartInstance = null;
  }
}

// Initialize modal event listeners
window.addEventListener("DOMContentLoaded", () => {
  const modal = document.getElementById("chartModal");
  const closeBtn = document.querySelector(".modal-close");

  // Close on X button
  if (closeBtn) {
    closeBtn.addEventListener("click", closeChartModal);
  }

  // Close on background click
  modal.addEventListener("click", (e) => {
    if (e.target === modal) {
      closeChartModal();
    }
  });

  // Close on Escape key
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && modal.classList.contains("show")) {
      closeChartModal();
    }
  });
});

// Show loading state
function addLoadingMessage() {
  const messageDiv = document.createElement("div");
  messageDiv.className = "message ai-message loading";

  const avatar = document.createElement("span");
  avatar.className = "avatar";
  avatar.textContent = "🤖";

  const content = document.createElement("div");
  content.className = "message-content";
  content.textContent = "Thinking...";

  messageDiv.appendChild(avatar);
  messageDiv.appendChild(content);
  chatMessages.appendChild(messageDiv);

  scrollToBottom();
  return messageDiv;
}

// Send message
async function sendMessage(event) {
  event.preventDefault();

  const message = userInput.value.trim();
  if (!message) return;

  // Disable input
  userInput.disabled = true;
  sendBtn.disabled = true;

  // Add user message
  addMessage(message, true);
  userInput.value = "";

  // Show loading
  const loadingMsg = addLoadingMessage();
  updateStatus("Sending...", "default");

  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ message: message }),
    });

    const data = await response.json();

    // Remove loading message
    loadingMsg.remove();

    if (response.ok) {
      // Check if response is a chart or text
      // First, check if data.response is a JSON string that needs parsing
      let responseData = data.response;

      // Try to parse if it's a string that looks like JSON
      if (typeof responseData === "string" && responseData.startsWith("{")) {
        try {
          responseData = JSON.parse(responseData);
        } catch (e) {
          // Not JSON, treat as plain text
        }
      }

      // Check for chart data at both levels
      const chartData =
        responseData &&
        typeof responseData === "object" &&
        (responseData.type === "chart" || responseData.chartType)
          ? responseData
          : data.type === "chart" || data.chartType
            ? data
            : null;

      if (chartData) {
        addMessage(chartData, false);
      } else {
        addMessage(responseData || "I couldn't process that.", false);
      }
      updateStatus("Ready", "success");
    } else {
      addMessage(
        data.response || "Something went wrong. Please try again.",
        false,
      );
      updateStatus("Error", "error");
    }
  } catch (error) {
    loadingMsg.remove();
    addMessage("Sorry, I encountered an error. Is the server running?", false);
    updateStatus("Error: " + error.message, "error");
    console.error("Error:", error);
  } finally {
    // Re-enable input
    userInput.disabled = false;
    sendBtn.disabled = false;
    userInput.focus();
  }
}

// Update status message
function updateStatus(message, type = "default") {
  status.textContent = message;
  status.className = "status";
  if (type !== "default") {
    status.classList.add(type);
  }
}

// Check health on load
async function checkHealth() {
  try {
    const response = await fetch("/api/health");
    if (response.ok) {
      updateStatus("Ready", "success");
    }
  } catch (error) {
    updateStatus("⚠️ Server not responding", "error");
  }
}

// Event listeners
chatForm.addEventListener("submit", sendMessage);
sendBtn.addEventListener("click", sendMessage);

// Focus input on load
userInput.focus();

// Check server health
checkHealth();
