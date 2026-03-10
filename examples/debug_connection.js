/*
 * DEBUGGING GUIDE: "No response received" Error
 * The API is running and working. Use this to fix your connection.
 */

// ============================================
// COMMON MISTAKE #1: Wrong URL
// ============================================

// ❌ WRONG - These won't work
const WRONG_URLS = [
  "http://localhost:8000/", // Extra trailing slash
  "localhost:8000", // Missing http://
  "127.0.0.1:8000", // Missing http://
  "http://localhost:8000/chat", // Wrong endpoint path
];

// ✅ CORRECT
const API_URL = "http://localhost:8000"; // No trailing slash!

// ============================================
// COMMON MISTAKE #2: Not handling async properly
// ============================================

// ❌ WRONG - Not waiting for response
function badExample() {
  axios.post(`${API_URL}/api/chat`, data);
  // Code continues immediately, response not received yet!
}

// ✅ CORRECT - Using async/await
async function goodExample() {
  try {
    const response = await axios.post(`${API_URL}/api/chat`, data);
    return response.data;
  } catch (error) {
    console.error("Error:", error.message);
  }
}

// ============================================
// COMMON MISTAKE #3: Missing error handling
// ============================================

// ❌ WRONG - No error handling
async function noErrorHandling() {
  const response = await axios.post(url, data);
  return response.data.response; // Will crash if error
}

// ✅ CORRECT - Proper error handling
async function withErrorHandling() {
  try {
    const response = await axios.post(url, data, {
      timeout: 10000, // 10 second timeout
    });

    if (!response || !response.data) {
      throw new Error("No response data received");
    }

    return response.data;
  } catch (error) {
    if (error.code === "ECONNREFUSED") {
      console.error("❌ Cannot connect to API. Is it running?");
      console.error("   Start it: uvicorn fastapi_server:app --port 8000");
    } else if (error.code === "ETIMEDOUT") {
      console.error("❌ Request timed out. API is too slow or not responding.");
    } else if (error.response) {
      console.error("❌ API returned error:", error.response.status);
      console.error("   Data:", error.response.data);
    } else {
      console.error("❌ Unknown error:", error.message);
    }
    throw error;
  }
}

// ============================================
// COMMON MISTAKE #4: CORS issue (browser only)
// ============================================

// If calling from browser and getting CORS error, the API needs CORS enabled
// Good news: Your API already has CORS enabled in fastapi_server.py!

// But make sure you're not blocking it:
// - Don't use 'localhost' in some places and '127.0.0.1' in others
// - Don't mix http and https
// - Use consistent URLs everywhere

// ============================================
// WORKING EXAMPLE - Copy this!
// ============================================

const axios = require("axios");

// Using API_URL defined at the top

// Step 1: Initialize
async function initialize() {
  try {
    // Test if API is alive
    console.log("🔍 Checking API health...");
    const health = await axios.get(`${API_URL}/api/health`, {
      timeout: 5000,
    });
    console.log("✅ API is healthy:", health.data);

    // Get API key
    console.log("🔑 Getting API key...");
    const keyResp = await axios.post(`${API_URL}/api/auth/generate-key`, null, {
      timeout: 5000,
    });
    const apiKey = keyResp.data.api_key;
    console.log("✅ API Key:", apiKey);

    // Get JWT token
    console.log("🎫 Getting JWT token...");
    const tokenResp = await axios.post(`${API_URL}/api/auth/token`, null, {
      params: { api_key: apiKey },
      timeout: 5000,
    });
    const token = tokenResp.data.access_token;
    console.log("✅ Token obtained");

    return token;
  } catch (error) {
    console.error("\n❌ Initialization failed!");

    if (error.code === "ECONNREFUSED") {
      console.error("\n🔧 FIX: Start the API server:");
      console.error("   cd /Users/mcbair/Desktop/pythonbotAI");
      console.error(
        "   /Users/mcbair/Library/Python/3.9/bin/uvicorn fastapi_server:app --port 8000",
      );
    } else if (error.code === "ETIMEDOUT") {
      console.error("\n🔧 FIX: Request timed out");
      console.error("   - Check if API is running: lsof -i :8000");
      console.error("   - Check if port 8000 is firewalled");
    } else {
      console.error("Error:", error.message);
      if (error.response) {
        console.error("Status:", error.response.status);
        console.error("Data:", error.response.data);
      }
    }

    throw error;
  }
}

// Step 2: Use the API
async function chat(token, message) {
  try {
    console.log(`\n💬 Sending: "${message}"`);

    const response = await axios.post(
      `${API_URL}/api/chat`,
      { message },
      {
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        timeout: 30000, // 30 seconds for AI processing
      },
    );

    if (!response || !response.data) {
      throw new Error("Empty response received");
    }

    if (!response.data.response) {
      console.error("Unexpected response structure:", response.data);
      throw new Error('Response missing "response" field');
    }

    console.log(
      "✅ Received:",
      response.data.response.substring(0, 100) + "...",
    );
    return response.data.response;
  } catch (error) {
    console.error("\n❌ Chat failed!");

    if (error.code === "ECONNREFUSED") {
      console.error("Cannot connect. API stopped running?");
    } else if (error.code === "ETIMEDOUT") {
      console.error("Request timed out. AI is taking too long?");
    } else if (error.response?.status === 401) {
      console.error("Unauthorized. Token invalid or expired?");
    } else if (error.response?.status === 422) {
      console.error("Invalid request format. Check your message format.");
    } else {
      console.error("Error:", error.message);
    }

    throw error;
  }
}

// Step 3: Run it
async function run() {
  try {
    const token = await initialize();
    const response = await chat(token, "What is the balance?");
    console.log("\n✅ SUCCESS! Response:", response);
  } catch (error) {
    console.error("\n❌ FAILED");
    process.exit(1);
  }
}

// Run if executed directly
if (require.main === module) {
  run();
}

module.exports = { initialize, chat };
