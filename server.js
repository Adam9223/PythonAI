const express = require("express");
const { spawn } = require("child_process");
const path = require("path");
const https = require("https");
const http = require("http");
const fs = require("fs");
const app = express();
const PORT = process.env.PORT || 3000;

// Load .env file if it exists
const ENV_PATH = path.join(__dirname, ".env");
function loadEnv() {
  if (!fs.existsSync(ENV_PATH)) return;
  try {
    const lines = fs.readFileSync(ENV_PATH, "utf8").split("\n");
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith("#")) continue;
      const idx = trimmed.indexOf("=");
      if (idx < 1) continue;
      const key = trimmed.slice(0, idx).trim();
      const value = trimmed
        .slice(idx + 1)
        .trim()
        .replace(/^["']|["']$/g, "");
      if (key && !(key in process.env)) process.env[key] = value;
    }
  } catch (e) {
    console.warn("[ENV] Could not read .env:", e.message);
  }
}
loadEnv();

// Save or update a single key in the .env file
function saveEnvKey(key, value) {
  let content = "";
  if (fs.existsSync(ENV_PATH)) {
    content = fs.readFileSync(ENV_PATH, "utf8");
  }
  const lines = content.split("\n");
  const prefix = `${key}=`;
  const idx = lines.findIndex((l) => l.startsWith(prefix));
  const newLine = `${key}=${value}`;
  if (idx >= 0) {
    lines[idx] = newLine;
  } else {
    lines.push(newLine);
  }
  fs.writeFileSync(
    ENV_PATH,
    lines
      .join("\n")
      .replace(/\n{3,}/g, "\n\n")
      .trim() + "\n",
  );
  process.env[key] = value;
}

// Update every api_fixed_auth_token entry in scraper_config.json
const SCRAPER_CONFIG_PATH = path.join(
  __dirname,
  "config",
  "scraper_config.json",
);
function updateScraperToken(token) {
  try {
    const cfg = JSON.parse(fs.readFileSync(SCRAPER_CONFIG_PATH, "utf8"));
    for (const section of Object.values(cfg)) {
      if (
        section &&
        typeof section === "object" &&
        "api_fixed_auth_token" in section
      ) {
        section.api_fixed_auth_token = token;
      }
    }
    fs.writeFileSync(SCRAPER_CONFIG_PATH, JSON.stringify(cfg, null, 2));
    console.log("[Auth] Scraper config token updated.");
  } catch (e) {
    console.error("[Auth] Failed to update scraper config:", e.message);
  }
}

// Login to the target site using basic auth; returns a Promise<string> token
function loginToSite(username, password, devId) {
  return new Promise((resolve, reject) => {
    const loginUrl =
      process.env.SITE_LOGIN_URL || "https://clone.ulap.biz/api/login";
    const parsed = new URL(loginUrl);
    const credentials = Buffer.from(`${username}:${password}`).toString(
      "base64",
    );
    const reqHeaders = {
      Authorization: `Basic ${credentials}`,
      Accept: "application/json",
      "Content-Type": "application/json",
    };
    if (devId) reqHeaders.Cookie = `devID=${devId}`;

    const lib = parsed.protocol === "https:" ? https : http;
    const options = {
      hostname: parsed.hostname,
      port: parsed.port || (parsed.protocol === "https:" ? 443 : 80),
      path: parsed.pathname + parsed.search,
      method: "GET",
      headers: reqHeaders,
    };

    const req = lib.request(options, (res) => {
      let data = "";
      res.on("data", (chunk) => (data += chunk));
      res.on("end", () => {
        if (res.statusCode >= 400) {
          return reject(
            new Error(
              `Login failed with status ${res.statusCode}: ${data.slice(0, 200)}`,
            ),
          );
        }
        try {
          const parsed = JSON.parse(data);
          const token =
            parsed.token ||
            parsed.access_token ||
            (parsed.data && parsed.data.token) ||
            parsed[process.env.SITE_TOKEN_FIELD || "token"];
          if (!token) {
            return reject(
              new Error(
                `No token found in response. Keys: ${Object.keys(parsed).join(", ")}`,
              ),
            );
          }
          resolve(token);
        } catch (e) {
          reject(new Error(`Invalid login response: ${data.slice(0, 200)}`));
        }
      });
    });
    req.on("error", (e) =>
      reject(new Error(`Login request failed: ${e.message}`)),
    );
    req.end();
  });
}

