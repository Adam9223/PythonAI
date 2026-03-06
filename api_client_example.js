// Example: How to call PythonAI API from your website/application
// This shows proper authentication and usage

const axios = require("axios");

// Configuration
const API_URL = "http://localhost:8000"; // Change to your server URL in production
let apiKey = null;
let jwtToken = null;
let tokenExpiry = null;

/**
 * Initialize API - Call this once when your app starts
 */
async function initializeAPI() {
  try {
    // Step 1: Generate API Key (do this once and save it permanently)
    const keyResponse = await axios.post(`${API_URL}/api/auth/generate-key`);
    apiKey = keyResponse.data.api_key;
    console.log("✅ API Key generated:", apiKey);

    // Step 2: Get JWT Token
    await refreshToken();

    console.log("✅ API initialized successfully");
  } catch (error) {
    console.error("❌ Failed to initialize API:", error.message);
    throw error;
  }
}

/**
 * Get or refresh JWT token
 */
async function refreshToken() {
  try {
    const tokenResponse = await axios.post(
      `${API_URL}/api/auth/token?api_key=${apiKey}`,
    );
    jwtToken = tokenResponse.data.access_token;
    tokenExpiry = Date.now() + tokenResponse.data.expires_in * 1000;
    console.log("✅ JWT Token refreshed");
  } catch (error) {
    console.error("❌ Failed to refresh token:", error.message);
    throw error;
  }
}

/**
 * Check if token is expired and refresh if needed
 */
async function ensureValidToken() {
  // Refresh token 1 hour before expiry
  if (!jwtToken || Date.now() > tokenExpiry - 3600000) {
    await refreshToken();
  }
}

/**
 * Chat with AI
 * @param {string} message - User's message
 * @returns {Promise<string>} AI's response
 */
async function chatWithAI(message) {
  await ensureValidToken();

  try {
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

    return response.data.response;
  } catch (error) {
    if (error.response?.status === 401) {
      console.error("❌ Unauthorized - Token may be invalid");
      await refreshToken();
      // Retry once
      return chatWithAI(message);
    }
    throw error;
  }
}

/**
 * Get balance from GL
 * @returns {Promise<object>} Balance data
 */
async function getBalance() {
  await ensureValidToken();

  const response = await axios.get(`${API_URL}/api/balance`, {
    headers: {
      Authorization: `Bearer ${jwtToken}`,
    },
  });

  return response.data;
}

/**
 * Get chart data
 * @param {string} chartType - 'line', 'bar', or 'pie'
 * @param {string} message - Description or query
 * @returns {Promise<object>} Chart data
 */
async function getChart(chartType, message) {
  await ensureValidToken();

  const response = await axios.post(
    `${API_URL}/api/chart`,
    { chart_type: chartType, message },
    {
      headers: {
        Authorization: `Bearer ${jwtToken}`,
        "Content-Type": "application/json",
      },
    },
  );

  return response.data;
}

// Example usage
async function example() {
  try {
    // Initialize (do this once when your app starts)
    await initializeAPI();

    // Use the API
    const chatResponse = await chatWithAI("What is the current balance?");
    console.log("AI:", chatResponse);

    const balance = await getBalance();
    console.log("Balance:", balance);

    const chart = await getChart("line", "Show balance over time");
    console.log("Chart:", chart);
  } catch (error) {
    console.error("Error:", error.message);
  }
}

// Export for use in your application
module.exports = {
  initializeAPI,
  chatWithAI,
  getBalance,
  getChart,
};

// If running directly, run example
if (require.main === module) {
  example();
}
