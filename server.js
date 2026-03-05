const express = require("express");
const { spawn } = require("child_process");
const path = require("path");
const app = express();
const PORT = 3000;

app.use(express.json());
app.use(express.static("public"));

// Python process reference
let pythonProcess = null;

// Start Python child process
function startPythonProcess() {
  pythonProcess = spawn("python3", [path.join(__dirname, "python_api.py")]);

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
      scriptPath: __dirname,
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

// Start server
app.listen(PORT, () => {
  console.log(`\n🤖 AI Chatbot Web Server`);
  console.log(`📍 Running on http://localhost:${PORT}`);
  console.log(`🔗 Open http://localhost:${PORT} in your browser\n`);
  startPythonProcess();
});

// Graceful shutdown
process.on("SIGINT", () => {
  if (pythonProcess) {
    pythonProcess.kill();
  }
  process.exit(0);
});
