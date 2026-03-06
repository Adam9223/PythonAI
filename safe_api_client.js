// ✅ SAFE API CLIENT - Proper error handling to avoid undefined errors

const axios = require("axios");

const API_URL = "http://localhost:8000";
let apiKey = null;
let jwtToken = null;
let tokenExpiry = null;

/**
 * Initialize API with error handling
 */
async function initializeAPI() {
  try {
    console.log("🔄 Initializing API...");

    // Step 1: Generate API Key
    const keyResponse = await axios.post(`${API_URL}/api/auth/generate-key`);

    if (!keyResponse || !keyResponse.data) {
      throw new Error("Failed to get API key response");
    }

    apiKey = keyResponse.data.api_key;
    console.log("✅ API Key:", apiKey);

    // Step 2: Get JWT Token
    const tokenResponse = await axios.post(
      `${API_URL}/api/auth/token?api_key=${apiKey}`,
    );

    if (!tokenResponse || !tokenResponse.data) {
      throw new Error("Failed to get token response");
    }

    jwtToken = tokenResponse.data.access_token;
    tokenExpiry = Date.now() + tokenResponse.data.expires_in * 1000;
    console.log("✅ JWT Token obtained");

    return true;
  } catch (error) {
    console.error("❌ Initialization failed:", error.message);
    if (error.response) {
      console.error("Response status:", error.response.status);
      console.error("Response data:", error.response.data);
    }
    throw error;
  }
}

/**
 * Chat with AI - SAFE version with error handling
 */
async function chatWithAI(message) {
  try {
    // Validate input
    if (!message || typeof message !== "string") {
      throw new Error("Message must be a non-empty string");
    }

    // Check token
    if (!jwtToken) {
      throw new Error("Not initialized. Call initializeAPI() first.");
    }

    // Make request
    console.log("📤 Sending message:", message);
    const response = await axios.post(
      `${API_URL}/api/chat`,
      { message },
      {
        headers: {
          Authorization: `Bearer ${jwtToken}`,
          "Content-Type": "application/json",
        },
      },
    );

    // Validate response
    if (!response) {
      throw new Error("No response received from API");
    }

    if (!response.data) {
      throw new Error("Response has no data");
    }

    // ✅ SAFE: Check if response property exists before accessing
    if (!response.data.response) {
      console.error("Unexpected response structure:", response.data);
      throw new Error('Response missing "response" field');
    }

    console.log(
      "✅ Got response:",
      response.data.response.substring(0, 100) + "...",
    );
    return response.data.response;
  } catch (error) {
    console.error("❌ Chat error:", error.message);

    // Handle specific error cases
    if (error.response) {
      console.error("Status:", error.response.status);
      console.error("Data:", error.response.data);

      if (error.response.status === 401) {
        console.error("🔐 Authentication failed. Token may be invalid.");
        console.error("Try calling initializeAPI() again.");
      } else if (error.response.status === 422) {
        console.error("📝 Invalid request format. Check message format.");
      }
    } else if (error.request) {
      console.error("🌐 No response received. Is the API running?");
      console.error("Start API: uvicorn fastapi_server:app --port 8000");
    }

    throw error;
  }
}

/**
 * Get balance - SAFE version
 */
async function getBalance() {
  try {
    if (!jwtToken) {
      throw new Error("Not initialized. Call initializeAPI() first.");
    }

    const response = await axios.get(`${API_URL}/api/balance`, {
      headers: {
        Authorization: `Bearer ${jwtToken}`,
      },
    });

    if (!response || !response.data) {
      throw new Error("Invalid balance response");
    }

    return response.data;
  } catch (error) {
    console.error("❌ Balance error:", error.message);
    if (error.response) {
      console.error("Status:", error.response.status);
    }
    throw error;
  }
}

/**
 * Example usage with proper error handling
 */
async function example() {
  try {
    // Step 1: Initialize
    console.log("\n=== Step 1: Initialize API ===");
    await initializeAPI();

    // Step 2: Test chat
    console.log("\n=== Step 2: Test Chat ===");
    const chatResponse = await chatWithAI("What is the balance?");
    console.log("Success! AI said:", chatResponse.substring(0, 200));

    // Step 3: Test balance
    console.log("\n=== Step 3: Test Balance ===");
    const balance = await getBalance();
    console.log("Balance:", JSON.stringify(balance, null, 2));

    console.log("\n✅ All tests passed!");
  } catch (error) {
    console.error("\n❌ Example failed:", error.message);
    console.error("\nTroubleshooting:");
    console.error(
      "1. Make sure API is running: uvicorn fastapi_server:app --port 8000",
    );
    console.error("2. Check API health: curl http://localhost:8000/api/health");
    console.error("3. Verify port 8000 is not blocked by firewall");
  }
}

// Export functions
module.exports = {
  initializeAPI,
  chatWithAI,
  getBalance,
};

// Run example if executed directly
if (require.main === module) {
  example();
}
