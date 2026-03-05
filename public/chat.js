// Chat functionality
const chatMessages = document.getElementById("chatMessages");
const userInput = document.getElementById("userInput");
const sendBtn = document.getElementById("sendBtn");
const status = document.getElementById("status");
const chatForm = document.getElementById("chatForm");

// Auto-scroll to bottom
function scrollToBottom() {
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

// Add message to chat
function addMessage(text, isUser = false) {
  const messageDiv = document.createElement("div");
  messageDiv.className = `message ${isUser ? "user-message" : "ai-message"}`;

  const avatar = document.createElement("span");
  avatar.className = "avatar";
  avatar.textContent = isUser ? "👤" : "🤖";

  const content = document.createElement("div");
  content.className = "message-content";
  content.textContent = text;

  messageDiv.appendChild(avatar);
  messageDiv.appendChild(content);
  chatMessages.appendChild(messageDiv);

  scrollToBottom();
  return messageDiv;
}

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
      // Add AI response
      addMessage(data.response || "I couldn't process that.", false);
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
