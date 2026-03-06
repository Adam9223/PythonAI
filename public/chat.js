// Chat functionality
const chatMessages = document.getElementById("chatMessages");
const userInput = document.getElementById("userInput");
const sendBtn = document.getElementById("sendBtn");
const status = document.getElementById("status");
const chatForm = document.getElementById("chatForm");

// Store chart instances for cleanup
const chartInstances = new Map();
let modalChartInstance = null;

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
    const chartType = chartData.chartType || chartData.type || "bar";
    const data = chartData.chartData || chartData.data || chartData;

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
        scales:
          chartType !== "pie" && chartType !== "doughnut"
            ? {
                y: {
                  beginAtZero: true,
                },
              }
            : undefined,
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
  const chartType = chartData.chartType || chartData.type || "bar";
  const data = chartData.chartData || chartData.data || chartData;

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
      scales:
        chartType !== "pie" && chartType !== "doughnut"
          ? {
              y: {
                beginAtZero: true,
                ticks: {
                  font: {
                    size: 12,
                  },
                },
              },
              x: {
                ticks: {
                  font: {
                    size: 12,
                  },
                },
              },
            }
          : undefined,
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
