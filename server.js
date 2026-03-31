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

function removeEnvKeys(keys) {
  let content = "";
  if (fs.existsSync(ENV_PATH)) {
    content = fs.readFileSync(ENV_PATH, "utf8");
  }
  const lines = content.split("\n");
  const keySet = new Set(keys);
  const filtered = lines.filter((line) => {
    const idx = line.indexOf("=");
    if (idx < 1) return true;
    const key = line.slice(0, idx).trim();
    return !keySet.has(key);
  });

  fs.writeFileSync(
    ENV_PATH,
    filtered
      .join("\n")
      .replace(/\n{3,}/g, "\n\n")
      .trim() + "\n",
  );

  for (const key of keySet) {
    delete process.env[key];
  }
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

function getCurrentSiteConnectionStatus() {
  let hasToken = false;
  try {
    const cfg = JSON.parse(fs.readFileSync(SCRAPER_CONFIG_PATH, "utf8"));
    for (const section of Object.values(cfg)) {
      if (
        section &&
        typeof section === "object" &&
        typeof section.api_fixed_auth_token === "string" &&
        section.api_fixed_auth_token.trim() !== ""
      ) {
        hasToken = true;
        break;
      }
    }
  } catch (_) {
    hasToken = false;
  }

  const hasSavedCreds = Boolean(
    (process.env.SITE_USERNAME || "").trim() &&
    (process.env.SITE_PASSWORD || "").trim(),
  );

  return {
    connected: hasSavedCreds && hasToken,
    hasSavedCreds,
    hasToken,
    username: (process.env.SITE_USERNAME || "").trim() || null,
  };
}

function extractToken(payload, tokenField) {
  if (!payload || typeof payload !== "object") return "";
  return (
    payload[tokenField] ||
    payload.token ||
    payload.access_token ||
    (payload.data && payload.data[tokenField]) ||
    (payload.data && payload.data.token) ||
    (payload.result && payload.result[tokenField]) ||
    (payload.result && payload.result.token) ||
    ""
  );
}

function loginAttempt({ loginUrl, headers, method, tokenField }) {
  return new Promise((resolve, reject) => {
    const parsed = new URL(loginUrl);
    const lib = parsed.protocol === "https:" ? https : http;
    const options = {
      hostname: parsed.hostname,
      port: parsed.port || (parsed.protocol === "https:" ? 443 : 80),
      path: parsed.pathname + parsed.search,
      method,
      headers,
    };

    const req = lib.request(options, (res) => {
      let data = "";
      res.on("data", (chunk) => (data += chunk));
      res.on("end", () => {
        const preview = (data || "").slice(0, 300);
        if ((res.statusCode || 0) >= 400) {
          const err = new Error(
            `Login failed with status ${res.statusCode}: ${preview}`,
          );
          err.statusCode = res.statusCode;
          return reject(err);
        }

        try {
          const json = data ? JSON.parse(data) : {};
          const token = extractToken(json, tokenField);
          if (token) {
            return resolve(token);
          }

          const headerToken =
            res.headers["x-access-token"] || res.headers["authorization"] || "";
          if (headerToken) {
            return resolve(String(headerToken).replace(/^Bearer\s+/i, ""));
          }

          const err = new Error(
            `No token found in ${method} login response. Keys: ${Object.keys(json).join(", ")}`,
          );
          err.statusCode = 502;
          return reject(err);
        } catch (e) {
          const err = new Error(
            `Invalid login response from upstream (${method}): ${preview}`,
          );
          err.statusCode = 502;
          return reject(err);
        }
      });
    });

    req.on("error", (e) => {
      const err = new Error(`Login request failed (${method}): ${e.message}`);
      err.statusCode = 502;
      reject(err);
    });

    if (method === "POST") {
      req.write("{}");
    }
    req.end();
  });
}

// Login to the target site using basic auth; returns a Promise<string> token
async function loginToSite(username, password, devId) {
  const loginUrl =
    process.env.SITE_LOGIN_URL || "https://clone.ulap.biz/api/login";
  const tokenField = process.env.SITE_TOKEN_FIELD || "token";
  const effectiveDevId = devId || process.env.SITE_DEV_ID || "";
  const credentials = Buffer.from(`${username}:${password}`).toString("base64");
  const reqHeaders = {
    Authorization: `Basic ${credentials}`,
    Accept: "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "User-Agent":
      "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
  };

  if (effectiveDevId) {
    reqHeaders.Cookie = `devID=${effectiveDevId}`;
  }

  const preferredMethod = (
    process.env.SITE_LOGIN_METHOD || "GET"
  ).toUpperCase();
  const methods =
    preferredMethod === "POST" ? ["POST", "GET"] : ["GET", "POST"];

  let lastError = null;
  for (const method of methods) {
    try {
      return await loginAttempt({
        loginUrl,
        headers: reqHeaders,
        method,
        tokenField,
      });
    } catch (err) {
      lastError = err;
      console.warn(`[Auth] ${method} login attempt failed: ${err.message}`);
    }
  }

  throw lastError || new Error("Login failed after all retry methods.");
}

function validateSiteApiToken(token, devId) {
  return new Promise((resolve) => {
    const validationUrl =
      process.env.SITE_VALIDATE_URL || "https://clone.ulap.biz/api/lib/brch";
    const validationMethod = (
      process.env.SITE_VALIDATE_METHOD || "GET"
    ).toUpperCase();

    const parsed = new URL(validationUrl);
    const lib = parsed.protocol === "https:" ? https : http;
    const headers = {
      "x-access-tokens": token,
      Accept: "application/json",
      "Content-Type": "application/json",
      Referer: "https://clone.ulap.biz/app/reports/sc",
      Origin: "https://clone.ulap.biz",
    };

    const effectiveDevId = devId || process.env.SITE_DEV_ID || "";
    if (effectiveDevId) {
      headers.Cookie = `devID=${effectiveDevId}`;
    }

    const req = lib.request(
      {
        hostname: parsed.hostname,
        port: parsed.port || (parsed.protocol === "https:" ? 443 : 80),
        path: parsed.pathname + parsed.search,
        method: validationMethod,
        headers,
      },
      (res) => {
        let data = "";
        res.on("data", (chunk) => (data += chunk));
        res.on("end", () => {
          const body = (data || "").slice(0, 300);
          const statusCode = res.statusCode || 0;
          if (statusCode >= 200 && statusCode < 300) {
            return resolve({ ok: true, statusCode, body });
          }
          resolve({ ok: false, statusCode, body });
        });
      },
    );

    req.on("error", (err) => {
      resolve({
        ok: false,
        statusCode: 0,
        body: err.message || "Validation request failed",
      });
    });

    if (validationMethod === "POST") {
      req.write("{}");
    }
    req.end();
  });
}

function isStrictTokenValidationEnabled() {
  const raw = (process.env.SITE_STRICT_TOKEN_VALIDATION || "false")
    .toString()
    .trim()
    .toLowerCase();
  return ["1", "true", "yes", "on"].includes(raw);
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
    const check = await validateSiteApiToken(
      token,
      process.env.SITE_DEV_ID || "",
    );
    if (!check.ok) {
      console.warn(
        `[Auth] Auto-login produced a token rejected by data APIs (${check.statusCode}): ${check.body}`,
      );
      return;
    }
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

function resolvePythonPath() {
  if (process.env.PYTHON_PATH) return process.env.PYTHON_PATH;
  const workspaceVenvPython = path.join(__dirname, ".venv", "bin", "python");
  if (fs.existsSync(workspaceVenvPython)) return workspaceVenvPython;
  if (process.env.VIRTUAL_ENV) {
    return path.join(process.env.VIRTUAL_ENV, "bin", "python");
  }
  return "python3";
}

// Start Python child process
function startPythonProcess() {
  pythonProcess = spawn(resolvePythonPath(), [
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

    const normalized = String(message).toLowerCase().trim();
    if (
      /accounts?\s+currently\s+logged\s+in|are\s+there\s+any\s+accounts?\s+currently\s+logged\s+in|are\s+there\s+any\s+accounts?\s+logged\s+in|accounts?\s+logged\s+in|who\s+is\s+logged\s+in/.test(
        normalized,
      )
    ) {
      const status = getCurrentSiteConnectionStatus();
      const detail = status.connected
        ? `A company account is connected (${status.username || "saved credentials"}), but I cannot list active website user sessions from this endpoint.`
        : "No connected company account is currently stored.";

      return res.json({
        response: detail,
        type: "text",
      });
    }

    // Import and call the Python respond function
    const { PythonShell } = require("python-shell");

    let options = {
      pythonPath: resolvePythonPath(),
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
    const effectiveDevId = dev_id || process.env.SITE_DEV_ID || "";
    const token = await loginToSite(username, password, effectiveDevId);

    const check = await validateSiteApiToken(token, effectiveDevId);
    const strictValidation = isStrictTokenValidationEnabled();

    // Persist credentials so the server can auto-refresh when the token expires
    saveEnvKey("SITE_USERNAME", username);
    saveEnvKey("SITE_PASSWORD", password);
    if (effectiveDevId) saveEnvKey("SITE_DEV_ID", effectiveDevId);

    // Apply the fresh token immediately to all scraper config sections
    updateScraperToken(token);

    if (!check.ok && strictValidation) {
      return res.status(401).json({
        error: "Login succeeded but upstream data API rejected the token.",
        details: `Validation status ${check.statusCode}: ${check.body}`,
        hint: "Your clone.ulap session likely needs a browser-issued token/cookie context. In this case, pass user_auth_token/user_cookie from the logged-in frontend session.",
      });
    }

    return res.json({
      success: true,
      message: check.ok
        ? "Connected successfully. Token updated."
        : "Connected with limited validation. Token saved, but one upstream endpoint rejected it.",
      warning: check.ok
        ? null
        : `Validation status ${check.statusCode}: ${check.body}`,
    });
  } catch (err) {
    console.error("[Auth] site-login error:", err.message);
    const statusCode =
      Number.isInteger(err.statusCode) && err.statusCode >= 400
        ? err.statusCode
        : 502;
    return res.status(statusCode).json({
      error: err.message || "Login failed.",
      hint: "If this keeps returning 500 from upstream, try setting SITE_LOGIN_METHOD=POST in .env and retry.",
    });
  }
});

// Site logout - clears saved site credentials + fixed scraper token
app.post("/api/auth/site-logout", async (_req, res) => {
  try {
    removeEnvKeys([
      "SITE_USERNAME",
      "SITE_PASSWORD",
      "SITE_DEV_ID",
      "SITE_LOGIN_METHOD",
    ]);
    updateScraperToken("");

    return res.json({
      success: true,
      message: "Disconnected successfully.",
    });
  } catch (err) {
    console.error("[Auth] site-logout error:", err.message);
    return res.status(500).json({
      success: false,
      error: "Failed to disconnect account.",
    });
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