// Attempt auto-login using stored .env credentials on startup / token expiry
async function tryAutoLogin() {
  const username = process.env.SITE_USERNAME;
  const password = process.env.SITE_PASSWORD;
  if (!username || !password) return;
  try {
    const token = await loginToSite(
      username,
      password,
      process.env.SITE_DEV_ID || "",
    );
    updateScraperToken(token);
    console.log("[Auth] Auto-login successful. Site token refreshed.");
  } catch (e) {
    console.warn("[Auth] Auto-login failed:", e.message);
  }
}

app.use(express.json());
app.use(express.static("public"));

// Python process reference
let pythonProcess = null;

// Start Python child process
function startPythonProcess() {
  pythonProcess = spawn("python3", [
    path.join(__dirname, "src", "python_api.py"),
  ]);

  pythonProcess.stdout.on("data", (data) => {
    console.log(`[Python] ${data}`);
  });

  pythonProcess.stderr.on("data", (data) => {
    console.error(`[Python Error] ${data}`);
  });
}

// Chat endpoint
app.post("/api/chat", async (req, res) => {
  try {
    const { message } = req.body;

    if (!message || message.trim() === "") {
      return res.status(400).json({ error: "Message is required" });
    }

    // Import and call the Python respond function
    const { PythonShell } = require("python-shell");

    let options = {
      pythonPath: "/usr/bin/python3",
      scriptPath: path.join(__dirname, "src"),
      args: [message],
    };

    PythonShell.run("python_api.py", options, (err, results) => {
      if (err) {
        console.error("Error:", err);
        return res.status(500).json({
          error: "Failed to get response",
          response: "I'm having trouble processing that right now.",
        });
      }

      try {
        // Parse JSON response from Python
        const output = results ? results[results.length - 1] : "";
        const parsed = JSON.parse(output);
        res.json({
          response: parsed.response || "No response",
          type: "text",
        });
      } catch (parseErr) {
        // Fallback if JSON parsing fails
        const response = results ? results[results.length - 1] : "No response";
        res.json({
          response: response,
          type: "text",
        });
      }
    });
  } catch (error) {
    console.error("Endpoint error:", error);
    res.status(500).json({ error: "Server error" });
  }
});

// Health check
app.get("/api/health", (req, res) => {
  res.json({
    status: "ok",
    message: "AI chatbot is running",
    timestamp: new Date().toISOString(),
  });
});

// Site login — accepts user credentials, logs into the target site, stores the token
app.post("/api/auth/site-login", async (req, res) => {
  const { username, password, dev_id } = req.body || {};
  if (!username || !password) {
    return res
      .status(400)
      .json({ error: "Username and password are required." });
  }

  try {
    const token = await loginToSite(username, password, dev_id || "");

    // Persist credentials so the server can auto-refresh when the token expires
    saveEnvKey("SITE_USERNAME", username);
    saveEnvKey("SITE_PASSWORD", password);
    if (dev_id) saveEnvKey("SITE_DEV_ID", dev_id);

    // Apply the fresh token immediately to all scraper config sections
    updateScraperToken(token);

    return res.json({
      success: true,
      message: "Connected successfully. Token updated.",
    });
  } catch (err) {
    console.error("[Auth] site-login error:", err.message);
    return res.status(401).json({ error: err.message || "Login failed." });
  }
});

// Start server
app.listen(PORT, () => {
  console.log(`\n🤖 AI Chatbot Web Server`);
  console.log(`📍 Running on http://localhost:${PORT}`);
  console.log(`🔗 Open http://localhost:${PORT} in your browser\n`);
  startPythonProcess();
  // Attempt token refresh on startup if credentials are already saved
  tryAutoLogin();
});

// Graceful shutdown
process.on("SIGINT", () => {
  if (pythonProcess) {
    pythonProcess.kill();
  }
  process.exit(0);
});
